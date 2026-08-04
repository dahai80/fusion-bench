"""Tests for storage (trace_store) and engine (metal_monitor, task_runner)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fusion_bench.core.models import (
    EvalLevel,
    GateResult,
    GateTier,
    TaskStatus,
    TraceRecord,
)
from fusion_bench.engine.metal_monitor import MetalMonitor
from fusion_bench.engine.task_runner import LMEvalTaskRunner
from fusion_bench.storage.trace_store import TraceStore

# ── TraceStore ──


class TestTraceStore:
    def test_init_creates_db(self, tmp_path):
        db_path = tmp_path / "test_traces.db"
        store = TraceStore(db_path=str(db_path))
        assert db_path.exists()
        store.close()

    def test_init_creates_parent_dir(self, tmp_path):
        db_path = tmp_path / "sub" / "dir" / "traces.db"
        store = TraceStore(db_path=str(db_path))
        assert db_path.parent.exists()
        store.close()

    def test_insert_and_query(self, tmp_path):
        store = TraceStore(db_path=str(tmp_path / "t.db"))
        record = TraceRecord(
            trace_id="tr-001",
            model="test-model",
            level=EvalLevel.L1_MODEL,
            executor_key="speed",
            task_id="t1",
            status=TaskStatus.COMPLETED,
            eval_result={"metric": 25.0},
            duration_seconds=1.5,
        )
        store.insert(record)

        results = store.query(model="test-model")
        assert len(results) == 1
        assert results[0].trace_id == "tr-001"
        assert results[0].model == "test-model"
        assert results[0].level == EvalLevel.L1_MODEL
        store.close()

    def test_insert_with_gate_results(self, tmp_path):
        store = TraceStore(db_path=str(tmp_path / "t.db"))
        record = TraceRecord(
            trace_id="tr-002",
            model="test-model",
            level=EvalLevel.L1_MODEL,
            executor_key="speed",
            task_id="t2",
            status=TaskStatus.COMPLETED,
            eval_result={"metric": 30.0},
            gate_results=[
                GateResult(
                    gate_id="speed-min",
                    gate_name="Min speed",
                    tier=GateTier.EXPERIMENTAL,
                    metric_name="decode_speed",
                    metric_value=30.0,
                    threshold=5.0,
                    passed=True,
                ).to_dict()
            ],
            duration_seconds=2.0,
        )
        store.insert(record)

        results = store.query()
        assert len(results) == 1
        assert len(results[0].gate_results) == 1
        store.close()

    def test_query_by_executor(self, tmp_path):
        store = TraceStore(db_path=str(tmp_path / "t.db"))
        for i, ek in enumerate(["speed", "quant", "speed"]):
            store.insert(
                TraceRecord(
                    trace_id=f"tr-{i}",
                    model="m1",
                    level=EvalLevel.L1_MODEL,
                    executor_key=ek,
                    task_id=f"t{i}",
                    status=TaskStatus.COMPLETED,
                    duration_seconds=1.0,
                )
            )

        speed_results = store.query(executor_key="speed")
        assert len(speed_results) == 2
        store.close()

    def test_query_by_level(self, tmp_path):
        store = TraceStore(db_path=str(tmp_path / "t.db"))
        store.insert(
            TraceRecord(
                trace_id="tr-l1",
                model="m1",
                level=EvalLevel.L1_MODEL,
                executor_key="speed",
                task_id="t1",
                status=TaskStatus.COMPLETED,
                duration_seconds=1.0,
            )
        )
        store.insert(
            TraceRecord(
                trace_id="tr-l3",
                model="m1",
                level=EvalLevel.L3_APP,
                executor_key="security",
                task_id="t2",
                status=TaskStatus.COMPLETED,
                duration_seconds=1.0,
            )
        )

        l1_results = store.query(level="L1")
        assert len(l1_results) == 1
        assert l1_results[0].level == EvalLevel.L1_MODEL
        store.close()

    def test_query_by_status(self, tmp_path):
        store = TraceStore(db_path=str(tmp_path / "t.db"))
        store.insert(
            TraceRecord(
                trace_id="tr-ok",
                model="m1",
                level=EvalLevel.L1_MODEL,
                executor_key="speed",
                task_id="t1",
                status=TaskStatus.COMPLETED,
                duration_seconds=1.0,
            )
        )
        store.insert(
            TraceRecord(
                trace_id="tr-fail",
                model="m1",
                level=EvalLevel.L1_MODEL,
                executor_key="speed",
                task_id="t2",
                status=TaskStatus.FAILED,
                duration_seconds=0.5,
            )
        )

        failed = store.query(status="failed")
        assert len(failed) == 1
        assert failed[0].status == TaskStatus.FAILED
        store.close()

    def test_query_limit(self, tmp_path):
        store = TraceStore(db_path=str(tmp_path / "t.db"))
        for i in range(10):
            store.insert(
                TraceRecord(
                    trace_id=f"tr-{i}",
                    model="m1",
                    level=EvalLevel.L1_MODEL,
                    executor_key="speed",
                    task_id=f"t{i}",
                    status=TaskStatus.COMPLETED,
                    duration_seconds=1.0,
                )
            )

        results = store.query(limit=3)
        assert len(results) == 3
        store.close()

    def test_stats(self, tmp_path):
        store = TraceStore(db_path=str(tmp_path / "t.db"))
        store.insert(
            TraceRecord(
                trace_id="tr-1",
                model="m1",
                level=EvalLevel.L1_MODEL,
                executor_key="speed",
                task_id="t1",
                status=TaskStatus.COMPLETED,
                duration_seconds=1.0,
            )
        )
        store.insert(
            TraceRecord(
                trace_id="tr-2",
                model="m1",
                level=EvalLevel.L3_APP,
                executor_key="security",
                task_id="t2",
                status=TaskStatus.FAILED,
                duration_seconds=0.5,
            )
        )

        stats = store.stats()
        assert stats["total"] == 2
        assert "completed" in stats["by_status"]
        assert "L1" in stats["by_level"]
        store.close()

    def test_insert_with_host_info(self, tmp_path):
        store = TraceStore(db_path=str(tmp_path / "t.db"))
        record = TraceRecord(
            trace_id="tr-host",
            model="m1",
            level=EvalLevel.L1_MODEL,
            executor_key="speed",
            task_id="t1",
            status=TaskStatus.COMPLETED,
            duration_seconds=1.0,
            host_info={"chip": "M2", "memory_gb": 16},
        )
        store.insert(record)

        results = store.query()
        assert results[0].host_info["chip"] == "M2"
        store.close()

    def test_insert_with_error_message(self, tmp_path):
        store = TraceStore(db_path=str(tmp_path / "t.db"))
        record = TraceRecord(
            trace_id="tr-err",
            model="m1",
            level=EvalLevel.L1_MODEL,
            executor_key="speed",
            task_id="t1",
            status=TaskStatus.FAILED,
            error_message="connection refused",
            duration_seconds=0.1,
        )
        store.insert(record)

        results = store.query(status="failed")
        assert results[0].error_message == "connection refused"
        store.close()

    def test_close_idempotent(self, tmp_path):
        store = TraceStore(db_path=str(tmp_path / "t.db"))
        store.close()
        store.close()

    def test_insert_replaces_duplicate_trace_id(self, tmp_path):
        store = TraceStore(db_path=str(tmp_path / "t.db"))
        record1 = TraceRecord(
            trace_id="tr-dup",
            model="m1",
            level=EvalLevel.L1_MODEL,
            executor_key="speed",
            task_id="t1",
            status=TaskStatus.COMPLETED,
            duration_seconds=1.0,
        )
        record2 = TraceRecord(
            trace_id="tr-dup",
            model="m2",
            level=EvalLevel.L1_MODEL,
            executor_key="speed",
            task_id="t1",
            status=TaskStatus.COMPLETED,
            duration_seconds=2.0,
        )
        store.insert(record1)
        store.insert(record2)

        results = store.query()
        assert len(results) == 1
        assert results[0].model == "m2"
        store.close()

    def test_row_to_record_malformed_json(self, tmp_path):
        store = TraceStore(db_path=str(tmp_path / "t.db"))
        store.conn.execute(
            """INSERT INTO traces (trace_id, model, level, executor_key, task_id,
               status, eval_result, gate_results, host_info, duration_seconds, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (
                "tr-bad",
                "m1",
                "L1",
                "speed",
                "t1",
                "completed",
                "not-json",
                "not-json",
                "not-json",
                1.0,
            ),
        )
        store.conn.commit()

        results = store.query()
        assert len(results) == 1
        assert results[0].eval_result is None
        assert results[0].gate_results == []
        assert results[0].host_info == {}
        store.close()

    def test_insert_sqlite_error(self, tmp_path):
        store = TraceStore(db_path=str(tmp_path / "t.db"))
        record = TraceRecord(
            trace_id="tr-ok",
            model="m1",
            level=EvalLevel.L1_MODEL,
            executor_key="speed",
            task_id="t1",
            status=TaskStatus.COMPLETED,
            duration_seconds=1.0,
        )
        store._conn.close()
        store.insert(record)
        store._conn = None
        results = store.query()
        assert len(results) == 0


