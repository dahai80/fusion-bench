"""LM Harness executor plugin — wraps LMEvalTaskRunner as an ExecutorPlugin."""

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
from ..engine.task_runner import LMEvalTaskRunner

logger = logging.getLogger(__name__)


class LMHarnessExecutor(ExecutorPlugin):
    name = "lm_harness"
    executor_type = ExecutorType.MODEL

    def __init__(self, mlx_base_url: str = "http://localhost:11434/v1", tasks_dir: str = ""):
        self.mlx_base_url = mlx_base_url
        self.tasks_dir = tasks_dir

    async def run(self, config: TaskConfig) -> EvalResult:
        start = time.time()
        runner = LMEvalTaskRunner(
            model=config.model,
            mlx_base_url=config.get("mlx_base_url", self.mlx_base_url),
            tasks_dir=config.get("tasks_dir", self.tasks_dir),
            max_samples=config.max_samples or 0,
        )

        task_name = config.get("task_name", config.dataset or "mmlu")
        num_fewshot = config.get("num_fewshot", 0)

        try:
            result = await runner.run_task(task_name, num_fewshot=num_fewshot)
            errors_list: list[str] = []
            if "error" in result:
                errors_list.append(result["error"])

            metrics = result.get("metrics", {})
            accuracy = metrics.get("accuracy", 0.0)

            cases: list[CaseResult] = []
            for item in result.get("results", []):
                cases.append(
                    CaseResult(
                        input_text=item.get("prompt", "")[:200],
                        expected=item.get("target", ""),
                        actual=item.get("prediction", ""),
                        score=1.0 if item.get("correct") else 0.0,
                        passed=item.get("correct", False),
                        meta=item,
                    )
                )

            return EvalResult(
                task_id=config.task_id,
                executor_key=self.name,
                model=config.model,
                level="L1",
                metric_name="accuracy",
                metric_value=round(accuracy, 4),
                cases=cases,
                duration_seconds=time.time() - start,
                errors=errors_list,
                meta=metrics,
            )
        except Exception as e:
            logger.error("LMHarness run failed: %s", e)
            return EvalResult(
                task_id=config.task_id,
                executor_key=self.name,
                model=config.model,
                level="L1",
                metric_name="accuracy",
                metric_value=0.0,
                duration_seconds=time.time() - start,
                errors=[str(e)],
            )

    def is_available(self) -> bool:
        try:
            import yaml  # noqa: F401

            return True
        except ImportError:
            return False
