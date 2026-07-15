"""Tests for Fusion-Bench core modules."""
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


# ── SpeedMetrics ──

class TestSpeedMetrics:
    def test_defaults(self):
        m = SpeedMetrics()
        assert m.decode_speed == 0.0
        assert m.peak_memory_mb == 0.0

    def test_to_dict(self):
        m = SpeedMetrics(decode_speed=25.5, peak_memory_mb=4096)
        d = m.to_dict()
        assert d["decode_speed"] == 25.5
        assert d["peak_memory_mb"] == 4096.0


# ── BenchmarkResult ──

class TestBenchmarkResult:
    def test_defaults(self):
        r = BenchmarkResult(model="test-model")
        assert r.model == "test-model"
        assert r.stable is True
        assert r.errors == []


# ── BenchmarkRunner ──

class TestBenchmarkRunner:
    def test_init(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:11434/v1")
        assert runner.mlx_base_url == "http://localhost:11434/v1"
        assert runner.timeout == 300.0

    @pytest.mark.asyncio
    async def test_list_models_no_server(self):
        runner = BenchmarkRunner(mlx_base_url="http://localhost:19999/v1", timeout=1.0)
        models = await runner.list_models()
        assert models == []

    @pytest.mark.asyncio
    async def test_close(self):
        runner = BenchmarkRunner()
        _ = runner.client
        await runner.close()
        assert runner._client is None

    def test_parse_memory(self):
        assert BenchmarkRunner._parse_memory("512 MB") == 512.0
        assert BenchmarkRunner._parse_memory("2.5 GB") == 2560.0
        assert BenchmarkRunner._parse_memory("1 TB") == 1048576.0
        assert BenchmarkRunner._parse_memory("invalid") == 0.0


# ── MetricsCollector ──

class TestMetricsCollector:
    @pytest.mark.asyncio
    async def test_collect_no_server(self):
        collector = MetricsCollector(mlx_base_url="http://localhost:19999/v1")
        metrics = await collector.collect()
        assert metrics.total_requests == 0
        assert metrics.timestamp > 0

    @pytest.mark.asyncio
    async def test_collect_series(self):
        collector = MetricsCollector(mlx_base_url="http://localhost:19999/v1")
        series = await collector.collect_series(duration=0.5, interval=0.1)
        assert len(series) >= 1


# ── ParameterTuner ──

class TestParameterTuner:
    def test_init(self):
        tuner = ParameterTuner()
        assert len(tuner.BATCH_SIZES) >= 2
        assert len(tuner.MAX_TOKENS) >= 2

    def test_generate_configs(self):
        tuner = ParameterTuner()
        configs = tuner._generate_configs()
        assert len(configs) > 0
        for cfg in configs:
            assert "batch_size" in cfg
            assert "max_tokens" in cfg
            assert "temperature" in cfg

    @pytest.mark.asyncio
    async def test_tune_no_server(self):
        tuner = ParameterTuner(mlx_base_url="http://localhost:19999/v1")
        result = await tuner.tune("test-model", max_combinations=2)
        assert result.model == "test-model"
        assert len(result.all_results) >= 0


# ── ReportGenerator ──

class TestReportGenerator:
    def test_to_json(self):
        r = BenchmarkResult(model="test", metrics=SpeedMetrics(decode_speed=25.0))
        output = ReportGenerator.to_json([r])
        data = json.loads(output)
        assert data["total_benchmarks"] == 1

    def test_to_markdown(self):
        r = BenchmarkResult(model="test", metrics=SpeedMetrics(decode_speed=25.0, peak_memory_mb=4096))
        md = ReportGenerator.to_markdown([r], "Test Report")
        assert "Test Report" in md
        assert "25.0" in md
        assert "4096" in md

    def test_generate_chart_no_results(self):
        path = ReportGenerator.generate_chart_path([])
        assert path == ""

    def test_generate_config_template(self):
        r = BenchmarkResult(
            model="qwen3.5-9b",
            config={"max_tokens": 4096, "temperature": 0.7},
            metrics=SpeedMetrics(decode_speed=25.5, peak_memory_mb=4096),
        )
        template = ReportGenerator.generate_config_template(r)
        assert "qwen3.5-9b" in template
        assert "25.5" in template