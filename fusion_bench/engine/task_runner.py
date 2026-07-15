"""Task runner — loads and runs lm-evaluation-harness tasks via fusion-mlx.

All model inference goes through fusion-mlx HTTP API.
No direct MLX, torch, or transformers imports.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from ..adapters.mlx_model import MLXModel

logger = logging.getLogger(__name__)


class LMEvalTaskRunner:
    """Runs lm-evaluation-harness tasks using MLXModel via fusion-mlx.

    Loads YAML task definitions from lm-evaluation-harness and executes
    them using the MLX model adapter.
    """

    def __init__(
        self,
        model: str = "qwen3.5-9b",
        mlx_base_url: str = "http://localhost:11434/v1",
        tasks_dir: str = "",
        max_samples: int = 0,
    ):
        self.model_name = model
        self.mlx_base_url = mlx_base_url
        self.max_samples = max_samples

        # Auto-detect lm-evaluation-harness tasks directory
        if not tasks_dir:
            candidates = [
                Path.home() / "bench" / "lm-evaluation-harness" / "lm_eval" / "tasks",
                Path("/Users/dahai/bench/lm-evaluation-harness/lm_eval/tasks"),
            ]
            for c in candidates:
                if c.exists():
                    tasks_dir = str(c)
                    break
        self.tasks_dir = Path(tasks_dir) if tasks_dir else None

    def list_tasks(self) -> list[dict[str, Any]]:
        """List available tasks from lm-evaluation-harness."""
        if not self.tasks_dir or not self.tasks_dir.exists():
            return []

        tasks = []
        for task_file in sorted(self.tasks_dir.glob("*/*.yaml")):
            try:
                import yaml
                data = yaml.safe_load(task_file.read_text(encoding="utf-8"))
                if data and "task" in data:
                    tasks.append({
                        "name": data["task"],
                        "group": data.get("group", ""),
                        "description": data.get("description", ""),
                        "path": str(task_file.relative_to(self.tasks_dir)),
                        "dataset": data.get("dataset_path", ""),
                        "num_fewshot": data.get("num_fewshot", 0),
                    })
            except Exception:
                pass

        return tasks

    async def run_task(
        self,
        task_name: str,
        num_fewshot: int = 0,
        max_samples: int = 0,
    ) -> dict[str, Any]:
        """Run a single evaluation task.

        Args:
            task_name: Name of the task to run (e.g., "mmlu", "gsm8k").
            num_fewshot: Number of few-shot examples.
            max_samples: Max samples to evaluate (0 = all).

        Returns:
            Dict with task results.
        """
        task_data = self._load_task(task_name)
        if not task_data:
            return {"task": task_name, "error": f"Task '{task_name}' not found", "results": {}}

        model = MLXModel(
            model=self.model_name,
            base_url=self.mlx_base_url,
        )

        max_s = max_samples or self.max_samples or task_data.get("num_fewshot", 0)
        fewshot = num_fewshot or task_data.get("num_fewshot", 0)

        try:
            result = await self._evaluate_task(model, task_data, max_s, fewshot)
            result["task"] = task_name
            result["model"] = self.model_name
            result["usage"] = model.get_usage_report()
            return result
        finally:
            await model.close()

    async def run_benchmark(
        self,
        tasks: list[str],
        num_fewshot: int = 0,
    ) -> list[dict[str, Any]]:
        """Run multiple tasks sequentially."""
        results = []
        for task_name in tasks:
            logger.info("Running task: %s", task_name)
            result = await self.run_task(task_name, num_fewshot)
            results.append(result)
        return results

    # ── Internal ──

    def _load_task(self, task_name: str) -> dict | None:
        """Load a task definition from YAML files."""
        if not self.tasks_dir:
            return None

        for task_file in sorted(self.tasks_dir.rglob("*.yaml")):
            try:
                import yaml
                data = yaml.safe_load(task_file.read_text(encoding="utf-8"))
                if data and data.get("task") == task_name:
                    return data
            except Exception:
                pass
        return None

    async def _evaluate_task(
        self,
        model: MLXModel,
        task_data: dict,
        max_samples: int,
        num_fewshot: int,
    ) -> dict[str, Any]:
        """Evaluate a single task."""
        dataset_path = task_data.get("dataset_path", "")
        dataset_name = task_data.get("dataset_name", "")
        test_split = task_data.get("test_split", "test")
        doc_to_text = task_data.get("doc_to_text", "")
        doc_to_target = task_data.get("doc_to_target", "")

        if not dataset_path:
            return {"error": "No dataset_path in task definition", "results": {}}

        # Load dataset
        try:
            from datasets import load_dataset
            ds = load_dataset(dataset_path, dataset_name, split=test_split)
        except Exception as e:
            logger.warning("Failed to load dataset %s: %s", dataset_path, e)
            return {"error": str(e), "results": {}}

        samples = list(ds)
        if max_samples > 0:
            samples = samples[:max_samples]

        correct = 0
        total = 0
        results = []
        start_time = time.time()

        for i, sample in enumerate(samples):
            # Build prompt
            prompt = self._format_prompt(sample, doc_to_text)
            target = self._format_target(sample, doc_to_target)

            if not prompt or not target:
                continue

            # Generate
            try:
                gen_result = await model.generate_until([{
                    "context": prompt,
                    "until": ["\n"],
                    "max_length": 128,
                }])
                prediction = gen_result[0] if gen_result else ""

                # Normalize for comparison
                pred_norm = self._normalize(prediction)
                target_norm = self._normalize(target)

                is_correct = pred_norm == target_norm or target_norm in pred_norm
                if is_correct:
                    correct += 1
                total += 1

                results.append({
                    "prompt": prompt[:200],
                    "target": target,
                    "prediction": prediction,
                    "correct": is_correct,
                })

            except Exception as e:
                logger.error("Sample %d failed: %s", i, e)

            if (i + 1) % 10 == 0:
                logger.info("  Progress: %d/%d, accuracy: %.1f%%",
                           i + 1, len(samples), correct / max(total, 1) * 100)

        elapsed = time.time() - start_time
        accuracy = correct / max(total, 1)

        return {
            "results": results[:50],  # Return first 50 for detail
            "metrics": {
                "accuracy": round(accuracy, 4),
                "correct": correct,
                "total": total,
                "precision_at_1": round(accuracy, 4),
            },
            "timing": {
                "elapsed_seconds": round(elapsed, 2),
                "samples_per_second": round(total / max(elapsed, 0.001), 2),
            },
        }

    @staticmethod
    def _format_prompt(sample: dict, template: str) -> str:
        """Format a prompt from a template string with sample variables."""
        if not template:
            return str(sample.get("text", sample.get("question", "")))
        try:
            return template.format(**sample)
        except KeyError:
            return str(sample.get("text", sample.get("question", "")))

    @staticmethod
    def _format_target(sample: dict, template: str) -> str:
        """Format the target answer from a template."""
        if not template:
            answer = sample.get("answer", sample.get("label", sample.get("target", "")))
            return str(answer) if answer is not None else ""
        try:
            return template.format(**sample)
        except KeyError:
            return str(sample.get("answer", sample.get("label", "")))

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize text for answer comparison."""
        text = text.strip().lower()
        text = re.sub(r"[^a-z0-9\s]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text