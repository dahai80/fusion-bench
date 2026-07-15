"""Tests for Fusion-Bench CLI, Metal monitor, cache, and quant benchmark."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fusion_bench.cli import main as cli_main
from fusion_bench.engine.metal_monitor import MetalMonitor
from fusion_bench.cache import BenchmarkCache
from fusion_bench.optimizer.quant_bench import QuantBenchmark, QuantResult


# ── MetalMonitor ──

class TestMetalMonitor:
    def test_collect_gpu_info(self):
        info = MetalMonitor.collect_gpu_info()
        assert isinstance(info, dict)

    def test_collect_system_info(self):
        info = MetalMonitor.collect_system_info()
        assert isinstance(info, dict)
        if info:
            assert "total_memory_gb" in info

    @pytest.mark.asyncio
    async def test_collect_mlx_stats_no_server(self):
        stats = await MetalMonitor.collect_mlx_stats("http://localhost:19999")
        assert stats == {}

    def test_collect_power_info(self):
        info = MetalMonitor.collect_power_info()
        assert isinstance(info, dict)

    @pytest.mark.asyncio
    async def test_collect_all(self):
        info = await MetalMonitor().collect_all("http://localhost:19999")
        assert "gpu" in info
        assert "system" in info
        assert "mlx" in info

    def test_format_report(self):
        data = {
            "gpu": {"gpu_model": "Apple M5 Max", "gpu_cores": 40, "metal_family": "Metal 3"},
            "system": {"total_memory_gb": 128, "cpu_cores": 16},
            "mlx": {"models_loaded": 2, "total_requests": 100},
        }
        report = MetalMonitor.format_report(data)
        assert "Apple M5 Max" in report
        assert "128 GB" in report
        assert "Metal" in report


# ── BenchmarkCache ──

class TestBenchmarkCache:
    def test_set_and_get(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = BenchmarkCache(str(Path(tmpdir) / "cache.db"))
            cache.set("model1", {}, "mmlu", {"accuracy": 0.85})
            result = cache.get("model1", {}, "mmlu")
            assert result is not None
            assert result["accuracy"] == 0.85

    def test_get_miss(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = BenchmarkCache(str(Path(tmpdir) / "cache.db"))
            result = cache.get("nonexistent", {}, "task")
            assert result is None

    def test_get_with_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = BenchmarkCache(str(Path(tmpdir) / "cache.db"))
            cache.set("model1", {"temperature": 0.7}, "gsm8k", {"accuracy": 0.75})
            result = cache.get("model1", {"temperature": 0.7}, "gsm8k")
            assert result["accuracy"] == 0.75
            # Different config should miss
            result2 = cache.get("model1", {"temperature": 0.0}, "gsm8k")
            assert result2 is None

    def test_clear_all(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = BenchmarkCache(str(Path(tmpdir) / "cache.db"))
            cache.set("m1", {}, "t1", {"a": 1})
            cache.set("m1", {}, "t2", {"a": 2})
            cache.set("m2", {}, "t1", {"a": 3})
            assert cache.stats()["total_entries"] == 3
            deleted = cache.clear()
            assert deleted == 3
            assert cache.stats()["total_entries"] == 0

    def test_clear_by_model(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = BenchmarkCache(str(Path(tmpdir) / "cache.db"))
            cache.set("m1", {}, "t1", {"a": 1})
            cache.set("m1", {}, "t2", {"a": 2})
            cache.set("m2", {}, "t1", {"a": 3})
            deleted = cache.clear(model="m1")
            assert deleted == 2
            assert cache.stats()["total_entries"] == 1

    def test_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = BenchmarkCache(str(Path(tmpdir) / "cache.db"))
            stats = cache.stats()
            assert stats["total_entries"] == 0
            cache.set("m1", {}, "t1", {"a": 1})
            stats = cache.stats()
            assert stats["total_entries"] == 1

    def test_close(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = BenchmarkCache(str(Path(tmpdir) / "cache.db"))
            cache.close()
            assert cache._conn is None


# ── QuantBenchmark ──

class TestQuantResult:
    def test_defaults(self):
        r = QuantResult(quant="mxfp4")
        assert r.quant == "mxfp4"
        assert r.speed == 0.0
        assert r.stable is True


class TestQuantBenchmark:
    def test_init(self):
        qb = QuantBenchmark(mlx_base_url="http://localhost:11434/v1", base_model="qwen3.5-9b")
        assert qb.base_model == "qwen3.5-9b"
        assert len(qb.DEFAULT_LEVELS) >= 5

    @pytest.mark.asyncio
    async def test_run_speed_no_server(self):
        qb = QuantBenchmark(mlx_base_url="http://localhost:19999/v1")
        results = await qb.run_speed_comparison(levels=["mxfp4"], runs=1)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_run_accuracy_no_server(self):
        qb = QuantBenchmark(mlx_base_url="http://localhost:19999/v1")
        results = await qb.run_accuracy_comparison(levels=["mxfp8"], task="mmlu", max_samples=1)
        assert len(results) >= 1

    def test_generate_report(self):
        results = [
            QuantResult(quant="mxfp4", speed=30.0, memory_mb=4096, accuracy=0.85),
            QuantResult(quant="mxfp8", speed=20.0, memory_mb=8192, accuracy=0.88),
            QuantResult(quant="quant2", speed=45.0, memory_mb=2048),
        ]
        report = QuantBenchmark(mlx_base_url="").generate_report(results)
        assert "mxfp4" in report
        assert "mxfp8" in report
        assert "quant2" in report
        assert "Fastest" in report
        assert "Most memory efficient" in report

    def test_generate_report_empty(self):
        report = QuantBenchmark(mlx_base_url="").generate_report([], "Test")
        assert "Test" in report


# ── CLI ──

class TestCLI:
    def test_list_tasks(self):
        """Just verify the CLI module loads without errors."""
        # Can't easily test argparse without sys.exit, but at least verify module loads
        from fusion_bench import cli
        assert hasattr(cli, "main")
        assert hasattr(cli, "cmd_list_tasks")
        assert hasattr(cli, "cmd_run")
        assert hasattr(cli, "cmd_tune")
        assert hasattr(cli, "cmd_compare")
        assert hasattr(cli, "cmd_speed")
        assert hasattr(cli, "cmd_quant")