"""EvalScope adapter - integrates Alibaba EvalScope benchmark results.

Importers/callers: executors/__init__.py register_all() imports and registers EvalScopeExecutor.
Affected API: calls POST /chat/completions on fusion-mlx HTTP; no new REST endpoint exposed.
Data schemas: EvalScopeConfig dataclass (task_name, subset, metric_keys, num_fewshot); EvalResult/CaseResult from core/plugin_base.
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P1-9 EvalScope integration).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field

import httpx

from fusion_bench.core.plugin_base import (
    CaseResult,
    EvalResult,
    ExecutorPlugin,
    ExecutorType,
    TaskConfig,
)

logger = logging.getLogger(__name__)

_DEFAULT_EVALSCOPE_DIR = os.path.expanduser("~/bench/evalscope")


@dataclass
class EvalScopeConfig:
    task_name: str
    subset: str = "default"
    metric_keys: list[str] = field(default_factory=lambda: ["accuracy"])
    num_fewshot: int = 0


class EvalScopeExecutor(ExecutorPlugin):
    """P1-9 EvalScope integration - runs EvalScope tasks via fusion-mlx."""

    name = "evalscope"
    executor_type = ExecutorType.MODEL

    def __init__(
        self,
        base_url: str = "http://localhost:11432/v1",
        evalscope_dir: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.evalscope_dir = evalscope_dir or _DEFAULT_EVALSCOPE_DIR

    def is_available(self) -> bool:
        try:
            from evalscope.run import run_task  # noqa: F401

            return True
        except ImportError:
            pass
        return os.path.exists(os.path.join(self.evalscope_dir, "evalscope"))

    async def run(self, task_config: TaskConfig) -> EvalResult:
        logger.info("EvalScopeExecutor: running for model=%s", task_config.model)
        configs = self._load_configs(task_config)
        if not configs:
            configs = [EvalScopeConfig(task_name=task_config.params.get("task", "mmlu"))]

        all_case_results: list[CaseResult] = []
        all_metrics: dict[str, float] = {}
        t0 = time.time()

        for cfg in configs:
            results = await self._run_evalscope_task(cfg, task_config)
            all_case_results.extend(results["case_results"])
            all_metrics.update(results["metrics"])

        total_time = (time.time() - t0) * 1000
        if not all_case_results:
            return EvalResult(
                score=0.0,
                metrics={"evalscope_total_time_ms": total_time},
                details={"error": "No EvalScope results"},
            )

        passed = sum(1 for c in all_case_results if c.passed)
        score = passed / len(all_case_results)
        all_metrics["evalscope_total_time_ms"] = total_time
        return EvalResult(
            score=score,
            metrics=all_metrics,
            case_results=all_case_results,
        )

    def _load_configs(self, task_config: TaskConfig) -> list[EvalScopeConfig]:
        raw = task_config.params.get("evalscope_configs", [])
        if not raw:
            task_names = task_config.params.get("evalscope_tasks", [])
            if isinstance(task_names, str):
                task_names = [t.strip() for t in task_names.split(",")]
            return [EvalScopeConfig(task_name=t) for t in task_names]
        return [EvalScopeConfig(**c) if isinstance(c, dict) else c for c in raw]

    async def _run_evalscope_task(
        self,
        cfg: EvalScopeConfig,
        task_config: TaskConfig,
    ) -> dict:
        try:
            from evalscope.run import run_task as evalscope_run  # noqa: F401

            result = await asyncio.to_thread(
                evalscope_run,
                task=cfg.task_name,
                model=task_config.model,
                api_url=self.base_url,
                subset=cfg.subset,
                num_fewshot=cfg.num_fewshot,
            )
            return self._parse_evalscope_result(cfg, result)
        except ImportError:
            logger.info("EvalScope not installed, using direct HTTP evaluation")
            return await self._run_via_http(cfg, task_config)
        except Exception as e:
            logger.error("EvalScope task %s failed: %s", cfg.task_name, e)
            return {"case_results": [], "metrics": {f"{cfg.task_name}:error": 0.0}}

    async def _run_via_http(self, cfg: EvalScopeConfig, task_config: TaskConfig) -> dict:
        questions = self._load_task_questions(cfg)
        if not questions:
            return {"case_results": [], "metrics": {}}

        case_results: list[CaseResult] = []
        for q in questions:
            result = await self._evaluate_question(q, task_config)
            case_results.append(result)

        passed = sum(1 for c in case_results if c.passed)
        metrics: dict[str, float] = {}
        for mk in cfg.metric_keys:
            metrics[f"{cfg.task_name}:{mk}"] = passed / len(case_results) if case_results else 0.0
        return {"case_results": case_results, "metrics": metrics}

    def _load_task_questions(self, cfg: EvalScopeConfig) -> list[dict]:
        task_dir = os.path.join(self.evalscope_dir, "tasks", cfg.task_name)
        questions_file = os.path.join(task_dir, f"{cfg.subset}.json")
        if os.path.exists(questions_file):
            try:
                with open(questions_file) as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data[:20]
                if isinstance(data, dict):
                    return data.get("questions", data.get("data", []))[:20]
            except Exception as e:
                logger.error("Failed to load questions from %s: %s", questions_file, e)
        return []

    async def _evaluate_question(self, question: dict, task_config: TaskConfig) -> CaseResult:
        prompt = question.get("question", question.get("input", str(question)))
        expected = question.get("answer", question.get("target", ""))
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json={
                        "model": task_config.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": task_config.params.get("max_tokens", 512),
                        "temperature": 0.0,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                actual = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            latency = (time.time() - t0) * 1000
            passed = expected.lower().strip() in actual.lower() if expected else False
            return CaseResult(
                input_text=prompt[:200],
                expected=expected,
                actual=actual[:200],
                score=1.0 if passed else 0.0,
                passed=passed,
                latency_ms=latency,
            )
        except Exception as e:
            return CaseResult(
                input_text=prompt[:200],
                expected=expected,
                actual=str(e),
                score=0.0,
                passed=False,
                latency_ms=(time.time() - t0) * 1000,
            )

    @staticmethod
    def _parse_evalscope_result(cfg: EvalScopeConfig, result: dict) -> dict:
        case_results: list[CaseResult] = []
        metrics: dict[str, float] = {}
        report = result.get("report", result)
        if isinstance(report, dict):
            for mk in cfg.metric_keys:
                val = report.get(mk, report.get("metrics", {}).get(mk, 0))
                if isinstance(val, (int, float)):
                    metrics[f"{cfg.task_name}:{mk}"] = float(val)
        items = result.get("details", result.get("results", []))
        if isinstance(items, list):
            for item in items[:50]:
                if isinstance(item, dict):
                    case_results.append(
                        CaseResult(
                            input_text=item.get("input", "")[:200],
                            expected=item.get("target", ""),
                            actual=item.get("output", "")[:200],
                            score=1.0 if item.get("correct", False) else 0.0,
                            passed=item.get("correct", False),
                            latency_ms=item.get("latency_ms", 0),
                        )
                    )
        return {"case_results": case_results, "metrics": metrics}