# ── MetalMonitor ──


class TestMetalMonitor:
    def test_collect_gpu_info_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "SPDisplaysDataType": [
                    {
                        "sppci_model": "Apple M2 Pro",
                        "sppci_cores": 16,
                        "metal_family": "Metal 3",
                        "spdisplays_vram": "Dynamic",
                        "sppci_device_type": "GPU",
                    }
                ]
            }
        )

        with patch("fusion_bench.engine.metal_monitor.subprocess.run", return_value=mock_result):
            info = MetalMonitor.collect_gpu_info()

        assert info["gpu_model"] == "Apple M2 Pro"
        assert info["gpu_cores"] == 16

    def test_collect_gpu_info_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1

        with patch("fusion_bench.engine.metal_monitor.subprocess.run", return_value=mock_result):
            info = MetalMonitor.collect_gpu_info()

        assert info == {}

    def test_collect_gpu_info_timeout(self):
        import subprocess

        with patch(
            "fusion_bench.engine.metal_monitor.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="system_profiler", timeout=5),
        ):
            info = MetalMonitor.collect_gpu_info()

        assert info == {}

    def test_collect_gpu_info_no_displays(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"SPDisplaysDataType": []})

        with patch("fusion_bench.engine.metal_monitor.subprocess.run", return_value=mock_result):
            info = MetalMonitor.collect_gpu_info()

        assert info == {}

    def test_collect_system_info_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "17179869184\n10\nApple M2 Pro\n"

        with patch("fusion_bench.engine.metal_monitor.subprocess.run", return_value=mock_result):
            info = MetalMonitor.collect_system_info()

        assert info["total_memory_gb"] == 16.0
        assert info["cpu_cores"] == 10
        assert info["cpu_model"] == "Apple M2 Pro"

    def test_collect_system_info_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1

        with patch("fusion_bench.engine.metal_monitor.subprocess.run", return_value=mock_result):
            info = MetalMonitor.collect_system_info()

        assert info == {}

    def test_collect_system_info_timeout(self):
        import subprocess

        with patch(
            "fusion_bench.engine.metal_monitor.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="sysctl", timeout=3),
        ):
            info = MetalMonitor.collect_system_info()

        assert info == {}

    @pytest.mark.asyncio
    async def test_collect_mlx_stats_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models_loaded": 1,
            "total_requests": 42,
            "model_memory_used_formatted": "4.5 GB",
            "model_memory_max_formatted": "unlimited",
            "total_prompt_tokens": 1000,
            "total_tokens_generated": 5000,
        }

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        mock_httpx = MagicMock()
        mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            stats = await MetalMonitor.collect_mlx_stats("http://localhost:11432")

        assert stats["models_loaded"] == 1
        assert stats["total_requests"] == 42

    @pytest.mark.asyncio
    async def test_collect_mlx_stats_failure(self):
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("conn refused"))

        mock_httpx = MagicMock()
        mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            stats = await MetalMonitor.collect_mlx_stats()

        assert stats == {}

    def test_collect_power_info_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Battery: 95%"

        with patch("fusion_bench.engine.metal_monitor.subprocess.run", return_value=mock_result):
            info = MetalMonitor.collect_power_info()

        assert "power_stats" in info

    def test_collect_power_info_failure(self):
        import subprocess

        with patch(
            "fusion_bench.engine.metal_monitor.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pmset", timeout=3),
        ):
            info = MetalMonitor.collect_power_info()

        assert info == {}

    @pytest.mark.asyncio
    async def test_collect_all(self):
        p1 = patch.object(MetalMonitor, "collect_gpu_info", return_value={"gpu_model": "M2"})
        p2 = patch.object(MetalMonitor, "collect_system_info", return_value={"cpu_cores": 10})
        p3 = patch.object(
            MetalMonitor,
            "collect_mlx_stats",
            new_callable=AsyncMock,
            return_value={"models_loaded": 1},
        )
        p4 = patch.object(MetalMonitor, "collect_power_info", return_value={"power_stats": "ok"})
        with p1, p2, p3, p4:
            monitor = MetalMonitor()
            data = await monitor.collect_all()

        assert data["gpu"]["gpu_model"] == "M2"
        assert data["system"]["cpu_cores"] == 10
        assert data["mlx"]["models_loaded"] == 1
        assert data["power"]["power_stats"] == "ok"

    def test_format_report(self):
        data = {
            "gpu": {
                "gpu_model": "M2 Pro",
                "gpu_cores": 16,
                "metal_family": "Metal 3",
                "vram": "Dynamic",
            },
            "system": {"total_memory_gb": 16.0, "cpu_cores": 10, "cpu_model": "M2 Pro"},
            "mlx": {
                "models_loaded": 1,
                "total_requests": 42,
                "model_memory_used": "4.5 GB",
                "model_memory_max": "unlimited",
            },
        }
        report = MetalMonitor.format_report(data)
        assert "M2 Pro" in report
        assert "16.0 GB" in report


