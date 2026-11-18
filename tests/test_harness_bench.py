"""Tests for the harness comparison benchmark (issue #48).

All model interaction is scripted (FakeModelClient) so the suite is fully
offline and deterministic; scoring depends only on verifiers and fixed
token counts.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from fusion_bench.harness_bench.detour import score_trajectory
from fusion_bench.harness_bench.model_client import ChatTurn
from fusion_bench.harness_bench.runners import (
    FusionHarnessRunner,
    MiniSweRunner,
    extract_action,
    fusion_harness_importable,
)
from fusion_bench.harness_bench.tasks import BUILTIN_TASKS, tasks_by_ids

FH_AVAILABLE = fusion_harness_importable()


class FakeModelClient:
    """Scripted model: pops one reply per chat() call, fixed token counts."""

    def __init__(self, replies: list[str], tokens_per_call: tuple[int, int] = (120, 40)):
        self.replies = list(replies)
        self.model = "fake-model"
        self.tokens_in, self.tokens_out = tokens_per_call
        self.calls = 0

    async def chat(self, messages: list[dict], max_tokens: int = 512) -> ChatTurn:
        self.calls += 1
        text = self.replies.pop(0) if self.replies else "DONE"
        return ChatTurn(
            text=text,
            prompt_tokens=self.tokens_in,
            completion_tokens=self.tokens_out,
            cached=False,
            latency_s=0.001,
        )


def test_extract_action_variants():
    assert extract_action("```bash\necho hi\n```") == "echo hi"
    assert extract_action("```sh\nls -la\n```") == "ls -la"
    assert extract_action("done\nDONE") == "DONE"
    assert extract_action("no action here") is None
    assert extract_action("```bash\n\n```") is None


def test_miniswe_solves_create_notes(tmp_path):
    client = FakeModelClient(["```bash\necho 'harness bench' > notes.md\n```", "DONE"])
    task = tasks_by_ids(["create-notes"])[0]
    import asyncio

    result = asyncio.run(MiniSweRunner(client).run(task, tmp_path / "ws"))
    assert result.passed, result.verify_detail
    assert result.steps == 1
    assert result.tokens_in == 240 and result.tokens_out == 80
    assert result.harness == "mini-swe"


def test_miniswe_gives_up_after_max_steps(tmp_path):
    client = FakeModelClient(["I am not sure what to do"] * 3)
    task = tasks_by_ids(["create-notes"])[0]
    import asyncio

    result = asyncio.run(MiniSweRunner(client, max_steps=3).run(task, tmp_path / "ws"))
    assert not result.passed
    assert result.steps == 0
    assert result.llm_calls == 3
    assert result.error == ""


def test_fusion_harness_runner_solves_task(tmp_path):
    if not FH_AVAILABLE:
        pytest.skip("fusion_harness not installed")
    client = FakeModelClient(["```bash\necho 'harness bench' > notes.md\n```", "DONE"])
    task = tasks_by_ids(["create-notes"])[0]
    import asyncio

    result = asyncio.run(FusionHarnessRunner(client).run(task, tmp_path / "ws"))
    assert result.passed, result.verify_detail
    assert result.harness == "fusion-harness"


def test_fusion_harness_budget_denies_llm(tmp_path):
    if not FH_AVAILABLE:
        pytest.skip("fusion_harness not installed")
    client = FakeModelClient(["```bash\necho 'harness bench' > notes.md\n```", "DONE"])
    task = tasks_by_ids(["create-notes"])[0]
    import asyncio

    # Budget of 10 tokens: after the first metered LLM call (160 tokens) both
    # the tool funnel and the next LLM call are denied.
    result = asyncio.run(FusionHarnessRunner(client, max_steps=2, budget_tokens=10).run(task, tmp_path / "ws"))
    assert not result.passed
    assert result.llm_calls == 2 and result.tokens_in == 120 and result.tokens_out == 40


def test_fusion_harness_missing_module_reports_error(tmp_path, monkeypatch):
    import fusion_bench.harness_bench.runners as runners_mod

    monkeypatch.setattr(runners_mod, "fusion_harness_importable", lambda: False)
    client = FakeModelClient(["DONE"])
    task = tasks_by_ids(["create-notes"])[0]
    import asyncio

    runner = runners_mod.FusionHarnessRunner(client)
    result = asyncio.run(runner.run(task, tmp_path / "ws"))
    assert "fusion_harness not installed" in result.error


def test_detour_scoring():
    refs = ["sed -i 's/Helo/Hello/' greeting.txt"]
    clean = score_trajectory(["sed -i 's/Helo/Hello/' greeting.txt"], refs, passed=True)
    assert clean["detours"] == 0 and clean["one_step_misses"] == 0 and clean["minimal_delta"] == 0

    detour = score_trajectory(["ls -la", "sed -i 's/Helo/Hello/' greeting.txt"], refs, passed=True)
    assert detour["detours"] == 1 and detour["one_step_misses"] == 1

    failed_detour = score_trajectory(["ls -la", "sed -i 's/Helo/Hello/' greeting.txt"], refs, passed=False)
    assert failed_detour["one_step_misses"] == 0 and failed_detour["detours"] == 1

    missing = score_trajectory(["ls"], refs, passed=False)
    assert missing["minimal_delta"] == 2  # 1 detour + 1 unmatched reference


def test_tasks_by_ids_unknown():
    with pytest.raises(ValueError, match="unknown harness-bench tasks"):
        tasks_by_ids(["no-such-task"])
    assert tasks_by_ids(None) == BUILTIN_TASKS
    assert tasks_by_ids([]) == BUILTIN_TASKS


def test_run_comparison_offline(tmp_path, monkeypatch):
    import fusion_bench.harness_bench.compare as compare_mod

    replies = ["```bash\necho 'harness bench' > notes.md\n```", "DONE"]

    def fake_client(base_url, model, seed=42, timeout=120.0):
        return FakeModelClient(replies)

    monkeypatch.setattr(compare_mod, "ModelClient", fake_client)
    harnesses = ["mini-swe"] + (["fusion-harness"] if FH_AVAILABLE else [])
    import asyncio

    report = asyncio.run(
        compare_mod.run_comparison(
            model="fake-model",
            task_ids=["create-notes", "compute-sum"],
            harnesses=harnesses,
            runs=2,
            max_steps=4,
            price_in_per_m=1.0,
            price_out_per_m=2.0,
            out_dir=tmp_path,
        )
    )
    assert report["schema"] == "fusion-bench/harness-comparison@v1"
    assert "create-notes" in report["tasks"] and "compute-sum" in report["tasks"]
    mini = report["tasks"]["create-notes"]["mini-swe"]["metrics"]
    assert mini["runs"] == 2
    assert mini["success_rate"] == 1.0
    assert mini["cache_hit_rate"] == 0.0
    # cost table: 2 tasks x len(harnesses) x 2 runs rows; priced > 0
    assert len(report["cost_table"]) == 2 * len(harnesses) * 2
    assert all(row["cost_usd"] > 0 for row in report["cost_table"])
    assert report["summary"]["mini-swe"]["detours_total"] >= 0
    # artifact files
    data = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert data["model"] == "fake-model"
    md = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "Harness comparison report" in md
    assert "Per-run cost table" in md
    # workspaces cleaned up
    assert not list(tmp_path.glob("hb-*"))


def test_report_markdown_contains_task_tables(tmp_path, monkeypatch):
    import fusion_bench.harness_bench.compare as compare_mod
    from fusion_bench.harness_bench.report import render_markdown

    def fake_client(base_url, model, seed=42, timeout=120.0):
        return FakeModelClient(["```bash\necho 391 > sum.txt\n```", "DONE"])

    monkeypatch.setattr(compare_mod, "ModelClient", fake_client)
    import asyncio

    report = asyncio.run(
        compare_mod.run_comparison(
            model="fake-model", task_ids=["compute-sum"], harnesses=["mini-swe"], runs=1, out_dir=tmp_path
        )
    )
    md = render_markdown(report)
    assert "### task: compute-sum" in md
    assert "| mini-swe |" in md
    assert "Total per harness" in md


def test_cli_harness_bench_help():
    proc = subprocess.run(
        [sys.executable, "-m", "fusion_bench.cli", "harness-bench", "--help"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0
    assert "--harnesses" in proc.stdout


def test_chat_turn_ok_property():
    ok = ChatTurn(text="x", prompt_tokens=1, completion_tokens=1, cached=False, latency_s=0.1)
    bad = ChatTurn(text="", prompt_tokens=0, completion_tokens=0, cached=False, latency_s=0.1, error="boom")
    assert ok.ok and not bad.ok
