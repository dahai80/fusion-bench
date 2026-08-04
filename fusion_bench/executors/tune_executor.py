"""Tune executor plugin — wraps ParameterTuner as an ExecutorPlugin."""

from __future__ import annotations

import asyncio
import logging
import time

from ..core.plugin_base import (
    CaseResult,
    EvalResult,
    ExecutorPlugin,
    ExecutorType,
    TaskConfig,
)
from ..optimizer.tuner import ParameterTuner

logger = logging.getLogger(__name__)


class TuneExecutor(ExecutorPlugin):
    name = "tune"
    executor_type = ExecutorType.SPEED

    def __init__(self, mlx_base_url: str = "http://localhost:11432/v1"):
        self.mlx_base_url = mlx_base_url

    async def run(self, config: TaskConfig) -> EvalResult:
        start = time.time()
        tuner = ParameterTuner(mlx_base_url=config.get("mlx_base_url", self.mlx_base_url))
        errors: list[str] = []

        try:
            prompt = config.get(
                "prompt",
                "Explain machine learning in 3 sentences. Be concise and clear.",
            )
            max_combinations = config.get("max_combinations", 12)

            tune_result = await tuner.tune(
                model=config.model,
                prompt=prompt,
                max_combinations=max_combinations,
            )

            cases: list[CaseResult] = []
            for br in tune_result.all_results:
                cases.append(
                    CaseResult(
                        input_text=prompt[:200],
                        actual=f"decode={br.metrics.decode_speed:.1f} tok/s",
                        score=br.metrics.decode_speed,
                        passed=br.metrics.decode_speed > 0,
                        latency_ms=br.metrics.total_time * 1000,
                        meta={"config": br.config, "metrics": br.metrics.to_dict()},
                    )
                )

            return EvalResult(
                task_id=config.task_id,
                executor_key=self.name,
                model=config.model,
                level="L1",
                metric_name="best_decode_speed",
                metric_value=round(tune_result.best_speed, 2),
                cases=cases,
                duration_seconds=time.time() - start,
                errors=errors,
                meta={
                    "best_config": tune_result.best_config,
                    "top3_configs": tune_result.top3_configs,
                    "memory_saving_config": tune_result.memory_saving_config,
                    "balanced_config": tune_result.balanced_config,
                },
            )
        except Exception as e:
            logger.error("Tune run failed: %s", e)
            return EvalResult(
                task_id=config.task_id,
                executor_key=self.name,
                model=config.model,
                level="L1",
                metric_name="best_decode_speed",
                metric_value=0.0,
                duration_seconds=time.time() - start,
                errors=[str(e)],
            )
        finally:
            if hasattr(tuner.runner, "close"):
                close_coro = tuner.runner.close()
                if asyncio.iscoroutine(close_coro):
                    await close_coro

    def is_available(self) -> bool:
        return True
