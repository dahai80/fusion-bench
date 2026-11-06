"""SxS run persistence (#41) — SQLite store for double-blind pairwise verdicts.

Follows the JudgeStore pattern: one db file under ~/.fusion-bench/, WAL mode,
row_factory=sqlite3.Row. Rows keep the TRUE winner (a/b/tie) plus the full
verdict JSON for audit; the shuffled slot identities never leave position_map.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DB_DIR = Path.home() / ".fusion-bench"
_DEFAULT_DB_PATH = _DB_DIR / "sxs_runs.db"


class SxSRunStore:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or _DEFAULT_DB_PATH
        _DB_DIR.mkdir(parents=True, exist_ok=True)
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
            CREATE TABLE IF NOT EXISTS sxs_runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                judge_model TEXT NOT NULL,
                seed INTEGER NOT NULL DEFAULT 42,
                prompt TEXT NOT NULL DEFAULT '',
                winner TEXT NOT NULL,
                avg_a REAL NOT NULL DEFAULT 0.0,
                avg_b REAL NOT NULL DEFAULT 0.0,
                verdict_json TEXT NOT NULL DEFAULT '{}'
            )
        """)
        self.conn.commit()

    def save_run(self, verdict_dict: dict[str, Any], judge_model: str, seed: int, prompt: str) -> str:
        run_id = uuid.uuid4().hex[:12]
        self.conn.execute(
            """INSERT INTO sxs_runs
               (run_id, created_at, judge_model, seed, prompt, winner, avg_a, avg_b, verdict_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                datetime.now(UTC).isoformat(),
                judge_model,
                seed,
                prompt,
                str(verdict_dict.get("winner", "tie")),
                float(verdict_dict.get("avg_a", 0.0)),
                float(verdict_dict.get("avg_b", 0.0)),
                json.dumps(verdict_dict, ensure_ascii=False),
            ),
        )
        self.conn.commit()
        logger.info("SxS run saved: %s (winner=%s, judge_model=%s)", run_id, verdict_dict.get("winner"), judge_model)
        return run_id

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM sxs_runs ORDER BY created_at DESC LIMIT ?", (max(1, limit),)).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            try:
                item["verdict"] = json.loads(item.pop("verdict_json", "{}"))
            except ValueError:
                item["verdict"] = {}
            out.append(item)
        return out

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
