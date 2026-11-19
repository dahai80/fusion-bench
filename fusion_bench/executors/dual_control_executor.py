"""Dual-control executor plugin (issue #51).

Wraps the dual-control episode suite (agent + simulated user on a shared
world) as a standard ExecutorPlugin so it is schedulable through the
Pipeline/REST API like any other bench. L4.
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
from ..dual_control.generator import generate_task
from ..dual_control.runner import run_suite
from ..harness_bench.model_client import ModelClient

logger = logging.getLogger(__name__)

DEFAULT_MLX_URL = "http://127.0.0.1:11434/v1"


class DualControlExecutor(ExecutorPlugin):
    name = "dual-control"
    executor_type = ExecutorType.AGENT

    def __init__(self, mlx_base_url: str | None = None):
        self.mlx_base_url = mlx_base_url or os.environ.get("FUSION_MLX_URL", DEFAULT_MLX_URL)

    async def run(self, config: TaskConfig) -> EvalResult:
        start = time.time()
        seeds = config.get("seeds") or [1, 2, 3]
        n_req = int(config.get("n_requirements", 1))
        client = ModelClient(
            base_url=config.get("mlx_base_url", self.mlx_base_url),
            model=config.model,
            seed=config.random_seed or 42,
        )
        try:
            report = await run_suite(
                model=config.model,
                client=client,
                seeds=[int(s) for s in seeds],
                n_requirements=n_req,
                max_turns=int(config.get("max_turns", 12)),
                llm_user=bool(config.get("llm_user", False)),
            )
        except Exception as e:
            logger.exception("dual-control suite failed model=%s", config.model)
            return EvalResult(
                task_id=config.task_id,
                executor_key=self.name,
                model=config.model,
                level="L4",
                metric_name="dual_success_rate",
                metric_value=0.0,
                duration_seconds=time.time() - start,
                errors=[f"dual-control suite failed: {e}"],
            )
        cases = [
            CaseResult(
                input_text=f"{e['task_id']} seed-family",
                actual=f"success={e['success']} turns={e['turns']} invalid={e['invalid_actions']}",
                score=1.0 if e["success"] else 0.0,
                passed=e["success"],
                latency_ms=e["duration_s"] * 1000,
                meta={
                    k: e[k]
                    for k in ("task_id", "turns", "actions", "invalid_actions", "tokens_in", "tokens_out", "failures")
                },
            )
            for e in report["episodes"]
        ]
        metrics = report["metrics"]
        logger.info("dual-control suite done: %s", metrics)
        return EvalResult(
            task_id=config.task_id,
            executor_key=self.name,
            model=config.model,
            level="L4",
            metric_name="dual_success_rate",
            metric_value=metrics["dual_success_rate"],
            duration_seconds=time.time() - start,
            cases=cases,
            meta={"metrics": metrics},
        )

    def is_available(self) -> bool:
        try:
            generate_task(1)
            return True
        except Exception as e:
            logger.warning("dual-control executor unavailable: %s", e)
            return False


__all__ = ["DualControlExecutor"]
