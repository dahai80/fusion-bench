"""Tests for executor plugins: speed, lm_harness, tune, quant, security."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fusion_bench.core.plugin_base import ExecutorType, TaskConfig
from fusion_bench.executors.lm_harness_executor import LMHarnessExecutor
from fusion_bench.executors.quant_executor import QuantExecutor
from fusion_bench.executors.security_executor import (
    BUILTIN_PROBES,
    SecurityExecutor,
)
from fusion_bench.executors.speed_executor import SpeedExecutor
from fusion_bench.executors.tune_executor import TuneExecutor


class MockHTTPResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {
            "choices": [{"message": {"content": "I cannot help with that."}}],
        }

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self):
        return self._json


def _make_speed_metrics(decode_speed=25.0, total_time=1.0):
    from fusion_bench.engine.benchmark import SpeedMetrics

    return SpeedMetrics(
        prefill_tokens=50,
        decode_tokens=100,
        prefill_time=0.1,
        decode_time=0.9,
        prefill_speed=500.0,
        decode_speed=decode_speed,
        total_time=total_time,
        peak_memory_mb=2048.0,
    )


# ── SecurityExecutor ──


class TestSecurityExecutor:
    def test_name_and_type(self):
        e = SecurityExecutor()
        assert e.name == "security"
        assert e.executor_type == ExecutorType.SECURITY

    def test_is_available(self):
        e = SecurityExecutor()
        assert e.is_available() is True

    def test_builtin_probes_structure(self):
        for key in ("injection", "harmful", "pii"):
            assert key in BUILTIN_PROBES
            assert len(BUILTIN_PROBES[key]) >= 2
            for probe in BUILTIN_PROBES[key]:
                assert "prompt" in probe
                assert "expected_safe" in probe

    def test_is_safe_response_refusal(self):
        assert SecurityExecutor._is_safe_response("I cannot help with that.", "refusal")
        assert SecurityExecutor._is_safe_response("I can't assist with this.", "refusal")
        assert SecurityExecutor._is_safe_response("I must decline.", "refusal")

    def test_is_safe_response_unsafe(self):
        assert not SecurityExecutor._is_safe_response("Sure, here are the steps to hack:", "refusal")
        assert not SecurityExecutor._is_safe_response("Yes, I will help you with that.", "refusal")

    def test_is_safe_response_empty(self):
        assert SecurityExecutor._is_safe_response("", "refusal")

    def test_is_safe_response_short_generic(self):
        assert SecurityExecutor._is_safe_response("No.", "refusal")
        assert SecurityExecutor._is_safe_response("Error.", "refusal")

    def test_is_safe_response_non_refusal_behavior(self):
        assert SecurityExecutor._is_safe_response("anything", "other")

    @pytest.mark.asyncio
    async def test_run_success(self):
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=MockHTTPResponse())

        config = TaskConfig(
            task_id="sec-1",
            model="test-model",
            executor_key="security",
            params={"probe_set": "injection"},
        )

        with patch(
            "fusion_bench.executors.security_executor.httpx.AsyncClient",
            return_value=mock_client,
        ):
            executor = SecurityExecutor()
            result = await executor.run(config)

        assert result.executor_key == "security"
        assert result.metric_name == "safety_rate"
        assert result.metric_value == 1.0
        assert len(result.cases) == 3
        assert all(c.passed for c in result.cases)

    @pytest.mark.asyncio
    async def test_run_mixed_safety(self):
        safe_resp = MockHTTPResponse(
            json_data={
                "choices": [{"message": {"content": "I cannot help."}}],
            }
        )
        unsafe_resp = MockHTTPResponse(
            json_data={
                "choices": [{"message": {"content": "Sure, here is the info:"}}],
            }
        )
        responses = [safe_resp, unsafe_resp, safe_resp]
        call_idx = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_idx
            r = responses[call_idx]
            call_idx += 1
            return r

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = mock_post

        config = TaskConfig(
            task_id="sec-2",
            model="test-model",
            executor_key="security",
            params={"probe_set": "injection"},
        )

        with patch(
            "fusion_bench.executors.security_executor.httpx.AsyncClient",
            return_value=mock_client,
        ):
            executor = SecurityExecutor()
            result = await executor.run(config)

        assert result.metric_value == pytest.approx(2.0 / 3.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_run_http_error(self):
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=MockHTTPResponse(status_code=500))

        config = TaskConfig(
            task_id="sec-3",
            model="test-model",
            executor_key="security",
            params={"probe_set": "harmful"},
        )

        with patch(
            "fusion_bench.executors.security_executor.httpx.AsyncClient",
            return_value=mock_client,
        ):
            executor = SecurityExecutor()
            result = await executor.run(config)

        assert len(result.errors) == 2
        assert result.metric_value == 0.0

    @pytest.mark.asyncio
    async def test_run_unknown_probe_set_falls_back(self):
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=MockHTTPResponse())

        config = TaskConfig(
            task_id="sec-4",
            model="test-model",
            executor_key="security",
            params={"probe_set": "nonexistent"},
        )

        with patch(
            "fusion_bench.executors.security_executor.httpx.AsyncClient",
            return_value=mock_client,
        ):
            executor = SecurityExecutor()
            result = await executor.run(config)

        assert len(result.cases) == 3

    @pytest.mark.asyncio
    async def test_run_pii_probe_set(self):
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=MockHTTPResponse())

        config = TaskConfig(
            task_id="sec-5",
            model="test-model",
            executor_key="security",
            params={"probe_set": "pii"},
        )

        with patch(
            "fusion_bench.executors.security_executor.httpx.AsyncClient",
            return_value=mock_client,
        ):
            executor = SecurityExecutor()
            result = await executor.run(config)

        assert len(result.cases) == 2
        assert result.meta["probe_set"] == "pii"


# ── SpeedExecutor ──


class TestSpeedExecutor:
    def test_name_and_type(self):
        e = SpeedExecutor()
        assert e.name == "speed"
        assert e.executor_type == ExecutorType.SPEED

    def test_is_available(self):
        assert SpeedExecutor().is_available() is True

    @pytest.mark.asyncio
    async def test_run_success(self):
        mock_runner = MagicMock()
        mock_runner.run_single = AsyncMock(return_value=_make_speed_metrics(30.0))
        mock_runner.close = AsyncMock()

        config = TaskConfig(
            task_id="spd-1",
            model="test-model",
            executor_key="speed",
            params={"runs": 2},
        )

        with patch(
            "fusion_bench.executors.speed_executor.BenchmarkRunner",
            return_value=mock_runner,
        ):
            executor = SpeedExecutor()
            result = await executor.run(config)

        assert result.executor_key == "speed"
        assert result.metric_name == "decode_speed"
        assert result.metric_value == 30.0
        assert len(result.cases) == 2
        assert all(c.passed for c in result.cases)

    @pytest.mark.asyncio
    async def test_run_with_errors(self):
        mock_runner = MagicMock()
        mock_runner.run_single = AsyncMock(side_effect=Exception("conn refused"))
        mock_runner.close = AsyncMock()

        config = TaskConfig(
            task_id="spd-2",
            model="test-model",
            executor_key="speed",
            params={"runs": 1},
        )

        with patch(
            "fusion_bench.executors.speed_executor.BenchmarkRunner",
            return_value=mock_runner,
        ):
            executor = SpeedExecutor()
            result = await executor.run(config)

        assert len(result.errors) == 1
        assert result.metric_value == 0.0
        assert len(result.cases) == 0

    @pytest.mark.asyncio
    async def test_run_custom_params(self):
        mock_runner = MagicMock()
        mock_runner.run_single = AsyncMock(return_value=_make_speed_metrics(50.0))
        mock_runner.close = AsyncMock()

        config = TaskConfig(
            task_id="spd-3",
            model="test-model",
            executor_key="speed",
            params={"prompt": "test", "max_tokens": 64, "temperature": 0.5, "runs": 1},
        )

        with patch(
            "fusion_bench.executors.speed_executor.BenchmarkRunner",
            return_value=mock_runner,
        ):
            executor = SpeedExecutor()
            result = await executor.run(config)

        assert result.metric_value == 50.0


# ── LMHarnessExecutor ──


class TestLMHarnessExecutor:
    def test_name_and_type(self):
        e = LMHarnessExecutor()
        assert e.name == "lm_harness"
        assert e.executor_type == ExecutorType.MODEL

    def test_is_available_with_yaml(self):
        e = LMHarnessExecutor()
        assert e.is_available() is True

    def test_is_available_without_yaml(self):
        e = LMHarnessExecutor()
        with patch(
            "fusion_bench.executors.lm_harness_executor.LMHarnessExecutor.is_available",
            return_value=False,
        ):
            assert e.is_available() is False

    @pytest.mark.asyncio
    async def test_run_success(self):
        mock_runner = MagicMock()
        mock_runner.run_task = AsyncMock(
            return_value={
                "metrics": {"accuracy": 0.65},
                "results": [
                    {"prompt": "Q1", "target": "A", "prediction": "A", "correct": True},
                    {
                        "prompt": "Q2",
                        "target": "B",
                        "prediction": "C",
                        "correct": False,
                    },
                ],
            }
        )

        config = TaskConfig(
            task_id="lm-1",
            model="test-model",
            executor_key="lm_harness",
            dataset="mmlu",
        )

        with patch(
            "fusion_bench.executors.lm_harness_executor.LMEvalTaskRunner",
            return_value=mock_runner,
        ):
            executor = LMHarnessExecutor()
            result = await executor.run(config)

        assert result.executor_key == "lm_harness"
        assert result.metric_name == "accuracy"
        assert result.metric_value == 0.65
        assert len(result.cases) == 2

    @pytest.mark.asyncio
    async def test_run_with_error(self):
        mock_runner = MagicMock()
        mock_runner.run_task = AsyncMock(
            return_value={
                "error": "Task not found",
            }
        )

        config = TaskConfig(
            task_id="lm-2",
            model="test-model",
            executor_key="lm_harness",
            dataset="nonexistent",
        )

        with patch(
            "fusion_bench.executors.lm_harness_executor.LMEvalTaskRunner",
            return_value=mock_runner,
        ):
            executor = LMHarnessExecutor()
            result = await executor.run(config)

        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_run_exception(self):
        mock_runner = MagicMock()
        mock_runner.run_task = AsyncMock(side_effect=RuntimeError("conn error"))

        config = TaskConfig(
            task_id="lm-3",
            model="test-model",
            executor_key="lm_harness",
        )

        with patch(
            "fusion_bench.executors.lm_harness_executor.LMEvalTaskRunner",
            return_value=mock_runner,
        ):
            executor = LMHarnessExecutor()
            result = await executor.run(config)

        assert result.metric_value == 0.0
        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_run_empty_results(self):
        mock_runner = MagicMock()
        mock_runner.run_task = AsyncMock(
            return_value={
                "metrics": {"accuracy": 0.0},
                "results": [],
            }
        )

        config = TaskConfig(
            task_id="lm-4",
            model="test-model",
            executor_key="lm_harness",
        )

        with patch(
            "fusion_bench.executors.lm_harness_executor.LMEvalTaskRunner",
            return_value=mock_runner,
        ):
            executor = LMHarnessExecutor()
            result = await executor.run(config)

        assert result.metric_value == 0.0
        assert len(result.cases) == 0


# ── TuneExecutor ──


class TestTuneExecutor:
    def test_name_and_type(self):
        e = TuneExecutor()
        assert e.name == "tune"
        assert e.executor_type == ExecutorType.SPEED

    def test_is_available(self):
        assert TuneExecutor().is_available() is True

    @pytest.mark.asyncio
    async def test_run_success(self):
        from fusion_bench.engine.benchmark import SpeedMetrics

        m1 = SpeedMetrics(
            prefill_tokens=50,
            decode_tokens=100,
            prefill_time=0.1,
            decode_time=0.9,
            prefill_speed=500.0,
            decode_speed=20.0,
            total_time=1.0,
            peak_memory_mb=2048.0,
        )
        m2 = SpeedMetrics(
            prefill_tokens=50,
            decode_tokens=100,
            prefill_time=0.1,
            decode_time=0.5,
            prefill_speed=500.0,
            decode_speed=35.0,
            total_time=0.6,
            peak_memory_mb=2048.0,
        )

        br1 = MagicMock(metrics=m1, config={"batch_size": 1})
        br2 = MagicMock(metrics=m2, config={"batch_size": 4})

        mock_tune_result = MagicMock(
            best_speed=35.0,
            best_config={"batch_size": 4},
            all_results=[br1, br2],
            top3_configs=[{"batch_size": 4}],
            memory_saving_config={"batch_size": 1},
            balanced_config={"batch_size": 2},
        )

        mock_tuner = MagicMock()
        mock_tuner.tune = AsyncMock(return_value=mock_tune_result)

        config = TaskConfig(
            task_id="tune-1",
            model="test-model",
            executor_key="tune",
        )

        with patch(
            "fusion_bench.executors.tune_executor.ParameterTuner",
            return_value=mock_tuner,
        ):
            executor = TuneExecutor()
            result = await executor.run(config)

        assert result.executor_key == "tune"
        assert result.metric_name == "best_decode_speed"
        assert result.metric_value == 35.0
        assert len(result.cases) == 2

    @pytest.mark.asyncio
    async def test_run_exception(self):
        mock_tuner = MagicMock()
        mock_tuner.tune = AsyncMock(side_effect=RuntimeError("failed"))

        config = TaskConfig(
            task_id="tune-2",
            model="test-model",
            executor_key="tune",
        )

        with patch(
            "fusion_bench.executors.tune_executor.ParameterTuner",
            return_value=mock_tuner,
        ):
            executor = TuneExecutor()
            result = await executor.run(config)

        assert result.metric_value == 0.0
        assert len(result.errors) == 1


# ── QuantExecutor ──


class TestQuantExecutor:
    def test_name_and_type(self):
        e = QuantExecutor()
        assert e.name == "quant"
        assert e.executor_type == ExecutorType.QUANT

    def test_is_available(self):
        assert QuantExecutor().is_available() is True

    @pytest.mark.asyncio
    async def test_run_success(self):
        from fusion_bench.optimizer.quant_bench import QuantResult

        qr1 = QuantResult(quant="q4", speed=15.0, memory_mb=2048.0, stable=True)
        qr2 = QuantResult(quant="q8", speed=25.0, memory_mb=4096.0, stable=True)

        mock_qb = MagicMock()
        mock_qb.run_speed_comparison = AsyncMock(return_value=[qr1, qr2])

        config = TaskConfig(
            task_id="quant-1",
            model="test-model-q4",
            executor_key="quant",
        )

        with patch("fusion_bench.executors.quant_executor.QuantBenchmark", return_value=mock_qb):
            executor = QuantExecutor()
            result = await executor.run(config)

        assert result.executor_key == "quant"
        assert result.metric_name == "best_quant_speed"
        assert result.metric_value == 25.0
        assert len(result.cases) == 2

    @pytest.mark.asyncio
    async def test_run_exception(self):
        mock_qb = MagicMock()
        mock_qb.run_speed_comparison = AsyncMock(side_effect=RuntimeError("no models"))

        config = TaskConfig(
            task_id="quant-2",
            model="test-model",
            executor_key="quant",
        )

        with patch("fusion_bench.executors.quant_executor.QuantBenchmark", return_value=mock_qb):
            executor = QuantExecutor()
            result = await executor.run(config)

        assert result.metric_value == 0.0
        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_run_unstable_quant(self):
        from fusion_bench.optimizer.quant_bench import QuantResult

        qr1 = QuantResult(quant="q2", speed=0.0, memory_mb=1024.0, stable=False)
        qr2 = QuantResult(quant="q4", speed=10.0, memory_mb=2048.0, stable=True)

        mock_qb = MagicMock()
        mock_qb.run_speed_comparison = AsyncMock(return_value=[qr1, qr2])

        config = TaskConfig(
            task_id="quant-3",
            model="test-model",
            executor_key="quant",
        )

        with patch("fusion_bench.executors.quant_executor.QuantBenchmark", return_value=mock_qb):
            executor = QuantExecutor()
            result = await executor.run(config)

        assert not result.cases[0].passed
        assert result.cases[1].passed


# ── AgentExecutor ──


class TestAgentExecutor:
    def test_name_and_type(self):
        from fusion_bench.executors.agent_executor import AgentExecutor

        e = AgentExecutor()
        assert e.name == "agent"
        assert e.executor_type == ExecutorType.AGENT

    def test_safe_arith(self):
        from fusion_bench.executors.agent_executor import _safe_arith

        assert _safe_arith("15 * 7") == 105
        assert _safe_arith("105 - 10") == 95
        assert _safe_arith("9 * 8") == 72
        assert _safe_arith("-(2+3)") == -5
        assert _safe_arith("100 / 4") == 25

    def test_safe_arith_rejects_bad_input(self):
        from fusion_bench.executors.agent_executor import _safe_arith

        with pytest.raises(ValueError):
            _safe_arith("__import__('os')")
        with pytest.raises(ValueError):
            _safe_arith("abc")
        with pytest.raises(ZeroDivisionError):
            _safe_arith("1 / 0")

    def test_tool_sandbox_allowed(self):
        from fusion_bench.executors.agent_executor import ToolSandbox

        sb = ToolSandbox(["calculator", "weather"])
        assert sb.execute("calculator", {"expr": "2 + 3"}) == {"result": 5.0}
        assert sb.execute("weather", {"city": "Tokyo"})["temp_c"] == 20

    def test_tool_sandbox_rejects_unknown(self):
        from fusion_bench.executors.agent_executor import ToolSandbox

        sb = ToolSandbox(["search"])
        result = sb.execute("rm", {"path": "/"})
        assert "error" in result

    def test_tool_sandbox_rejects_calc_injection(self):
        from fusion_bench.executors.agent_executor import ToolSandbox

        sb = ToolSandbox(["calculator"])
        result = sb.execute("calculator", {"expr": "__import__('os')"})
        assert result == {"error": "invalid expression"}

    def test_trajectory_scorer_full(self):
        from fusion_bench.executors.agent_executor import (
            AgentScenario,
            TrajectoryScorer,
            TurnRecord,
        )

        turns = [
            TurnRecord(0, "assistant", "let me calculate", {"name": "calculator", "args": {}}),
            TurnRecord(1, "assistant", "actually, correction: the answer is 95"),
        ]
        scenario = AgentScenario(
            scenario_id="s",
            instruction="i",
            expected_behavior="e",
            tools_available=["calculator"],
            expected_tool_calls=["calculator"],
            expected_final_answer="95",
        )
        sc = TrajectoryScorer.score(turns, scenario)
        assert sc["tool_correct"] == 1
        assert sc["expected_coverage"] == 1.0
        assert sc["self_corrections"] == 1
        assert sc["answer_correct"] is True
        assert sc["trajectory_score"] == 1.0

    def test_trajectory_scorer_no_tools(self):
        from fusion_bench.executors.agent_executor import (
            AgentScenario,
            TrajectoryScorer,
            TurnRecord,
        )

        turns = [TurnRecord(0, "assistant", "red, green, blue")]
        scenario = AgentScenario(
            scenario_id="s",
            instruction="i",
            expected_behavior="e",
            tools_available=[],
            expected_tool_calls=[],
        )
        sc = TrajectoryScorer.score(turns, scenario)
        assert sc["tool_total"] == 0
        assert sc["expected_coverage"] == 1.0

    def test_default_scenarios_count(self):
        from fusion_bench.executors.agent_executor import AgentExecutor

        scenarios = AgentExecutor._default_scenarios()
        assert len(scenarios) >= 5
        ids = {s.scenario_id for s in scenarios}
        assert "agent-multi-step" in ids
        assert "agent-self-correction" in ids
        assert "agent-file-read" in ids

    def test_parse_tool_call(self):
        from fusion_bench.executors.agent_executor import AgentExecutor

        resp = 'I will search.\n```json\n{"name": "search", "args": {"q": "tokyo"}}\n```'
        tc = AgentExecutor._parse_tool_call(resp)
        assert tc == {"name": "search", "args": {"q": "tokyo"}}

    def test_parse_tool_call_none(self):
        from fusion_bench.executors.agent_executor import AgentExecutor

        assert AgentExecutor._parse_tool_call("no tool call here") is None

    def test_parse_tool_call_arguments_alias(self):
        from fusion_bench.executors.agent_executor import AgentExecutor

        resp = '```json\n{"name": "calc", "arguments": {"expr": "1+1"}}\n```'
        tc = AgentExecutor._parse_tool_call(resp)
        assert tc["args"] == {"expr": "1+1"}

    @pytest.mark.asyncio
    async def test_run_multi_turn_with_tool(self):
        from fusion_bench.executors.agent_executor import AgentExecutor

        responses = iter(
            [
                '```json\n{"name": "calculator", "args": {"expr": "15 * 7"}}\n```',
                "The result is 105, then 105 - 10 = 95. Final: 95",
            ]
        )
        mock_resp = MockHTTPResponse()

        async def fake_post(*args, **kwargs):
            mock_resp._json = {"choices": [{"message": {"content": next(responses)}}]}
            return mock_resp

        with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=fake_post)):
            executor = AgentExecutor(base_url="http://localhost:11432/v1")
            scenario = AgentExecutor._default_scenarios()[2]
            turns = await executor._run_multi_turn(
                scenario,
                TaskConfig(task_id="t", model="m", executor_key="agent"),
            )
        assert len(turns) == 2
        assert turns[0].tool_call["name"] == "calculator"
        assert turns[0].tool_result == {"result": 105.0}

    @pytest.mark.asyncio
    async def test_run_no_scenarios(self):
        from fusion_bench.executors.agent_executor import AgentExecutor

        config = TaskConfig(
            task_id="agent-empty",
            model="test-model",
            executor_key="agent",
            params={"scenarios": []},
        )
        executor = AgentExecutor(base_url="http://localhost:11432/v1")
        with patch.object(executor, "_default_scenarios", return_value=[]):
            result = await executor.run(config)
        assert result.metric_value == 0.0
        assert len(result.errors) == 1
        assert result.executor_key == "agent"
        assert result.level == "L2"

    @pytest.mark.asyncio
    async def test_run_success(self):
        from fusion_bench.executors.agent_executor import AgentExecutor

        config = TaskConfig(
            task_id="agent-1",
            model="test-model",
            executor_key="agent",
            params={
                "scenarios": [
                    {
                        "scenario_id": "s1",
                        "instruction": "say hello",
                        "expected_behavior": "greets",
                        "eval_criteria": ["contains_3_items"],
                        "max_turns": 1,
                    }
                ]
            },
        )

        mock_resp = MockHTTPResponse(json_data={"choices": [{"message": {"content": "- a\n- b\n- c"}}]})
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
            executor = AgentExecutor(base_url="http://localhost:11432/v1")
            result = await executor.run(config)

        assert result.executor_key == "agent"
        assert result.metric_name == "agent_score"
        assert len(result.cases) == 1
        assert "scenarios_total" in result.meta

    @pytest.mark.asyncio
    async def test_run_exception(self):
        from fusion_bench.executors.agent_executor import AgentExecutor

        config = TaskConfig(
            task_id="agent-err",
            model="test-model",
            executor_key="agent",
        )
        with patch(
            "httpx.AsyncClient.post",
            new=AsyncMock(side_effect=RuntimeError("connection refused")),
        ):
            executor = AgentExecutor(base_url="http://localhost:11432/v1")
            result = await executor.run(config)

        assert result.metric_value == 0.0
        assert all(not c.passed for c in result.cases)


class TestCodeExecutor:
    def test_name_and_type(self):
        from fusion_bench.executors.code_executor import CodeExecutor

        e = CodeExecutor()
        assert e.name == "code"
        assert e.executor_type == ExecutorType.CODE

    def test_default_test_cases(self):
        from fusion_bench.executors.code_executor import CodeExecutor

        cases = CodeExecutor._default_test_cases()
        assert len(cases) == 3
        assert all(tc.test_id for tc in cases)

    def test_eval_code_output_pass(self):
        from fusion_bench.executors.code_executor import CodeExecutor, CodeTestCase

        tc = CodeTestCase(
            test_id="t1",
            prompt="p",
            expected_patterns=[r"def\s+foo", r"return"],
            forbidden_patterns=[r"exec\s*\("],
        )
        result = CodeExecutor._eval_code_output(tc, "def foo():\n    return 1")
        assert result["passed"] is True
        assert result["score"] == 1.0

    def test_eval_code_output_forbidden(self):
        from fusion_bench.executors.code_executor import CodeExecutor, CodeTestCase

        tc = CodeTestCase(
            test_id="t1",
            prompt="p",
            expected_patterns=[r"def\s+foo"],
            forbidden_patterns=[r"exec\s*\("],
        )
        result = CodeExecutor._eval_code_output(tc, "def foo():\n    exec('x')")
        assert result["passed"] is False

    @pytest.mark.asyncio
    async def test_run_no_test_cases(self):
        from fusion_bench.executors.code_executor import CodeExecutor

        config = TaskConfig(
            task_id="code-empty",
            model="test-model",
            executor_key="code",
            params={"test_cases": []},
        )
        executor = CodeExecutor(base_url="http://localhost:11432/v1")
        with patch.object(executor, "_load_test_cases", return_value=[]):
            result = await executor.run(config)

        assert result.executor_key == "code"
        assert result.metric_name == "code_pass_rate"
        assert result.metric_value == 0.0
        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_run_success(self):
        from fusion_bench.executors.code_executor import CodeExecutor

        config = TaskConfig(
            task_id="code-1",
            model="test-model",
            executor_key="code",
            params={
                "test_cases": [
                    {
                        "test_id": "c1",
                        "prompt": "write sort",
                        "language": "python",
                        "expected_patterns": [r"def\s+\w+\s*\(", r"sort", r"return"],
                        "forbidden_patterns": [r"exec\s*\("],
                    }
                ]
            },
        )
        mock_resp = MockHTTPResponse(
            json_data={
                "choices": [{"message": {"content": "```python\ndef sort_fn(lst):\n    return sorted(lst)\n```"}}]
            }
        )
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
            executor = CodeExecutor(base_url="http://localhost:11432/v1")
            result = await executor.run(config)

        assert result.executor_key == "code"
        assert result.metric_name == "code_pass_rate"
        assert result.metric_value == 1.0
        assert len(result.cases) == 1
        assert "test_cases_total" in result.meta
