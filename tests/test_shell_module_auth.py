# Issue #38 re-verification fix: gateway shell proxy module-credential path.
#
# The proxy injects Bearer <module key> with no X-Tenant-Id. Covers:
# module key shape detection, claims on match / fail-closed on mismatch,
# the header-supply middleware, and the full middleware stack (module Bearer
# with no tenant header is admitted; no Bearer still 401s).

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fusion_bench.api.app import app
from fusion_bench.auth.shell_module import (
    SHELL_ROLE,
    SHELL_TENANT_ID,
    ShellModuleHeaderMiddleware,
    looks_like_jwt,
    verify_module_token,
)
from fusion_bench.auth.tenant import TenantVerifyError, _verify_jwt


def test_looks_like_jwt_shapes():
    assert looks_like_jwt("a.b.c") is True
    assert looks_like_jwt("a..c") is False
    assert looks_like_jwt("fm-bench-abc123") is False
    assert looks_like_jwt("") is False


def test_verify_module_token_match(monkeypatch):
    monkeypatch.setenv("FUSION_BENCH_SHELL_API_KEY", "fm-bench-k1")
    claims = verify_module_token("fm-bench-k1")
    assert claims == {"tid": SHELL_TENANT_ID, "role": SHELL_ROLE, "scopes": []}


def test_verify_module_token_mismatch_fail_closed(monkeypatch):
    monkeypatch.setenv("FUSION_BENCH_SHELL_API_KEY", "fm-bench-k1")
    with pytest.raises(ValueError):
        verify_module_token("wrong-key")


def test_verify_module_token_jwt_shape_falls_through(monkeypatch):
    monkeypatch.setenv("FUSION_BENCH_SHELL_API_KEY", "fm-bench-k1")
    assert verify_module_token("h.p.s") is None


def test_verify_jwt_module_path(monkeypatch):
    monkeypatch.setenv("FUSION_BENCH_SHELL_API_KEY", "fm-bench-k1")
    monkeypatch.delenv("FUSION_IDENTITY_SERVICE_TOKEN", raising=False)
    claims = _verify_jwt("fm-bench-k1")
    assert claims["tid"] == SHELL_TENANT_ID
    assert claims["role"] == SHELL_ROLE


def test_verify_jwt_bad_module_key_rejected(monkeypatch):
    monkeypatch.setenv("FUSION_BENCH_SHELL_API_KEY", "fm-bench-k1")
    monkeypatch.delenv("FUSION_IDENTITY_SERVICE_TOKEN", raising=False)
    with pytest.raises((ValueError, TenantVerifyError)):
        _verify_jwt("not-the-key")


def test_verify_jwt_jwt_shape_unaffected(monkeypatch):
    # JWT-shaped tokens must still take the identity path (service token
    # missing -> TenantVerifyError), never the module-key path.
    monkeypatch.setenv("FUSION_BENCH_SHELL_API_KEY", "fm-bench-k1")
    monkeypatch.delenv("FUSION_IDENTITY_SERVICE_TOKEN", raising=False)
    with pytest.raises(TenantVerifyError):
        _verify_jwt("h.p.s")


class _Agent:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)


def _req(path, headers):
    return {"type": "http", "path": path, "headers": headers, "method": "GET", "query_string": b""}


def test_header_middleware_supplies_shell_tenant(monkeypatch):
    monkeypatch.setenv("FUSION_BENCH_SHELL_API_KEY", "fm-bench-k1")
    captured = {}

    async def inner(scope, receive, send):
        captured["headers"] = dict(scope["headers"])

    mw = ShellModuleHeaderMiddleware(inner)
    import asyncio

    asyncio.run(mw(_req("/api/v1/tasks", [(b"authorization", b"Bearer fm-bench-k1")]), None, None))
    assert captured["headers"][b"x-tenant-id"] == b"shell"


def test_header_middleware_untouched_without_module_key(monkeypatch):
    monkeypatch.setenv("FUSION_BENCH_SHELL_API_KEY", "fm-bench-k1")
    captured = {}

    async def inner(scope, receive, send):
        captured["headers"] = dict(scope["headers"])

    mw = ShellModuleHeaderMiddleware(inner)
    import asyncio

    asyncio.run(mw(_req("/api/v1/tasks", [(b"authorization", b"Bearer wrong")]), None, None))
    assert b"x-tenant-id" not in captured["headers"]


def test_full_stack_module_bearer_admitted(monkeypatch):
    # Module Bearer + no tenant header must NOT 401 at the tenant middleware.
    monkeypatch.setenv("FUSION_BENCH_SHELL_API_KEY", "fm-bench-k1")
    app.build_middleware_stack()
    client = TestClient(app)
    resp = client.get("/api/v1/tasks", headers={"Authorization": "Bearer fm-bench-k1"})
    assert resp.status_code != 401


def test_full_stack_no_token_still_401(monkeypatch):
    monkeypatch.setenv("FUSION_BENCH_SHELL_API_KEY", "fm-bench-k1")
    app.build_middleware_stack()
    client = TestClient(app)
    resp = client.get("/api/v1/tasks")
    assert resp.status_code == 401