# ── LMEvalTaskRunner ──


class TestLMEvalTaskRunner:
    def test_init_default(self):
        runner = LMEvalTaskRunner(model="test-model")
        assert runner.model_name == "test-model"

    def test_init_with_tasks_dir(self, tmp_path):
        runner = LMEvalTaskRunner(model="test-model", tasks_dir=str(tmp_path))
        assert runner.tasks_dir == tmp_path

    def test_list_tasks_no_dir(self, tmp_path):
        runner = LMEvalTaskRunner(model="test-model", tasks_dir=str(tmp_path / "nonexistent"))
        assert runner.list_tasks() == []

    def test_list_tasks_empty_dir(self, tmp_path):
        runner = LMEvalTaskRunner(model="test-model", tasks_dir=str(tmp_path))
        assert runner.list_tasks() == []

    def test_list_tasks_with_yaml(self, tmp_path):
        task_dir = tmp_path / "mmlu"
        task_dir.mkdir()
        task_file = task_dir / "mmlu.yaml"
        task_file.write_text("task: mmlu\ngroup: knowledge\ndescription: Test\n")

        runner = LMEvalTaskRunner(model="test-model", tasks_dir=str(tmp_path))
        tasks = runner.list_tasks()

        assert len(tasks) == 1
        assert tasks[0]["name"] == "mmlu"

    def test_format_prompt_with_template(self):
        result = LMEvalTaskRunner._format_prompt(
            {"question": "What is 2+2?", "subject": "math"},
            "Question about {subject}: {question}",
        )
        assert "math" in result
        assert "2+2" in result

    def test_format_prompt_empty_template(self):
        result = LMEvalTaskRunner._format_prompt(
            {"question": "What is 2+2?"},
            "",
        )
        assert "2+2" in result

    def test_format_prompt_key_error(self):
        result = LMEvalTaskRunner._format_prompt(
            {"text": "hello"},
            "{nonexistent_var}",
        )
        assert result == "hello"

    def test_format_target_with_template(self):
        result = LMEvalTaskRunner._format_target(
            {"answer": "4"},
            "{answer}",
        )
        assert result == "4"

    def test_format_target_empty_template(self):
        result = LMEvalTaskRunner._format_target(
            {"answer": "42"},
            "",
        )
        assert result == "42"

    def test_format_target_label(self):
        result = LMEvalTaskRunner._format_target(
            {"label": "positive"},
            "",
        )
        assert result == "positive"

    def test_format_target_none_value(self):
        result = LMEvalTaskRunner._format_target(
            {"answer": None},
            "",
        )
        assert result == ""

    def test_normalize(self):
        assert LMEvalTaskRunner._normalize("  Hello, World!  ") == "hello world"
        assert LMEvalTaskRunner._normalize("A) Answer") == "a answer"
        assert LMEvalTaskRunner._normalize("") == ""

    @pytest.mark.asyncio
    async def test_run_task_not_found(self):
        runner = LMEvalTaskRunner(model="test-model", tasks_dir="")
        result = await runner.run_task("nonexistent")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_run_benchmark(self):
        runner = LMEvalTaskRunner(model="test-model", tasks_dir="")
        runner.run_task = AsyncMock(return_value={"task": "mmlu", "metrics": {}})

        results = await runner.run_benchmark(["mmlu"])
        assert len(results) == 1

    def test_load_task_none_dir(self):
        runner = LMEvalTaskRunner(model="test-model", tasks_dir="")
        assert runner._load_task("anything") is None

    def test_load_task_not_found(self, tmp_path):
        runner = LMEvalTaskRunner(model="test-model", tasks_dir=str(tmp_path))
        assert runner._load_task("nonexistent") is None

    def test_load_task_found(self, tmp_path):
        task_dir = tmp_path / "mmlu"
        task_dir.mkdir()
        task_file = task_dir / "mmlu.yaml"
        task_file.write_text("task: mmlu\ndataset_path: test\n")

        runner = LMEvalTaskRunner(model="test-model", tasks_dir=str(tmp_path))
        result = runner._load_task("mmlu")
        assert result is not None
        assert result["task"] == "mmlu"
