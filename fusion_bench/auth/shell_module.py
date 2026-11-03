# Union-web shell module credential auth (#38 re-verification fix).
#
# The gateway shell proxy (internal/shell/proxy.go) forwards module traffic
# with `Authorization: Bearer <module credential>` and strips the caller's
# session token/cookie — it never injects X-Tenant-Id. Without special
# handling every proxied request died at the tenant middleware
# ("missing X-Tenant-Id").
#
# Resolution: the module credential is FUSION_BENCH_SHELL_API_KEY (carried
# in the registration body by shell_registry, so the proxy injects exactly
# this value). A non-JWT-shaped Bearer matching that key is the gateway's
# vetted principal: the outer middleware below supplies the synthetic
# "shell" tenant header, and _verify_jwt (tenant.py) issues claims for it.
# Everything else stays fail-closed — wrong key, missing key, or missing
# tenant header still 401s at the tenant middleware.

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

MODULE_KEY_ENV = "FUSION_BENCH_SHELL_API_KEY"
SHELL_TENANT_ID = "shell"
SHELL_ROLE = "operator"


def module_key() -> str:
    # Read at request time (getter pattern, per repo convention).
    return os.environ.get(MODULE_KEY_ENV, "").strip()


def looks_like_jwt(token: str) -> bool:
    # JWT shape = three dot-separated base64url segments. The gateway proxy
    # injects the module API key (fm- / fm-bench-...), never JWT-shaped —
    # such tokens take the module-key path, not identity verification.
    parts = token.split(".")
    return len(parts) == 3 and all(parts)


def verify_module_token(token: str) -> dict | None:
    # Returns service claims when the token IS the configured module key.
    # JWT-shaped -> None (caller falls through to identity). No module key
    # configured -> None as well: identity may legitimately verify opaque
    # tokens, so the module path only activates when the key env is set.
    # Key configured + mismatch -> fail-closed raise.
    if looks_like_jwt(token):
        return None
    expected = module_key()
    if not expected:
        return None
    if token == expected:
        return {"tid": SHELL_TENANT_ID, "role": SHELL_ROLE, "scopes": []}
    raise ValueError("module credential mismatch")


class ShellModuleHeaderMiddleware:
    # ASGI middleware OUTSIDE the tenant middleware: for requests carrying
    # the module credential but no X-Tenant-Id, inject the synthetic shell
    # tenant header. Anything else passes through untouched — the tenant
    # middleware keeps its fail-closed behavior (missing header -> 401).

    def __init__(self, app) -> None:
        self._app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = list(scope.get("headers") or [])
        names = {k.lower() for k, _ in headers}
        if b"x-tenant-id" not in names and module_key():
            auth = b""
            for k, v in headers:
                if k.lower() == b"authorization":
                    auth = v
                    break
            token = auth[7:].decode("latin-1").strip() if auth.lower().startswith(b"bearer ") else ""
            if token and not looks_like_jwt(token) and token == module_key():
                headers.append((b"x-tenant-id", SHELL_TENANT_ID.encode()))
                scope["headers"] = headers
        await self._app(scope, receive, send)
