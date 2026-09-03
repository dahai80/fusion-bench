"""Tests for fusion-identity tenant integration + RBAC permission matrix (issue #16)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from fusion_bench.auth.rbac import ROLE_PERMISSIONS, Permission, Role, require_permission
from fusion_bench.auth.tenant import TenantVerifyError, _map_role, _report_usage, _verify_jwt

# ── Role mapping ────────────────────────────────────────────────────


class TestRoleMapping:
    def test_tenant_admin_maps_to_admin(self):
        assert _map_role("tenant_admin") == "admin"

    def test_operator_maps_to_operator(self):
        assert _map_role("operator") == "operator"

    def test_member_maps_to_operator(self):
        assert _map_role("member") == "operator"

    def test_viewer_maps_to_viewer(self):
        assert _map_role("viewer") == "viewer"

    def test_unknown_role_falls_back_to_viewer(self):
        assert _map_role("superuser") == "viewer"

    def test_none_role_falls_back_to_viewer(self):
        assert _map_role(None) == "viewer"


# ── Permission matrix ───────────────────────────────────────────────


class TestPermissionMatrix:
    def test_admin_has_all_permissions(self):
        assert ROLE_PERMISSIONS[Role.ADMIN] == set(Permission)

    def test_operator_has_no_system_admin(self):
        assert Permission.SYSTEM_ADMIN not in ROLE_PERMISSIONS[Role.OPERATOR]

    def test_operator_has_task_create(self):
        assert Permission.TASK_CREATE in ROLE_PERMISSIONS[Role.OPERATOR]

    def test_viewer_is_read_only(self):
        viewer = ROLE_PERMISSIONS[Role.VIEWER]
        assert Permission.TASK_READ in viewer
        assert Permission.GATE_READ in viewer
        assert Permission.AUDIT_READ in viewer
        assert Permission.TASK_CREATE not in viewer


# ── _verify_jwt (mocked httpx) ──────────────────────────────────────


def _mock_response(status_code=200, body=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body or {}
    return resp


class TestVerifyJwt:
    def test_valid_token_returns_mapped_claims(self, monkeypatch):
        monkeypatch.setenv("FUSION_IDENTITY_SERVICE_TOKEN", "svc-tok")
        monkeypatch.setattr(
            "fusion_bench.auth.tenant.httpx.post",
            lambda *a, **k: _mock_response(
                200, {"tid": "t1", "role": "tenant_admin", "scopes": ["x"], "tenant_status": "active", "revoked": False}
            ),
        )
        claims = _verify_jwt("good-token")
        assert claims["tid"] == "t1"
        assert claims["role"] == "admin"
        assert claims["scopes"] == ["x"]

    def test_missing_service_token_fail_closed(self, monkeypatch):
        monkeypatch.delenv("FUSION_IDENTITY_SERVICE_TOKEN", raising=False)
        with pytest.raises(TenantVerifyError):
            _verify_jwt("tok")

    def test_identity_unreachable_fail_closed(self, monkeypatch):
        import httpx

        monkeypatch.setenv("FUSION_IDENTITY_SERVICE_TOKEN", "svc-tok")
        monkeypatch.setattr("fusion_bench.auth.tenant.httpx.post", MagicMock(side_effect=httpx.ConnectError("nope")))
        with pytest.raises(TenantVerifyError):
            _verify_jwt("tok")

    def test_non_200_rejected(self, monkeypatch):
        monkeypatch.setenv("FUSION_IDENTITY_SERVICE_TOKEN", "svc-tok")
        monkeypatch.setattr("fusion_bench.auth.tenant.httpx.post", lambda *a, **k: _mock_response(401))
        with pytest.raises(TenantVerifyError):
            _verify_jwt("tok")

    def test_inactive_tenant_rejected(self, monkeypatch):
        monkeypatch.setenv("FUSION_IDENTITY_SERVICE_TOKEN", "svc-tok")
        monkeypatch.setattr(
            "fusion_bench.auth.tenant.httpx.post",
            lambda *a, **k: _mock_response(200, {"tid": "t1", "role": "viewer", "tenant_status": "suspended"}),
        )
        with pytest.raises(TenantVerifyError):
            _verify_jwt("tok")

    def test_revoked_token_rejected(self, monkeypatch):
        monkeypatch.setenv("FUSION_IDENTITY_SERVICE_TOKEN", "svc-tok")
        monkeypatch.setattr(
            "fusion_bench.auth.tenant.httpx.post",
            lambda *a, **k: _mock_response(
                200, {"tid": "t1", "role": "viewer", "tenant_status": "active", "revoked": True}
            ),
        )
        with pytest.raises(TenantVerifyError):
            _verify_jwt("tok")


# ── _report_usage (best-effort, never raises) ───────────────────────


class TestReportUsage:
    def test_success_no_raise(self, monkeypatch):
        monkeypatch.setenv("FUSION_IDENTITY_SERVICE_TOKEN", "svc-tok")
        post = MagicMock(return_value=_mock_response(200))
        monkeypatch.setattr("fusion_bench.auth.tenant.httpx.post", post)
        _report_usage("t1", "tokens", 42, model="m", user_id="u")  # must not raise
        assert post.called

    def test_failure_does_not_raise(self, monkeypatch):
        import httpx

        monkeypatch.setenv("FUSION_IDENTITY_SERVICE_TOKEN", "svc-tok")
        monkeypatch.setattr(
            "fusion_bench.auth.tenant.httpx.post", MagicMock(side_effect=httpx.TimeoutException("slow"))
        )
        _report_usage("t1", "tokens", 42)  # must not raise

    def test_no_service_token_skips_silently(self, monkeypatch):
        monkeypatch.delenv("FUSION_IDENTITY_SERVICE_TOKEN", raising=False)
        post = MagicMock()
        monkeypatch.setattr("fusion_bench.auth.tenant.httpx.post", post)
        _report_usage("t1", "tokens", 42)
        assert not post.called


# ── Tenant middleware integration ───────────────────────────────────


def _stub_identity(monkeypatch, role="admin", tid="t1"):
    """Make _verify_jwt (already bound in app middleware) return canned claims.

    Patches httpx.post inside tenant module so the real _verify_jwt runs but
    talks to a fake identity. Service token must be set to avoid fail-closed.
    """
    monkeypatch.setenv("FUSION_IDENTITY_SERVICE_TOKEN", "svc-tok")
    monkeypatch.setattr(
        "fusion_bench.auth.tenant.httpx.post",
        lambda *a, **k: _mock_response(
            200, {"tid": tid, "role": role, "scopes": [], "tenant_status": "active", "revoked": False}
        ),
    )


def _make_app():
    from fusion_core.tenant import install_tenant_middleware

    app = FastAPI()
    install_tenant_middleware(
        app,
        verify_jwt=_verify_jwt,
        exempt_paths=frozenset({"/public", "/docs", "/openapi.json", "/redoc"}),
    )

    @app.get("/public")
    async def public():
        return {"ok": True}

    @app.get("/read")
    async def read(_u: str = Depends(require_permission(Permission.TASK_READ))):
        return {"ok": True}

    @app.post("/write")
    async def write(_u: str = Depends(require_permission(Permission.TASK_CREATE))):
        return {"ok": True}

    return app


class TestTenantMiddleware:
    def test_exempt_path_passes_without_auth(self, monkeypatch):
        _stub_identity(monkeypatch)
        client = TestClient(_make_app())
        resp = client.get("/public")
        assert resp.status_code == 200

    def test_missing_tenant_header_rejected(self, monkeypatch):
        _stub_identity(monkeypatch)
        client = TestClient(_make_app())
        resp = client.get("/read", headers={"Authorization": "Bearer tok"})
        assert resp.status_code == 401

    def test_missing_token_rejected(self, monkeypatch):
        _stub_identity(monkeypatch)
        client = TestClient(_make_app())
        resp = client.get("/read", headers={"X-Tenant-Id": "t1"})
        assert resp.status_code == 401

    def test_valid_token_matching_tenant_passes(self, monkeypatch):
        _stub_identity(monkeypatch, role="operator", tid="t1")
        client = TestClient(_make_app())
        resp = client.get("/read", headers={"X-Tenant-Id": "t1", "Authorization": "Bearer tok"})
        assert resp.status_code == 200

    def test_tenant_mismatch_rejected(self, monkeypatch):
        _stub_identity(monkeypatch, role="admin", tid="t1")
        client = TestClient(_make_app())
        resp = client.get("/read", headers={"X-Tenant-Id": "t2", "Authorization": "Bearer tok"})
        assert resp.status_code == 401

    def test_invalid_token_rejected(self, monkeypatch):
        import httpx

        monkeypatch.setenv("FUSION_IDENTITY_SERVICE_TOKEN", "svc-tok")
        monkeypatch.setattr("fusion_bench.auth.tenant.httpx.post", MagicMock(side_effect=httpx.ConnectError("down")))
        client = TestClient(_make_app())
        resp = client.get("/read", headers={"X-Tenant-Id": "t1", "Authorization": "Bearer tok"})
        assert resp.status_code == 401

    def test_viewer_denied_write(self, monkeypatch):
        _stub_identity(monkeypatch, role="viewer", tid="t1")
        client = TestClient(_make_app())
        resp = client.post("/write", headers={"X-Tenant-Id": "t1", "Authorization": "Bearer tok"})
        assert resp.status_code == 403

    def test_operator_allowed_write(self, monkeypatch):
        _stub_identity(monkeypatch, role="operator", tid="t1")
        client = TestClient(_make_app())
        resp = client.post("/write", headers={"X-Tenant-Id": "t1", "Authorization": "Bearer tok"})
        assert resp.status_code == 200

    def test_no_service_token_fail_closed(self, monkeypatch):
        monkeypatch.delenv("FUSION_IDENTITY_SERVICE_TOKEN", raising=False)
        client = TestClient(_make_app())
        resp = client.get("/read", headers={"X-Tenant-Id": "t1", "Authorization": "Bearer tok"})
        assert resp.status_code == 401
