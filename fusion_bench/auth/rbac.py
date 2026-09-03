"""RBAC permission framework backed by fusion-identity tenant context (issue #16).

Local api_keys/user_roles tables retired — credentials now issued by
fusion-identity. Permission enforcement reads TenantContext set by the
tenant middleware (fail-closed: no context, no anonymous, no default-tenant).

Importers/callers: api/app.py FastAPI Depends(require_permission(Permission.X)).
"""

from __future__ import annotations

import logging
from enum import StrEnum

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


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


ROLE_PERMISSIONS: dict[str, set[Permission]] = {
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


def require_permission(permission: Permission):
    """FastAPI dependency: enforce permission against TenantContext.role.

    Fail-closed — no TenantContext means no authenticated tenant, so 401
    (not 403, not anonymous passthrough, not default-tenant degradation).
    """

    def _check(request: Request) -> str:
        from fusion_core.tenant import current

        ctx = current()
        if ctx is None or ctx.tenant_id is None:
            logger.warning("require_permission: no tenant context for %s — fail-closed", permission.value)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        role = ctx.role
        if role not in ROLE_PERMISSIONS:
            logger.warning("require_permission: unknown role=%s for %s", role, permission.value)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission {permission.value} required")
        if permission not in ROLE_PERMISSIONS[role]:
            logger.warning("require_permission: role=%s lacks %s (tenant=%s)", role, permission.value, ctx.tenant_id)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission {permission.value} required")
        return ctx.user_id or ctx.tenant_id

    return _check
