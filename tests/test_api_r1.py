"""Release 1 API tests — IdentityMiddleware, /judges CRUD, authz guards, TLS."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fusion_bench.auth.rbac import RBACStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Redirect all default DB paths to tmp so tests never touch home dir.
    monkeypatch.setattr(
        "fusion_bench.auth.rbac._DEFAULT_DB_PATH", tmp_path / "rbac.db"
    )
    monkeypatch.setattr(
        "fusion_bench.core.judge_config._DEFAULT_DB_PATH", tmp_path / "judges.db"
    )
    monkeypatch.setattr(
        "fusion_bench.storage.trace_store._DEFAULT_DB_PATH", tmp_path / "traces.db"
    )
    # Re-exported alias used by storage.judge_store.
    monkeypatch.setattr(
        "fusion_bench.storage.judge_store._DEFAULT_DB_PATH", tmp_path / "judges.db"
    )
    monkeypatch.setenv("FUSION_BENCH_API_KEY_ENABLED", "1")
    monkeypatch.delenv("FUSION_BENCH_OAUTH_ENABLED", raising=False)
    monkeypatch.delenv("FUSION_BENCH_TLS_ENFORCE", raising=False)

    from fusion_bench.api import app as app_module

    app_module._store = None  # reset cached store so it re-reads patched path
    with TestClient(app_module.app) as c:
        yield c
    app_module._store = None


@pytest.fixture
def admin_key(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "fusion_bench.auth.rbac._DEFAULT_DB_PATH", tmp_path / "rbac.db"
    )
    store = RBACStore()
    try:
        key = store.create_api_key("u-admin", role="admin", workspace_id="ws1")
    finally:
        store.close()
    return key


@pytest.fixture
def viewer_key(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "fusion_bench.auth.rbac._DEFAULT_DB_PATH", tmp_path / "rbac.db"
    )
    store = RBACStore()
    try:
        key = store.create_api_key("u-viewer", role="viewer", workspace_id="ws1")
    finally:
        store.close()
    return key


# ── Health (no auth) ────────────────────────────────────────────────


class TestHealthEndpoint:
    def test_health_ok(self, client):
        resp = client.get("/api/v1/system/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"


# ── /judges CRUD ────────────────────────────────────────────────────


class TestJudgesCRUD:
    def test_create_judge(self, client):
        resp = client.post(
            "/api/v1/judges",
            json={"name": "j1", "model": "qwen3.5-9b", "judge_type": "hybrid"},
        )
        assert resp.status_code == 201
        assert resp.json() == {"name": "j1", "created": True}

    def test_list_judges(self, client):
        client.post("/api/v1/judges", json={"name": "list-a"})
        client.post("/api/v1/judges", json={"name": "list-b"})
        resp = client.get("/api/v1/judges")
        assert resp.status_code == 200
        names = {j["name"] for j in resp.json()["judges"]}
        assert {"list-a", "list-b"} <= names

    def test_list_judges_empty(self, client):
        resp = client.get("/api/v1/judges")
        assert resp.status_code == 200
        assert resp.json() == {"judges": []}

    def test_delete_judge_existing(self, client):
        client.post("/api/v1/judges", json={"name": "del-me"})
        resp = client.delete("/api/v1/judges/del-me")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": True}
        # gone from list
        assert all(j["name"] != "del-me" for j in client.get("/api/v1/judges").json()["judges"])

    def test_delete_judge_missing(self, client):
        resp = client.delete("/api/v1/judges/nope")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": False}

    def test_judge_roundtrip_preserves_fields(self, client):
        client.post(
            "/api/v1/judges",
            json={
                "name": "rt",
                "model": "deepseek-v4",
                "judge_type": "llm",
                "weight": 0.8,
                "criteria": ["fluency", "accuracy"],
                "rubric": "strict",
                "temperature": 0.1,
                "max_tokens": 512,
            },
        )
        judges = {j["name"]: j for j in client.get("/api/v1/judges").json()["judges"]}
        assert judges["rt"]["model"] == "deepseek-v4"
        assert judges["rt"]["judge_type"] == "llm"
        assert judges["rt"]["weight"] == 0.8
        assert judges["rt"]["criteria"] == ["fluency", "accuracy"]
        assert judges["rt"]["rubric"] == "strict"


# ── IdentityMiddleware + authz guards ───────────────────────────────


class TestAuthGuards:
    def test_anonymous_write_non_strict_allowed(self, client):
        # Default non-strict: anonymous can hit a write endpoint (warns).
        resp = client.post(
            "/api/v1/datasets",
            json={"name": "anon-ds", "format": "json", "path": "/tmp/x.json"},
        )
        # Dataset endpoint may 4xx on bad path, but NOT 403 (auth passed).
        assert resp.status_code != 403

    def test_anonymous_write_strict_forbidden(self, client, monkeypatch):
        monkeypatch.setenv("FUSION_BENCH_AUTH_STRICT", "1")
        resp = client.post(
            "/api/v1/datasets",
            json={"name": "anon-ds", "format": "json", "path": "/tmp/x.json"},
        )
        assert resp.status_code == 403

    def test_admin_key_passes_write_guard(self, client, admin_key):
        resp = client.post(
            "/api/v1/datasets",
            json={"name": "adm-ds", "format": "json", "path": "/tmp/x.json"},
            headers={"x-api-key": admin_key},
        )
        assert resp.status_code != 403

    def test_viewer_key_denied_write_guard(self, client, viewer_key):
        # VIEWER lacks DATASET_MANAGE.
        resp = client.post(
            "/api/v1/datasets",
            json={"name": "vw-ds", "format": "json", "path": "/tmp/x.json"},
            headers={"x-api-key": viewer_key},
        )
        assert resp.status_code == 403

    def test_viewer_key_allows_read(self, client, viewer_key):
        # VIEWER has TASK_READ.
        resp = client.get("/api/v1/tasks", headers={"x-api-key": viewer_key})
        assert resp.status_code == 200

    def test_invalid_api_key_falls_back_anonymous(self, client):
        # Bogus key resolves to None -> anonymous (non-strict) -> not 403.
        resp = client.get(
            "/api/v1/tasks", headers={"x-api-key": "bogus-not-real"}
        )
        assert resp.status_code == 200

    def test_api_key_disabled_anonymous(self, client, monkeypatch):
        monkeypatch.setenv("FUSION_BENCH_API_KEY_ENABLED", "0")
        # Even with a header, key disabled -> anonymous.
        resp = client.get(
            "/api/v1/tasks", headers={"x-api-key": "whatever"}
        )
        assert resp.status_code == 200


# ── TLS enforcement middleware ──────────────────────────────────────


class TestTLSEnforcement:
    def test_tls_enforce_rejects_http(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "fusion_bench.auth.rbac._DEFAULT_DB_PATH", tmp_path / "rbac.db"
        )
        monkeypatch.setattr(
            "fusion_bench.core.judge_config._DEFAULT_DB_PATH",
            tmp_path / "judges.db",
        )
        monkeypatch.setattr(
            "fusion_bench.storage.trace_store._DEFAULT_DB_PATH",
            tmp_path / "traces.db",
        )
        monkeypatch.setenv("FUSION_BENCH_TLS_ENFORCE", "1")
        # Reimport app so the TLS middleware branch registers.
        import importlib

        import fusion_bench.api.app as app_module

        importlib.reload(app_module)
        with TestClient(app_module.app) as c:
            resp = c.get("/api/v1/system/health")
            assert resp.status_code == 426
            assert resp.headers.get("upgrade") == "TLS"
        # Restore module for other tests.
        monkeypatch.delenv("FUSION_BENCH_TLS_ENFORCE", raising=False)
        importlib.reload(app_module)
