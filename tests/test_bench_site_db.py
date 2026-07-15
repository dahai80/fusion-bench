"""Tests for Fusion-Bench bench-site database integration."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from fusion_bench.reporter.bench_site_db import BenchSiteDB, BenchSiteRecord
from fusion_bench.engine.benchmark import SpeedMetrics, BenchmarkResult


class TestBenchSiteRecord:
    def test_defaults(self):
        r = BenchSiteRecord(chip_name="M5 Max", memory_gb=128, gpu_cores=40,
                            model_name="test", quantization="mxfp8",
                            context_length=4096, pp_tps=500.0, tg_tps=25.0)
        assert r.chip_name == "M5 Max"
        assert r.omlx_version == "fusion-mlx"
        assert r.submission_group == "fusion-bench"


class TestBenchSiteDB:
    @pytest.fixture
    def db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "bench.db")
            bdb = BenchSiteDB(db_path=db_path)
            yield bdb
            bdb.close()

    def test_ensure_schema(self, db):
        db._ensure_schema()
        conn = db._get_conn()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        assert any(t["name"] == "benchmarks" for t in tables)

    def test_insert_and_query(self, db):
        record = BenchSiteRecord(
            chip_name="M5 Max", memory_gb=128, gpu_cores=40,
            model_name="qwen3.5-9b", quantization="mxfp8",
            context_length=4096, pp_tps=500.0, tg_tps=25.0,
        )
        row_id = db.insert(record)
        assert row_id > 0
        results = db.query(model="qwen")
        assert len(results) >= 1
        assert results[0]["model_name"] == "qwen3.5-9b"

    def test_insert_from_metrics(self, db):
        metrics = SpeedMetrics(
            prefill_speed=600.0, decode_speed=30.0,
            prefill_time=0.1, peak_memory_mb=4096,
        )
        row_id = db.insert_from_metrics(
            metrics=metrics, model_name="qwen3.5-9b",
            quantization="mxfp4", context_length=8192,
            hw_info={"chip_name": "M5 Pro", "memory_gb": 64, "gpu_cores": 24, "os_version": "macOS 15.0"},
        )
        assert row_id > 0
        results = db.query(model="qwen3.5-9b")
        assert len(results) >= 1
        assert results[0]["tg_tps"] == 30.0

    def test_insert_from_metrics_no_hw(self, db):
        metrics = SpeedMetrics(decode_speed=20.0)
        with patch.object(BenchSiteDB, "_detect_hardware", return_value={
            "chip_name": "M5", "memory_gb": 32, "gpu_cores": 16, "os_version": "macOS 15.0",
        }):
            row_id = db.insert_from_metrics(
                metrics=metrics, model_name="test",
            )
            assert row_id > 0

    def test_insert_from_benchmark(self, db):
        result = BenchmarkResult(
            model="qwen3.5-9b-mxfp4",
            config={"max_tokens": 8192},
            metrics=SpeedMetrics(decode_speed=30.0, prefill_speed=600.0, peak_memory_mb=8192),
        )
        row_id = db.insert_from_benchmark(
            result=result,
            hw_info={"chip_name": "M5 Ultra", "memory_gb": 128, "gpu_cores": 40, "os_version": "macOS 15.0"},
        )
        assert row_id > 0
        results = db.query(model="qwen3.5-9b")
        assert len(results) >= 1

    def test_query_by_chip(self, db):
        record1 = BenchSiteRecord(chip_name="M5", memory_gb=64, gpu_cores=32,
                                  model_name="m1", quantization="mxfp8",
                                  context_length=4096, pp_tps=100.0, tg_tps=10.0)
        record2 = BenchSiteRecord(chip_name="M4", memory_gb=32, gpu_cores=16,
                                  model_name="m2", quantization="mxfp8",
                                  context_length=4096, pp_tps=200.0, tg_tps=20.0)
        db.insert(record1)
        db.insert(record2)
        results = db.query(chip="M5")
        assert len(results) >= 1
        assert results[0]["chip_name"] == "M5"

    def test_stats(self, db):
        stats = db.stats()
        assert stats["total_entries"] == 0
        db.insert(BenchSiteRecord(chip_name="M5", memory_gb=64, gpu_cores=32,
                                  model_name="test", quantization="mxfp8",
                                  context_length=4096, pp_tps=100.0, tg_tps=10.0))
        stats = db.stats()
        assert stats["total_entries"] == 1
        assert stats["unique_models"] == 1

    def test_insert_multiple(self, db):
        for i in range(5):
            db.insert(BenchSiteRecord(
                chip_name="M5", memory_gb=64, gpu_cores=32,
                model_name=f"model-{i}", quantization="mxfp8",
                context_length=4096, pp_tps=100.0, tg_tps=10.0,
            ))
        assert db.stats()["total_entries"] == 5

    def test_detect_hardware(self):
        info = BenchSiteDB._detect_hardware()
        assert "chip_name" in info
        assert "memory_gb" in info
        assert "gpu_cores" in info