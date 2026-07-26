"""Tests for the new plugin architecture: core, executors, orchestrator, storage."""

import tempfile
from pathlib import Path

import pytest

from fusion_bench.core.models import (
    EvalLevel,
    GateResult,
    GateTier,
    QualityGate,
    SuiteResult,
    TaskStatus,
    TraceRecord,
)
from fusion_bench.core.plugin_base import (
    CaseResult,
    EvalResult,
    ExecutorPlugin,
    ExecutorType,
    TaskConfig,
)
from fusion_bench.core.registry import Registry, executor_registry
from fusion_bench.orchestrator.gate_engine import GateEngine
from fusion_bench.orchestrator.scheduler import Scheduler
from fusion_bench.storage.trace_store import TraceStore


class TestRegistry:
    def test_register_and_get(self):
        reg = Registry[str]("test")

        class DummyPlugin(ExecutorPlugin):
            name = "dummy"

        reg.register("dummy", DummyPlugin)
        assert reg.get("dummy") is DummyPlugin
        assert reg.has("dummy")
        assert "dummy" in reg

    def test_get_or_raise_missing(self):
        reg = Registry("test")
        with pytest.raises(KeyError, match="no item registered"):
            reg.get_or_raise("nonexistent")

    def test_list_keys(self):
        reg = Registry[int]("test")
        reg.register("b", int)
        reg.register("a", int)
        assert reg.list_keys() == ["a", "b"]

    def test_unregister(self):
        reg = Registry("test")
        reg.register("x", int)
        reg.unregister("x")
        assert not reg.has("x")

    def test_len(self):
        reg = Registry("test")
        assert len(reg) == 0
        reg.register("a", int)
        assert len(reg) == 1


class TestTaskConfig:
    def test_get_default(self):
        config = TaskConfig(task_id="t1", model="m1", executor_key="speed")
        assert config.get("nonexistent") is None
        assert config.get("nonexistent", 42) == 42

    def test_get_existing(self):
        config = TaskConfig(task_id="t1", model="m1", executor_key="speed", params={"key": "val"})
        assert config.get("key") == "val"


class TestEvalResult:
    def test_pass_rate_empty(self):
        result = EvalResult(task_id="t1", executor_key="speed", model="m1")
        assert result.pass_rate == 0.0

    def test_pass_rate_half(self):
        cases = [
            CaseResult(input_text="a", passed=True),
            CaseResult(input_text="b", passed=False),
        ]
        result = EvalResult(task_id="t1", executor_key="speed", model="m1", cases=cases)
        assert result.pass_rate == 0.5

    def test_to_dict(self):
        result = EvalResult(task_id="t1", executor_key="speed", model="m1", metric_value=42.0)
        d = result.to_dict()
        assert d["metric_value"] == 42.0
        assert d["task_id"] == "t1"


class TestQualityGate:
    def test_gte(self):
        gate = QualityGate("g1", "test", GateTier.EXPERIMENTAL, "accuracy", ">=", 0.5)
        assert gate.evaluate(0.6) is True
        assert gate.evaluate(0.5) is True
        assert gate.evaluate(0.4) is False

    def test_lt(self):
        gate = QualityGate("g1", "test", GateTier.BUSINESS, "memory", "<", 1000.0)
        assert gate.evaluate(500.0) is True
        assert gate.evaluate(1000.0) is False

    def test_unknown_operator(self):
        gate = QualityGate("g1", "test", GateTier.EXPERIMENTAL, "x", "???", 0)
        assert gate.evaluate(1.0) is False

    def test_to_dict(self):
        gate = QualityGate("g1", "test", GateTier.PRODUCTION, "accuracy", ">=", 0.9)
        d = gate.to_dict()
        assert d["tier"] == "production"
        assert d["operator"] == ">="


class TestGateEngine:
    def test_evaluate_matching_gate(self):
        engine = GateEngine()
        gate = QualityGate(
            "g1",
            "Min speed",
            GateTier.EXPERIMENTAL,
            "decode_speed",
            ">=",
            10.0,
            executor_key="speed",
        )
        engine.add_gate(gate)

        results = engine.evaluate("speed", "decode_speed", 15.0)
        assert len(results) == 1
        assert results[0].passed is True

    def test_evaluate_non_matching_metric(self):
        engine = GateEngine()
        gate = QualityGate(
            "g1",
            "Min speed",
            GateTier.EXPERIMENTAL,
            "decode_speed",
            ">=",
            10.0,
            executor_key="speed",
        )
        engine.add_gate(gate)

        results = engine.evaluate("speed", "accuracy", 0.5)
        assert len(results) == 0

    def test_evaluate_non_matching_executor(self):
        engine = GateEngine()
        gate = QualityGate(
            "g1",
            "Min speed",
            GateTier.EXPERIMENTAL,
            "decode_speed",
            ">=",
            10.0,
            executor_key="speed",
        )
        engine.add_gate(gate)

        results = engine.evaluate("security", "decode_speed", 15.0)
        assert len(results) == 0

    def test_load_default_gates(self):
        engine = GateEngine()
        engine.load_default_gates()
        assert len(engine._adhoc_gates) == 8


