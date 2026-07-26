"""OpenCompass executor plugin — Chinese LLM evaluation tasks via fusion-mlx.

Runs Chinese evaluation benchmarks (C-Eval, CMMLU, etc.) using the MLXModel
adapter. No direct MLX/torch/transformers imports.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from ..adapters.mlx_model import MLXModel
from ..core.plugin_base import (
    CaseResult,
    EvalResult,
    ExecutorPlugin,
    ExecutorType,
    TaskConfig,
)

logger = logging.getLogger(__name__)

_CHINESE_TASKS = {
    "ceval": {
        "dataset_path": "ceval/ceval-exam",
        "dataset_name": "all",
        "test_split": "test",
        "doc_to_text": "以下是中国关于{subject}考试的单项选择题，请选出其中的正确答案。\n\n{question}\nA. {A}\nB. {B}\nC. {C}\nD. {D}\n答案：",
        "doc_to_target": "{answer}",
        "fewshot_text": "以下是中国关于{subject}考试的单项选择题，请选出其中的正确答案。\n\n{question}\nA. {A}\nB. {B}\nC. {C}\nD. {D}\n答案：{answer}",
    },
    "cmmlu": {
        "dataset_path": "haonan-li/cmmlu",
        "dataset_name": "",
        "test_split": "test",
        "doc_to_text": "以下是中国关于{subject}考试的单项选择题，请选出其中的正确答案。\n\n{question}\nA. {A}\nB. {B}\nC. {C}\nD. {D}\n答案：",
        "doc_to_target": "{answer}",
    },
    "mmlu_zh": {
        "dataset_path": "cais/mmlu",
        "dataset_name": "all",
        "test_split": "test",
        "doc_to_text": "以下是关于{subject}的单项选择题，请选出其中的正确答案。\n\n{question}\nA. {A}\nB. {B}\nC. {C}\nD. {D}\n答案：",
        "doc_to_target": "{answer}",
    },
}

_ANSWER_MAP = {"A": 0, "B": 1, "C": 2, "D": 3}


class OpenCompassExecutor(ExecutorPlugin):
    name = "opencompass"
    executor_type = ExecutorType.MODEL

    def __init__(self, mlx_base_url: str = "http://localhost:11434/v1"):
        self.mlx_base_url = mlx_base_url

    async def run(self, config: TaskConfig) -> EvalResult:
        start = time.time()
        task_name = config.get("task_name", config.dataset or "ceval")
        max_samples = config.max_samples or 0

        task_def = _CHINESE_TASKS.get(task_name)
        if not task_def:
            return EvalResult(
                task_id=config.task_id,
                executor_key=self.name,
                model=config.model,
                level="L1",
                metric_name="accuracy",
                metric_value=0.0,
                duration_seconds=time.time() - start,
                errors=[f"Unknown Chinese task: {task_name}. Available: {list(_CHINESE_TASKS.keys())}"],
            )

        try:
            result = await self._run_task(config.model, task_name, task_def, max_samples)
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

            eval_result = EvalResult(
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
            eval_result.analyze_failure()
            return eval_result

        except Exception as e:
            logger.error("OpenCompass run failed: %s", e)
            eval_result = EvalResult(
                task_id=config.task_id,
                executor_key=self.name,
                model=config.model,
                level="L1",
                metric_name="accuracy",
                metric_value=0.0,
                duration_seconds=time.time() - start,
                errors=[str(e)],
            )
            eval_result.analyze_failure()
            return eval_result

    async def _run_task(
        self,
        model_name: str,
        task_name: str,
        task_def: dict[str, Any],
        max_samples: int,
    ) -> dict[str, Any]:
        dataset_path = task_def["dataset_path"]
        dataset_name = task_def.get("dataset_name", "")
        test_split = task_def.get("test_split", "test")
        doc_to_text = task_def.get("doc_to_text", "")
        doc_to_target = task_def.get("doc_to_target", "")

        try:
            from datasets import load_dataset

            kwargs = {"path": dataset_path}
            if dataset_name:
                kwargs["name"] = dataset_name
            ds = load_dataset(**kwargs, split=test_split)
        except Exception as e:
            logger.warning("Failed to load dataset %s: %s", dataset_path, e)
            return {"error": str(e), "results": {}}

        model = MLXModel(model=model_name, base_url=self.mlx_base_url)

        try:
            samples = list(ds)
            if max_samples > 0:
                samples = samples[:max_samples]

            correct = 0
            total = 0
            results = []
            start_time = time.time()

            for i, sample in enumerate(samples):
                prompt = self._format_prompt(sample, doc_to_text)
                target = self._format_target(sample, doc_to_target)

                if not prompt:
                    continue

                try:
                    gen_result = await model.generate_until(
                        [
                            {
                                "context": prompt,
                                "until": ["\n", "。"],
                                "max_length": 32,
                            }
                        ]
                    )
                    prediction = gen_result[0] if gen_result else ""

                    pred_norm = self._extract_answer(prediction)
                    target_norm = self._normalize(target)

                    is_correct = pred_norm == target_norm
                    if is_correct:
                        correct += 1
                    total += 1

                    results.append(
                        {
                            "prompt": prompt[:200],
                            "target": target_norm,
                            "prediction": prediction[:100],
                            "correct": is_correct,
                        }
                    )

                except Exception as e:
                    logger.error("Sample %d failed: %s", i, e)

                if (i + 1) % 10 == 0:
                    logger.info(
                        "  [%s] Progress: %d/%d, accuracy: %.1f%%",
                        task_name,
                        i + 1,
                        len(samples),
                        correct / max(total, 1) * 100,
                    )

            elapsed = time.time() - start_time
            accuracy = correct / max(total, 1)

            return {
                "results": results[:50],
                "metrics": {
                    "accuracy": round(accuracy, 4),
                    "correct": correct,
                    "total": total,
                },
                "timing": {
                    "elapsed_seconds": round(elapsed, 2),
                    "samples_per_second": round(total / max(elapsed, 0.001), 2),
                },
            }
        finally:
            await model.close()

    @staticmethod
    def _format_prompt(sample: dict, template: str) -> str:
        if not template:
            return str(sample.get("question", sample.get("text", "")))
        try:
            return template.format(**sample)
        except (KeyError, IndexError):
            return str(sample.get("question", sample.get("text", "")))

    @staticmethod
    def _format_target(sample: dict, template: str) -> str:
        if not template:
            answer = sample.get("answer", sample.get("label", ""))
            return str(answer) if answer is not None else ""
        try:
            return template.format(**sample)
        except (KeyError, IndexError):
            return str(sample.get("answer", sample.get("label", "")))

    @staticmethod
    def _extract_answer(text: str) -> str:
        text = text.strip().upper()
        for letter in ["A", "B", "C", "D"]:
            if text.startswith(letter) or f"答案{letter}" in text or f"选项{letter}" in text:
                return letter
        if text:
            return text[0]
        return ""

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.strip().upper()
        text = re.sub(r"[^A-Z]", "", text)
        return text

    def is_available(self) -> bool:
        try:
            from datasets import load_dataset  # noqa: F401

            return True
        except ImportError:
            logger.warning("OpenCompass executor requires 'datasets' package")
            return False
