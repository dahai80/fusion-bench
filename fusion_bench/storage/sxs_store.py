"""SQLite store for SxS pairwise judge verdicts (#18).

Persists per-pair verdicts + aggregate win/loss/tie stats so SxS results
survive across runs. Schema mirrors BaselineStore conventions (WAL, Row
factory, auto-created table + indexes).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from ..judge.sxs_config import SxSVerdict, aggregate_verdicts

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".fusion-bench" / "sxs.db"


class SxSStore:
    # SQLite persistence for double-blind pairwise verdicts.

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
            CREATE TABLE IF NOT EXISTS sxs_verdicts (
                verdict_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                model_a TEXT NOT NULL,
                model_b TEXT NOT NULL,
                prompt TEXT,
                winner TEXT NOT NULL,
                scores_a TEXT NOT NULL,
                scores_b TEXT NOT NULL,
                rationale TEXT,
                position_map TEXT,
                raw_response TEXT,
                created_at TEXT NOT NULL
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_sxs_session ON sxs_verdicts(session_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_sxs_models ON sxs_verdicts(model_a, model_b)")
        self.conn.commit()

    def save_verdict(
        self,
        session_id: str,
        model_a: str,
        model_b: str,
        prompt: str,
        verdict: SxSVerdict,
    ) -> str:
        verdict_id = f"sxs-{uuid.uuid4().hex[:12]}"
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.conn.execute(
            """
            INSERT INTO sxs_verdicts
                (verdict_id, session_id, model_a, model_b, prompt, winner,
                 scores_a, scores_b, rationale, position_map, raw_response, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                verdict_id,
                session_id,
                model_a,
                model_b,
                prompt[:500],
                verdict.winner,
                json.dumps(verdict.scores_a),
                json.dumps(verdict.scores_b),
                verdict.rationale,
                json.dumps(verdict.position_map),
                verdict.raw_response,
                created_at,
            ),
        )
        self.conn.commit()
        logger.info("Saved SxS verdict %s (session=%s winner=%s)", verdict_id, session_id, verdict.winner)
        return verdict_id

    def list_verdicts(self, session_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if session_id:
            rows = self.conn.execute(
                "SELECT * FROM sxs_verdicts WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM sxs_verdicts ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_aggregate(self, session_id: str, model_a: str | None = None, model_b: str | None = None) -> dict[str, Any]:
        conditions = ["session_id = ?"]
        params: list[Any] = [session_id]
        if model_a:
            conditions.append("model_a = ?")
            params.append(model_a)
        if model_b:
            conditions.append("model_b = ?")
            params.append(model_b)
        where = " AND ".join(conditions)
        rows = self.conn.execute(
            f"SELECT winner, scores_a, scores_b FROM sxs_verdicts WHERE {where}",
            params,
        ).fetchall()
        verdicts: list[SxSVerdict] = []
        for r in rows:
            scores_a = json.loads(r["scores_a"]) if r["scores_a"] else {}
            scores_b = json.loads(r["scores_b"]) if r["scores_b"] else {}
            verdicts.append(SxSVerdict(winner=r["winner"], scores_a=scores_a, scores_b=scores_b))
        agg = aggregate_verdicts(verdicts)
        logger.info("SxS aggregate session=%s: %s", session_id, agg)
        return agg

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "verdict_id": row["verdict_id"],
            "session_id": row["session_id"],
            "model_a": row["model_a"],
            "model_b": row["model_b"],
            "prompt": row["prompt"],
            "winner": row["winner"],
            "scores_a": json.loads(row["scores_a"]) if row["scores_a"] else {},
            "scores_b": json.loads(row["scores_b"]) if row["scores_b"] else {},
            "rationale": row["rationale"],
            "position_map": json.loads(row["position_map"]) if row["position_map"] else {},
            "created_at": row["created_at"],
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


__all__ = ["SxSStore", "_DEFAULT_DB_PATH"]
