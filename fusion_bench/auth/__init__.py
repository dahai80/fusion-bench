"""Auth module - RBAC permission framework.

Importers/callers: api/app.py imports require_permission for FastAPI Depends guards.
Affected API: FastAPI endpoint guards via Depends(require_permission(Permission.X)).
Data schema: re-exports RBACStore, Role, Permission from rbac.py.
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P2-12).
"""

from .rbac import ROLE_PERMISSIONS, Permission, RBACStore, Role, require_permission

__all__ = ["RBACStore", "Role", "Permission", "ROLE_PERMISSIONS", "require_permission"]
