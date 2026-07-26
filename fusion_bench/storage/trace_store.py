"""Trace store — SQLite-backed storage for benchmark trace records.

Persists TraceRecords for query and analysis. Uses json serialization
for the eval_result and gate_results fields.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from ..core.models import EvalLevel, TaskStatus, TraceRecord

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".fusion-bench" / "traces.db"


class TraceStore:
    """SQLite-backed trace record store."""

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
            CREATE TABLE IF NOT EXISTS traces (
                trace_id TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                level TEXT NOT NULL,
                executor_key TEXT NOT NULL,
                task_id TEXT NOT NULL,
                status TEXT NOT NULL,
                eval_result TEXT,
                gate_results TEXT,
                error_message TEXT,
                duration_seconds REAL DEFAULT 0,
                timestamp TEXT NOT NULL,
                host_info TEXT
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_model ON traces(model)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_executor ON traces(executor_key)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_level ON traces(level)")
        self.conn.commit()

    def insert(self, record: TraceRecord) -> None:
        try:
            self.conn.execute(
                """INSERT OR REPLACE INTO traces
                   (trace_id, model, level, executor_key, task_id, status,
                    eval_result, gate_results, error_message, duration_seconds,
                    timestamp, host_info)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.trace_id,
                    record.model,
                    record.level.value,
                    record.executor_key,
                    record.task_id,
                    record.status.value,
                    json.dumps(record.eval_result) if record.eval_result else None,
                    json.dumps(record.gate_results) if record.gate_results else None,
                    record.error_message,
                    record.duration_seconds,
                    record.timestamp,
                    json.dumps(record.host_info) if record.host_info else None,
                ),
            )
            self.conn.commit()
            logger.debug("Inserted trace %s", record.trace_id)
        except sqlite3.Error as e:
            logger.error("Failed to insert trace %s: %s", record.trace_id, e)

    def query(
        self,
        model: str | None = None,
        executor_key: str | None = None,
        level: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[TraceRecord]:
        """Query traces with optional filters."""
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
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        rows = self.conn.execute(
            f"SELECT * FROM traces WHERE {where} ORDER BY timestamp DESC LIMIT ?",
            params,
        ).fetchall()

        return [self._row_to_record(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        """Return aggregate stats about stored traces."""
        total = self.conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
        by_status = dict(
            self.conn.execute("SELECT status, COUNT(*) FROM traces GROUP BY status").fetchall()
        )
        by_level = dict(
            self.conn.execute("SELECT level, COUNT(*) FROM traces GROUP BY level").fetchall()
        )
        by_executor = dict(
            self.conn.execute("SELECT executor_key, COUNT(*) FROM traces GROUP BY executor_key").fetchall()
        )
        return {
            "total": total,
            "by_status": by_status,
            "by_level": by_level,
            "by_executor": by_executor,
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> TraceRecord:
        eval_result = None
        if row["eval_result"]:
            try:
                eval_result = json.loads(row["eval_result"])
            except json.JSONDecodeError:
                pass

        gate_results = []
        if row["gate_results"]:
            try:
                gate_results = json.loads(row["gate_results"])
            except json.JSONDecodeError:
                pass

        host_info = {}
        if row["host_info"]:
            try:
                host_info = json.loads(row["host_info"])
            except json.JSONDecodeError:
                pass

        return TraceRecord(
            trace_id=row["trace_id"],
            model=row["model"],
            level=EvalLevel(row["level"]),
            executor_key=row["executor_key"],
            task_id=row["task_id"],
            status=TaskStatus(row["status"]),
            eval_result=eval_result,
            gate_results=gate_results,
            error_message=row["error_message"],
            duration_seconds=row["duration_seconds"],
            timestamp=row["timestamp"],
            host_info=host_info,
        )
