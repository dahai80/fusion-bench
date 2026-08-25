"""SQLite store for named JudgeConfig definitions."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path

from ..judge.config import JudgeConfig

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".fusion-bench" / "judge.db"


class JudgeStore:
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
            CREATE TABLE IF NOT EXISTS judge_configs (
                name TEXT PRIMARY KEY,
                config_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def save(self, name: str, config: JudgeConfig) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.conn.execute(
            "INSERT OR REPLACE INTO judge_configs (name, config_json, created_at) VALUES (?, ?, ?)",
            (name, json.dumps(config.to_dict(), ensure_ascii=False), now),
        )
        self.conn.commit()
        logger.info("JudgeConfig saved: %s", name)

    def get(self, name: str) -> JudgeConfig | None:
        row = self.conn.execute("SELECT config_json FROM judge_configs WHERE name = ?", (name,)).fetchone()
        if not row:
            return None
        return JudgeConfig.from_dict(json.loads(row["config_json"]))

    def list(self) -> list[str]:
        rows = self.conn.execute("SELECT name FROM judge_configs ORDER BY name").fetchall()
        return [r["name"] for r in rows]

    def delete(self, name: str) -> bool:
        cursor = self.conn.execute("DELETE FROM judge_configs WHERE name = ?", (name,))
        self.conn.commit()
        return cursor.rowcount > 0

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
