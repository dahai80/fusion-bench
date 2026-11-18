"""Comparison orchestrator: task suite x harnesses x runs -> metrics + report (issue #48)."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from .detour import score_trajectory
from .model_client import ModelClient
from .report import render_markdown
from .runners import FusionHarnessRunner, MiniSweRunner
from .tasks import HarnessTask, tasks_by_ids

logger = logging.getLogger(__name__)

DEFAULT_MLX_URL = "http://localhost:11434/v1"
DEFAULT_PRICE_IN_PER_M = 0.0
DEFAULT_PRICE_OUT_PER_M = 0.0


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _cost_usd(tokens_in: int, tokens_out: int, price_in: float, price_out: float) -> float:
    return tokens_in / 1_000_000 * price_in + tokens_out / 1_000_000 * price_out


def _make_runner(harness: str, client: ModelClient, max_steps: int, budget_tokens: int):
    if harness == "mini-swe":
        return MiniSweRunner(client, max_steps=max_steps)
    if harness == "fusion-harness":
        return FusionHarnessRunner(client, max_steps=max_steps, budget_tokens=budget_tokens)
    raise ValueError(f"unknown harness: {harness}; known: mini-swe, fusion-harness")


def _aggregate(results: list[dict]) -> dict:
    runs = len(results)
    passed = sum(1 for r in results if r["passed"])
    tokens_in = sum(r["tokens_in"] for r in results)
    tokens_out = sum(r["tokens_out"] for r in results)
    llm_calls = sum(r["llm_calls"] for r in results)
    cache_hits = sum(r["cache_hits"] for r in results)
    return {
        "runs": runs,
        "success_rate": round(passed / runs, 4) if runs else 0.0,
        "tokens_in_total": tokens_in,
        "tokens_out_total": tokens_out,
        "tokens_in_mean": round(_mean([r["tokens_in"] for r in results]), 1),
        "tokens_out_mean": round(_mean([r["tokens_out"] for r in results]), 1),
        "cache_hit_rate": round(cache_hits / llm_calls, 4) if llm_calls else 0.0,
        "wall_s_mean": round(_mean([r["wall_s"] for r in results]), 3),
        "wall_s_total": round(sum(r["wall_s"] for r in results), 3),
        "steps_mean": round(_mean([r["steps"] for r in results]), 2),
        "detours_total": sum(r["trajectory"]["detours"] for r in results),
        "one_step_misses_total": sum(r["trajectory"]["one_step_misses"] for r in results),
    }


async def run_comparison(
    model: str,
    task_ids: list[str] | None = None,
    harnesses: list[str] | None = None,
    runs: int = 1,
    max_steps: int = 8,
    mlx_url: str = DEFAULT_MLX_URL,
    seed: int = 42,
    budget_tokens: int = 100000,
    price_in_per_m: float = DEFAULT_PRICE_IN_PER_M,
    price_out_per_m: float = DEFAULT_PRICE_OUT_PER_M,
    out_dir: str | Path | None = None,
    keep_workspaces: bool = False,
    tasks: list[HarnessTask] | None = None,
) -> dict:
    """Run the full comparison. Returns the report dict; writes JSON+MD when out_dir given."""
    harnesses = harnesses or ["mini-swe", "fusion-harness"]
    suite = tasks if tasks is not None else tasks_by_ids(task_ids)
    report: dict = {
        "schema": "fusion-bench/harness-comparison@v1",
        "model": model,
        "mlx_url": mlx_url,
        "seed": seed,
        "runs_per_cell": runs,
        "max_steps": max_steps,
        "price_in_per_m": price_in_per_m,
        "price_out_per_m": price_out_per_m,
        "harnesses": harnesses,
        "tasks": {},
        "summary": {},
        "cost_table": [],
        "errors": [],
    }
    cost_table = report["cost_table"]
    for task in suite:
        report["tasks"][task.task_id] = {}
        for harness in harnesses:
            cell_results: list[dict] = []
            for run_idx in range(runs):
                workspace = Path(tempfile.mkdtemp(prefix=f"hb-{task.task_id}-{harness}-"))
                try:
                    # Fresh client per run: keeps runs state-isolated and lets the
                    # fusion-harness budget funnel start from zero every time.
                    client = ModelClient(base_url=mlx_url, model=model, seed=seed)
                    runner = _make_runner(harness, client, max_steps, budget_tokens)
                    result = await runner.run(task, workspace)
                    trajectory = score_trajectory(result.actions, task.reference_actions, result.passed)
                    entry = result.to_dict()
                    entry["run"] = run_idx + 1
                    entry["trajectory"] = trajectory
                    entry["cost_usd"] = round(
                        _cost_usd(result.tokens_in, result.tokens_out, price_in_per_m, price_out_per_m), 6
                    )
                    cell_results.append(entry)
                    cost_table.append(
                        {
                            "task": task.task_id,
                            "harness": harness,
                            "run": run_idx + 1,
                            "tokens_in": result.tokens_in,
                            "tokens_out": result.tokens_out,
                            "llm_calls": result.llm_calls,
                            "cache_hits": result.cache_hits,
                            "cost_usd": entry["cost_usd"],
                        }
                    )
                    if result.error:
                        report["errors"].append(f"{harness}/{task.task_id}/run{run_idx + 1}: {result.error}")
                finally:
                    if keep_workspaces:
                        logger.info("workspace kept: %s", workspace)
                    else:
                        shutil.rmtree(workspace, ignore_errors=True)
            report["tasks"][task.task_id][harness] = {
                "metrics": _aggregate(cell_results),
                "runs": cell_results,
            }
    for harness in harnesses:
        harness_cells = [cell[harness]["metrics"] for cell in report["tasks"].values() if harness in cell]
        if harness_cells:
            report["summary"][harness] = {
                "success_rate": round(_mean([m["success_rate"] for m in harness_cells]), 4),
                "tokens_in_mean": round(_mean([m["tokens_in_mean"] for m in harness_cells]), 1),
                "tokens_out_mean": round(_mean([m["tokens_out_mean"] for m in harness_cells]), 1),
                "cache_hit_rate": round(_mean([m["cache_hit_rate"] for m in harness_cells]), 4),
                "wall_s_mean": round(_mean([m["wall_s_mean"] for m in harness_cells]), 3),
                "steps_mean": round(_mean([m["steps_mean"] for m in harness_cells]), 2),
                "detours_total": sum(m["detours_total"] for m in harness_cells),
                "one_step_misses_total": sum(m["one_step_misses_total"] for m in harness_cells),
            }
    total_cost = {
        harness: round(sum(row["cost_usd"] for row in cost_table if row["harness"] == harness), 6)
        for harness in harnesses
    }
    report["cost_total"] = total_cost
    if out_dir is not None:
        _write_report(report, Path(out_dir))
    return report


def _write_report(report: dict, out_dir: Path) -> tuple[Path, Path]:
    import json

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "report.json"
    md_path = out_dir / "report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    logger.info("harness-comparison report written: %s, %s", json_path, md_path)
    return json_path, md_path
