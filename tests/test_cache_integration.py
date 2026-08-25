"""Tests for BenchmarkCache executor_key + WAL + TTL + Pipeline integration."""

from __future__ import annotations

import time

import pytest

from fusion_bench.cache import BenchmarkCache
from fusion_bench.core.plugin_base import EvalResult, TaskConfig
from fusion_bench.core.registry import executor_registry
from fusion_bench.orchestrator.pipeline import Pipeline, _is_deterministic


class TestBenchmarkCacheUnit:
    def test_set_get_with_executor_key(self, tmp_path):
        cache = BenchmarkCache(db_path=str(tmp_path / "cache.db"))
        cache.set("qwen", {"temp": 0}, "mmlu", "speed", {"score": 0.8})
        got = cache.get("qwen", {"temp": 0}, "mmlu", "speed")
        assert got == {"score": 0.8}
        cache.close()

    def test_executor_key_isolation(self, tmp_path):
        cache = BenchmarkCache(db_path=str(tmp_path / "cache.db"))
        cache.set("qwen", {}, "mmlu", "speed", {"score": 0.8})
        cache.set("qwen", {}, "mmlu", "agent", {"score": 0.5})
        assert cache.get("qwen", {}, "mmlu", "speed") == {"score": 0.8}
        assert cache.get("qwen", {}, "mmlu", "agent") == {"score": 0.5}
        cache.close()

    def test_ttl_expiry(self, tmp_path):
        cache = BenchmarkCache(db_path=str(tmp_path / "cache.db"), ttl_seconds=0.5)
        cache.set("qwen", {}, "mmlu", "speed", {"score": 0.8})
        assert cache.get("qwen", {}, "mmlu", "speed") == {"score": 0.8}
        time.sleep(0.6)
        assert cache.get("qwen", {}, "mmlu", "speed") is None
        cache.close()

    def test_no_ttl_never_expires(self, tmp_path):
        cache = BenchmarkCache(db_path=str(tmp_path / "cache.db"), ttl_seconds=None)
        cache.set("qwen", {}, "mmlu", "speed", {"score": 0.8})
        assert cache.get("qwen", {}, "mmlu", "speed") == {"score": 0.8}
        cache.close()

    def test_clear_by_model(self, tmp_path):
        cache = BenchmarkCache(db_path=str(tmp_path / "cache.db"))
        cache.set("qwen", {}, "mmlu", "speed", {"score": 0.8})
        cache.set("llama", {}, "mmlu", "speed", {"score": 0.7})
        assert cache.clear(model="qwen") == 1
        assert cache.get("qwen", {}, "mmlu", "speed") is None
        assert cache.get("llama", {}, "mmlu", "speed") == {"score": 0.7}
        cache.close()


class TestDeterminismGate:
    def test_temp_zero_is_deterministic(self):
        cfg = TaskConfig(task_id="t1", model="m", executor_key="speed", params={"temperature": 0}, max_samples=10)
        assert _is_deterministic(cfg) is True

    def test_temp_nonzero_not_deterministic(self):
        cfg = TaskConfig(task_id="t1", model="m", executor_key="speed", params={"temperature": 0.7}, max_samples=10)
        assert _is_deterministic(cfg) is False

    def test_no_max_samples_not_deterministic(self):
        cfg = TaskConfig(task_id="t1", model="m", executor_key="speed", params={"temperature": 0}, max_samples=None)
        assert _is_deterministic(cfg) is False

    def test_temp_alias_temp(self):
        cfg = TaskConfig(task_id="t1", model="m", executor_key="speed", params={"temp": 0}, max_samples=5)
        assert _is_deterministic(cfg) is True


class TestPipelineCacheIntegration:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_executor(self, tmp_path):
        cache = BenchmarkCache(db_path=str(tmp_path / "cache.db"))
        cache.set("m", {"temperature": 0}, "t1", "speed", {
            "task_id": "t1", "executor_key": "speed", "model": "m", "level": "L1",
            "metric_name": "accuracy", "metric_value": 0.9, "cases": [], "duration_seconds": 0,
            "errors": [], "meta": {}, "failure_category": "", "failure_detail": "", "optimization_hints": [],
        })
        call_count = 0

        class FakeExecutor:
            name = "speed"
            executor_type = "speed"
            async def run(self, config):
                nonlocal call_count
                call_count += 1
                return EvalResult(task_id=config.task_id, executor_key="speed", model="m", metric_value=0.9)
            def is_available(self):
                return True

        executor_registry._items["speed"] = FakeExecutor
        try:
            pipe = Pipeline(cache=cache, use_cache=True)
            tasks = [{"task_id": "t1", "executor_key": "speed", "params": {"temperature": 0}, "max_samples": 10}]
            result = await pipe.run_suite("m", tasks, level="L1")
            assert call_count == 0  # executor never called — cache hit
            assert len(result.results) == 1
        finally:
            executor_registry._items.pop("speed", None)
        cache.close()

    @pytest.mark.asyncio
    async def test_non_deterministic_runs_executor(self, tmp_path):
        cache = BenchmarkCache(db_path=str(tmp_path / "cache.db"))

        class FakeExecutor:
            name = "speed"
            executor_type = "speed"
            async def run(self, config):
                return EvalResult(task_id=config.task_id, executor_key="speed", model="m", metric_value=0.5)
            def is_available(self):
                return True

        executor_registry._items["speed"] = FakeExecutor
        try:
            pipe = Pipeline(cache=cache, use_cache=True)
            tasks = [{"task_id": "t1", "executor_key": "speed", "params": {"temperature": 0.7}, "max_samples": 10}]
            await pipe.run_suite("m", tasks, level="L1")
            # non-deterministic → executor ran, nothing cached
            assert cache.get("m", {"temperature": 0.7}, "t1", "speed") is None
        finally:
            executor_registry._items.pop("speed", None)
        cache.close()
