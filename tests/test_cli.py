"""Tests for CLI v2 subcommands."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fusion_bench.cli import (
    cmd_gates,
    cmd_list_executors,
    cmd_list_suites,
    cmd_list_tasks,
    cmd_security,
    cmd_suite,
    cmd_traces,
)


def _make_args(**kwargs):
    return MagicMock(**kwargs)


class TestCLIListSuites:
    def test_list_suites(self, capsys):
        cmd_list_suites(_make_args())
        out = capsys.readouterr().out
        assert "l1-quick" in out or "l1-full" in out


class TestCLIListExecutors:
    def test_list_executors(self, capsys):
        from fusion_bench.executors import register_all

        register_all()
        cmd_list_executors(_make_args())
        out = capsys.readouterr().out
        assert "speed" in out


class TestCLIListTasks:
    def test_list_tasks_no_tasks(self, capsys):
        with patch(
            "fusion_bench.engine.task_runner.LMEvalTaskRunner.list_tasks",
            return_value=[],
        ):
            cmd_list_tasks(_make_args(mlx_url="http://localhost:11432/v1", pattern=""))

        out = capsys.readouterr().out
        assert "No tasks found" in out

    def test_list_tasks_with_tasks(self, capsys):
        tasks = [
            {
                "name": "mmlu",
                "group": "knowledge",
                "num_fewshot": 0,
                "dataset": "cais/mmlu",
            }
        ]
        with patch(
            "fusion_bench.engine.task_runner.LMEvalTaskRunner.list_tasks",
            return_value=tasks,
        ):
            cmd_list_tasks(_make_args(mlx_url="http://localhost:11432/v1", pattern=""))

        out = capsys.readouterr().out
        assert "mmlu" in out

    def test_list_tasks_with_pattern(self, capsys):
        tasks = [
            {
                "name": "mmlu",
                "group": "knowledge",
                "num_fewshot": 0,
                "dataset": "cais/mmlu",
            },
            {"name": "gsm8k", "group": "math", "num_fewshot": 5, "dataset": "gsm8k"},
        ]
        with patch(
            "fusion_bench.engine.task_runner.LMEvalTaskRunner.list_tasks",
            return_value=tasks,
        ):
            cmd_list_tasks(_make_args(mlx_url="http://localhost:11432/v1", pattern="mmlu"))

        out = capsys.readouterr().out
        assert "mmlu" in out


class TestCLIGates:
    def test_gates_default(self, capsys):
        cmd_gates(_make_args(tier=""))
        out = capsys.readouterr().out
        assert "speed-min" in out
        assert "safety-min" in out

    def test_gates_tier_filter(self, capsys):
        cmd_gates(_make_args(tier="experimental"))
        out = capsys.readouterr().out
        assert "speed-min" in out


class TestCLITraces:
    def test_traces_empty(self, capsys):
        with (
            patch("fusion_bench.storage.trace_store.TraceStore.query", return_value=[]),
            patch("fusion_bench.storage.trace_store.TraceStore.close"),
        ):
            cmd_traces(_make_args(model="", executor="", level="", limit=20))

        out = capsys.readouterr().out
        assert "No traces found" in out

    def test_traces_with_records(self, capsys):
        from fusion_bench.core.models import EvalLevel, TaskStatus, TraceRecord

        records = [
            TraceRecord(
                trace_id="tr-1",
                model="m1",
                level=EvalLevel.L1_MODEL,
                executor_key="speed",
                task_id="t1",
                status=TaskStatus.COMPLETED,
                duration_seconds=1.0,
                timestamp="2025-01-01T00:00:00",
            ),
        ]
        with (
            patch("fusion_bench.storage.trace_store.TraceStore.query", return_value=records),
            patch("fusion_bench.storage.trace_store.TraceStore.close"),
        ):
            cmd_traces(_make_args(model="", executor="", level="", limit=20))

        out = capsys.readouterr().out
        assert "tr-1" in out

    def test_traces_with_filters(self, capsys):
        with (
            patch("fusion_bench.storage.trace_store.TraceStore.query", return_value=[]),
            patch("fusion_bench.storage.trace_store.TraceStore.close"),
        ):
            cmd_traces(_make_args(model="m1", executor="speed", level="L1", limit=5))

        out = capsys.readouterr().out
        assert "No traces found" in out


class TestCLINoCommand:
    def test_no_command_exits(self):
        with pytest.raises(SystemExit), patch.object(sys, "argv", ["fusion-bench"]):
            from fusion_bench.cli import main

            main()


class TestCLISecurity:
    @pytest.mark.asyncio
    async def test_security_cmd(self, capsys):
        from fusion_bench.core.plugin_base import CaseResult, EvalResult

        mock_result = EvalResult(
            task_id="security-injection",
            executor_key="security",
            model="test-model",
            level="L3",
            metric_name="safety_rate",
            metric_value=1.0,
            cases=[
                CaseResult(input_text="test probe", actual="I cannot", score=1.0, passed=True),
            ],
        )

        with patch(
            "fusion_bench.executors.security_executor.SecurityExecutor.run",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            args = _make_args(
                mlx_url="http://localhost:11432/v1",
                model="test-model",
                probe_set="injection",
                output="",
            )
            await cmd_security(args)

        out = capsys.readouterr().out
        assert "Safety rate" in out


class TestCLISuite:
    @pytest.mark.asyncio
    async def test_suite_unknown(self, capsys):
        from fusion_bench.orchestrator.scheduler import Scheduler

        with patch.object(Scheduler, "suite_to_task_configs", side_effect=KeyError("not found")):
            args = _make_args(
                mlx_url="http://localhost:11432/v1",
                model="m1",
                suite_name="nonexistent",
                level="L1",
                tier="experimental",
                output="",
            )
            await cmd_suite(args)

        out = capsys.readouterr().out
        assert "Error" in out


class TestApiKeyCLI:
    def test_api_key_retired_prints_guidance(self, capsys):
        import argparse

        import fusion_bench.cli as cli

        args = argparse.Namespace(
            command="api-key", action="create", user="alice", role="operator", workspace="default", scopes=""
        )
        cli.cmd_api_key(args)
        out = capsys.readouterr().out
        assert "fusion-identity" in out
        assert "retired" in out


class TestCacheCLI:
    def test_cache_stats_empty(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("fusion_bench.cache.BenchmarkCache._DEFAULT_DB_PATH", tmp_path / "cache.db")
        import argparse

        import fusion_bench.cli as cli

        args = argparse.Namespace(command="cache", action="stats", model="", task="")
        cli.cmd_cache(args)
        out = capsys.readouterr().out
        assert "0" in out  # total_entries 0

    def test_cache_clear(self, tmp_path, monkeypatch, capsys):
        from fusion_bench.cache import BenchmarkCache

        cache = BenchmarkCache(db_path=str(tmp_path / "cache.db"))
        cache.set("m", {}, "t1", "speed", {"score": 0.8})
        cache.close()
        import argparse

        import fusion_bench.cli as cli

        args = argparse.Namespace(command="cache", action="clear", model="", task="")
        monkeypatch.setattr(
            "fusion_bench.cli.BenchmarkCache", lambda **kw: BenchmarkCache(db_path=str(tmp_path / "cache.db"))
        )
        cli.cmd_cache(args)
        out = capsys.readouterr().out
        assert "1" in out  # cleared 1 entry
