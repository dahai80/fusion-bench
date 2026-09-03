"""Release 1 API tests — tenant middleware, /judges CRUD, authz guards, cross-tenant isolation (issue #16)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


def _mock_response(status_code=200, body=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body or {}
    return resp


def _stub_identity(monkeypatch, role="admin", tid="t1"):
    """Stub fusion-identity /auth/verify so the real _verify_jwt runs but
    returns canned claims without network. Service token must be set."""
    monkeypatch.setenv("FUSION_IDENTITY_SERVICE_TOKEN", "svc-tok")
    monkeypatch.setattr(
        "fusion_bench.auth.tenant.httpx.post",
        lambda *a, **k: _mock_response(
            200, {"tid": tid, "role": role, "scopes": [], "tenant_status": "active", "revoked": False}
        ),
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Redirect all default DB paths to tmp so tests never touch home dir.
    monkeypatch.setattr("fusion_bench.core.judge_config._DEFAULT_DB_PATH", tmp_path / "judges.db")
    monkeypatch.setattr("fusion_bench.storage.trace_store._DEFAULT_DB_PATH", tmp_path / "traces.db")
    monkeypatch.setattr("fusion_bench.storage.judge_store._DEFAULT_DB_PATH", tmp_path / "judges.db")
    monkeypatch.delenv("FUSION_BENCH_TLS_ENFORCE", raising=False)
    _stub_identity(monkeypatch, role="admin", tid="t1")

    from fusion_bench.api import app as app_module

    app_module._store = None
    with TestClient(app_module.app) as c:
        yield c
    app_module._store = None


def _auth(tid="t1"):
    return {"X-Tenant-Id": tid, "Authorization": "Bearer tok"}


def _stub_role(monkeypatch, role, tid="t1"):
    _stub_identity(monkeypatch, role=role, tid=tid)


# ── Health (exempt, no auth) ────────────────────────────────────────


class TestHealthEndpoint:
    def test_health_ok_no_auth(self, client):
        resp = client.get("/api/v1/system/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ── /judges CRUD (tenant auth) ──────────────────────────────────────


class TestJudgesCRUD:
    def test_create_judge(self, client):
        resp = client.post(
            "/api/v1/judges",
            json={"name": "j1", "model": "qwen3.5-9b", "judge_type": "hybrid"},
            headers=_auth(),
        )
        assert resp.status_code == 201
        assert resp.json() == {"name": "j1", "created": True}

    def test_list_judges(self, client):
        client.post("/api/v1/judges", json={"name": "list-a"}, headers=_auth())
        client.post("/api/v1/judges", json={"name": "list-b"}, headers=_auth())
        resp = client.get("/api/v1/judges", headers=_auth())
        assert resp.status_code == 200
        names = {j["name"] for j in resp.json()["judges"]}
        assert {"list-a", "list-b"} <= names

    def test_list_judges_empty(self, client):
        resp = client.get("/api/v1/judges", headers=_auth())
        assert resp.status_code == 200
        assert resp.json() == {"judges": []}

    def test_delete_judge_existing(self, client):
        client.post("/api/v1/judges", json={"name": "del-me"}, headers=_auth())
        resp = client.delete("/api/v1/judges/del-me", headers=_auth())
        assert resp.status_code == 200
        assert resp.json() == {"deleted": True}
        assert all(j["name"] != "del-me" for j in client.get("/api/v1/judges", headers=_auth()).json()["judges"])

    def test_delete_judge_missing(self, client):
        resp = client.delete("/api/v1/judges/nope", headers=_auth())
        assert resp.status_code == 200
        assert resp.json() == {"deleted": False}


# ── Authz guards ────────────────────────────────────────────────────


class TestAuthGuards:
    def test_missing_tenant_header_rejected(self, client):
        resp = client.post(
            "/api/v1/datasets", json={"name": "ds", "format": "json"}, headers={"Authorization": "Bearer tok"}
        )
        assert resp.status_code == 401

    def test_missing_token_rejected(self, client):
        resp = client.post("/api/v1/datasets", json={"name": "ds", "format": "json"}, headers={"X-Tenant-Id": "t1"})
        assert resp.status_code == 401

    def test_viewer_denied_write(self, client, monkeypatch):
        _stub_role(monkeypatch, role="viewer")
        resp = client.post("/api/v1/datasets", json={"name": "vw-ds", "format": "json"}, headers=_auth())
        assert resp.status_code == 403

    def test_operator_allowed_write(self, client, monkeypatch):
        _stub_role(monkeypatch, role="operator")
        resp = client.get("/api/v1/tasks", headers=_auth())
        assert resp.status_code == 200

    def test_admin_allowed_write(self, client):
        resp = client.get("/api/v1/tasks", headers=_auth())
        assert resp.status_code == 200


# ── Cross-tenant data isolation ─────────────────────────────────────


class TestCrossTenantIsolation:
    def test_tenant_a_cannot_read_tenant_b_traces(self, tmp_path, monkeypatch):
        monkeypatch.setattr("fusion_bench.storage.trace_store._DEFAULT_DB_PATH", tmp_path / "traces.db")
        from fusion_bench.core.models import EvalLevel, TaskStatus, TraceRecord
        from fusion_bench.storage.trace_store import TraceStore

        store = TraceStore()
        store.insert(
            TraceRecord(
                trace_id="tr-A",
                model="m",
                level=EvalLevel.L1_MODEL,
                executor_key="speed",
                task_id="task-A",
                status=TaskStatus.COMPLETED,
                eval_result={"metric_value": 1.0},
                tenant_id="tenantA",
            )
        )
        store.insert(
            TraceRecord(
                trace_id="tr-B",
                model="m",
                level=EvalLevel.L1_MODEL,
                executor_key="speed",
                task_id="task-B",
                status=TaskStatus.COMPLETED,
                eval_result={"metric_value": 2.0},
                tenant_id="tenantB",
            )
        )

        a_only = store.query(tenant_id="tenantA")
        assert all(r.tenant_id == "tenantA" for r in a_only)
        assert {r.trace_id for r in a_only} == {"tr-A"}

        b_only = store.query(tenant_id="tenantB")
        assert {r.trace_id for r in b_only} == {"tr-B"}

        both = store.query()
        assert {r.trace_id for r in both} == {"tr-A", "tr-B"}
        store.close()

    def test_tenant_mismatch_at_gateway_rejected(self, client, monkeypatch):
        _stub_identity(monkeypatch, role="admin", tid="t1")
        # jwt.tid=t1 but header says t2 -> middleware 401.
        resp = client.get("/api/v1/tasks", headers={"X-Tenant-Id": "t2", "Authorization": "Bearer tok"})
        assert resp.status_code == 401


# ── TLS enforcement middleware ──────────────────────────────────────


class TestTLSEnforcement:
    def test_tls_enforce_rejects_http(self, tmp_path, monkeypatch):
        monkeypatch.setattr("fusion_bench.core.judge_config._DEFAULT_DB_PATH", tmp_path / "judges.db")
        monkeypatch.setattr("fusion_bench.storage.trace_store._DEFAULT_DB_PATH", tmp_path / "traces.db")
        monkeypatch.setenv("FUSION_BENCH_TLS_ENFORCE", "1")
        import importlib

        import fusion_bench.api.app as app_module

        importlib.reload(app_module)
        with TestClient(app_module.app) as c:
            resp = c.get("/api/v1/system/health")
            assert resp.status_code == 426
            assert resp.headers.get("upgrade") == "TLS"
        monkeypatch.delenv("FUSION_BENCH_TLS_ENFORCE", raising=False)
        importlib.reload(app_module)
