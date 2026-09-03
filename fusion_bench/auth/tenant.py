"""Tenant integration with fusion-identity (issue #16).

fusion-identity (port 11470) is the sole JWT issuer + tenant registry for the
Fusion ecosystem. This module provides the verify_jwt callback consumed by
fusion_core.tenant.install_tenant_middleware, role mapping to bench's
permission matrix, and best-effort usage reporting back to identity.

Three red lines enforced (via the upstream middleware):
  1. fail-closed — missing X-Tenant-Id or missing/invalid token -> 401
  2. cross-tenant denied — jwt.tid must match X-Tenant-Id header -> 401
  3. data isolation — traces scoped by tenant_id column + query guard

No local api_keys/user_roles tables; credentials are identity-issued.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_IDENTITY_URL = "http://127.0.0.1:11470"


def _identity_url() -> str:
    return os.environ.get("FUSION_IDENTITY_URL", _DEFAULT_IDENTITY_URL)


def _service_token() -> str:
    return os.environ.get("FUSION_IDENTITY_SERVICE_TOKEN", "")


# Identity unified roles -> bench role strings (key ROLE_PERMISSIONS in rbac.py).
_ROLE_MAP = {
    "tenant_admin": "admin",
    "operator": "operator",
    "member": "operator",
    "viewer": "viewer",
    "admin": "admin",
}


class TenantVerifyError(Exception):
    """Raised when identity /auth/verify rejects the token (-> 401)."""


def _map_role(identity_role: str | None) -> str:
    if not identity_role:
        return "viewer"
    return _ROLE_MAP.get(identity_role, "viewer")


def _verify_jwt(token: str) -> dict:
    """Verify a bearer token against fusion-identity /auth/verify.

    Called synchronously by the tenant middleware. Returns a claims dict
    the middleware inspects for tid/role/scope. Raises on any rejection so
    the middleware answers 401 (fail-closed).
    """
    service_token = _service_token()
    if not service_token:
        logger.error("tenant verify: FUSION_IDENTITY_SERVICE_TOKEN unset — fail-closed")
        raise TenantVerifyError("service token not configured")
    try:
        resp = httpx.post(
            f"{_identity_url()}/api/v1/auth/verify",
            json={"token": token},
            headers={"Authorization": f"Bearer {service_token}"},
            timeout=5.0,
        )
    except httpx.HTTPError as exc:
        logger.error("tenant verify: identity unreachable: %s", exc)
        raise TenantVerifyError("identity unreachable") from exc
    if resp.status_code != 200:
        logger.warning("tenant verify: identity rejected token (status=%s)", resp.status_code)
        raise TenantVerifyError(f"identity rejected: {resp.status_code}")
    body = resp.json()
    if body.get("tenant_status") != "active":
        logger.warning("tenant verify: tenant_status=%s — not active", body.get("tenant_status"))
        raise TenantVerifyError("tenant not active")
    if body.get("revoked"):
        logger.warning("tenant verify: token revoked")
        raise TenantVerifyError("token revoked")
    return {
        "tid": body["tid"],
        "role": _map_role(body.get("role")),
        "scopes": list(body.get("scopes") or []),
    }


def _report_usage(
    tenant_id: str,
    metric: str,
    value: int,
    model: str | None = None,
    user_id: str | None = None,
) -> None:
    """Best-effort benchmark usage report to identity /usage.

    Never raises — a failed report must not block a benchmark result.
    """
    service_token = _service_token()
    if not service_token:
        logger.debug("usage report skipped: no service token")
        return
    try:
        resp = httpx.post(
            f"{_identity_url()}/api/v1/tenants/{tenant_id}/usage",
            json={"metric": metric, "value": value, "source": "fusion-bench", "model": model, "user_id": user_id},
            headers={"Authorization": f"Bearer {service_token}"},
            timeout=5.0,
        )
        if resp.status_code != 200:
            logger.warning("usage report failed: tenant=%s status=%s", tenant_id, resp.status_code)
    except httpx.HTTPError as exc:
        logger.warning("usage report error: tenant=%s: %s", tenant_id, exc)
