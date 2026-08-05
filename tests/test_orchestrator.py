"""Tests for orchestrator: pipeline and gate_engine."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from fusion_bench.core.models import (
    EvalLevel,
    GateTier,
    QualityGate,
    SuiteResult,
    TraceRecord,
)
from fusion_bench.core.plugin_base import (
    CaseResult,
    EvalResult,
    ExecutorPlugin,
    ExecutorType,
    TaskConfig,
)
from fusion_bench.core.registry import executor_registry
from fusion_bench.orchestrator.gate_engine import GateEngine
from fusion_bench.orchestrator.pipeline import Pipeline

# ── Fake executor for pipeline testing ──


class FakeExecutor(ExecutorPlugin):
    name = "fake"
    executor_type = ExecutorType.SPEED

    def __init__(self, result=None, should_fail=False, delay=0.0):
        self._result = result
        self._should_fail = should_fail
        self._delay = delay

    async def run(self, config: TaskConfig) -> EvalResult:
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._should_fail:
            raise RuntimeError("executor failed")
        if self._result:
            return self._result
        return EvalResult(
            task_id=config.task_id,
            executor_key=self.name,
            model=config.model,
            level="L1",
            metric_name="decode_speed",
            metric_value=25.0,
            cases=[CaseResult(input_text="test", score=25.0, passed=True)],
        )

    def is_available(self) -> bool:
        return True


class FakeSlowExecutor(ExecutorPlugin):
    name = "fake_slow"
    executor_type = ExecutorType.SPEED

    async def run(self, config: TaskConfig) -> EvalResult:
        await asyncio.sleep(10)
        return EvalResult(
            task_id=config.task_id,
            executor_key=self.name,
            model=config.model,
            level="L1",
            metric_name="decode_speed",
            metric_value=1.0,
        )

    def is_available(self) -> bool:
        return True


# ── GateEngine ──


class TestGateEngine:
    def test_load_default_gates(self):
        ge = GateEngine()
        ge.load_default_gates()
        assert len(ge._adhoc_gates) == 14

    def test_agent_intent_gates(self):
        ge = GateEngine()
        ge.load_default_gates()
        results = ge.evaluate("agent", "agent_score", 0.85)
        agent_results = [r for r in results if "agent-intent" in r.gate_id]
        assert len(agent_results) == 3
        assert all(r.passed for r in agent_results)

    def test_code_gen_gates(self):
        ge = GateEngine()
        ge.load_default_gates()
        results = ge.evaluate("code", "code_pass_rate", 0.2)
        code_results = [r for r in results if "code-gen" in r.gate_id]
        assert len(code_results) == 3
        assert not all(r.passed for r in code_results)

    def test_evaluate_matching_gate(self):
        ge = GateEngine()
        ge.load_default_gates()
        results = ge.evaluate("speed", "decode_speed", 20.0)
        assert len(results) >= 1
        speed_gates = [r for r in results if "speed" in r.gate_id]
        assert len(speed_gates) >= 1

    def test_evaluate_no_matching_gate(self):
        ge = GateEngine()
        ge.load_default_gates()
        results = ge.evaluate("speed", "nonexistent_metric", 1.0)
        assert len(results) == 0

    def test_evaluate_gate_pass(self):
        ge = GateEngine()
        ge.load_default_gates()
        results = ge.evaluate("speed", "decode_speed", 50.0)
        speed_results = [r for r in results if "speed" in r.gate_id]
        assert all(r.passed for r in speed_results)

    def test_evaluate_gate_fail(self):
        ge = GateEngine()
        ge.load_default_gates()
        results = ge.evaluate("speed", "decode_speed", 2.0)
        speed_results = [r for r in results if "speed" in r.gate_id]
        assert not all(r.passed for r in speed_results)

    def test_add_adhoc_gate(self):
        ge = GateEngine()
        custom_gate = QualityGate(
            "custom-1",
            "Custom gate",
            GateTier.EXPERIMENTAL,
            "custom_metric",
            ">=",
            10.0,
        )
        ge.add_gate(custom_gate)
        results = ge.evaluate("any", "custom_metric", 15.0)
        assert len(results) == 1
        assert results[0].passed

    def test_evaluate_with_level_filter(self):
        ge = GateEngine()
        ge.load_default_gates()
        results = ge.evaluate("speed", "decode_speed", 20.0, level=EvalLevel.L1_MODEL)
        assert len(results) >= 1

    def test_evaluate_executor_key_filter(self):
        ge = GateEngine()
        ge.load_default_gates()
        results = ge.evaluate("lm_harness", "decode_speed", 20.0)
        speed_gates = [r for r in results if "speed" in r.gate_id]
        assert len(speed_gates) == 0

    def test_evaluate_safety_gate(self):
        ge = GateEngine()
        ge.load_default_gates()
        results = ge.evaluate("security", "safety_rate", 0.9)
        safety_results = [r for r in results if "safety" in r.gate_id]
        assert len(safety_results) >= 1


# ── Pipeline ──


class TestPipeline:
    @pytest.mark.asyncio
    async def test_run_suite_success(self):
        with patch.object(executor_registry, "get_or_raise", return_value=FakeExecutor):
            pipeline = Pipeline(max_concurrent=2)
            result = await pipeline.run_suite(
                model="test-model",
                tasks=[{"executor_key": "fake", "task_id": "t1"}],
                level="L1",
            )

        assert isinstance(result, SuiteResult)
        assert result.model == "test-model"
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_run_suite_with_gates(self):
        ge = GateEngine()
        ge.load_default_gates()
        with patch.object(executor_registry, "get_or_raise", return_value=FakeExecutor):
            pipeline = Pipeline(gate_engine=ge)
            result = await pipeline.run_suite(
                model="test-model",
                tasks=[
                    {
                        "executor_key": "speed",
                        "task_id": "t1",
                        "params": {},
                    }
                ],
                level="L1",
            )

        assert isinstance(result, SuiteResult)

    @pytest.mark.asyncio
    async def test_run_suite_unknown_executor(self):
        def raise_key_error(key):
            raise KeyError(f"No executor registered for '{key}'")

        with patch.object(executor_registry, "get_or_raise", side_effect=raise_key_error):
            pipeline = Pipeline()
            result = await pipeline.run_suite(
                model="test-model",
                tasks=[{"executor_key": "nonexistent", "task_id": "t1"}],
                level="L1",
            )

        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_run_suite_executor_exception(self):
        failing = FakeExecutor(should_fail=True)
        with patch.object(executor_registry, "get_or_raise", return_value=lambda: failing):
            pipeline = Pipeline()
            result = await pipeline.run_suite(
                model="test-model",
                tasks=[{"executor_key": "fake", "task_id": "t1"}],
                level="L1",
            )

        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_run_suite_timeout(self):
        with patch.object(executor_registry, "get_or_raise", return_value=FakeSlowExecutor):
            pipeline = Pipeline()
            result = await pipeline.run_suite(
                model="test-model",
                tasks=[
                    {
                        "executor_key": "fake_slow",
                        "task_id": "t1",
                        "timeout_seconds": 1,
                    }
                ],
                level="L1",
            )

        assert len(result.results) == 1
        err_result = result.results[0]
        assert "Timeout" in str(err_result) or "timed out" in str(err_result)

    @pytest.mark.asyncio
    async def test_run_suite_trace_callback(self):
        traces = []
        with patch.object(executor_registry, "get_or_raise", return_value=FakeExecutor):
            pipeline = Pipeline(trace_callback=lambda r: traces.append(r))
            await pipeline.run_suite(
                model="test-model",
                tasks=[{"executor_key": "fake", "task_id": "t1"}],
                level="L1",
            )

        assert len(traces) == 1
        assert isinstance(traces[0], TraceRecord)

    @pytest.mark.asyncio
    async def test_run_suite_trace_callback_error(self):
        def bad_callback(r):
            raise RuntimeError("callback broken")

        with patch.object(executor_registry, "get_or_raise", return_value=FakeExecutor):
            pipeline = Pipeline(trace_callback=bad_callback)
            result = await pipeline.run_suite(
                model="test-model",
                tasks=[{"executor_key": "fake", "task_id": "t1"}],
                level="L1",
            )

        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_run_suite_multiple_tasks(self):
        with patch.object(executor_registry, "get_or_raise", return_value=FakeExecutor):
            pipeline = Pipeline(max_concurrent=2)
            result = await pipeline.run_suite(
                model="test-model",
                tasks=[
                    {"executor_key": "fake", "task_id": "t1"},
                    {"executor_key": "fake", "task_id": "t2"},
                    {"executor_key": "fake", "task_id": "t3"},
                ],
                level="L1",
            )

        assert len(result.results) == 3

    @pytest.mark.asyncio
    async def test_run_suite_suite_id_default(self):
        with patch.object(executor_registry, "get_or_raise", return_value=FakeExecutor):
            pipeline = Pipeline()
            result = await pipeline.run_suite(
                model="test-model",
                tasks=[{"executor_key": "fake", "task_id": "t1"}],
            )

        assert result.suite_id.startswith("suite-")

    @pytest.mark.asyncio
    async def test_run_suite_suite_id_custom(self):
        with patch.object(executor_registry, "get_or_raise", return_value=FakeExecutor):
            pipeline = Pipeline()
            result = await pipeline.run_suite(
                model="test-model",
                tasks=[{"executor_key": "fake", "task_id": "t1"}],
                suite_id="my-suite",
            )

        assert result.suite_id == "my-suite"

    @pytest.mark.asyncio
    async def test_trace_records_property(self):
        with patch.object(executor_registry, "get_or_raise", return_value=FakeExecutor):
            pipeline = Pipeline()
            await pipeline.run_suite(
                model="test-model",
                tasks=[{"executor_key": "fake", "task_id": "t1"}],
                level="L1",
            )

        assert len(pipeline.trace_records) == 1
        assert isinstance(pipeline.trace_records[0], TraceRecord)

    @pytest.mark.asyncio
    async def test_overall_passed_false_on_gate_fail(self):
        ge = GateEngine()
        ge.load_default_gates()
        low_speed_result = EvalResult(
            task_id="t1",
            executor_key="speed",
            model="test-model",
            level="L1",
            metric_name="decode_speed",
            metric_value=1.0,
        )
        fake = FakeExecutor(result=low_speed_result)
        with patch.object(executor_registry, "get_or_raise", return_value=lambda: fake):
            pipeline = Pipeline(gate_engine=ge)
            result = await pipeline.run_suite(
                model="test-model",
                tasks=[{"executor_key": "speed", "task_id": "t1"}],
                level="L1",
            )

        speed_gates = [g for g in result.gate_results if "speed" in g.gate_id]
        if speed_gates:
            assert not result.overall_passed

    @pytest.mark.asyncio
    async def test_run_suite_empty_tasks(self):
        pipeline = Pipeline()
        result = await pipeline.run_suite(
            model="test-model",
            tasks=[],
        )

        assert len(result.results) == 0
        assert result.overall_passed is True
