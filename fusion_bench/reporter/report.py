"""Report generator — produces JSON, Markdown, and chart reports from benchmark results."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..engine.benchmark import BenchmarkResult


class ReportGenerator:
    """Generates formatted reports from benchmark results."""

    @staticmethod
    def to_json(results: list[BenchmarkResult], filepath: str = "") -> str:
        """Export benchmark results as JSON."""
        data = {
            "generated_at": datetime.now().isoformat(),
            "total_benchmarks": len(results),
            "results": [r.metrics.to_dict() if hasattr(r, 'metrics') else r for r in results],
        }
        output = json.dumps(data, indent=2, ensure_ascii=False)
        if filepath:
            Path(filepath).write_text(output, encoding="utf-8")
        return output

    @staticmethod
    def to_markdown(results: list[BenchmarkResult], title: str = "Benchmark Report") -> str:
        """Generate a Markdown report from benchmark results."""
        lines = [
            f"# {title}",
            f"",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
            "## Summary",
            f"",
            f"| Model | Config | Decode Speed | Prefill Speed | Peak Memory | Stable |",
            f"|-------|--------|-------------|--------------|-------------|--------|",
        ]

        for r in results:
            model = r.model
            cfg = json.dumps(r.config, ensure_ascii=False) if r.config else "default"
            speed = f"{r.metrics.decode_speed:.1f} tok/s" if r.metrics.decode_speed else "N/A"
            prefill = f"{r.metrics.prefill_speed:.1f} tok/s" if r.metrics.prefill_speed else "N/A"
            mem = f"{r.metrics.peak_memory_mb:.0f} MB" if r.metrics.peak_memory_mb else "N/A"
            stable = "✅" if r.stable else "❌"
            lines.append(f"| {model} | {cfg} | {speed} | {prefill} | {mem} | {stable} |")

        lines.extend([
            f"",
            "## Speed Rankings",
            f"",
        ])

        sorted_results = sorted(results, key=lambda r: r.metrics.decode_speed, reverse=True)
        for i, r in enumerate(sorted_results, 1):
            if r.metrics.decode_speed:
                lines.append(f"{i}. **{r.model}**: {r.metrics.decode_speed:.1f} tok/s")

        lines.extend([
            f"",
            "## Configuration Details",
            f"",
        ])
        for r in results:
            lines.append(f"### {r.model}")
            lines.append(f"```json")
            lines.append(json.dumps(r.metrics.to_dict(), indent=2, ensure_ascii=False))
            lines.append(f"```")
            lines.append(f"")

        return "\n".join(lines)

    @staticmethod
    def generate_chart_path(results: list[BenchmarkResult], output_path: str = "") -> str:
        """Generate a speed comparison chart (PNG) using matplotlib."""
        if not results:
            return ""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import numpy as np

            models = [r.model for r in results]
            speeds = [r.metrics.decode_speed for r in results]
            mems = [r.metrics.peak_memory_mb for r in results]

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

            # Speed chart
            colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(models)))
            bars1 = ax1.bar(range(len(models)), speeds, color=colors)
            ax1.set_xlabel("Model")
            ax1.set_ylabel("Decode Speed (tok/s)")
            ax1.set_title("Speed Comparison")
            ax1.set_xticks(range(len(models)))
            ax1.set_xticklabels(models, rotation=45, ha="right", fontsize=9)
            for bar, speed in zip(bars1, speeds):
                ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                         f"{speed:.1f}", ha="center", va="bottom", fontsize=8)

            # Memory chart
            bars2 = ax2.bar(range(len(models)), mems, color=colors)
            ax2.set_xlabel("Model")
            ax2.set_ylabel("Peak Memory (MB)")
            ax2.set_title("Memory Usage Comparison")
            ax2.set_xticks(range(len(models)))
            ax2.set_xticklabels(models, rotation=45, ha="right", fontsize=9)
            for bar, mem in zip(bars2, mems):
                ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                         f"{mem:.0f}", ha="center", va="bottom", fontsize=8)

            plt.tight_layout()
            path = output_path or "benchmark_chart.png"
            plt.savefig(path, dpi=150, bbox_inches="tight")
            plt.close()
            return path
        except ImportError:
            return ""

    @staticmethod
    def generate_config_template(result: BenchmarkResult) -> str:
        """Generate a fusion-mlx config template from the best result."""
        cfg = result.config
        return json.dumps({
            "model": result.model,
            "inference": {
                "max_tokens": cfg.get("max_tokens", 4096),
                "temperature": cfg.get("temperature", 0.7),
                "batch_size": cfg.get("batch_size", 1),
            },
            "performance": {
                "expected_decode_speed": f"{result.metrics.decode_speed:.1f} tok/s",
                "expected_peak_memory": f"{result.metrics.peak_memory_mb:.0f} MB",
                "max_stable_context": result.max_stable_context,
            },
            "generated_by": "fusion-bench",
        }, indent=2, ensure_ascii=False)