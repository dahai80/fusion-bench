"""Baseline store — multi-version baseline management for benchmark results.

Extends TraceStore with baseline set/query/diff capabilities.
Baselines are named snapshots of metric values for a given model+executor+level.
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".fusion-bench" / "baselines.db"


class BaselineStore:
    """SQLite-backed baseline store for version-over-version comparison."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._ensure_table()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _ensure_table(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS baselines (
                baseline_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                model TEXT NOT NULL,
                executor_key TEXT NOT NULL,
                level TEXT NOT NULL,
                metrics TEXT NOT NULL,
                source_trace_id TEXT,
                created_at TEXT NOT NULL,
                description TEXT
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_baselines_model ON baselines(model)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_baselines_name ON baselines(name)")
        self.conn.commit()

    def set_baseline(
        self,
        name: str,
        model: str,
        executor_key: str,
        level: str,
        metrics: dict[str, float],
        source_trace_id: str = "",
        description: str = "",
    ) -> str:
        baseline_id = f"bl-{name}-{model}-{executor_key}-{level}"
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            self.conn.execute(
                """INSERT OR REPLACE INTO baselines
                   (baseline_id, name, model, executor_key, level, metrics,
                    source_trace_id, created_at, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    baseline_id,
                    name,
                    model,
                    executor_key,
                    level,
                    json.dumps(metrics),
                    source_trace_id,
                    now,
                    description,
                ),
            )
            self.conn.commit()
            logger.info("Baseline set: %s for %s/%s/%s", name, model, executor_key, level)
            return baseline_id
        except sqlite3.Error as e:
            logger.error("Failed to set baseline %s: %s", name, e)
            return ""

    def get_baseline(
        self,
        name: str,
        model: str,
        executor_key: str = "",
        level: str = "",
    ) -> dict[str, Any] | None:
        conditions = ["name = ?"]
        params: list[Any] = [name]
        if model:
            conditions.append("model = ?")
            params.append(model)
        if executor_key:
            conditions.append("executor_key = ?")
            params.append(executor_key)
        if level:
            conditions.append("level = ?")
            params.append(level)
        where = " AND ".join(conditions)
        row = self.conn.execute(
            f"SELECT * FROM baselines WHERE {where} ORDER BY created_at DESC LIMIT 1",
            params,
        ).fetchone()
        if not row:
            return None
        metrics = {}
        if row["metrics"]:
            with contextlib.suppress(json.JSONDecodeError):
                metrics = json.loads(row["metrics"])
        return {
            "baseline_id": row["baseline_id"],
            "name": row["name"],
            "model": row["model"],
            "executor_key": row["executor_key"],
            "level": row["level"],
            "metrics": metrics,
            "source_trace_id": row["source_trace_id"],
            "created_at": row["created_at"],
            "description": row["description"],
        }

    def list_baselines(
        self,
        model: str = "",
        executor_key: str = "",
        level: str = "",
    ) -> list[dict[str, Any]]:
        conditions = []
        params: list[Any] = []
        if model:
            conditions.append("model = ?")
            params.append(model)
        if executor_key:
            conditions.append("executor_key = ?")
            params.append(executor_key)
        if level:
            conditions.append("level = ?")
            params.append(level)
        where = " AND ".join(conditions) if conditions else "1=1"
        rows = self.conn.execute(
            f"SELECT * FROM baselines WHERE {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
        result = []
        for row in rows:
            metrics = {}
            if row["metrics"]:
                with contextlib.suppress(json.JSONDecodeError):
                    metrics = json.loads(row["metrics"])
            result.append(
                {
                    "baseline_id": row["baseline_id"],
                    "name": row["name"],
                    "model": row["model"],
                    "executor_key": row["executor_key"],
                    "level": row["level"],
                    "metrics": metrics,
                    "created_at": row["created_at"],
                }
            )
        return result

    def diff(
        self,
        name: str,
        model: str,
        executor_key: str,
        level: str,
        current_metrics: dict[str, float],
    ) -> dict[str, Any]:
        baseline = self.get_baseline(name, model, executor_key, level)
        if not baseline:
            return {
                "baseline_name": name,
                "model": model,
                "baseline_found": False,
                "current": current_metrics,
                "diffs": {},
            }
        baseline_metrics = baseline["metrics"]
        diffs = {}
        for key in set(list(baseline_metrics.keys()) + list(current_metrics.keys())):
            bval = baseline_metrics.get(key)
            cval = current_metrics.get(key)
            if bval is not None and cval is not None:
                delta = cval - bval
                delta_pct = (delta / bval * 100) if bval != 0 else None
                diffs[key] = {
                    "baseline": bval,
                    "current": cval,
                    "delta": round(delta, 6),
                    "delta_pct": round(delta_pct, 2) if delta_pct is not None else None,
                    "direction": "improved" if delta > 0 else ("regressed" if delta < 0 else "stable"),
                }
            elif bval is not None:
                diffs[key] = {
                    "baseline": bval,
                    "current": None,
                    "delta": None,
                    "direction": "missing_current",
                }
            else:
                diffs[key] = {
                    "baseline": None,
                    "current": cval,
                    "delta": None,
                    "direction": "new_metric",
                }

        return {
            "baseline_name": name,
            "model": model,
            "baseline_found": True,
            "baseline_created_at": baseline["created_at"],
            "current": current_metrics,
            "baseline": baseline_metrics,
            "diffs": diffs,
        }

    def delete_baseline(self, name: str, model: str = "", executor_key: str = "") -> int:
        conditions = ["name = ?"]
        params: list[Any] = [name]
        if model:
            conditions.append("model = ?")
            params.append(model)
        if executor_key:
            conditions.append("executor_key = ?")
            params.append(executor_key)
        where = " AND ".join(conditions)
        cursor = self.conn.execute(f"DELETE FROM baselines WHERE {where}", params)
        self.conn.commit()
        logger.info("Deleted %d baseline(s) for name=%s", cursor.rowcount, name)
        return cursor.rowcount

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
