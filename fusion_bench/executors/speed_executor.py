"""Speed executor plugin — wraps BenchmarkRunner as an ExecutorPlugin."""

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
from ..engine.benchmark import BenchmarkRunner

logger = logging.getLogger(__name__)


class SpeedExecutor(ExecutorPlugin):
    name = "speed"
    executor_type = ExecutorType.SPEED

    def __init__(self, mlx_base_url: str | None = None):
        # issue #23 E2E: api_key 之前硬编码 "local", 经 gateway/直连 mlx 均 401。
        # 与 bnup/laya executor 对齐 — FUSION_MLX_URL / FUSION_MLX_API_KEY env。
        self.mlx_base_url = mlx_base_url or os.environ.get("FUSION_MLX_URL", "http://localhost:11432/v1")
        self.api_key = os.environ.get("FUSION_MLX_API_KEY", "local")

    async def run(self, config: TaskConfig) -> EvalResult:
        start = time.time()
        runner = BenchmarkRunner(
            mlx_base_url=config.get("mlx_base_url", self.mlx_base_url),
            api_key=self.api_key,
        )
        errors: list[str] = []
        cases: list[CaseResult] = []

        try:
            prompt = config.get(
                "prompt",
                "Explain machine learning in 3 sentences. Be concise and clear.",
            )
            max_tokens = config.get("max_tokens", 256)
            temperature = config.get("temperature", 0.7)
            runs = config.get("runs", 3)

            for i in range(runs):
                try:
                    metrics = await runner.run_single(
                        model=config.model,
                        prompt=prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    cases.append(
                        CaseResult(
                            input_text=prompt[:200],
                            actual=f"decode={metrics.decode_speed:.1f} tok/s",
                            score=metrics.decode_speed,
                            passed=metrics.decode_speed > 0,
                            latency_ms=metrics.total_time * 1000,
                            meta=metrics.to_dict(),
                        )
                    )
                except Exception as e:
                    errors.append(f"Run {i + 1}: {e}")
                    logger.warning("Speed run %d failed for %s: %s", i + 1, config.model, e)

            avg_speed = 0.0
            if cases:
                avg_speed = sum(c.score for c in cases) / len(cases)

            return EvalResult(
                task_id=config.task_id,
                executor_key=self.name,
                model=config.model,
                level="L1",
                metric_name="decode_speed",
                metric_value=round(avg_speed, 2),
                cases=cases,
                duration_seconds=time.time() - start,
                errors=errors,
            )
        finally:
            await runner.close()

    def is_available(self) -> bool:
        return True
