"""Benchmark cache — SQLite-based caching to avoid redundant evaluations."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class BenchmarkCache:
    """SQLite-backed cache for benchmark results.

    Avoids re-running the same benchmark with the same model+config+tasks.
    """

    def __init__(self, db_path: str = ""):
        if not db_path:
            db_path = str(Path.home() / ".fusion-bench" / "cache.db")
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    @contextmanager
    def _cursor(self):
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_db(self) -> None:
        with self._cursor() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS benchmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    task TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE(model, config_json, task)
                );
                CREATE INDEX IF NOT EXISTS idx_benchmarks_lookup
                    ON benchmarks(model, config_json, task);
            """)

    def get(self, model: str, config: dict | None, task: str) -> dict | None:
        """Get cached result for a model+config+task combination."""
        config_json = json.dumps(config or {}, sort_keys=True)
        with self._cursor() as conn:
            row = conn.execute(
                "SELECT result_json FROM benchmarks WHERE model = ? AND config_json = ? AND task = ?",
                (model, config_json, task),
            ).fetchone()
        if row:
            return json.loads(row["result_json"])
        return None

    def set(self, model: str, config: dict | None, task: str, result: dict) -> None:
        """Cache a benchmark result."""
        config_json = json.dumps(config or {}, sort_keys=True)
        result_json = json.dumps(result, ensure_ascii=False)
        with self._cursor() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO benchmarks
                   (model, config_json, task, result_json, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (model, config_json, task, result_json, time.time()),
            )

    def clear(self, model: str = "", task: str = "") -> int:
        """Clear cache entries. Returns count of deleted rows."""
        with self._cursor() as conn:
            if model and task:
                cursor = conn.execute(
                    "DELETE FROM benchmarks WHERE model = ? AND task = ?",
                    (model, task),
                )
            elif model:
                cursor = conn.execute(
                    "DELETE FROM benchmarks WHERE model = ?", (model,)
                )
            elif task:
                cursor = conn.execute(
                    "DELETE FROM benchmarks WHERE task = ?", (task,)
                )
            else:
                cursor = conn.execute("DELETE FROM benchmarks")
        return cursor.rowcount

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._cursor() as conn:
            total = conn.execute("SELECT COUNT(*) as cnt FROM benchmarks").fetchone()
            models = conn.execute(
                "SELECT model, COUNT(*) as cnt FROM benchmarks GROUP BY model ORDER BY cnt DESC"
            ).fetchall()
        return {
            "total_entries": total["cnt"] if total else 0,
            "models": [dict(r) for r in models] if models else [],
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None