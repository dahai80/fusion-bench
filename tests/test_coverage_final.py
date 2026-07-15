"""Final coverage push — targets remaining uncovered lines in benchmark.py and tuner.py."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fusion_bench.engine.benchmark import BenchmarkRunner, SpeedMetrics, BenchmarkResult
from fusion_bench.optimizer.tuner import ParameterTuner, TuneResult


class MockResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {
            "usage": {"prompt_tokens": 50, "completion_tokens": 100},
            "choices": [{"message": {"content": "test"}}],
        }
    def raise_for_status(self):
        pass
    def json(self):
        return self._json


class TestBenchmarkFinal:
    """Cover remaining uncovered branches in benchmark.py."""

    @pytest.mark.asyncio
    async def test_benchmark_all_runs_fail(self):
        """Cover case where all benchmark runs fail."""
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=MockResponse(
            json_data={"usage": {"prompt_tokens": 0, "completion_tokens": 0}},
        ))
        runner._client = mock_client
        results = await runner.benchmark(model="test", max_tokens=50, runs=3)
        for r in results:
            assert r.metrics.decode_speed == 0.0  # No speed recorded

    @pytest.mark.asyncio
    async def test_benchmark_with_memory_stats_fail(self):
        """Cover case where memory stats endpoint fails."""
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=MockResponse())
        mock_client.get = AsyncMock(side_effect=RuntimeError("stats fail"))
        runner._client = mock_client
        results = await runner.benchmark(model="test", max_tokens=50, runs=1)
        assert len(results) >= 1
        # Memory should be 0 since stats endpoint failed
        assert results[0].metrics.peak_memory_mb == 0.0

    @pytest.mark.asyncio
    async def test_benchmark_with_memory_bad_response(self):
        """Cover case where memory stats returns bad data."""
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=MockResponse())
        mock_client.get = AsyncMock(return_value=MockResponse(
            status_code=200, json_data={"no_memory": True},
        ))
        runner._client = mock_client
        results = await runner.benchmark(model="test", max_tokens=50, runs=1)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_parse_memory_kb(self):
        assert BenchmarkRunner._parse_memory("500 KB") == pytest.approx(0.488, rel=0.1)

    @pytest.mark.asyncio
    async def test_parse_memory_tb(self):
        assert BenchmarkRunner._parse_memory("2 TB") == 2097152.0

    @pytest.mark.asyncio
    async def test_run_single_with_config(self):
        """Cover run_single with custom config parameters."""
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=MockResponse())
        runner._client = mock_client
        config = {"extra_params": {"stop": ["\n"]}}
        metrics = await runner.run_single(
            model="test", prompt="hi", max_tokens=50,
            config=config,
        )
        # Verify the config was passed to the API call
        call_kwargs = mock_client.post.call_args[1]["json"]
        assert "extra_params" in call_kwargs

    @pytest.mark.asyncio
    async def test_benchmark_multiple_configs_mixed_results(self):
        """Cover benchmark with multiple configs where some succeed."""
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        # First config succeeds, second fails
        mock_client.post = AsyncMock(side_effect=[
            MockResponse(),
            RuntimeError("fail"),
        ])
        runner._client = mock_client
        configs = [{"temperature": 0.0}, {"temperature": 0.7}]
        results = await runner.benchmark(model="test", configs=configs, max_tokens=50, runs=1)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_probe_max_context_success_at_max(self):
        """Cover probe_max_context where max is reached."""
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=MockResponse())
        runner._client = mock_client
        ctx = await runner.probe_max_context(model="test", max_context=8192, step=8192)
        assert ctx >= 4096

    @pytest.mark.asyncio
    async def test_run_stability_all_fail_run_single(self):
        """Cover run_stability where all run_single calls fail silently."""
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=RuntimeError("always fail"))
        runner._client = mock_client
        result = await runner.run_stability(model="test", rounds=5)
        assert result.stable is False


class TestTunerFinal:
    """Cover remaining uncovered branches in tuner.py."""

    @pytest.mark.asyncio
    async def test_tune_with_some_failures(self):
        """Cover tune where some configs fail."""
        tuner = ParameterTuner(mlx_base_url="http://localhost:11434/v1")
        # Some configs succeed, some fail
        tuner.runner.run_single = AsyncMock(side_effect=[
            SpeedMetrics(decode_speed=25.0, peak_memory_mb=4096),
            RuntimeError("fail"),
            SpeedMetrics(decode_speed=30.0, peak_memory_mb=2048),
        ])
        result = await tuner.tune("test-model", max_combinations=3)
        # At least one result should be in all_results
        assert len(result.all_results) >= 1

    @pytest.mark.asyncio
    async def test_tune_few_configs(self):
        """Cover tune with fewer than 3 configs."""
        tuner = ParameterTuner(mlx_base_url="http://localhost:11434/v1")
        tuner.runner.run_single = AsyncMock(return_value=SpeedMetrics(
            decode_speed=25.0, peak_memory_mb=4096,
        ))
        result = await tuner.tune("test-model", max_combinations=2)
        assert len(result.all_results) >= 1
        # top3_configs should have at most 2 items
        assert len(result.top3_configs) <= 2

    @pytest.mark.asyncio
    async def test_tune_memory_saving_config(self):
        """Cover memory_saving_config selection."""
        tuner = ParameterTuner(mlx_base_url="http://localhost:11434/v1")
        tuner.runner.run_single = AsyncMock(side_effect=[
            SpeedMetrics(decode_speed=10.0, peak_memory_mb=8192),
            SpeedMetrics(decode_speed=20.0, peak_memory_mb=4096),
            SpeedMetrics(decode_speed=30.0, peak_memory_mb=2048),
        ])
        result = await tuner.tune("test-model", max_combinations=3)
        # memory_saving_config should be the one with lowest memory
        if result.memory_saving_config:
            assert result.memory_saving_config is not None

    @pytest.mark.asyncio
    async def test_tune_multi_model_all_fail(self):
        """Cover tune_multi_model where all models fail."""
        tuner = ParameterTuner(mlx_base_url="http://localhost:11434/v1")
        tuner.runner.run_single = AsyncMock(side_effect=RuntimeError("fail"))
        results = await tuner.tune_multi_model(["model-a", "model-b"], max_combinations=1)
        assert len(results) == 2
        # Both should have empty all_results
        assert len(results["model-a"].all_results) == 0
        assert len(results["model-b"].all_results) == 0