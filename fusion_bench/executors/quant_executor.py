"""Quant executor plugin — wraps QuantBenchmark as an ExecutorPlugin."""

from __future__ import annotations

import logging
import time

from ..core.plugin_base import (
    CaseResult,
    EvalResult,
    ExecutorPlugin,
    ExecutorType,
    TaskConfig,
)
from ..optimizer.quant_bench import QuantBenchmark

logger = logging.getLogger(__name__)


class QuantExecutor(ExecutorPlugin):
    name = "quant"
    executor_type = ExecutorType.QUANT

    def __init__(self, mlx_base_url: str = "http://localhost:11432/v1"):
        self.mlx_base_url = mlx_base_url

    async def run(self, config: TaskConfig) -> EvalResult:
        start = time.time()
        base_model = config.get("base_model", config.model)
        qbench = QuantBenchmark(
            mlx_base_url=config.get("mlx_base_url", self.mlx_base_url),
            base_model=base_model,
        )
        errors: list[str] = []

        try:
            levels = config.get("levels", None)
            runs = config.get("runs", 2)

            quant_results = await qbench.run_speed_comparison(levels=levels, runs=runs)

            cases: list[CaseResult] = []
            for qr in quant_results:
                cases.append(
                    CaseResult(
                        input_text=f"quant={qr.quant}",
                        score=qr.speed,
                        passed=qr.speed > 0 and qr.stable,
                        latency_ms=0.0,
                        meta={
                            "quant": qr.quant,
                            "speed": qr.speed,
                            "memory_mb": qr.memory_mb,
                            "stable": qr.stable,
                        },
                    )
                )

            best_speed = max((c.score for c in cases), default=0.0)

            return EvalResult(
                task_id=config.task_id,
                executor_key=self.name,
                model=config.model,
                level="L1",
                metric_name="best_quant_speed",
                metric_value=round(best_speed, 2),
                cases=cases,
                duration_seconds=time.time() - start,
                errors=errors,
                meta={"base_model": base_model},
            )
        except Exception as e:
            logger.error("Quant run failed: %s", e)
            return EvalResult(
                task_id=config.task_id,
                executor_key=self.name,
                model=config.model,
                level="L1",
                metric_name="best_quant_speed",
                metric_value=0.0,
                duration_seconds=time.time() - start,
                errors=[str(e)],
            )

    def is_available(self) -> bool:
        return True
