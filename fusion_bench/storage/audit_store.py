"""Audit store — operation audit logging for compliance.

Records all API actions (create task, modify gate, approve, etc.)
Imported by API middleware in api/app.py. Schema: audit_logs table.
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P2-13).
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

_DEFAULT_DB_PATH = Path.home() / ".fusion-bench" / "audit.db"


class AuditStore:
    """SQLite-backed audit log store for compliance and traceability."""

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
            CREATE TABLE IF NOT EXISTS audit_logs (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                actor TEXT NOT NULL DEFAULT 'system',
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                detail TEXT DEFAULT '{}',
                ip_address TEXT DEFAULT '',
                timestamp TEXT NOT NULL
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_logs(resource_type, resource_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp)")
        self.conn.commit()

    def log(
        self,
        action: str,
        actor: str = "system",
        resource_type: str = "",
        resource_id: str = "",
        detail: dict[str, Any] | None = None,
        ip_address: str = "",
    ) -> int:
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            cursor = self.conn.execute(
                """INSERT INTO audit_logs
                   (action, actor, resource_type, resource_id, detail, ip_address, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    action,
                    actor,
                    resource_type,
                    resource_id,
                    json.dumps(detail or {}),
                    ip_address,
                    now,
                ),
            )
            self.conn.commit()
            logger.debug("Audit: %s by %s on %s/%s", action, actor, resource_type, resource_id)
            return cursor.lastrowid or 0
        except sqlite3.Error as e:
            logger.error("Failed to write audit log: %s", e)
            return 0

    def query(
        self,
        action: str = "",
        actor: str = "",
        resource_type: str = "",
        resource_id: str = "",
        start_time: str = "",
        end_time: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conditions = []
        params: list[Any] = []
        if action:
            conditions.append("action = ?")
            params.append(action)
        if actor:
            conditions.append("actor = ?")
            params.append(actor)
        if resource_type:
            conditions.append("resource_type = ?")
            params.append(resource_type)
        if resource_id:
            conditions.append("resource_id = ?")
            params.append(resource_id)
        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time)

        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)
        rows = self.conn.execute(
            f"SELECT * FROM audit_logs WHERE {where} ORDER BY timestamp DESC LIMIT ?",
            params,
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        total = self.conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        by_action = dict(self.conn.execute("SELECT action, COUNT(*) FROM audit_logs GROUP BY action").fetchall())
        by_actor = dict(
            self.conn.execute(
                "SELECT actor, COUNT(*) FROM audit_logs GROUP BY actor ORDER BY COUNT(*) DESC LIMIT 20"
            ).fetchall()
        )
        return {"total": total, "by_action": by_action, "by_actor": by_actor}

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        detail = {}
        if row["detail"]:
            with contextlib.suppress(json.JSONDecodeError):
                detail = json.loads(row["detail"])
        return {
            "audit_id": row["audit_id"],
            "action": row["action"],
            "actor": row["actor"],
            "resource_type": row["resource_type"],
            "resource_id": row["resource_id"],
            "detail": detail,
            "ip_address": row["ip_address"],
            "timestamp": row["timestamp"],
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
