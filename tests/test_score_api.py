"""Issue #44 — per-item scoring endpoint tests (offline)."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from fusion_bench.scoring.per_item import extract_answer, score_item, score_items


def _stub_identity(monkeypatch, role="admin", tid="t1"):
    monkeypatch.setenv("FUSION_IDENTITY_SERVICE_TOKEN", "svc-tok")

    def _ok_post(*a, **k):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "tid": tid,
            "role": role,
            "scopes": [],
            "tenant_status": "active",
            "revoked": False,
        }
        return resp

    monkeypatch.setattr("fusion_bench.auth.tenant.httpx.post", _ok_post)


_AUTH = {"X-Tenant-Id": "t1", "Authorization": "Bearer tok"}


class TestExtractAnswer:
    def test_boxed(self):
        assert extract_answer(r"reasoning \\boxed{42} end", "boxed") == "42"

    def test_boxed_missing(self):
        assert extract_answer("no box here", "boxed") == ""

    def test_last_number(self):
        assert extract_answer("steps 3, 5 then 105 total", "last_number") == "105"

    def test_none_passthrough(self):
        assert extract_answer("raw text", "") == "raw text"


class TestScoreItem:
    def test_explicit_expected_match(self):
        out = score_item({"input": "q", "completion": "The answer is Paris.", "expected": "Paris"})
        assert out["score"] == 1.0
        assert out["details"]["matched_by"] == "contains"
        assert out["details"]["expected_source"] == "explicit"

    def test_explicit_expected_mismatch(self):
        out = score_item({"input": "q", "completion": "Berlin", "expected": "Paris"})
        assert out["score"] == 0.0
        assert out["details"]["matched_by"] == "none"

    def test_extract_mode(self):
        out = score_item(
            {"input": "q", "completion": r"work... \\boxed{72}", "expected": "72", "params": {"extract": "boxed"}}
        )
        assert out["score"] == 1.0
        assert out["details"]["extract"] == "boxed"

    def test_params_expected(self):
        out = score_item({"input": "q", "completion": "9", "params": {"expected": "9"}})
        assert out["score"] == 1.0

    def test_missing_everything_errors_gracefully(self):
        out = score_item({"input": "q", "completion": "x"})
        assert out["score"] == 0.0
        assert "expected or task" in out["details"]["error"]

    def test_empty_completion(self):
        out = score_item({"input": "q", "completion": "", "expected": "a"})
        assert out["score"] == 0.0
        assert "completion" in out["details"]["error"]

    def test_task_ground_truth_lookup(self, monkeypatch):
        monkeypatch.setattr(
            "fusion_bench.scoring.per_item._task_targets",
            lambda task, tasks_dir="": {"What is 2+2?": "4"},
        )
        out = score_item({"task": "gsm8k", "input": "What is 2+2?", "completion": "The answer is 4."})
        assert out["score"] == 1.0
        assert out["details"]["expected_source"] == "task_dataset"

    def test_task_input_not_found(self, monkeypatch):
        monkeypatch.setattr(
            "fusion_bench.scoring.per_item._task_targets",
            lambda task, tasks_dir="": {"known": "1"},
        )
        out = score_item({"task": "gsm8k", "input": "unknown question", "completion": "x"})
        assert out["score"] == 0.0
        assert "No ground truth" in out["details"]["error"]


class TestScoreItems:
    def test_batch(self):
        items = [
            {"input": "q1", "completion": "paris", "expected": "Paris"},
            {"input": "q2", "completion": "berlin", "expected": "Paris"},
        ]
        outs = score_items(items)
        assert [o["score"] for o in outs] == [1.0, 0.0]


class TestScoreEndpoint:
    def test_single_and_batch(self, monkeypatch):
        _stub_identity(monkeypatch)
        from fusion_bench.api import app as app_module

        with TestClient(app_module.app, headers=_AUTH) as c:
            r = c.post(
                "/api/v1/score",
                json={"input": "q", "completion": "Paris!", "expected": "Paris"},
            )
            assert r.status_code == 200
            assert r.json()["score"] == 1.0

            r = c.post(
                "/api/v1/score",
                json={
                    "items": [
                        {"input": "q1", "completion": "4", "expected": "4"},
                        {"input": "q2", "completion": "5", "expected": "4"},
                    ]
                },
            )
            assert r.status_code == 200
            assert [x["score"] for x in r.json()["results"]] == [1.0, 0.0]

    def test_missing_fields_422(self, monkeypatch):
        _stub_identity(monkeypatch)
        from fusion_bench.api import app as app_module

        with TestClient(app_module.app, headers=_AUTH) as c:
            r = c.post("/api/v1/score", json={"input": "q"})
            assert r.status_code == 422

    def test_no_task_record_created(self, monkeypatch):
        _stub_identity(monkeypatch)
        from fusion_bench.api import app as app_module

        app_module._background_tasks.clear()
        with TestClient(app_module.app, headers=_AUTH) as c:
            c.post("/api/v1/score", json={"input": "q", "completion": "a", "expected": "a"})
            assert not app_module._background_tasks
