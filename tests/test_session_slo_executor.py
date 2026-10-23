"""SessionSloExecutor tests — issue #24: agent-studio long-session SLO baselines."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fusion_bench.core.plugin_base import ExecutorType, TaskConfig
from fusion_bench.executors.session_slo_executor import _SLO_METRICS, SessionSloExecutor
from fusion_bench.orchestrator.scheduler import Scheduler

_SLO_SUMMARY = {
    "sessions_completed": 12,
    "compactions_total": 5,
    "approvals_total": 30,
    "avg_approval_latency_ms": 820.5,
    "p99_approval_latency_ms": 3100.25,
    "avg_session_duration_ms": 450000.0,
    "p99_session_duration_ms": 1800000.0,
}


def _task(params=None):
    return TaskConfig(
        task_id="task-slo-1",
        model="agent-studio",
        executor_key="session_slo",
        params=params or {},
    )


class TestSessionSloExecutor:
    def test_name_and_type(self):
        e = SessionSloExecutor()
        assert e.name == "session_slo"
        assert e.executor_type == ExecutorType.SESSION_SLO

    def test_is_available(self):
        assert SessionSloExecutor().is_available() is True

    def test_default_base_url(self):
        assert SessionSloExecutor().base_url == "http://127.0.0.1:11442"

    def test_env_base_url(self, monkeypatch):
        monkeypatch.setenv("FUSION_AGENT_STUDIO_URL", "http://10.0.0.5:11442/")
        assert SessionSloExecutor().base_url == "http://10.0.0.5:11442"

    def test_registered_in_executor_registry(self):
        from fusion_bench.core.registry import executor_registry
        from fusion_bench.executors import register_all

        register_all()
        assert "session_slo" in executor_registry

    @pytest.mark.asyncio
    async def test_run_records_all_baselines(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = dict(_SLO_SUMMARY)
        with patch(
            "fusion_bench.executors.session_slo_executor.httpx.AsyncClient.post",
            new=AsyncMock(return_value=mock_resp),
        ):
            result = await SessionSloExecutor().run(_task())

        assert result.errors == []
        assert result.level == "L3"
        assert result.metric_name == "p99_approval_latency_ms"
        assert result.metric_value == pytest.approx(3100.25)
        assert result.pass_rate == 1.0
        case_metrics = {c.meta["metric"] for c in result.cases}
        assert case_metrics == set(_SLO_METRICS)
        by_metric = {c.meta["metric"]: c for c in result.cases}
        assert by_metric["sessions_completed"].score == 12.0
        assert by_metric["compactions_total"].score == 5.0
        assert by_metric["avg_session_duration_ms"].score == 450000.0
        assert result.meta["slo_summary"]["approvals_total"] == 30

    @pytest.mark.asyncio
    async def test_run_sends_rpc_method_and_auth_header(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = dict(_SLO_SUMMARY)
        post_mock = AsyncMock(return_value=mock_resp)
        with patch(
            "fusion_bench.executors.session_slo_executor.httpx.AsyncClient.post",
            new=post_mock,
        ):
            await SessionSloExecutor("http://127.0.0.1:11442").run(_task({"agent_studio_api_key": "sk-test"}))
        post_mock.assert_awaited_once()
        args, kwargs = post_mock.await_args
        assert args[0] == "http://127.0.0.1:11442/v1/rpc"
        assert kwargs["json"] == {"method": "telemetry.session_slo", "params": {}}
        assert kwargs["headers"] == {"Authorization": "Bearer sk-test"}

    @pytest.mark.asyncio
    async def test_run_param_url_overrides_default(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = dict(_SLO_SUMMARY)
        post_mock = AsyncMock(return_value=mock_resp)
        with patch(
            "fusion_bench.executors.session_slo_executor.httpx.AsyncClient.post",
            new=post_mock,
        ):
            await SessionSloExecutor().run(_task({"agent_studio_url": "http://127.0.0.1:9999"}))
        args, _ = post_mock.await_args
        assert args[0] == "http://127.0.0.1:9999/v1/rpc"

    @pytest.mark.asyncio
    async def test_run_handles_missing_keys(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"sessions_completed": 1}
        with patch(
            "fusion_bench.executors.session_slo_executor.httpx.AsyncClient.post",
            new=AsyncMock(return_value=mock_resp),
        ):
            result = await SessionSloExecutor().run(_task())
        assert result.errors == []
        assert len(result.cases) == len(_SLO_METRICS)
        by_metric = {c.meta["metric"]: c for c in result.cases}
        assert by_metric["sessions_completed"].score == 1.0
        assert by_metric["p99_approval_latency_ms"].score == 0.0
        assert result.metric_value == 0.0

    @pytest.mark.asyncio
    async def test_run_handles_non_numeric_values(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {**_SLO_SUMMARY, "approvals_total": "many"}
        with patch(
            "fusion_bench.executors.session_slo_executor.httpx.AsyncClient.post",
            new=AsyncMock(return_value=mock_resp),
        ):
            result = await SessionSloExecutor().run(_task())
        by_metric = {c.meta["metric"]: c for c in result.cases}
        assert by_metric["approvals_total"].score == 0.0

    @pytest.mark.asyncio
    async def test_run_rpc_failure_returns_errors(self):
        with patch(
            "fusion_bench.executors.session_slo_executor.httpx.AsyncClient.post",
            new=AsyncMock(side_effect=ConnectionError("refused")),
        ):
            result = await SessionSloExecutor().run(_task())
        assert len(result.errors) == 1
        assert "telemetry.session_slo RPC failed" in result.errors[0]
        assert result.cases == []
        assert result.metric_value == 0.0

    @pytest.mark.asyncio
    async def test_run_http_error_returns_errors(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock(side_effect=Exception("HTTP 401"))
        with patch(
            "fusion_bench.executors.session_slo_executor.httpx.AsyncClient.post",
            new=AsyncMock(return_value=mock_resp),
        ):
            result = await SessionSloExecutor().run(_task())
        assert len(result.errors) == 1
        assert "HTTP 401" in result.errors[0]


class TestLongSessionSuite:
    def test_suite_registered(self):
        s = Scheduler()
        s.load_default_suites()
        tasks = s.get_suite("long-session")
        assert len(tasks) == 1
        assert tasks[0].executor_key == "session_slo"
        assert tasks[0].level.value == "L3"

    def test_suite_listed(self):
        s = Scheduler()
        s.load_default_suites()
        assert "long-session" in s.list_suites()
