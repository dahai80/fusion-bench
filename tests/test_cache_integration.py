"""Tests for BenchmarkCache executor_key + WAL + TTL."""

from __future__ import annotations

import time

from fusion_bench.cache import BenchmarkCache


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
