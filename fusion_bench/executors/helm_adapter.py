"""HELM adapter - parses Stanford HELM benchmark results.

Imported by executors/__init__.py register_all(). Converts HELM JSON output to EvalResult.
Schema: HelmMetric dataclass, reads stats.json from HELM output dir.
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P1-8).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from fusion_bench.core.plugin_base import (
    CaseResult,
    EvalResult,
    ExecutorPlugin,
    ExecutorType,
    TaskConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class HelmMetric:
    scenario_name: str
    metric_name: str
    metric_value: float
    run_id: str = ""


class HelmAdapter(ExecutorPlugin):
    """P1-8 HELM interface adapter - parses HELM benchmark results."""

    name = "helm"
    executor_type = ExecutorType.MODEL

    def __init__(self, helm_dir: str | None = None):
        self.helm_dir = helm_dir or os.path.expanduser("~/bench/helm")

    def is_available(self) -> bool:
        helm_exec = os.path.join(self.helm_dir, "helm")
        if os.path.exists(helm_exec):
            return True
        try:
            import helm  # noqa: F401

            return True
        except ImportError:
            return False

    async def run(self, task_config: TaskConfig) -> EvalResult:
        logger.info("HelmAdapter: model=%s", task_config.model)
        scenarios = task_config.params.get("helm_scenarios", [])
        if not scenarios:
            scenarios = ["mmlu", "gsm8k"]

        results = await self._run_helm(task_config.model, scenarios)
        if not results:
            return EvalResult(
                score=0.0,
                metrics={"scenarios_run": 0},
                details={"error": "No HELM results found"},
            )

        case_results = [
            CaseResult(
                input_text=r.scenario_name,
                expected=r.metric_name,
                actual=f"{r.metric_value:.4f}",
                score=r.metric_value,
                passed=r.metric_value >= 0.5,
                latency_ms=0,
                meta={"run_id": r.run_id, "metric": r.metric_name},
            )
            for r in results
        ]
        avg_score = sum(r.metric_value for r in results) / len(results)
        return EvalResult(
            score=avg_score,
            metrics={f"{r.scenario_name}:{r.metric_name}": r.metric_value for r in results},
            case_results=case_results,
        )

    async def _run_helm(self, model: str, scenarios: list[str]) -> list[HelmMetric]:
        output_dir = os.path.join(self.helm_dir, "benchmark_output", model)
        os.makedirs(output_dir, exist_ok=True)

        cmd = self._build_helm_cmd(model, scenarios, output_dir)
        if not cmd:
            return self._parse_existing_results(output_dir)

        logger.info("Running HELM: %s", " ".join(cmd))
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=7200)
            if proc.returncode != 0:
                logger.error("HELM failed: %s", stderr.decode()[:500])
        except TimeoutError:
            logger.error("HELM timed out")
        except Exception as e:
            logger.error("HELM error: %s", e)

        return self._parse_existing_results(output_dir)

    def _build_helm_cmd(self, model: str, scenarios: list[str], output_dir: str) -> list[str] | None:
        helm_exec = os.path.join(self.helm_dir, "helm")
        if not os.path.exists(helm_exec):
            try:
                import helm  # noqa: F401

                helm_exec = "helm"
            except ImportError:
                return None
        return [
            helm_exec,
            "run",
            "--conf-paths",
            ",".join(scenarios),
            "--model",
            model,
            "--suite",
            f"fusion-bench-{int(time.time())}",
            "--output-dir",
            output_dir,
        ]

    def _parse_existing_results(self, output_dir: str) -> list[HelmMetric]:
        results: list[HelmMetric] = []
        stats_file = os.path.join(output_dir, "stats.json")
        if os.path.exists(stats_file):
            return self._parse_stats_json(stats_file)

        for root, _dirs, files in os.walk(output_dir):
            for fname in files:
                if fname == "stats.json":
                    results.extend(self._parse_stats_json(os.path.join(root, fname)))
        if not results:
            for root, _dirs, files in os.walk(output_dir):
                for fname in files:
                    if fname.endswith(".json") and "result" in fname.lower():
                        results.extend(self._parse_generic_json(os.path.join(root, fname)))
        return results

    def _parse_stats_json(self, path: str) -> list[HelmMetric]:
        try:
            with open(path) as f:
                data = json.load(f)
            results: list[HelmMetric] = []
            if isinstance(data, list):
                for item in data:
                    results.append(
                        HelmMetric(
                            scenario_name=item.get("scenario", "unknown"),
                            metric_name=item.get("metric", "mean"),
                            metric_value=float(item.get("value", 0)),
                            run_id=item.get("run_id", ""),
                        )
                    )
            elif isinstance(data, dict):
                for scenario, metrics in data.items():
                    if isinstance(metrics, dict):
                        for m_name, m_val in metrics.items():
                            if isinstance(m_val, (int, float)):
                                results.append(
                                    HelmMetric(
                                        scenario_name=scenario,
                                        metric_name=m_name,
                                        metric_value=float(m_val),
                                    )
                                )
            return results
        except Exception as e:
            logger.error("Failed to parse HELM stats %s: %s", path, e)
            return []

    def _parse_generic_json(self, path: str) -> list[HelmMetric]:
        try:
            with open(path) as f:
                data = json.load(f)
            results: list[HelmMetric] = []
            if isinstance(data, dict):
                metrics = data.get("metrics", data.get("results", {}))
                if isinstance(metrics, dict):
                    for m_name, m_val in metrics.items():
                        if isinstance(m_val, (int, float)):
                            results.append(
                                HelmMetric(
                                    scenario_name=data.get("scenario", Path(path).parent.name),
                                    metric_name=m_name,
                                    metric_value=float(m_val),
                                )
                            )
            return results
        except Exception as e:
            logger.error("Failed to parse HELM result %s: %s", path, e)
            return []
