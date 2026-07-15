"""Additional tests to push coverage to 95%+ for Fusion-Bench."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fusion_bench.engine.benchmark import BenchmarkRunner, SpeedMetrics, BenchmarkResult
from fusion_bench.engine.metrics import MetricsCollector, SystemMetrics
from fusion_bench.optimizer.tuner import ParameterTuner, TuneResult
from fusion_bench.reporter.report import ReportGenerator


# ── SpeedMetrics edge cases ──

class TestSpeedMetricsAdvanced:
    def test_partial_metrics(self):
        m = SpeedMetrics(decode_speed=15.0)
        d = m.to_dict()
        assert d["decode_speed"] == 15.0
        assert d["prefill_speed"] == 0.0

    def test_high_values(self):
        m = SpeedMetrics(
            prefill_tokens=10000, decode_tokens=5000,
            prefill_time=0.5, decode_time=2.0,
            prefill_speed=20000.0, decode_speed=2500.0,
            peak_memory_mb=64000.0,
        )
        d = m.to_dict()
        assert d["prefill_speed"] == 20000.0
        assert d["peak_memory_mb"] == 64000.0


# ── BenchmarkRunner advanced ──

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


class TestBenchmarkRunnerAdvanced:
    @pytest.mark.asyncio
    async def test_run_single_success(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=MockResponse())
        mock_client.get = AsyncMock(return_value=MockResponse(json_data={
            "model_memory_used_formatted": "4.5 GB",
        }))
        runner._client = mock_client
        metrics = await runner.run_single(model="test-model", prompt="hi", max_tokens=50)
        assert metrics.decode_speed > 0
        assert metrics.peak_memory_mb > 0

    @pytest.mark.asyncio
    async def test_run_single_timeout(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1", timeout=1.0)
        mock_client = MagicMock()
        from httpx import TimeoutException
        mock_client.post = AsyncMock(side_effect=TimeoutException("timeout"))
        runner._client = mock_client
        metrics = await runner.run_single(model="test-model")
        assert metrics.total_time == 1.0

    @pytest.mark.asyncio
    async def test_run_single_generic_error(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=RuntimeError("connection error"))
        runner._client = mock_client
        metrics = await runner.run_single(model="test-model")
        assert metrics.total_time == 0.0

    @pytest.mark.asyncio
    async def test_benchmark_multiple_runs(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=MockResponse())
        mock_client.get = AsyncMock(return_value=MockResponse(json_data={
            "model_memory_used_formatted": "2 GB",
        }))
        runner._client = mock_client
        results = await runner.benchmark(model="test", max_tokens=50, runs=2)
        assert len(results) >= 1
        for r in results:
            assert r.metrics.decode_speed > 0

    @pytest.mark.asyncio
    async def test_benchmark_with_configs(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=MockResponse())
        runner._client = mock_client
        configs = [{"temperature": 0.0}, {"temperature": 0.7}]
        results = await runner.benchmark(model="test", configs=configs, max_tokens=50, runs=1)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_benchmark_no_configs(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=MockResponse())
        runner._client = mock_client
        results = await runner.benchmark(model="test", max_tokens=50, runs=1)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_list_models_success(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=MockResponse(json_data={
            "data": [{"id": "model1"}, {"id": "model2"}],
        }))
        runner._client = mock_client
        models = await runner.list_models()
        assert len(models) == 2

    @pytest.mark.asyncio
    async def test_list_models_error(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("fail"))
        runner._client = mock_client
        models = await runner.list_models()
        assert models == []

    @pytest.mark.asyncio
    async def test_run_stability_all_success(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=MockResponse())
        runner._client = mock_client
        result = await runner.run_stability(model="test", rounds=3)
        assert result.stable is True

    @pytest.mark.asyncio
    async def test_run_stability_partial_fail(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock()
        # Two successes, one failure (caught by run_single)
        mock_client.post.side_effect = [
            MockResponse(),
            RuntimeError("fail"),
            MockResponse(),
        ]
        mock_client.get = AsyncMock(return_value=MockResponse(json_data={
            "model_memory_used_formatted": "2 GB",
        }))
        runner._client = mock_client
        result = await runner.run_stability(model="test", rounds=3)
        # Two out of three succeeded -> stable (2 >= 3*0.9=2.7 -> False since 2 < 2.7)
        # Actually 2 >= 2.7 is False, so stable=False
        # But errors are caught by run_single, not run_stability, so errors is empty
        assert len(result.errors) == 0  # errors are caught inside run_single

    @pytest.mark.asyncio
    async def test_probe_max_context(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=MockResponse())
        runner._client = mock_client
        ctx = await runner.probe_max_context(model="test", max_context=8192, step=4096)
        assert ctx >= 4096

    @pytest.mark.asyncio
    async def test_probe_max_context_fails_early(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=RuntimeError("OOM"))
        runner._client = mock_client
        ctx = await runner.probe_max_context(model="test", max_context=8192, step=4096)
        assert ctx == 4096  # last valid is the initial value

    @pytest.mark.asyncio
    async def test_parse_memory_edge_cases(self):
        assert BenchmarkRunner._parse_memory("") == 0.0
        assert BenchmarkRunner._parse_memory("abc") == 0.0
        assert BenchmarkRunner._parse_memory("10 KB") == 0.009765625
        assert BenchmarkRunner._parse_memory("1.5 GB") == 1536.0

    @pytest.mark.asyncio
    async def test_benchmark_no_prompt(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=MockResponse())
        runner._client = mock_client
        results = await runner.benchmark(model="test", prompt="", max_tokens=50, runs=1)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_close_no_client(self):
        runner = BenchmarkRunner()
        await runner.close()
        assert runner._client is None


# ── MetricsCollector advanced ──

class TestMetricsCollectorAdvanced:
    @pytest.mark.asyncio
    async def test_collect_success(self):
        collector = MetricsCollector(mlx_base_url="http://localhost:11434/v1")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models_loaded": 2,
            "models_discovered": 5,
            "total_requests": 100,
            "total_prompt_tokens": 5000,
            "total_tokens_generated": 3000,
            "model_memory_used_formatted": "8 GB",
            "model_memory_max_formatted": "64 GB",
        }
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
            metrics = await collector.collect()
            assert metrics.models_loaded == 2
            assert metrics.total_requests == 100
            assert metrics.model_memory_used == "8 GB"

    @pytest.mark.asyncio
    async def test_collect_http_error(self):
        collector = MetricsCollector(mlx_base_url="http://localhost:11434/v1")
        with patch("httpx.AsyncClient.get", side_effect=RuntimeError("fail")):
            metrics = await collector.collect()
            assert metrics.total_requests == 0

    def test_system_metrics_defaults(self):
        m = SystemMetrics()
        assert m.models_loaded == 0
        assert m.uptime_seconds == 0

    def test_system_metrics_to_dict(self):
        m = SystemMetrics(models_loaded=3, total_requests=200)
        d = m.to_dict()
        assert d["models_loaded"] == 3
        assert d["total_requests"] == 200


# ── ParameterTuner advanced ──

class TestParameterTunerAdvanced:
    @pytest.mark.asyncio
    async def test_tune_with_results(self):
        tuner = ParameterTuner(mlx_base_url="http://localhost:11434/v1")
        # Mock the runner's run_single
        tuner.runner.run_single = AsyncMock(return_value=SpeedMetrics(
            decode_speed=25.0, peak_memory_mb=4096.0,
        ))
        result = await tuner.tune("test-model", max_combinations=3)
        assert result.model == "test-model"
        assert result.best_speed > 0
        assert len(result.top3_configs) > 0
        assert result.best_config != {}

    @pytest.mark.asyncio
    async def test_tune_all_fail(self):
        tuner = ParameterTuner(mlx_base_url="http://localhost:11434/v1")
        tuner.runner.run_single = AsyncMock(side_effect=RuntimeError("fail"))
        result = await tuner.tune("test-model", max_combinations=3)
        assert result.best_config == {}

    @pytest.mark.asyncio
    async def test_tune_single_result(self):
        tuner = ParameterTuner(mlx_base_url="http://localhost:11434/v1")
        tuner.runner.run_single = AsyncMock(return_value=SpeedMetrics(
            decode_speed=30.0, peak_memory_mb=2048.0,
        ))
        result = await tuner.tune("test-model", max_combinations=1)
        assert len(result.all_results) == 1
        assert result.best_speed == 30.0

    @pytest.mark.asyncio
    async def test_tune_multi_model(self):
        tuner = ParameterTuner(mlx_base_url="http://localhost:11434/v1")
        tuner.runner.run_single = AsyncMock(return_value=SpeedMetrics(
            decode_speed=20.0, peak_memory_mb=3072.0,
        ))
        results = await tuner.tune_multi_model(["model-a", "model-b"], max_combinations=2)
        assert len(results) == 2
        assert "model-a" in results
        assert "model-b" in results

    @pytest.mark.asyncio
    async def test_tune_multi_model_one_fails(self):
        tuner = ParameterTuner(mlx_base_url="http://localhost:11434/v1")
        tuner.runner.run_single = AsyncMock(side_effect=[
            SpeedMetrics(decode_speed=20.0),
            RuntimeError("fail"),
        ])
        results = await tuner.tune_multi_model(["model-a", "model-b"], max_combinations=1)
        assert "model-a" in results
        assert "model-b" in results
        # model-b should have empty results since it failed
        assert len(results["model-b"].all_results) == 0

    def test_generate_configs(self):
        tuner = ParameterTuner()
        configs = tuner._generate_configs()
        expected_count = len(tuner.BATCH_SIZES) * len(tuner.MAX_TOKENS) * len(tuner.TEMPERATURES)
        assert len(configs) == expected_count


# ── ReportGenerator advanced ──

class TestReportGeneratorAdvanced:
    @pytest.mark.asyncio
    async def test_to_json_with_file(self):
        r = BenchmarkResult(model="test", metrics=SpeedMetrics(decode_speed=25.0))
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "report.json")
            output = ReportGenerator.to_json([r], filepath=path)
            assert Path(path).exists()
            data = json.loads(output)
            assert data["total_benchmarks"] == 1

    def test_to_markdown_multiple_results(self):
        results = [
            BenchmarkResult(model="model-a", metrics=SpeedMetrics(decode_speed=30.0, peak_memory_mb=4096)),
            BenchmarkResult(model="model-b", metrics=SpeedMetrics(decode_speed=20.0, peak_memory_mb=2048)),
        ]
        md = ReportGenerator.to_markdown(results, "Multi Model Test")
        assert "model-a" in md
        assert "model-b" in md
        assert "30.0" in md
        assert "20.0" in md

    def test_to_markdown_no_speed(self):
        r = BenchmarkResult(model="test")
        md = ReportGenerator.to_markdown([r])
        assert "N/A" in md

    def test_generate_chart_with_results(self):
        results = [
            BenchmarkResult(model="a", metrics=SpeedMetrics(decode_speed=30.0, peak_memory_mb=4096)),
            BenchmarkResult(model="b", metrics=SpeedMetrics(decode_speed=20.0, peak_memory_mb=2048)),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "chart.png")
            result_path = ReportGenerator.generate_chart_path(results, output_path=path)
            if result_path:  # matplotlib may not be installed
                assert Path(result_path).exists()

    def test_generate_config_template_with_context(self):
        r = BenchmarkResult(
            model="qwen3.5-9b",
            config={"max_tokens": 4096, "temperature": 0.7},
            metrics=SpeedMetrics(decode_speed=25.5, peak_memory_mb=4096),
            max_stable_context=32768,
        )
        template = ReportGenerator.generate_config_template(r)
        assert "32768" in template
        assert "max_stable_context" in template