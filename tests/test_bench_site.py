"""Tests for Fusion-Bench bench-site integration."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fusion_bench.reporter.bench_site import BenchSiteEntry, BenchSiteReporter, BenchSiteSubmitter
from fusion_bench.engine.benchmark import SpeedMetrics, BenchmarkResult


class TestBenchSiteEntry:
    def test_defaults(self):
        e = BenchSiteEntry()
        assert e.chip_name == ""
        assert e.submission_group == "fusion-bench"

    def test_to_dict_minimal(self):
        e = BenchSiteEntry(
            chip_name="M5 Max", memory_gb=128, gpu_cores=40,
            model_name="qwen3.5-9b", quantization="mxfp8",
            context_length=4096, pp_tps=500.0, tg_tps=25.0,
        )
        d = e.to_dict()
        assert d["chip_name"] == "M5 Max"
        assert d["pp_tps"] == 500.0
        assert d["tg_tps"] == 25.0
        assert "ttft_ms" not in d  # None values are excluded

    def test_to_dict_full(self):
        e = BenchSiteEntry(
            chip_name="M5 Max", memory_gb=128, gpu_cores=40,
            model_name="qwen3.5-9b", quantization="mxfp4",
            context_length=8192, pp_tps=800.0, tg_tps=35.0,
            ttft_ms=50.0, peak_memory_gb=12.5,
            owner_hash="abc123",
        )
        d = e.to_dict()
        assert d["ttft_ms"] == 50.0
        assert d["peak_memory_gb"] == 12.5
        assert d["owner_hash"] == "abc123"


class TestBenchSiteReporter:
    def test_detect_hardware(self):
        info = BenchSiteReporter.detect_hardware()
        assert "chip_name" in info
        assert "memory_gb" in info
        assert "gpu_cores" in info

    def test_from_speed_metrics(self):
        metrics = SpeedMetrics(
            prefill_speed=500.0, decode_speed=25.0,
            prefill_time=0.1, peak_memory_mb=4096,
        )
        entry = BenchSiteReporter.from_speed_metrics(
            metrics=metrics, model_name="qwen3.5-9b",
            quantization="mxfp4", context_length=8192,
        )
        assert entry.model_name == "qwen3.5-9b"
        assert entry.quantization == "mxfp4"
        assert entry.tg_tps == 25.0
        assert entry.pp_tps == 500.0
        assert entry.peak_memory_gb == 4.0  # 4096 MB / 1024

    def test_from_speed_metrics_zero_memory(self):
        metrics = SpeedMetrics(decode_speed=20.0, peak_memory_mb=0)
        entry = BenchSiteReporter.from_speed_metrics(
            metrics=metrics, model_name="test",
        )
        assert entry.peak_memory_gb is None

    def test_from_benchmark_result(self):
        result = BenchmarkResult(
            model="qwen3.5-9b-mxfp4",
            config={"max_tokens": 8192},
            metrics=SpeedMetrics(decode_speed=30.0, prefill_speed=600.0, peak_memory_mb=8192),
        )
        entry = BenchSiteReporter.from_benchmark_result(result)
        assert entry.quantization == "mxfp4"
        assert entry.model_name == "qwen3.5-9b"
        assert entry.context_length == 8192


class TestBenchSiteSubmitter:
    @pytest.mark.asyncio
    async def test_submit_success(self):
        submitter = BenchSiteSubmitter(api_url="http://localhost:19999/api/benchmarks")
        entry = BenchSiteEntry(
            chip_name="M5", memory_gb=64, gpu_cores=32,
            model_name="test", quantization="mxfp8",
            context_length=4096, pp_tps=100.0, tg_tps=10.0,
        )
        with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_resp.json.return_value = {"id": 123, "url": "http://bench.dpdns.org/benchmarks/123"}
            mock_post.return_value = mock_resp
            result = await submitter.submit(entry)
            assert result["status"] == "created"
            assert result["id"] == 123

    @pytest.mark.asyncio
    async def test_submit_duplicate(self):
        submitter = BenchSiteSubmitter(api_url="http://localhost:19999/api/benchmarks")
        entry = BenchSiteEntry(
            chip_name="M5", memory_gb=64, gpu_cores=32,
            model_name="test", quantization="mxfp8",
            context_length=4096, pp_tps=100.0, tg_tps=10.0,
        )
        with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 409
            mock_resp.json.return_value = {"existing_id": 456, "existing_url": "http://bench.dpdns.org/benchmarks/456"}
            mock_post.return_value = mock_resp
            result = await submitter.submit(entry)
            assert result["status"] == "duplicate"
            assert result["existing_id"] == 456

    @pytest.mark.asyncio
    async def test_submit_error(self):
        submitter = BenchSiteSubmitter(api_url="http://localhost:19999/api/benchmarks")
        entry = BenchSiteEntry(
            chip_name="M5", memory_gb=64, gpu_cores=32,
            model_name="test", quantization="mxfp8",
            context_length=4096, pp_tps=100.0, tg_tps=10.0,
        )
        with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
            mock_post.side_effect = RuntimeError("connection failed")
            result = await submitter.submit(entry)
            assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_submit_batch(self):
        submitter = BenchSiteSubmitter(api_url="http://localhost:19999/api/benchmarks")
        entries = [
            BenchSiteEntry(chip_name="M5", memory_gb=64, gpu_cores=32,
                           model_name="m1", quantization="mxfp8",
                           context_length=4096, pp_tps=100.0, tg_tps=10.0),
            BenchSiteEntry(chip_name="M5", memory_gb=64, gpu_cores=32,
                           model_name="m2", quantization="mxfp4",
                           context_length=4096, pp_tps=200.0, tg_tps=20.0),
        ]
        with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_resp.json.return_value = {"id": 789, "url": "http://bench.dpdns.org/benchmarks/789"}
            mock_post.return_value = mock_resp
            results = await submitter.submit_batch(entries)
            assert len(results) == 2
            assert results[0]["status"] == "created"