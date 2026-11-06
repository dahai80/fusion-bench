"""Issue #41 - SxS judge REST surface tests (run endpoint + run store)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fusion_bench.judge.sxs_config import SxSVerdict
from fusion_bench.judge.sxs_store import SxSRunStore


def _mock_response(status_code=200, body=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body or {}
    return resp


def _stub_identity(monkeypatch, role="admin", tid="t1"):
    monkeypatch.setenv("FUSION_IDENTITY_SERVICE_TOKEN", "svc-tok")
    monkeypatch.setattr(
        "fusion_bench.auth.tenant.httpx.post",
        lambda *a, **k: _mock_response(
            200, {"tid": tid, "role": role, "scopes": [], "tenant_status": "active", "revoked": False}
        ),
    )


_AUTH = {"X-Tenant-Id": "t1", "Authorization": "Bearer tok"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("fusion_bench.judge.sxs_store._DEFAULT_DB_PATH", tmp_path / "sxs_runs.db")
    _stub_identity(monkeypatch, role="admin", tid="t1")
    from fusion_bench.api.app import app

    with TestClient(app) as c:
        yield c


def _verdict(winner="a", rationale="r"):
    return SxSVerdict(
        winner=winner,
        scores_a={"socratic_guidance": 4},
        scores_b={"socratic_guidance": 2},
        rationale=rationale,
        position_map={"slot1": "b", "slot2": "a"},
    )


def _patch_judge_pair(verdict):
    return patch(
        "fusion_bench.judge.sxs_judge.SxSJudge.judge_pair",
        new=AsyncMock(return_value=verdict),
    )


class TestSxSRunEndpoint:
    async def test_run_no_persist(self, client):
        with _patch_judge_pair(_verdict()):
            resp = client.post(
                "/api/v1/judges/sxs/run",
                headers=_AUTH,
                json={"prompt": "p", "model_a_output": "A", "model_b_output": "B", "persist": False},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["winner"] == "a"
        assert body["avg_a"] == 4.0
        assert body["position_map"] == {"slot1": "b", "slot2": "a"}
        assert "run_id" not in body

    async def test_run_persists_and_lists(self, client):
        with _patch_judge_pair(_verdict(winner="b", rationale="b wins")):
            resp = client.post(
                "/api/v1/judges/sxs/run",
                headers=_AUTH,
                json={"prompt": "p", "model_a_output": "A", "model_b_output": "B"},
            )
        assert resp.status_code == 200
        assert resp.json()["run_id"]
        runs = client.get("/api/v1/judges/sxs/runs?limit=5", headers=_AUTH).json()["runs"]
        assert len(runs) == 1
        assert runs[0]["winner"] == "b"
        assert runs[0]["verdict"]["rationale"] == "b wins"


class TestSxSRunStore:
    def test_save_and_list(self, tmp_path):
        store = SxSRunStore(db_path=tmp_path / "sxs.db")
        run_id = store.save_run(
            {"winner": "a", "avg_a": 3.5, "avg_b": 2.0, "rationale": "r"},
            judge_model="m",
            seed=42,
            prompt="p",
        )
        runs = store.list_runs()
        assert len(runs) == 1
        assert runs[0]["run_id"] == run_id
        assert runs[0]["winner"] == "a"
        assert runs[0]["verdict"]["rationale"] == "r"
        store.close()

    def test_list_empty(self, tmp_path):
        store = SxSRunStore(db_path=tmp_path / "sxs.db")
        assert store.list_runs() == []
        store.close()
