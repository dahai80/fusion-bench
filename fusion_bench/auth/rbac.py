"""RBAC permission framework for API access control.

Importers/callers: api/app.py FastAPI middleware imports require_permission() dependency.
Affected API: FastAPI Depends(require_permission(Permission.X)) guards endpoints.
Data schema: Role enum (ADMIN/OPERATOR/VIEWER), Permission enum, user_roles table (user_id PK, role, assigned_by, assigned_at).
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P2-12 RBAC).
"""

from __future__ import annotations

import logging
import sqlite3
import time
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".fusion-bench" / "rbac.db"


class Role(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class Permission(StrEnum):
    TASK_CREATE = "task:create"
    TASK_READ = "task:read"
    TASK_CANCEL = "task:cancel"
    GATE_READ = "gate:read"
    GATE_APPROVE = "gate:approve"
    BASELINE_MANAGE = "baseline:manage"
    SCHEDULE_MANAGE = "schedule:manage"
    DATASET_MANAGE = "dataset:manage"
    AUDIT_READ = "audit:read"
    SYSTEM_ADMIN = "system:admin"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: set(Permission),
    Role.OPERATOR: {
        Permission.TASK_CREATE,
        Permission.TASK_READ,
        Permission.TASK_CANCEL,
        Permission.GATE_READ,
        Permission.BASELINE_MANAGE,
        Permission.SCHEDULE_MANAGE,
        Permission.DATASET_MANAGE,
    },
    Role.VIEWER: {
        Permission.TASK_READ,
        Permission.GATE_READ,
        Permission.AUDIT_READ,
    },
}


class RBACStore:
    """SQLite-backed RBAC store."""

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
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id TEXT PRIMARY KEY,
                role TEXT NOT NULL DEFAULT 'viewer',
                assigned_by TEXT DEFAULT 'system',
                assigned_at TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def assign_role(self, user_id: str, role: str, assigned_by: str = "system") -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.conn.execute(
            "INSERT OR REPLACE INTO user_roles (user_id, role, assigned_by, assigned_at) VALUES (?, ?, ?, ?)",
            (user_id, role, assigned_by, now),
        )
        self.conn.commit()
        logger.info("Role %s assigned to %s by %s", role, user_id, assigned_by)

    def get_role(self, user_id: str) -> Role:
        row = self.conn.execute("SELECT role FROM user_roles WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            try:
                return Role(row["role"])
            except ValueError:
                pass
        return Role.VIEWER

    def get_permissions(self, user_id: str) -> set[Permission]:
        role = self.get_role(user_id)
        return ROLE_PERMISSIONS.get(role, set())

    def has_permission(self, user_id: str, permission: Permission) -> bool:
        return permission in self.get_permissions(user_id)

    def list_users(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM user_roles ORDER BY assigned_at DESC").fetchall()
        return [
            {
                "user_id": r["user_id"],
                "role": r["role"],
                "assigned_by": r["assigned_by"],
                "assigned_at": r["assigned_at"],
            }
            for r in rows
        ]

    def remove_user(self, user_id: str) -> bool:
        cursor = self.conn.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


def require_permission(permission: Permission):
    """FastAPI dependency factory for permission checks."""

    def _check(user_id: str = "anonymous") -> str:
        store = RBACStore()
        try:
            if not store.has_permission(user_id, permission):
                raise PermissionError(f"User {user_id} lacks permission {permission.value}")
            return user_id
        finally:
            store.close()

    return _check
