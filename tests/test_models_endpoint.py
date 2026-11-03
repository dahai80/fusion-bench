"""GET /api/v1/models — downloaded-model dropdown source (#38 UX)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


def _mock_response(status_code=200, body=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body or {}
    return resp


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("fusion_bench.core.judge_config._DEFAULT_DB_PATH", tmp_path / "judges.db")
    monkeypatch.setattr("fusion_bench.storage.trace_store._DEFAULT_DB_PATH", tmp_path / "traces.db")
    monkeypatch.setattr("fusion_bench.storage.judge_store._DEFAULT_DB_PATH", tmp_path / "judges.db")
    monkeypatch.setenv("FUSION_IDENTITY_SERVICE_TOKEN", "svc-tok")
    monkeypatch.setattr(
        "fusion_bench.auth.tenant.httpx.post",
        lambda *a, **k: _mock_response(
            200, {"tid": "t1", "role": "admin", "scopes": [], "tenant_status": "active", "revoked": False}
        ),
    )

    from fusion_bench.api import app as app_module

    app_module._store = None
    with TestClient(app_module.app) as c:
        yield c
    app_module._store = None


def _auth():
    return {"X-Tenant-Id": "t1", "Authorization": "Bearer tok"}


def _stub_runner(monkeypatch, ids):
    from fusion_bench.engine import benchmark as bench_mod

    class FakeRunner:
        async def list_models(self):
            return [{"id": i} for i in ids]

        async def close(self):
            pass

    monkeypatch.setattr(bench_mod, "BenchmarkRunner", FakeRunner)


class TestModelsEndpoint:
    def test_models_sorted_dedup(self, client, monkeypatch):
        _stub_runner(monkeypatch, ["b-model", "a-model", "a-model"])
        resp = client.get("/api/v1/models", headers=_auth())
        assert resp.status_code == 200
        assert resp.json() == {"models": ["a-model", "b-model"]}

    def test_models_empty(self, client, monkeypatch):
        _stub_runner(monkeypatch, [])
        resp = client.get("/api/v1/models", headers=_auth())
        assert resp.status_code == 200
        assert resp.json() == {"models": []}

    def test_models_requires_auth(self, client):
        resp = client.get("/api/v1/models")
        assert resp.status_code == 401
