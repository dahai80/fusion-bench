"""Parameter tuner — automatically finds optimal fusion-mlx parameters for any model."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from ..engine.benchmark import BenchmarkRunner, SpeedMetrics, BenchmarkResult

logger = logging.getLogger(__name__)


@dataclass
class TuneResult:
    """Result of auto-tuning for a single model."""
    model: str = ""
    best_config: dict[str, Any] = field(default_factory=dict)
    best_speed: float = 0.0
    top3_configs: list[dict[str, Any]] = field(default_factory=list)
    memory_saving_config: dict[str, Any] = field(default_factory=dict)
    balanced_config: dict[str, Any] = field(default_factory=dict)
    all_results: list[BenchmarkResult] = field(default_factory=list)


class ParameterTuner:
    """Automatically finds optimal parameters for a model on current hardware.

    Traverses combinations of:
    - batch_size: 1, 2, 4, 8
    - max_tokens: 256, 512, 1024, 2048
    - temperature: 0.0, 0.7
    """

    BATCH_SIZES = [1, 2, 4]
    MAX_TOKENS = [128, 256, 512]
    TEMPERATURES = [0.0, 0.7]

    def __init__(self, mlx_base_url: str = "http://localhost:11434/v1"):
        self.runner = BenchmarkRunner(mlx_base_url=mlx_base_url)

    async def tune(
        self,
        model: str,
        prompt: str = "",
        max_combinations: int = 12,
    ) -> TuneResult:
        """Run auto-tuning for a model."""
        if not prompt:
            prompt = "Explain machine learning in 3 sentences. Be concise and clear."

        result = TuneResult(model=model)
        configs = self._generate_configs()[:max_combinations]

        logger.info("Tuning %s with %d configurations...", model, len(configs))

        for cfg in configs:
            try:
                metrics = await self.runner.run_single(
                    model=model, prompt=prompt,
                    max_tokens=cfg.get("max_tokens", 256),
                    temperature=cfg.get("temperature", 0.7),
                )
                br = BenchmarkResult(model=model, config=cfg, metrics=metrics)
                result.all_results.append(br)
            except Exception as e:
                logger.warning("Config %s failed: %s", cfg, e)

        # Analyze results
        if result.all_results:
            sorted_results = sorted(result.all_results, key=lambda r: r.metrics.decode_speed, reverse=True)
            if sorted_results:
                result.best_config = sorted_results[0].config
                result.best_speed = sorted_results[0].metrics.decode_speed
                result.top3_configs = [r.config for r in sorted_results[:3]]

            # Memory-saving config (lowest max_tokens)
            memory_sorted = sorted(result.all_results, key=lambda r: r.metrics.peak_memory_mb)
            if memory_sorted:
                result.memory_saving_config = memory_sorted[0].config

            # Balanced config (middle of the pack)
            if len(sorted_results) >= 3:
                result.balanced_config = sorted_results[len(sorted_results) // 2].config

        return result

    async def tune_multi_model(
        self,
        models: list[str],
        prompt: str = "",
        max_combinations: int = 8,
    ) -> dict[str, TuneResult]:
        """Tune multiple models in sequence."""
        results = {}
        for model in models:
            try:
                result = await self.tune(model, prompt, max_combinations)
                results[model] = result
            except Exception as e:
                logger.error("Failed to tune %s: %s", model, e)
        return results

    def _generate_configs(self) -> list[dict[str, Any]]:
        """Generate all parameter combinations to test."""
        configs = []
        for batch in self.BATCH_SIZES:
            for tokens in self.MAX_TOKENS:
                for temp in self.TEMPERATURES:
                    configs.append({
                        "batch_size": batch,
                        "max_tokens": tokens,
                        "temperature": temp,
                    })
        return configs