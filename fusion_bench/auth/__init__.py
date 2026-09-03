"""Auth module — RBAC permission framework backed by fusion-identity tenant context.

Importers/callers: api/app.py imports require_permission for FastAPI Depends guards.
Affected API: FastAPI endpoint guards via Depends(require_permission(Permission.X)).
Data schema: re-exports Role, Permission, ROLE_PERMISSIONS, require_permission from rbac.py.
Tenant integration: auth/tenant.py provides _verify_jwt + _report_usage.
"""

from .rbac import ROLE_PERMISSIONS, Permission, Role, require_permission
from .tenant import _report_usage, _verify_jwt

__all__ = ["Role", "Permission", "ROLE_PERMISSIONS", "require_permission", "_verify_jwt", "_report_usage"]
