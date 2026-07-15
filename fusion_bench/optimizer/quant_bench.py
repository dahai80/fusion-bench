"""Quantization benchmark — compares model performance across different quantization levels.

All model inference goes through fusion-mlx HTTP API.
Tests speed, memory, and accuracy across quant levels.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from ..engine.benchmark import BenchmarkRunner, SpeedMetrics

logger = logging.getLogger(__name__)


@dataclass
class QuantResult:
    """Result for a single quantization level."""
    quant: str = ""
    speed: float = 0.0
    memory_mb: float = 0.0
    accuracy: float = 0.0
    stable: bool = True
    model_name: str = ""


class QuantBenchmark:
    """Compares model performance across different quantization levels.

    Tests each quant level for speed, memory, and optionally accuracy.
    """

    # Default quant levels available in fusion-mlx
    DEFAULT_LEVELS = [
        "mxfp4",
        "mxfp8",
        "mixed_3_4",
        "mixed_2_6",
        "mixed_2_4",
        "quant2",
        "quant2_all",
    ]

    def __init__(
        self,
        mlx_base_url: str = "http://localhost:11434/v1",
        base_model: str = "qwen3.5-9b",
    ):
        self.mlx_base_url = mlx_base_url
        self.base_model = base_model

    async def run_speed_comparison(self, levels: list[str] | None = None,
                                     runs: int = 2) -> list[QuantResult]:
        """Compare speed and memory across quantization levels."""
        levels = levels or self.DEFAULT_LEVELS
        runner = BenchmarkRunner(mlx_base_url=self.mlx_base_url)
        results = []

        for quant in levels:
            model_name = f"{self.base_model}-{quant}"
            logger.info("Benchmarking %s ...", model_name)
            try:
                metrics = await runner.run_single(
                    model=model_name,
                    prompt="Explain machine learning in 3 sentences.",
                    max_tokens=128,
                )
                results.append(QuantResult(
                    quant=quant,
                    speed=metrics.decode_speed,
                    memory_mb=metrics.peak_memory_mb,
                    model_name=model_name,
                ))
            except Exception as e:
                logger.warning("Failed to benchmark %s: %s", model_name, e)
                results.append(QuantResult(quant=quant, model_name=model_name))

        await runner.close()
        return results

    async def run_accuracy_comparison(self, levels: list[str] | None = None,
                                       task: str = "mmlu",
                                       max_samples: int = 10) -> list[QuantResult]:
        """Compare accuracy across quantization levels on a specific task."""
        from ..engine.task_runner import LMEvalTaskRunner
        levels = levels or self.DEFAULT_LEVELS
        results = []

        for quant in levels:
            model_name = f"{self.base_model}-{quant}"
            logger.info("Evaluating %s on %s ...", model_name, task)
            try:
                runner = LMEvalTaskRunner(
                    model=model_name,
                    mlx_base_url=self.mlx_base_url,
                    max_samples=max_samples,
                )
                task_result = await runner.run_task(task)
                acc = task_result.get("metrics", {}).get("accuracy", 0.0)
                results.append(QuantResult(
                    quant=quant,
                    accuracy=acc,
                    model_name=model_name,
                ))
            except Exception as e:
                logger.warning("Failed to evaluate %s: %s", model_name, e)
                results.append(QuantResult(quant=quant, model_name=model_name))

        return results

    def generate_report(self, results: list[QuantResult], title: str = "") -> str:
        """Generate a markdown report from quant comparison results."""
        if not title:
            title = f"Quantization Comparison — {self.base_model}"
        lines = [
            f"# {title}",
            f"",
            f"| Quant Level | Speed (tok/s) | Memory (MB) | Accuracy | Stable |",
            f"|-------------|:-------------:|:-----------:|:--------:|:------:|",
        ]
        for r in results:
            speed = f"{r.speed:.1f}" if r.speed else "N/A"
            mem = f"{r.memory_mb:.0f}" if r.memory_mb else "N/A"
            acc = f"{r.accuracy:.2%}" if r.accuracy else "N/A"
            stable = "✅" if r.stable else "❌"
            lines.append(f"| {r.quant} | {speed} | {mem} | {acc} | {stable} |")

        # Find best
        valid = [r for r in results if r.speed > 0]
        if valid:
            best_speed = max(valid, key=lambda r: r.speed)
            best_mem = min(valid, key=lambda r: r.memory_mb)
            lines.extend([
                f"",
                f"**Fastest:** {best_speed.quant} ({best_speed.speed:.1f} tok/s)",
                f"**Most memory efficient:** {best_mem.quant} ({best_mem.memory_mb:.0f} MB)",
            ])

        return "\n".join(lines)