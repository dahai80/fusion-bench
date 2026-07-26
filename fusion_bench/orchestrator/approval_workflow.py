"""Approval workflow - gate approval orchestration for production tier.

Importers/callers: api/app.py /approvals endpoints; gate_engine.py production tier.
Affected API: /approvals CRUD endpoints; GateResult.approve() integration.
Data schema: ApprovalRequest (request_id, gate_id, gate_name, metric_name, metric_value, threshold, requester, status, approver, reason); approvals table (request_id PK).
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P3-19 approval workflow).
"""

from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".fusion-bench" / "approvals.db"


class ApprovalStatus(str):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalRequest:
    def __init__(
        self,
        request_id: str = "",
        gate_id: str = "",
        gate_name: str = "",
        metric_name: str = "",
        metric_value: float = 0.0,
        threshold: float = 0.0,
        requester: str = "system",
        status: str = ApprovalStatus.PENDING,
        approver: str = "",
        reason: str = "",
        expires_hours: int = 24,
    ):
        self.request_id = request_id or f"apr-{uuid.uuid4().hex[:8]}"
        self.gate_id = gate_id
        self.gate_name = gate_name
        self.metric_name = metric_name
        self.metric_value = metric_value
        self.threshold = threshold
        self.requester = requester
        self.status = status
        self.approver = approver
        self.reason = reason
        self.expires_hours = expires_hours
        self.created_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.resolved_at = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "gate_id": self.gate_id,
            "gate_name": self.gate_name,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "requester": self.requester,
            "status": self.status,
            "approver": self.approver,
            "reason": self.reason,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }


class ApprovalStore:
    """SQLite-backed approval workflow store."""

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
            CREATE TABLE IF NOT EXISTS approvals (
                request_id TEXT PRIMARY KEY,
                gate_id TEXT NOT NULL,
                gate_name TEXT DEFAULT '',
                metric_name TEXT DEFAULT '',
                metric_value REAL DEFAULT 0.0,
                threshold REAL DEFAULT 0.0,
                requester TEXT DEFAULT 'system',
                status TEXT NOT NULL DEFAULT 'pending',
                approver TEXT DEFAULT '',
                reason TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                resolved_at TEXT DEFAULT ''
            )
        """)
        self.conn.commit()

    def create_request(self, req: ApprovalRequest) -> str:
        try:
            self.conn.execute(
                """INSERT INTO approvals
                   (request_id, gate_id, gate_name, metric_name, metric_value,
                    threshold, requester, status, approver, reason, created_at, resolved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    req.request_id,
                    req.gate_id,
                    req.gate_name,
                    req.metric_name,
                    req.metric_value,
                    req.threshold,
                    req.requester,
                    req.status,
                    req.approver,
                    req.reason,
                    req.created_at,
                    req.resolved_at,
                ),
            )
            self.conn.commit()
            logger.info("Approval request created: %s for gate %s", req.request_id, req.gate_id)
            return req.request_id
        except sqlite3.Error as e:
            logger.error("Failed to create approval request: %s", e)
            return ""

    def approve(self, request_id: str, approver: str, reason: str = "") -> bool:
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        cursor = self.conn.execute(
            "UPDATE approvals SET status = ?, approver = ?, reason = ?, resolved_at = ? WHERE request_id = ? AND status = 'pending'",
            (ApprovalStatus.APPROVED, approver, reason, now, request_id),
        )
        self.conn.commit()
        if cursor.rowcount > 0:
            logger.info("Approval %s granted by %s", request_id, approver)
            return True
        logger.warning("Approval %s not found or not pending", request_id)
        return False

    def reject(self, request_id: str, approver: str, reason: str = "") -> bool:
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        cursor = self.conn.execute(
            "UPDATE approvals SET status = ?, approver = ?, reason = ?, resolved_at = ? WHERE request_id = ? AND status = 'pending'",
            (ApprovalStatus.REJECTED, approver, reason, now, request_id),
        )
        self.conn.commit()
        if cursor.rowcount > 0:
            logger.info("Approval %s rejected by %s", request_id, approver)
            return True
        return False

    def get(self, request_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM approvals WHERE request_id = ?", (request_id,)).fetchone()
        return dict(row) if row else None

    def list_pending(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM approvals WHERE status = 'pending' ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_all(self, status: str = "", limit: int = 50) -> list[dict[str, Any]]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM approvals ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
