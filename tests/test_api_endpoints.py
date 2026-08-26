"""API endpoint tests — task lifecycle, suites, gates, results read paths."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fusion_bench.core.models import EvalLevel, TaskStatus, TraceRecord


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "fusion_bench.auth.rbac._DEFAULT_DB_PATH", tmp_path / "rbac.db"
    )
    monkeypatch.setattr(
        "fusion_bench.core.judge_config._DEFAULT_DB_PATH", tmp_path / "judges.db"
    )
    monkeypatch.setattr(
        "fusion_bench.storage.trace_store._DEFAULT_DB_PATH", tmp_path / "traces.db"
    )
    monkeypatch.setattr(
        "fusion_bench.storage.judge_store._DEFAULT_DB_PATH", tmp_path / "judges.db"
    )
    monkeypatch.setenv("FUSION_BENCH_API_KEY_ENABLED", "1")
    monkeypatch.delenv("FUSION_BENCH_OAUTH_ENABLED", raising=False)
    monkeypatch.delenv("FUSION_BENCH_TLS_ENFORCE", raising=False)

    from fusion_bench.api import app as app_module

    app_module._store = None
    app_module._background_tasks.clear()
    app_module._gate_approvals.clear()

    # Stub background runner so create_task does not launch a real executor.
    async def _noop_run(task_id, req):
        app_module._background_tasks[task_id]["status"] = "completed"

    monkeypatch.setattr(app_module, "_run_task", _noop_run)

    with TestClient(app_module.app) as c:
        yield c
    app_module._store = None
    app_module._background_tasks.clear()
    app_module._gate_approvals.clear()


@pytest.fixture
def seeded_trace(client):
    # Insert a completed trace directly into the store for read-path tests.
    from fusion_bench.api import app as app_module

    store = app_module._get_store()
    rec = TraceRecord(
        trace_id="trace-seed-1",
        model="qwen3.5-9b",
        level=EvalLevel.L1_MODEL,
        executor_key="speed",
        task_id="task-seed-1",
        status=TaskStatus.COMPLETED,
        eval_result={
            "metric_name": "tokens_per_second",
            "metric_value": 42.5,
            "pass_rate": 1.0,
            "num_cases": 10,
            "errors": [],
            "meta": {"host": "mac"},
        },
        duration_seconds=5.2,
    )
    store.insert(rec)
    return rec


# ── Task lifecycle ──────────────────────────────────────────────────


class TestTaskLifecycle:
    def test_create_task_returns_pending(self, client):
        resp = client.post(
            "/api/v1/tasks",
            json={"model": "qwen3.5-9b", "executor_key": "speed"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "pending"
        assert body["model"] == "qwen3.5-9b"
        assert body["task_id"].startswith("task-")

    def test_create_task_with_bad_executor_still_201(self, client):
        # 201 returned before background run; failure surfaces in detail/logs.
        resp = client.post(
            "/api/v1/tasks",
            json={"model": "m", "executor_key": "nonexistent"},
        )
        assert resp.status_code == 201

    def test_get_task_detail_from_background(self, client):
        from fusion_bench.api import app as app_module

        app_module._background_tasks["task-bg-1"] = {
            "task_id": "task-bg-1",
            "status": "running",
            "model": "m",
            "executor_key": "speed",
            "level": "L1",
            "created_at": "2026-08-26T10:00:00",
            "progress": 0.5,
        }
        resp = client.get("/api/v1/tasks/task-bg-1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"
        assert resp.json()["progress"] == 0.5

    def test_get_task_detail_from_store(self, client, seeded_trace):
        resp = client.get("/api/v1/tasks/task-seed-1")
        assert resp.status_code == 200
        assert resp.json()["model"] == "qwen3.5-9b"
        assert resp.json()["result"]["metric_value"] == 42.5

    def test_get_task_404(self, client):
        resp = client.get("/api/v1/tasks/does-not-exist")
        assert resp.status_code == 404

    def test_list_tasks_includes_background(self, client):
        from fusion_bench.api import app as app_module

        app_module._background_tasks["task-list-1"] = {
            "task_id": "task-list-1",
            "status": "pending",
            "model": "m1",
            "executor_key": "speed",
            "level": "L1",
            "created_at": "2026-08-26T10:00:00",
        }
        resp = client.get("/api/v1/tasks")
        assert resp.status_code == 200
        ids = {t["task_id"] for t in resp.json()}
        assert "task-list-1" in ids

    def test_list_tasks_filter_by_model(self, client):
        from fusion_bench.api import app as app_module

        app_module._background_tasks["t-a"] = {
            "task_id": "t-a", "status": "pending", "model": "alpha",
            "executor_key": "speed", "level": "L1", "created_at": "2026-08-26T10:00:00",
        }
        app_module._background_tasks["t-b"] = {
            "task_id": "t-b", "status": "pending", "model": "beta",
            "executor_key": "speed", "level": "L1", "created_at": "2026-08-26T10:00:00",
        }
        resp = client.get("/api/v1/tasks?model=alpha")
        assert resp.status_code == 200
        models = {t["model"] for t in resp.json()}
        assert models == {"alpha"}

    def test_cancel_running_task(self, client):
        from fusion_bench.api import app as app_module

        app_module._background_tasks["task-can"] = {
            "task_id": "task-can", "status": "running", "model": "m",
            "executor_key": "speed", "level": "L1", "created_at": "2026-08-26T10:00:00",
        }
        resp = client.post("/api/v1/tasks/task-can/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_cancel_completed_task_400(self, client):
        from fusion_bench.api import app as app_module

        app_module._background_tasks["task-done"] = {
            "task_id": "task-done", "status": "completed", "model": "m",
            "executor_key": "speed", "level": "L1", "created_at": "2026-08-26T10:00:00",
        }
        resp = client.post("/api/v1/tasks/task-done/cancel")
        assert resp.status_code == 400

    def test_cancel_missing_task_404(self, client):
        resp = client.post("/api/v1/tasks/nope/cancel")
        assert resp.status_code == 404

    def test_retry_failed_task(self, client):
        from fusion_bench.api import app as app_module

        app_module._background_tasks["task-fail"] = {
            "task_id": "task-fail", "status": "failed", "model": "m",
            "executor_key": "speed", "level": "L1", "created_at": "2026-08-26T10:00:00",
            "request": {"model": "m", "executor_key": "speed"},
        }
        resp = client.post("/api/v1/tasks/task-fail/retry")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"
        assert resp.json()["task_id"] != "task-fail"

    def test_retry_running_task_400(self, client):
        from fusion_bench.api import app as app_module

        app_module._background_tasks["task-run"] = {
            "task_id": "task-run", "status": "running", "model": "m",
            "executor_key": "speed", "level": "L1", "created_at": "2026-08-26T10:00:00",
        }
        resp = client.post("/api/v1/tasks/task-run/retry")
        assert resp.status_code == 400

    def test_task_logs(self, client):
        from fusion_bench.api import app as app_module

        app_module._background_tasks["task-log"] = {
            "task_id": "task-log", "status": "failed", "model": "m",
            "executor_key": "speed", "level": "L1", "created_at": "2026-08-26T10:00:00",
            "error": "boom",
        }
        resp = client.get("/api/v1/tasks/task-log/logs")
        assert resp.status_code == 200
        assert any("boom" in line for line in resp.json()["lines"])

    def test_task_logs_404(self, client):
        resp = client.get("/api/v1/tasks/nope/logs")
        assert resp.status_code == 404


# ── Suites ──────────────────────────────────────────────────────────


class TestSuites:
    def test_list_suites(self, client):
        resp = client.get("/api/v1/suites")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        # Default suites should be registered.
        names = {s["suite_id"] for s in resp.json()}
        assert len(names) > 0

    def test_get_suite_existing(self, client):
        suites = client.get("/api/v1/suites").json()
        sid = suites[0]["suite_id"]
        resp = client.get(f"/api/v1/suites/{sid}")
        assert resp.status_code == 200
        assert resp.json()["suite_id"] == sid

    def test_get_suite_404(self, client):
        resp = client.get("/api/v1/suites/no-such-suite")
        assert resp.status_code == 404


# ── Gates ───────────────────────────────────────────────────────────


class TestGates:
    def test_list_gates(self, client):
        resp = client.get("/api/v1/gates")
        assert resp.status_code == 200
        assert "gates" in resp.json()

    def test_create_gate(self, client):
        resp = client.post(
            "/api/v1/gates",
            json={
                "name": "my-gate",
                "tier": "experimental",
                "metric_name": "tokens_per_second",
                "operator": ">=",
                "threshold": 10.0,
                "executor_key": "speed",
                "level": "L1",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["gate"]["name"] == "my-gate"

    def test_check_gate_missing_task_404(self, client):
        resp = client.post(
            "/api/v1/gates/check", json={"task_id": "no-such-task"}
        )
        assert resp.status_code == 404

    def test_check_gate_for_seeded_task(self, client, seeded_trace):
        resp = client.post(
            "/api/v1/gates/check", json={"task_id": "task-seed-1"}
        )
        assert resp.status_code == 200
        assert "passed" in resp.json()
        assert "gates" in resp.json()

    def test_approve_gate(self, client):
        resp = client.post(
            "/api/v1/gates/some-gate/approve",
            json={"approver": "dahai", "remark": "lgtm"},
        )
        assert resp.status_code == 200
        assert resp.json()["approved"] is True


# ── Results ─────────────────────────────────────────────────────────


class TestResults:
    def test_get_result(self, client, seeded_trace):
        resp = client.get("/api/v1/results/task-seed-1")
        assert resp.status_code == 200
        assert resp.json()["metric_value"] == 42.5

    def test_get_result_404(self, client):
        resp = client.get("/api/v1/results/nope")
        assert resp.status_code == 404

    def test_export_result_json(self, client, seeded_trace):
        resp = client.post("/api/v1/results/task-seed-1/export?format=json")
        assert resp.status_code == 200
        assert resp.json()["format"] == "json"

    def test_export_result_markdown(self, client, seeded_trace):
        resp = client.post("/api/v1/results/task-seed-1/export?format=markdown")
        assert resp.status_code == 200
        assert resp.json()["format"] == "markdown"
        assert "qwen3.5-9b" in resp.json()["content"]

    def test_export_result_404(self, client):
        resp = client.post("/api/v1/results/nope/export")
        assert resp.status_code == 404

    def test_compare_results_too_few(self, client, seeded_trace):
        resp = client.post(
            "/api/v1/results/compare", json={"task_ids": ["task-seed-1"]}
        )
        assert resp.status_code == 400

    def test_compare_results_missing(self, client, seeded_trace):
        resp = client.post(
            "/api/v1/results/compare",
            json={"task_ids": ["task-seed-1", "task-seed-2"]},
        )
        # Only one found -> 400.
        assert resp.status_code == 400
