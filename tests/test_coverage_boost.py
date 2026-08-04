"""Tests to boost coverage to 90%+ — CLI dispatch, task_runner, gate_engine, bench_site."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fusion_bench.core.models import (
    EvalLevel,
    GateResult,
    GateTier,
    QualityGate,
    SuiteResult,
)
from fusion_bench.core.plugin_base import CaseResult, EvalResult, TaskConfig
from fusion_bench.core.registry import gate_registry

# ── CLI dispatch coverage (lines 123-142, 207-245, 250-262, 267-287,
#    292-321, 326-336, 343-363, 390-393) ──


class TestCLIDispatch:
    """Cover main() dispatch and cmd_run/cmd_tune/cmd_compare/cmd_speed/cmd_quant/cmd_suite/cmd_security."""

    @pytest.mark.asyncio
    async def test_cmd_run_success(self, capsys, tmp_path):
        from fusion_bench.cli import cmd_run

        mock_result = {"task": "mmlu", "results": {"accuracy": 0.65}, "model": "m1"}
        with patch(
            "fusion_bench.engine.task_runner.LMEvalTaskRunner.run_task",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            args = MagicMock(
                task="mmlu",
                model="m1",
                mlx_url="http://localhost:11432/v1",
                max_samples=0,
                output="",
            )
            await cmd_run(args)

        out = capsys.readouterr().out
        assert "mmlu" in out

    @pytest.mark.asyncio
    async def test_cmd_run_with_output(self, capsys, tmp_path):
        from fusion_bench.cli import cmd_run

        out_file = tmp_path / "result.json"
        mock_result = {"task": "mmlu", "results": {"accuracy": 0.65}}
        with patch(
            "fusion_bench.engine.task_runner.LMEvalTaskRunner.run_task",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            args = MagicMock(
                task="mmlu",
                model="m1",
                mlx_url="http://localhost:11432/v1",
                max_samples=0,
                output=str(out_file),
            )
            await cmd_run(args)

        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert data["task"] == "mmlu"

    @pytest.mark.asyncio
    async def test_cmd_tune_success(self, capsys, tmp_path):
        from fusion_bench.cli import cmd_tune
        from fusion_bench.optimizer.tuner import TuneResult

        mock_result = TuneResult(
            best_config={"batch_size": 32, "max_tokens": 256},
            best_speed=45.0,
            top3_configs=[{"batch_size": 32, "max_tokens": 256}],
            memory_saving_config={"batch_size": 8},
            balanced_config={"batch_size": 16},
        )
        with patch(
            "fusion_bench.optimizer.tuner.ParameterTuner.tune",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            args = MagicMock(
                model="m1",
                mlx_url="http://localhost:11432/v1",
                max_combinations=12,
                output="",
            )
            await cmd_tune(args)

        out = capsys.readouterr().out
        assert "Best config" in out
        assert "45.0" in out

    @pytest.mark.asyncio
    async def test_cmd_tune_with_output(self, capsys, tmp_path):
        from fusion_bench.cli import cmd_tune
        from fusion_bench.optimizer.tuner import TuneResult

        out_file = tmp_path / "tune.json"
        mock_result = TuneResult(
            best_config={"batch_size": 32},
            best_speed=45.0,
            top3_configs=[{"batch_size": 32}],
            memory_saving_config={"batch_size": 8},
            balanced_config={"batch_size": 16},
        )
        with patch(
            "fusion_bench.optimizer.tuner.ParameterTuner.tune",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            args = MagicMock(
                model="m1",
                mlx_url="http://localhost:11432/v1",
                max_combinations=12,
                output=str(out_file),
            )
            await cmd_tune(args)

        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert data["best_speed"] == 45.0

    @pytest.mark.asyncio
    async def test_cmd_speed_success(self, capsys, tmp_path):
        from fusion_bench.cli import cmd_speed
        from fusion_bench.engine.benchmark import BenchmarkResult, SpeedMetrics

        metrics = SpeedMetrics(
            decode_speed=40.0,
            prefill_speed=800.0,
            total_time=2.5,
            prefill_time=0.1,
            prompt_tokens=100,
            completion_tokens=200,
            peak_memory_mb=4096.0,
        )
        mock_results = [BenchmarkResult(model="m1", metrics=metrics, config={})]
        with patch(
            "fusion_bench.engine.benchmark.BenchmarkRunner.benchmark",
            new_callable=AsyncMock,
            return_value=mock_results,
        ):
            args = MagicMock(
                model="m1",
                mlx_url="http://localhost:11432/v1",
                runs=3,
                output="",
            )
            await cmd_speed(args)

        out = capsys.readouterr().out
        assert "40.0" in out

    @pytest.mark.asyncio
    async def test_cmd_speed_with_output(self, capsys, tmp_path):
        from fusion_bench.cli import cmd_speed
        from fusion_bench.engine.benchmark import BenchmarkResult, SpeedMetrics

        out_file = tmp_path / "speed.json"
        metrics = SpeedMetrics(
            decode_speed=40.0,
            prefill_speed=800.0,
            total_time=2.5,
            prefill_time=0.1,
            prompt_tokens=100,
            completion_tokens=200,
            peak_memory_mb=4096.0,
        )
        mock_results = [BenchmarkResult(model="m1", metrics=metrics, config={})]
        with patch(
            "fusion_bench.engine.benchmark.BenchmarkRunner.benchmark",
            new_callable=AsyncMock,
            return_value=mock_results,
        ):
            args = MagicMock(
                model="m1",
                mlx_url="http://localhost:11432/v1",
                runs=3,
                output=str(out_file),
            )
            await cmd_speed(args)

        assert out_file.exists()

    @pytest.mark.asyncio
    async def test_cmd_quant_success(self, capsys):
        from fusion_bench.cli import cmd_quant
        from fusion_bench.engine.benchmark import BenchmarkResult, SpeedMetrics

        metrics = SpeedMetrics(
            decode_speed=40.0,
            prefill_speed=800.0,
            total_time=2.5,
            prefill_time=0.1,
            prompt_tokens=100,
            completion_tokens=200,
            peak_memory_mb=4096.0,
        )
        mock_results = [BenchmarkResult(model="m1-mxfp4", metrics=metrics, config={})]
        with patch(
            "fusion_bench.engine.benchmark.BenchmarkRunner.benchmark",
            new_callable=AsyncMock,
            return_value=mock_results,
        ):
            args = MagicMock(
                model="m1",
                mlx_url="http://localhost:11432/v1",
                levels="mxfp4",
                output="",
            )
            await cmd_quant(args)

        out = capsys.readouterr().out
        assert "mxfp4" in out

    @pytest.mark.asyncio
    async def test_cmd_quant_with_output(self, capsys, tmp_path):
        from fusion_bench.cli import cmd_quant
        from fusion_bench.engine.benchmark import BenchmarkResult, SpeedMetrics

        out_file = tmp_path / "quant.json"
        metrics = SpeedMetrics(
            decode_speed=40.0,
            prefill_speed=800.0,
            total_time=2.5,
            prefill_time=0.1,
            prompt_tokens=100,
            completion_tokens=200,
            peak_memory_mb=4096.0,
        )
        mock_results = [BenchmarkResult(model="m1-mxfp4", metrics=metrics, config={})]
        with patch(
            "fusion_bench.engine.benchmark.BenchmarkRunner.benchmark",
            new_callable=AsyncMock,
            return_value=mock_results,
        ):
            args = MagicMock(
                model="m1",
                mlx_url="http://localhost:11432/v1",
                levels="mxfp4",
                output=str(out_file),
            )
            await cmd_quant(args)

        assert out_file.exists()

    @pytest.mark.asyncio
    async def test_cmd_quant_empty_result(self, capsys):
        from fusion_bench.cli import cmd_quant

        with patch(
            "fusion_bench.engine.benchmark.BenchmarkRunner.benchmark",
            new_callable=AsyncMock,
            return_value=[],
        ):
            args = MagicMock(
                model="m1",
                mlx_url="http://localhost:11432/v1",
                levels="mxfp4",
                output="",
            )
            await cmd_quant(args)

        out = capsys.readouterr().out
        assert "mxfp4" in out

    @pytest.mark.asyncio
    async def test_cmd_compare_success(self, capsys):
        from fusion_bench.cli import cmd_compare

        mock_results = [{"metrics": {"accuracy": 0.65}}]
        with patch(
            "fusion_bench.engine.task_runner.LMEvalTaskRunner.run_benchmark",
            new_callable=AsyncMock,
            return_value=mock_results,
        ):
            args = MagicMock(
                models="model-a,model-b",
                tasks="mmlu",
                mlx_url="http://localhost:11432/v1",
                output="",
            )
            await cmd_compare(args)

        out = capsys.readouterr().out
        assert "model-a" in out

    @pytest.mark.asyncio
    async def test_cmd_compare_with_output(self, capsys, tmp_path):
        from fusion_bench.cli import cmd_compare

        out_file = tmp_path / "compare.json"
        mock_results = [{"metrics": {"accuracy": 0.65}}]
        with patch(
            "fusion_bench.engine.task_runner.LMEvalTaskRunner.run_benchmark",
            new_callable=AsyncMock,
            return_value=mock_results,
        ):
            args = MagicMock(
                models="model-a",
                tasks="mmlu",
                mlx_url="http://localhost:11432/v1",
                output=str(out_file),
            )
            await cmd_compare(args)

        assert out_file.exists()

    @pytest.mark.asyncio
    async def test_cmd_suite_success(self, capsys):
        from fusion_bench.cli import cmd_suite

        suite_result = SuiteResult(
            suite_id="suite-1",
            model="m1",
            level=EvalLevel.L1_MODEL,
            results=[
                {
                    "executor_key": "speed",
                    "metric_name": "decode_speed",
                    "metric_value": 25.0,
                    "errors": [],
                }
            ],
            gate_results=[],
            duration_seconds=1.0,
        )
        with (
            patch(
                "fusion_bench.orchestrator.pipeline.Pipeline.run_suite",
                new_callable=AsyncMock,
                return_value=suite_result,
            ),
            patch("fusion_bench.storage.trace_store.TraceStore"),
        ):
            args = MagicMock(
                suite_name="l1-quick",
                model="m1",
                mlx_url="http://localhost:11432/v1",
                level="L1",
                tier="experimental",
                output="",
            )
            await cmd_suite(args)

        out = capsys.readouterr().out
        assert "PASS" in out or "suite-1" in out

    @pytest.mark.asyncio
    async def test_cmd_suite_with_output(self, capsys, tmp_path):
        from fusion_bench.cli import cmd_suite

        out_file = tmp_path / "suite.json"
        suite_result = SuiteResult(
            suite_id="suite-1",
            model="m1",
            level=EvalLevel.L1_MODEL,
            results=[
                {
                    "executor_key": "speed",
                    "metric_name": "decode_speed",
                    "metric_value": 25.0,
                    "errors": [],
                }
            ],
            gate_results=[],
            duration_seconds=1.0,
        )
        with (
            patch(
                "fusion_bench.orchestrator.pipeline.Pipeline.run_suite",
                new_callable=AsyncMock,
                return_value=suite_result,
            ),
            patch("fusion_bench.storage.trace_store.TraceStore"),
        ):
            args = MagicMock(
                suite_name="l1-quick",
                model="m1",
                mlx_url="http://localhost:11432/v1",
                level="L1",
                tier="experimental",
                output=str(out_file),
            )
            await cmd_suite(args)

        assert out_file.exists()

    @pytest.mark.asyncio
    async def test_cmd_suite_with_gates(self, capsys):
        from fusion_bench.cli import cmd_suite

        gate_result = GateResult(
            gate_id="speed-min",
            gate_name="Min decode speed",
            tier=GateTier.EXPERIMENTAL,
            metric_name="decode_speed",
            metric_value=25.0,
            threshold=5.0,
            passed=True,
        )
        suite_result = SuiteResult(
            suite_id="suite-1",
            model="m1",
            level=EvalLevel.L1_MODEL,
            results=[
                {
                    "executor_key": "speed",
                    "metric_name": "decode_speed",
                    "metric_value": 25.0,
                    "errors": [],
                }
            ],
            gate_results=[gate_result],
            duration_seconds=1.0,
        )
        with (
            patch(
                "fusion_bench.orchestrator.pipeline.Pipeline.run_suite",
                new_callable=AsyncMock,
                return_value=suite_result,
            ),
            patch("fusion_bench.storage.trace_store.TraceStore"),
        ):
            args = MagicMock(
                suite_name="l1-quick",
                model="m1",
                mlx_url="http://localhost:11432/v1",
                level="L1",
                tier="experimental",
                output="",
            )
            await cmd_suite(args)

        out = capsys.readouterr().out
        assert "Quality Gates" in out

    @pytest.mark.asyncio
    async def test_cmd_security_with_output(self, capsys, tmp_path):
        from fusion_bench.cli import cmd_security

        out_file = tmp_path / "security.json"
        mock_result = EvalResult(
            task_id="security-injection",
            executor_key="security",
            model="m1",
            level="L3",
            metric_name="safety_rate",
            metric_value=0.85,
            cases=[
                CaseResult(input_text="test probe", actual="I cannot", score=1.0, passed=True),
            ],
        )
        with patch(
            "fusion_bench.executors.security_executor.SecurityExecutor.run",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            args = MagicMock(
                mlx_url="http://localhost:11432/v1",
                model="m1",
                probe_set="injection",
                output=str(out_file),
            )
            await cmd_security(args)

        assert out_file.exists()


# ── Task runner coverage (lines 96-111, 131, 151-220, 252-253) ──


class TestTaskRunnerAdvanced:
    """Cover run_task, _evaluate_task, _load_task, _format_prompt/target edge cases."""

    @pytest.mark.asyncio
    async def test_run_task_not_found(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        runner = LMEvalTaskRunner(model="m1", tasks_dir="/nonexistent/path")
        result = await runner.run_task("nonexistent_task")
        assert result["error"] is not None
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_run_task_found_but_no_dataset(self, tmp_path):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        task_dir = tmp_path / "tasks"
        task_dir.mkdir()
        sub = task_dir / "mmlu"
        sub.mkdir()
        (sub / "mmlu.yaml").write_text("task: mmlu\ndataset_path: ''\n")

        runner = LMEvalTaskRunner(model="m1", tasks_dir=str(task_dir))
        result = await runner.run_task("mmlu")
        assert "error" in result or "results" in result

    @pytest.mark.asyncio
    async def test_run_task_with_model_and_close(self, tmp_path):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        task_dir = tmp_path / "tasks"
        task_dir.mkdir()
        sub = task_dir / "mmlu"
        sub.mkdir()
        (sub / "mmlu.yaml").write_text("task: mmlu\ndataset_path: fake_ds\nnum_fewshot: 0\n")

        mock_model = MagicMock()
        mock_model.generate_until = AsyncMock(return_value=["A"])
        mock_model.get_usage_report = MagicMock(return_value={"tokens": 100})
        mock_model.close = AsyncMock()

        with (
            patch("fusion_bench.engine.task_runner.MLXModel", return_value=mock_model),
            patch(
                "fusion_bench.engine.task_runner.LMEvalTaskRunner._evaluate_task",
                new_callable=AsyncMock,
                return_value={
                    "results": [],
                    "metrics": {"accuracy": 0.5},
                    "timing": {},
                },
            ),
        ):
            runner = LMEvalTaskRunner(model="m1", tasks_dir=str(task_dir))
            result = await runner.run_task("mmlu")

        assert result["task"] == "mmlu"
        assert result["model"] == "m1"

    def test_load_task_no_tasks_dir(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        runner = LMEvalTaskRunner(model="m1", tasks_dir="")
        result = runner._load_task("anything")
        assert result is None

    def test_format_prompt_empty_template(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        result = LMEvalTaskRunner._format_prompt({"text": "hello"}, "")
        assert result == "hello"

    def test_format_prompt_with_question_fallback(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        result = LMEvalTaskRunner._format_prompt({"question": "what?"}, "")
        assert result == "what?"

    def test_format_prompt_with_template(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        result = LMEvalTaskRunner._format_prompt({"x": "val"}, "{x}")
        assert result == "val"

    def test_format_prompt_key_error(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        result = LMEvalTaskRunner._format_prompt({"x": "val"}, "{missing}")
        assert result == ""

    def test_format_prompt_key_error_with_text(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        result = LMEvalTaskRunner._format_prompt({"x": "val", "text": "fallback"}, "{missing}")
        assert result == "fallback"

    def test_format_target_empty_template_answer(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        result = LMEvalTaskRunner._format_target({"answer": "A"}, "")
        assert result == "A"

    def test_format_target_label_fallback(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        result = LMEvalTaskRunner._format_target({"label": "B"}, "")
        assert result == "B"

    def test_format_target_none_answer(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        result = LMEvalTaskRunner._format_target({"answer": None}, "")
        assert result == ""

    def test_format_target_with_template(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        result = LMEvalTaskRunner._format_target({"ans": "yes"}, "{ans}")
        assert result == "yes"

    def test_format_target_key_error(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        result = LMEvalTaskRunner._format_target({"x": "val"}, "{missing}")
        assert result == ""

    def test_format_target_key_error_with_answer(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        result = LMEvalTaskRunner._format_target({"x": "val", "answer": "fallback"}, "{missing}")
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_evaluate_task_no_dataset_path(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        runner = LMEvalTaskRunner(model="m1")
        mock_model = MagicMock()
        result = await runner._evaluate_task(mock_model, {"dataset_path": ""}, 0, 0)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_evaluate_task_dataset_load_fail(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        runner = LMEvalTaskRunner(model="m1")
        mock_model = MagicMock()

        with patch.dict(
            "sys.modules",
            {"datasets": MagicMock(load_dataset=MagicMock(side_effect=ImportError("no datasets")))},
        ):
            result = await runner._evaluate_task(
                mock_model,
                {"dataset_path": "fake_ds"},
                0,
                0,
            )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_evaluate_task_success(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        runner = LMEvalTaskRunner(model="m1")
        mock_model = MagicMock()
        mock_model.generate_until = AsyncMock(return_value=["A"])

        mock_ds = [
            {"text": "What is 2+2?", "answer": "4"},
            {"text": "Capital of France?", "answer": "paris"},
        ]

        with patch.dict(
            "sys.modules",
            {"datasets": MagicMock(load_dataset=MagicMock(return_value=mock_ds))},
        ):
            result = await runner._evaluate_task(
                mock_model,
                {"dataset_path": "fake_ds", "doc_to_text": "", "doc_to_target": ""},
                10,
                0,
            )

        assert "metrics" in result
        assert "accuracy" in result["metrics"]

    @pytest.mark.asyncio
    async def test_evaluate_task_with_max_samples(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        runner = LMEvalTaskRunner(model="m1")
        mock_model = MagicMock()
        mock_model.generate_until = AsyncMock(return_value=["A"])

        mock_ds = [{"text": f"Q{i}", "answer": f"A{i}"} for i in range(20)]

        with patch.dict(
            "sys.modules",
            {"datasets": MagicMock(load_dataset=MagicMock(return_value=mock_ds))},
        ):
            result = await runner._evaluate_task(
                mock_model,
                {"dataset_path": "fake_ds", "doc_to_text": "", "doc_to_target": ""},
                5,
                0,
            )

        assert result["metrics"]["total"] <= 5

    @pytest.mark.asyncio
    async def test_evaluate_task_generate_error(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        runner = LMEvalTaskRunner(model="m1")
        mock_model = MagicMock()
        mock_model.generate_until = AsyncMock(side_effect=RuntimeError("timeout"))

        mock_ds = [{"text": "Q1", "answer": "A1"}]

        with patch.dict(
            "sys.modules",
            {"datasets": MagicMock(load_dataset=MagicMock(return_value=mock_ds))},
        ):
            result = await runner._evaluate_task(
                mock_model,
                {"dataset_path": "fake_ds", "doc_to_text": "", "doc_to_target": ""},
                10,
                0,
            )

        assert result["metrics"]["correct"] == 0

    @pytest.mark.asyncio
    async def test_evaluate_task_empty_prompt_skip(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        runner = LMEvalTaskRunner(model="m1")
        mock_model = MagicMock()

        mock_ds = [{"no_text_key": "val"}]

        with patch.dict(
            "sys.modules",
            {"datasets": MagicMock(load_dataset=MagicMock(return_value=mock_ds))},
        ):
            result = await runner._evaluate_task(
                mock_model,
                {"dataset_path": "fake_ds", "doc_to_text": "", "doc_to_target": ""},
                10,
                0,
            )

        assert result["metrics"]["total"] == 0

    def test_normalize(self):
        from fusion_bench.engine.task_runner import LMEvalTaskRunner

        assert LMEvalTaskRunner._normalize("  Hello, World!  ") == "hello world"
        assert LMEvalTaskRunner._normalize("A-B_C") == "abc"
        assert LMEvalTaskRunner._normalize("  multiple   spaces  ") == "multiple spaces"


# ── GateEngine coverage (lines 44-52, 76) — registered gates path ──


class TestGateEngineRegistered:
    """Cover the gate_registry path in evaluate()."""

    def test_evaluate_with_registered_gate(self):
        from fusion_bench.orchestrator.gate_engine import GateEngine

        test_gate = QualityGate(
            "reg-test",
            "Registered test gate",
            GateTier.EXPERIMENTAL,
            "test_metric",
            ">=",
            10.0,
        )
        gate_registry.register("reg-test", test_gate)
        try:
            ge = GateEngine()
            results = ge.evaluate("any", "test_metric", 15.0)
            assert any(r.gate_id == "reg-test" for r in results)
        finally:
            gate_registry.unregister("reg-test")

    def test_evaluate_registered_gate_class(self):
        from fusion_bench.orchestrator.gate_engine import GateEngine

        test_gate = QualityGate(
            "cls-gate",
            "Class gate",
            GateTier.EXPERIMENTAL,
            "cls_metric",
            ">=",
            5.0,
        )
        gate_registry.register("cls-gate", test_gate)
        try:
            ge = GateEngine()
            results = ge.evaluate("any", "cls_metric", 10.0)
            assert len(results) >= 1
        finally:
            gate_registry.unregister("cls-gate")

    def test_evaluate_registered_non_gate_ignored(self):
        from fusion_bench.orchestrator.gate_engine import GateEngine

        gate_registry.register("bad-entry", "not a gate object")
        try:
            ge = GateEngine()
            results = ge.evaluate("any", "any_metric", 1.0)
            assert not any(r.gate_id == "bad-entry" for r in results)
        finally:
            gate_registry.unregister("bad-entry")

    def test_eval_one_level_mismatch(self):
        from fusion_bench.orchestrator.gate_engine import GateEngine

        gate = QualityGate(
            "lvl-gate",
            "Level gate",
            GateTier.EXPERIMENTAL,
            "lvl_metric",
            ">=",
            5.0,
            level=EvalLevel.L3_APP,
        )
        engine = GateEngine()
        result = engine._eval_one(
            gate,
            "any",
            "lvl_metric",
            10.0,
            EvalLevel.L1_MODEL,
        )
        assert result is None

    def test_eval_one_no_level_gate(self):
        from fusion_bench.orchestrator.gate_engine import GateEngine

        gate = QualityGate(
            "no-lvl",
            "No level gate",
            GateTier.EXPERIMENTAL,
            "nolvl_metric",
            ">=",
            5.0,
        )
        engine = GateEngine()
        result = engine._eval_one(
            gate,
            "any",
            "nolvl_metric",
            10.0,
            EvalLevel.L1_MODEL,
        )
        assert result is not None
        assert result.passed


# ── BenchSite coverage (lines 66, 93-94, 98, 107-108, 115-118, 196, 208-211) ──


class TestBenchSiteEntry:
    """Cover BenchSiteEntry.to_dict() with optional fields."""

    def test_to_dict_with_all_optionals(self):
        from fusion_bench.reporter.bench_site import BenchSiteEntry

        entry = BenchSiteEntry(
            chip_name="M2",
            memory_gb=16,
            gpu_cores=10,
            os_version="macOS 14.0",
            model_name="m1",
            quantization="mxfp4",
            pp_tps=100.0,
            tg_tps=30.0,
            ttft_ms=50.0,
            peak_memory_gb=4.5,
            batching_results=[{"batch": 1}],
            owner_hash="abc123",
        )
        d = entry.to_dict()
        assert d["ttft_ms"] == 50.0
        assert d["peak_memory_gb"] == 4.5
        assert d["batching_results"] == [{"batch": 1}]
        assert d["owner_hash"] == "abc123"

    def test_to_dict_without_optionals(self):
        from fusion_bench.reporter.bench_site import BenchSiteEntry

        entry = BenchSiteEntry(chip_name="M2", memory_gb=16, gpu_cores=10)
        d = entry.to_dict()
        assert "ttft_ms" not in d
        assert "peak_memory_gb" not in d
        assert "batching_results" not in d
        assert "owner_hash" not in d


class TestBenchSiteReporter:
    """Cover detect_hardware branches and from_benchmark_result."""

    def test_detect_hardware_fallback(self):
        from fusion_bench.reporter.bench_site import BenchSiteReporter

        # ruff: noqa: SIM117 — nested with is clearer here
        with patch("subprocess.run", side_effect=Exception("no system_profiler")):
            with patch("fusion_bench.reporter.bench_site.platform") as mock_plat:
                mock_plat.mac_ver.return_value = ("14.0", "", "")
                mock_plat.processor.return_value = "Apple M2"
                info = BenchSiteReporter.detect_hardware()

        assert "chip_name" in info

    def test_detect_hardware_no_displays(self):
        from fusion_bench.reporter.bench_site import BenchSiteReporter

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"SPDisplaysDataType": []})

        with patch("subprocess.run", return_value=mock_result):
            info = BenchSiteReporter.detect_hardware()

        assert "chip_name" in info

    def test_detect_hardware_no_psutil(self):
        from fusion_bench.reporter.bench_site import BenchSiteReporter

        mock_gpu = MagicMock()
        mock_gpu.returncode = 0
        mock_gpu.stdout = json.dumps({"SPDisplaysDataType": [{"sppci_model": "Apple M2 Pro", "sppci_cores": 16}]})

        mock_mem = MagicMock()
        mock_mem.returncode = 0
        mock_mem.stdout = "17179869184\n"

        call_count = 0

        def mock_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if "SPDisplaysDataType" in cmd:
                return mock_gpu
            if "hw.memsize" in cmd:
                return mock_mem
            return MagicMock(returncode=1)

        # ruff: noqa: SIM117 — nested with is clearer here
        with patch("subprocess.run", side_effect=mock_run), patch.dict("sys.modules", {"psutil": None}):
            with patch("fusion_bench.reporter.bench_site.platform") as mock_plat:
                mock_plat.mac_ver.return_value = ("14.0", "", "")
                info = BenchSiteReporter.detect_hardware()

        assert info["chip_name"] == "M2 Pro"
        assert info["memory_gb"] > 0

    def test_from_benchmark_result_with_quant(self):
        from fusion_bench.engine.benchmark import BenchmarkResult, SpeedMetrics
        from fusion_bench.reporter.bench_site import BenchSiteReporter

        metrics = SpeedMetrics(
            decode_speed=40.0,
            prefill_speed=800.0,
            total_time=2.5,
            prefill_time=0.1,
            prompt_tokens=100,
            completion_tokens=200,
            peak_memory_mb=4096.0,
        )
        result = BenchmarkResult(
            model="qwen3.5-9b-mxfp4",
            metrics=metrics,
            config={"max_tokens": 2048},
        )

        with patch.object(
            BenchSiteReporter,
            "detect_hardware",
            return_value={
                "chip_name": "M2",
                "chip_variant": "",
                "memory_gb": 16,
                "gpu_cores": 10,
                "os_version": "macOS 14.0",
            },
        ):
            entry = BenchSiteReporter.from_benchmark_result(result)

        assert entry.model_name == "qwen3.5-9b"
        assert entry.quantization == "mxfp4"

    def test_from_benchmark_result_no_quant(self):
        from fusion_bench.engine.benchmark import BenchmarkResult, SpeedMetrics
        from fusion_bench.reporter.bench_site import BenchSiteReporter

        metrics = SpeedMetrics(
            decode_speed=40.0,
            prefill_speed=800.0,
            total_time=2.5,
            prefill_time=0.1,
            prompt_tokens=100,
            completion_tokens=200,
            peak_memory_mb=4096.0,
        )
        result = BenchmarkResult(
            model="qwen3.5-9b",
            metrics=metrics,
            config={},
        )

        with patch.object(
            BenchSiteReporter,
            "detect_hardware",
            return_value={
                "chip_name": "M2",
                "chip_variant": "",
                "memory_gb": 16,
                "gpu_cores": 10,
                "os_version": "macOS 14.0",
            },
        ):
            entry = BenchSiteReporter.from_benchmark_result(result)

        assert entry.model_name == "qwen3.5-9b"
        assert entry.quantization == "mxfp8"


class TestBenchSiteSubmitter:
    """Cover submit and submit_batch."""

    @pytest.mark.asyncio
    async def test_submit_success(self):
        from fusion_bench.reporter.bench_site import BenchSiteEntry, BenchSiteSubmitter

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": 42, "url": "https://bench.dpdns.org/b/42"}

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        mock_httpx = MagicMock()
        mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

        entry = BenchSiteEntry(chip_name="M2", memory_gb=16, gpu_cores=10)
        submitter = BenchSiteSubmitter()

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = await submitter.submit(entry)

        assert result["status"] == "created"
        assert result["id"] == 42

    @pytest.mark.asyncio
    async def test_submit_duplicate(self):
        from fusion_bench.reporter.bench_site import BenchSiteEntry, BenchSiteSubmitter

        mock_resp = MagicMock()
        mock_resp.status_code = 409
        mock_resp.json.return_value = {
            "existing_id": 1,
            "existing_url": "https://bench.dpdns.org/b/1",
        }

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        mock_httpx = MagicMock()
        mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

        entry = BenchSiteEntry(chip_name="M2", memory_gb=16, gpu_cores=10)
        submitter = BenchSiteSubmitter()

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = await submitter.submit(entry)

        assert result["status"] == "duplicate"

    @pytest.mark.asyncio
    async def test_submit_error_status(self):
        from fusion_bench.reporter.bench_site import BenchSiteEntry, BenchSiteSubmitter

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        mock_httpx = MagicMock()
        mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

        entry = BenchSiteEntry(chip_name="M2", memory_gb=16, gpu_cores=10)
        submitter = BenchSiteSubmitter()

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = await submitter.submit(entry)

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_submit_exception(self):
        from fusion_bench.reporter.bench_site import BenchSiteEntry, BenchSiteSubmitter

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))

        mock_httpx = MagicMock()
        mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

        entry = BenchSiteEntry(chip_name="M2", memory_gb=16, gpu_cores=10)
        submitter = BenchSiteSubmitter()

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = await submitter.submit(entry)

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_submit_batch(self, capsys):
        from fusion_bench.reporter.bench_site import BenchSiteEntry, BenchSiteSubmitter

        mock_resp_created = MagicMock()
        mock_resp_created.status_code = 201
        mock_resp_created.json.return_value = {"id": 1, "url": "http://b/1"}

        mock_resp_dup = MagicMock()
        mock_resp_dup.status_code = 409
        mock_resp_dup.json.return_value = {
            "existing_id": 2,
            "existing_url": "http://b/2",
        }

        mock_resp_err = MagicMock()
        mock_resp_err.status_code = 500
        mock_resp_err.text = "err"

        call_count = 0

        async def mock_post(url, json=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_resp_created
            elif call_count == 2:
                return mock_resp_dup
            return mock_resp_err

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = mock_post

        mock_httpx = MagicMock()
        mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

        entries = [
            BenchSiteEntry(
                chip_name="M2",
                model_name="m1",
                quantization="mxfp4",
                memory_gb=16,
                gpu_cores=10,
            ),
            BenchSiteEntry(
                chip_name="M2",
                model_name="m2",
                quantization="mxfp8",
                memory_gb=16,
                gpu_cores=10,
            ),
            BenchSiteEntry(
                chip_name="M2",
                model_name="m3",
                quantization="mixed",
                memory_gb=16,
                gpu_cores=10,
            ),
        ]
        submitter = BenchSiteSubmitter()

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            results = await submitter.submit_batch(entries)

        assert len(results) == 3
        assert results[0]["status"] == "created"
        assert results[1]["status"] == "duplicate"
        assert results[2]["status"] == "error"


# ── BenchSiteDB coverage (lines 60-71, 173->177, 243-244, 247-251, 249-250) ──


class TestBenchSiteDBAdvanced:
    """Cover auto-detect paths, insert_from_benchmark with quant, _detect_hardware branches."""

    def test_insert_from_benchmark_with_quant(self, tmp_path):
        from fusion_bench.engine.benchmark import BenchmarkResult, SpeedMetrics
        from fusion_bench.reporter.bench_site_db import BenchSiteDB

        db = BenchSiteDB(db_path=str(tmp_path / "test.db"))
        metrics = SpeedMetrics(
            decode_speed=40.0,
            prefill_speed=800.0,
            total_time=2.5,
            prefill_time=0.1,
            prompt_tokens=100,
            completion_tokens=200,
            peak_memory_mb=4096.0,
        )
        result = BenchmarkResult(
            model="qwen3.5-9b-mxfp4",
            metrics=metrics,
            config={"max_tokens": 2048},
        )
        row_id = db.insert_from_benchmark(
            result,
            hw_info={
                "chip_name": "M2",
                "chip_variant": "",
                "memory_gb": 16,
                "gpu_cores": 10,
                "os_version": "macOS 14.0",
            },
        )
        assert row_id > 0
        db.close()

    def test_detect_hardware_success(self):
        from fusion_bench.reporter.bench_site_db import BenchSiteDB

        mock_subprocess = MagicMock()
        mock_gpu = MagicMock()
        mock_gpu.returncode = 0
        mock_gpu.stdout = json.dumps({"SPDisplaysDataType": [{"sppci_model": "Apple M3 Max", "sppci_cores": 30}]})
        mock_mem = MagicMock()
        mock_mem.returncode = 0
        mock_mem.stdout = "68719476736\n"

        call_count = 0

        def mock_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if "SPDisplaysDataType" in cmd:
                return mock_gpu
            if "hw.memsize" in cmd:
                return mock_mem
            return MagicMock(returncode=1)

        mock_subprocess.run = mock_run

        mock_platform = MagicMock()
        mock_platform.mac_ver.return_value = ("15.0", "", "")

        with patch.dict("sys.modules", {"subprocess": mock_subprocess, "platform": mock_platform}):
            info = BenchSiteDB._detect_hardware()

        assert info["chip_name"] == "M3 Max"
        assert info["gpu_cores"] == 30
        assert info["memory_gb"] > 0

    def test_detect_hardware_no_cores(self):
        from fusion_bench.reporter.bench_site_db import BenchSiteDB

        mock_subprocess = MagicMock()
        mock_gpu = MagicMock()
        mock_gpu.returncode = 0
        mock_gpu.stdout = json.dumps({"SPDisplaysDataType": [{"sppci_model": "Apple M2"}]})
        mock_mem = MagicMock()
        mock_mem.returncode = 1

        call_count = 0

        def mock_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if "SPDisplaysDataType" in cmd:
                return mock_gpu
            return mock_mem

        mock_subprocess.run = mock_run
        mock_platform = MagicMock()
        mock_platform.mac_ver.return_value = ("14.0", "", "")

        with patch.dict("sys.modules", {"subprocess": mock_subprocess, "platform": mock_platform}):
            info = BenchSiteDB._detect_hardware()

        assert info["gpu_cores"] == 0

    def test_detect_hardware_exception(self):
        from fusion_bench.reporter.bench_site_db import BenchSiteDB

        mock_subprocess = MagicMock()
        mock_subprocess.run = MagicMock(side_effect=Exception("no system_profiler"))
        mock_platform = MagicMock()
        mock_platform.mac_ver.return_value = ("14.0", "", "")

        with patch.dict("sys.modules", {"subprocess": mock_subprocess, "platform": mock_platform}):
            info = BenchSiteDB._detect_hardware()

        assert info["chip_name"] == "Apple Silicon"

    def test_detect_hardware_no_os(self):
        from fusion_bench.reporter.bench_site_db import BenchSiteDB

        mock_subprocess = MagicMock()
        mock_subprocess.run = MagicMock(side_effect=Exception("err"))
        mock_platform = MagicMock()
        mock_platform.mac_ver.return_value = ("", "", "")

        with patch.dict("sys.modules", {"subprocess": mock_subprocess, "platform": mock_platform}):
            info = BenchSiteDB._detect_hardware()

        assert info["os_version"] == ""

    def test_detect_hardware_memsize_fail(self):
        from fusion_bench.reporter.bench_site_db import BenchSiteDB

        mock_subprocess = MagicMock()
        mock_gpu = MagicMock()
        mock_gpu.returncode = 1
        mock_subprocess.run = MagicMock(return_value=mock_gpu)
        mock_platform = MagicMock()
        mock_platform.mac_ver.return_value = ("14.0", "", "")

        with patch.dict("sys.modules", {"subprocess": mock_subprocess, "platform": mock_platform}):
            info = BenchSiteDB._detect_hardware()

        assert info["chip_name"] == "Apple Silicon"


# ── Pipeline coverage (lines 121-122, 123->119) ──


class TestPipelineEdgeCases:
    """Cover remaining Pipeline edge cases."""

    @pytest.mark.asyncio
    async def test_pipeline_run_task_dict_conversion(self):
        from fusion_bench.core.plugin_base import (
            EvalResult,
            ExecutorPlugin,
            ExecutorType,
        )
        from fusion_bench.core.registry import executor_registry
        from fusion_bench.orchestrator.pipeline import Pipeline

        class SimpleExecutor(ExecutorPlugin):
            name = "simple"
            executor_type = ExecutorType.SPEED

            async def run(self, config: TaskConfig) -> EvalResult:
                return EvalResult(
                    task_id=config.task_id,
                    executor_key=self.name,
                    model=config.model,
                    level="L1",
                    metric_name="decode_speed",
                    metric_value=30.0,
                )

            def is_available(self) -> bool:
                return True

        with patch.object(executor_registry, "get_or_raise", return_value=SimpleExecutor):
            pipeline = Pipeline()
            result = await pipeline.run_suite(
                model="test",
                tasks=[
                    {
                        "executor_key": "simple",
                        "task_id": "t1",
                        "params": {"key": "val"},
                    }
                ],
                level="L1",
            )

        assert len(result.results) == 1
