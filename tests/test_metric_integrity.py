"""Issue #28 — metric integrity: real TTFT, no fabricated prefill, lm-eval hard fail."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fusion_bench.engine.benchmark import BenchmarkRunner, SpeedMetrics
from fusion_bench.engine.task_runner import TASKS_DIR_HINT, LMEvalTaskRunner, TasksDirMissingError


def _sse(content_chunks, prompt_tokens, completion_tokens):
    lines = [f'data: {{"choices": [{{"delta": {{"content": "{c}"}}}}]}}' for c in content_chunks]
    lines.append(
        f'data: {{"choices": [], "usage": {{"prompt_tokens": {prompt_tokens}, "completion_tokens": {completion_tokens}}}}}'
    )
    lines.append("data: [DONE]")
    return lines


class FakeStreamResponse:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class FakeStreamCtx:
    def __init__(self, lines):
        self._lines = lines

    async def __aenter__(self):
        return FakeStreamResponse(self._lines)

    async def __aexit__(self, *exc):
        return False


def make_client(lines=None, stream_side_effect=None):
    client = MagicMock()
    if stream_side_effect is not None:
        client.stream = MagicMock(side_effect=stream_side_effect)
    else:
        client.stream = MagicMock(
            return_value=FakeStreamCtx(lines if lines is not None else _sse(["he", "llo"], 50, 100))
        )
    return client


class TestRealTTFT:
    async def test_ttft_measured_from_first_streamed_token(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11432/v1")
        runner._client = make_client(_sse(["he", "llo", " world"], 50, 100))
        metrics = await runner.run_single(model="m", prompt="hello world " * 10, max_tokens=32)
        assert metrics.ttft > 0
        assert metrics.prefill_time == metrics.ttft
        assert metrics.prefill_speed == pytest.approx(50 / max(metrics.ttft, 0.001))
        assert metrics.decode_time == pytest.approx(metrics.total_time - metrics.ttft)
        assert metrics.decode_speed == pytest.approx(100 / metrics.decode_time)

    async def test_ttft_zero_when_no_content_token(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11432/v1")
        lines = ['data: {"choices": [{"delta": {}}]}', "data: [DONE]"]
        runner._client = make_client(lines)
        metrics = await runner.run_single(model="m", prompt="hi", max_tokens=8)
        assert metrics.ttft == 0.0
        assert metrics.prefill_speed == 0.0

    async def test_to_dict_includes_ttft_ms(self):
        m = SpeedMetrics(ttft=0.123)
        d = m.to_dict()
        assert d["ttft_ms"] == 123.0
        assert "ttft_p50_ms" not in d


class TestAggregation:
    async def test_benchmark_aggregates_p50_p95(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11432/v1")
        runner._client = make_client(_sse(["a", "b"], 50, 100))
        results = await runner.benchmark(model="m", max_tokens=16, runs=3)
        avg = results[0].metrics
        assert avg.ttft_p50_ms is not None
        assert avg.ttft_p95_ms is not None
        assert avg.decode_speed_p50 is not None
        assert avg.decode_speed_p95 is not None
        d = avg.to_dict()
        assert d["ttft_p50_ms"] == avg.ttft_p50_ms
        assert d["ttft_p95_ms"] == avg.ttft_p95_ms

    async def test_single_run_no_percentiles(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11432/v1")
        runner._client = make_client(_sse(["a"], 50, 100))
        results = await runner.benchmark(model="m", max_tokens=16, runs=1)
        assert results[0].metrics.ttft_p50_ms is None

    def test_percentile_helper(self):
        vals = [1.0, 2.0, 3.0, 4.0]
        assert BenchmarkRunner._percentile(vals, 50) == 2.5
        assert BenchmarkRunner._percentile(vals, 95) == pytest.approx(3.85)
        assert BenchmarkRunner._percentile([5.0], 50) == 5.0
        assert BenchmarkRunner._percentile([], 50) == 0.0


class TestNoFabricatedPrefill:
    def test_no_hardcoded_prefill_assumption(self):
        # grep gate: the elapsed*0.3 fabrication must be gone from the engine
        src = Path("fusion_bench/engine/benchmark.py").read_text(encoding="utf-8")
        assert "elapsed * 0.3" not in src
        assert "* 0.3" not in src


class TestLMEvalHardFail:
    async def test_run_task_missing_dir_raises(self):
        runner = LMEvalTaskRunner(tasks_dir="/nonexistent/lm-eval-tasks")
        with pytest.raises(TasksDirMissingError) as exc:
            await runner.run_task("mmlu")
        assert "lm-evaluation-harness" in str(exc.value)

    async def test_run_task_no_dir_raises(self):
        runner = LMEvalTaskRunner()
        runner.tasks_dir = None
        with pytest.raises(TasksDirMissingError):
            await runner.run_task("mmlu")

    async def test_run_benchmark_missing_dir_raises(self):
        runner = LMEvalTaskRunner(tasks_dir="/nonexistent/lm-eval-tasks")
        with pytest.raises(TasksDirMissingError):
            await runner.run_benchmark(["mmlu"])

    async def test_executor_surfaces_actionable_error(self):
        from fusion_bench.core.plugin_base import TaskConfig
        from fusion_bench.executors.lm_harness_executor import LMHarnessExecutor

        executor = LMHarnessExecutor(tasks_dir="/nonexistent/lm-eval-tasks")
        config = TaskConfig(task_id="mmlu", model="m", executor_key="lm_harness")
        result = await executor.run(config)
        assert result.errors
        assert "lm-evaluation-harness" in result.errors[0]

    def test_hint_mentions_clone_and_skip(self):
        assert "clone" in TASKS_DIR_HINT.lower()
        assert "skip" in TASKS_DIR_HINT.lower()
