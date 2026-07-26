"""Garak deep integration executor - structured result parsing for security probes.

Importers/callers: executors/__init__.py register_all(); api/app.py /tasks endpoint.
Affected API: new executor "garak"; no REST schema changes.
Data schema: GarakProbeResult (probe_name, passed, severity, detail); inherits EvalResult.
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (Enhancement A Garak deep integration).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

from fusion_bench.core.plugin_base import (
    EvalResult,
    ExecutorPlugin,
    ExecutorType,
    TaskConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class GarakProbeResult:
    probe_name: str
    passed: bool = True
    severity: str = "low"
    detail: str = ""
    detector_results: dict[str, Any] = field(default_factory=dict)


class GarakExecutor(ExecutorPlugin):
    name = "garak"
    executor_type = ExecutorType.SECURITY

    def is_available(self) -> bool:
        try:
            result = subprocess.run(["garak", "--version"], capture_output=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    async def run(self, task_config: TaskConfig) -> EvalResult:
        model = task_config.model
        probes = task_config.params.get("probes", "lite")
        generations = task_config.params.get("generations", 10)
        eval_threshold = task_config.params.get("eval_threshold", 0.8)

        probe_results: list[GarakProbeResult] = []
        output_dir = os.path.expanduser(f"~/.fusion-bench/garak/{model}")

        cmd = [
            "garak",
            "--model_type",
            "openai",
            "--model_name",
            model,
            "--probes",
            probes,
            "--generations",
            str(generations),
            "--report_prefix",
            f"{output_dir}/report",
        ]
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = env.get("OPENAI_API_KEY", "sk-fusion-bench-local")
        env["OPENAI_BASE_URL"] = env.get("OPENAI_BASE_URL", "http://localhost:11434/v1")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                env=env,
            )
            logger.info("Garak exit code: %d", proc.returncode)
            probe_results = _parse_garak_output(output_dir, proc.stdout)
        except FileNotFoundError:
            logger.warning("Garak not installed, falling back to built-in security executor")
            from fusion_bench.executors.security_executor import SecurityExecutor

            sec = SecurityExecutor()
            return await sec.run(task_config)
        except subprocess.TimeoutExpired:
            logger.error("Garak timed out after 600s")
            return EvalResult(score=0.0, passed=False, detail={"error": "garak_timeout"})
        except Exception as e:
            logger.error("Garak execution error: %s", e)
            return EvalResult(score=0.0, passed=False, detail={"error": str(e)})

        if not probe_results:
            return EvalResult(score=0.0, passed=False, detail={"error": "no_probe_results"})

        total = len(probe_results)
        passed = sum(1 for p in probe_results if p.passed)
        score = passed / total if total else 0.0

        return EvalResult(
            score=score,
            passed=score >= eval_threshold,
            detail={
                "probes_run": total,
                "probes_passed": passed,
                "probes_failed": total - passed,
                "results": [vars(r) for r in probe_results],
            },
        )


def _parse_garak_output(output_dir: str, stdout: str) -> list[GarakProbeResult]:
    results: list[GarakProbeResult] = []

    report_file = os.path.join(output_dir, "report.jsonl")
    if os.path.exists(report_file):
        try:
            with open(report_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    probe_name = entry.get("probe", entry.get("run", "unknown"))
                    status = entry.get("status", "")
                    passed = status not in ("FAIL", "fail", "detected")
                    severity = entry.get("severity", "medium")
                    results.append(
                        GarakProbeResult(
                            probe_name=probe_name,
                            passed=passed,
                            severity=severity,
                            detail=entry.get("detail", ""),
                            detector_results=entry.get("detectors", {}),
                        )
                    )
        except Exception as e:
            logger.warning("Failed to parse garak JSONL: %s", e)

    if not results and stdout:
        for line in stdout.split("\n"):
            line = line.strip()
            if "probe" in line.lower() and ("pass" in line.lower() or "fail" in line.lower()):
                passed = "pass" in line.lower()
                probe_name = line.split()[0] if line.split() else "unknown"
                results.append(
                    GarakProbeResult(
                        probe_name=probe_name,
                        passed=passed,
                        severity="high" if not passed else "low",
                        detail=line,
                    )
                )

    return results
