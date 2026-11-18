"""Harness comparison executor plugin (issue #48).

Wraps the same-model harness comparison (fusion-harness kernel loop vs
mini-swe-agent style baseline) as a standard ExecutorPlugin so it is
schedulable through the Pipeline/REST API like any other bench.
"""

from __future__ import annotations

import logging
import os
import time

from ..core.plugin_base import (
    CaseResult,
    EvalResult,
    ExecutorPlugin,
    ExecutorType,
    TaskConfig,
)
from ..harness_bench.compare import DEFAULT_MLX_URL, run_comparison

logger = logging.getLogger(__name__)


class HarnessBenchExecutor(ExecutorPlugin):
    name = "harness-bench"
    executor_type = ExecutorType.AGENT

    def __init__(self, mlx_base_url: str | None = None):
        self.mlx_base_url = mlx_base_url or os.environ.get("FUSION_MLX_URL", DEFAULT_MLX_URL)

    async def run(self, config: TaskConfig) -> EvalResult:
        start = time.time()
        errors: list[str] = []
        cases: list[CaseResult] = []

        harnesses = config.get("harnesses", ["mini-swe", "fusion-harness"])
        out_dir = config.get("out_dir") or os.path.join("benchmarks", "results", "harness-comparison")
        try:
            report = await run_comparison(
                model=config.model,
                task_ids=config.get("tasks"),
                harnesses=harnesses,
                runs=int(config.get("runs", 1)),
                max_steps=int(config.get("max_steps", 8)),
                mlx_url=config.get("mlx_base_url", self.mlx_base_url),
                seed=config.random_seed,
                budget_tokens=int(config.get("budget_tokens", 100000)),
                price_in_per_m=float(config.get("price_in_per_m", 0.0)),
                price_out_per_m=float(config.get("price_out_per_m", 0.0)),
                out_dir=out_dir,
            )
        except Exception as e:
            logger.exception("harness-bench comparison failed model=%s", config.model)
            return EvalResult(
                task_id=config.task_id,
                executor_key=self.name,
                model=config.model,
                level="L4",
                metric_name="success_rate",
                metric_value=0.0,
                duration_seconds=time.time() - start,
                errors=[f"harness-bench comparison failed: {e}"],
            )
        errors.extend(report.get("errors", []))

        for task_id, cells in report["tasks"].items():
            for harness, cell in cells.items():
                m = cell["metrics"]
                cases.append(
                    CaseResult(
                        input_text=f"{harness}/{task_id}",
                        actual=f"success={m['success_rate']} steps={m['steps_mean']} detours={m['detours_total']}",
                        score=m["success_rate"],
                        passed=m["success_rate"] >= 1.0,
                        latency_ms=m["wall_s_mean"] * 1000,
                        meta={"harness": harness, "task_id": task_id, **m},
                    )
                )

        harness_count = max(1, len(report["summary"]))
        mean_success = sum(s["success_rate"] for s in report["summary"].values()) / harness_count
        return EvalResult(
            task_id=config.task_id,
            executor_key=self.name,
            model=config.model,
            level="L4",
            metric_name="success_rate",
            metric_value=round(mean_success, 4),
            cases=cases,
            duration_seconds=time.time() - start,
            errors=errors,
            meta={"report": {k: v for k, v in report.items() if k != "cost_table"}, "cost_table": report["cost_table"]},
        )

    def is_available(self) -> bool:
        return True