class TestScheduler:
    def test_load_default_suites(self):
        scheduler = Scheduler()
        scheduler.load_default_suites()
        suites = scheduler.list_suites()
        assert "l1-quick" in suites
        assert "l1-full" in suites
        assert "l3-security" in suites
        assert "full" in suites

    def test_suite_to_task_configs(self):
        scheduler = Scheduler()
        scheduler.load_default_suites()
        configs = scheduler.suite_to_task_configs("l1-quick")
        assert len(configs) == 1
        assert configs[0]["executor_key"] == "speed"

    def test_missing_suite(self):
        scheduler = Scheduler()
        with pytest.raises(KeyError):
            scheduler.get_suite("nonexistent")


class TestTraceStore:
    def test_insert_and_query(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TraceStore(db_path=Path(tmpdir) / "test.db")
            record = TraceRecord(
                trace_id="t-001",
                model="test-model",
                level=EvalLevel.L1_MODEL,
                executor_key="speed",
                task_id="speed-1",
                status=TaskStatus.COMPLETED,
                eval_result={"metric_value": 42.0},
            )
            store.insert(record)

            results = store.query(model="test-model")
            assert len(results) == 1
            assert results[0].trace_id == "t-001"
            assert results[0].model == "test-model"
            assert results[0].eval_result["metric_value"] == 42.0
            store.close()

    def test_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TraceStore(db_path=Path(tmpdir) / "test.db")
            record = TraceRecord(
                trace_id="t-002",
                model="m1",
                level=EvalLevel.L1_MODEL,
                executor_key="speed",
                task_id="s1",
                status=TaskStatus.COMPLETED,
            )
            store.insert(record)

            stats = store.stats()
            assert stats["total"] == 1
            assert "by_status" in stats
            store.close()

    def test_query_by_level(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TraceStore(db_path=Path(tmpdir) / "test.db")
            for i, level in enumerate([EvalLevel.L1_MODEL, EvalLevel.L3_APP]):
                store.insert(
                    TraceRecord(
                        trace_id=f"t-{i}",
                        model="m1",
                        level=level,
                        executor_key="speed",
                        task_id=f"s{i}",
                        status=TaskStatus.COMPLETED,
                    )
                )

            l1 = store.query(level="L1")
            assert len(l1) == 1
            l3 = store.query(level="L3")
            assert len(l3) == 1
            store.close()


class TestExecutorRegistration:
    def test_all_executors_registered(self):
        from fusion_bench.executors import register_all

        saved = dict(executor_registry._items)
        try:
            executor_registry._items.clear()
            register_all()
            keys = executor_registry.list_keys()
            assert "speed" in keys
            assert "security" in keys
            assert "quant" in keys
            assert "tune" in keys
        finally:
            executor_registry._items = saved

    def test_executor_types(self):
        from fusion_bench.executors import register_all

        saved = dict(executor_registry._items)
        try:
            executor_registry._items.clear()
            register_all()

            for key in executor_registry.list_keys():
                cls = executor_registry.get(key)
                instance = cls()
                assert isinstance(instance, ExecutorPlugin)
                assert instance.name
                assert isinstance(instance.executor_type, ExecutorType)
        finally:
            executor_registry._items = saved


class TestTraceRecordToDict:
    def test_roundtrip(self):
        record = TraceRecord(
            trace_id="t-001",
            model="m1",
            level=EvalLevel.L1_MODEL,
            executor_key="speed",
            task_id="s1",
            status=TaskStatus.COMPLETED,
            eval_result={"accuracy": 0.85},
            gate_results=[{"gate_id": "g1", "passed": True}],
        )
        d = record.to_dict()
        assert d["trace_id"] == "t-001"
        assert d["level"] == "L1"
        assert d["status"] == "completed"
        assert d["eval_result"]["accuracy"] == 0.85


class TestSuiteResultToDict:
    def test_roundtrip(self):
        result = SuiteResult(
            suite_id="s1",
            model="m1",
            level=EvalLevel.L1_MODEL,
            results=[{"accuracy": 0.9}],
            gate_results=[GateResult("g1", "gate1", GateTier.EXPERIMENTAL, "accuracy", 0.9, 0.5, True)],
            overall_passed=True,
        )
        d = result.to_dict()
        assert d["suite_id"] == "s1"
        assert d["overall_passed"] is True
        assert len(d["gate_results"]) == 1
