"""RBAC permission framework for API access control.

Importers/callers: api/app.py FastAPI middleware imports require_permission() dependency.
Affected API: FastAPI Depends(require_permission(Permission.X)) guards endpoints.
Data schema: Role enum (ADMIN/OPERATOR/VIEWER), Permission enum, user_roles table (user_id PK, role, assigned_by, assigned_at).
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P2-12 RBAC).
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
import time
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import Request

if TYPE_CHECKING:
    from .identity import Identity

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
            CREATE TABLE IF NOT EXISTS api_keys (
                api_key TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL DEFAULT 'default',
                role TEXT NOT NULL DEFAULT 'viewer',
                scopes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                last_used REAL,
                revoked INTEGER NOT NULL DEFAULT 0
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id TEXT PRIMARY KEY,
                role TEXT NOT NULL DEFAULT 'viewer',
                workspace_id TEXT NOT NULL DEFAULT 'default',
                assigned_by TEXT DEFAULT 'system',
                assigned_at TEXT NOT NULL
            )
        """)
        # Migrate existing DBs: add workspace_id to user_roles if missing
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(user_roles)").fetchall()}
        if "workspace_id" not in cols:
            self.conn.execute("ALTER TABLE user_roles ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'")
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

    def create_api_key(self, user_id: str, role: str, workspace_id: str = "default", scopes: list[str] | None = None) -> str:
        key = secrets.token_urlsafe(32)
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.conn.execute(
            "INSERT INTO api_keys (api_key, user_id, workspace_id, role, scopes, created_at, revoked) VALUES (?, ?, ?, ?, ?, ?, 0)",
            (key, user_id, workspace_id, role, json.dumps(scopes or []), now),
        )
        self.conn.commit()
        logger.info("API key created for user=%s role=%s workspace=%s", user_id, role, workspace_id)
        return key

    def verify_api_key(self, api_key: str) -> Identity | None:
        row = self.conn.execute(
            "SELECT api_key, user_id, workspace_id, role, scopes FROM api_keys WHERE api_key = ? AND revoked = 0",
            (api_key,),
        ).fetchone()
        if not row:
            return None
        self.conn.execute("UPDATE api_keys SET last_used = ? WHERE api_key = ?", (time.time(), api_key))
        self.conn.commit()
        try:
            role = Role(row["role"])
        except ValueError:
            role = Role.VIEWER
        from .identity import Identity
        return Identity(
            user_id=row["user_id"],
            workspace_id=row["workspace_id"],
            role=role,
            source="apikey",
            scopes=json.loads(row["scopes"]) if row["scopes"] else [],
        )

    def revoke_api_key(self, api_key: str) -> bool:
        cursor = self.conn.execute("UPDATE api_keys SET revoked = 1 WHERE api_key = ?", (api_key,))
        self.conn.commit()
        revoked = cursor.rowcount > 0
        if revoked:
            logger.info("API key revoked (prefix=%s)", api_key[:8])
        return revoked

    def list_api_keys(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT user_id, workspace_id, role, scopes, created_at, last_used, revoked FROM api_keys ORDER BY created_at DESC"
        ).fetchall()
        return [
            {
                "user_id": r["user_id"],
                "workspace_id": r["workspace_id"],
                "role": r["role"],
                "scopes": json.loads(r["scopes"]) if r["scopes"] else [],
                "created_at": r["created_at"],
                "last_used": r["last_used"],
                "revoked": r["revoked"],
            }
            for r in rows
        ]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


def has_permission(user_id: str, permission: Permission) -> bool:
    store = RBACStore()
    try:
        return store.has_permission(user_id, permission)
    finally:
        store.close()


def require_permission(permission: Permission, allow_anonymous: bool = False):
    # FastAPI dependency: resolves identity from request.state, enforces permission.
    from fastapi import HTTPException, status

    def _check(request: Request) -> str:
        from .identity import Identity
        identity: Identity = getattr(request.state, "identity", None) or Identity(user_id="anonymous")
        if identity.is_anonymous:
            if allow_anonymous:
                return identity.user_id
            strict = os.environ.get("FUSION_BENCH_AUTH_STRICT", "0") == "1"
            if strict:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authentication required")
            logger.warning("Anonymous access to write endpoint %s (non-strict mode)", permission.value)
            return identity.user_id
        if permission not in ROLE_PERMISSIONS.get(identity.role, set()):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission {permission.value} required")
        return identity.user_id

    return _check
