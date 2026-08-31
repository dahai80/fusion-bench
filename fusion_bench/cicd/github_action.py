"""GitHub Action integration for Fusion-Bench CI/CD.

Importers/callers: .github/workflows/benchmark.yml, external CI pipelines.
Affected API: wraps SDK client; no new REST endpoints.
Data schema: BenchmarkResult via SDK; action.yml inputs/outputs.
User instruction: "对比PRD、架构、计划文档，查看是否还存在遗留、defer的任务" (P2-09 CI/CD FEAT-030).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

logger = logging.getLogger(__name__)


def run_benchmark(
    model: str | None = None,
    executor_key: str = "speed",
    level: str = "L1",
    base_url: str = "http://localhost:11467",
    gate_tier: str | None = None,
    timeout: int = 600,
) -> dict[str, Any]:
    from ..sdk import FusionBenchClient

    model = model or os.environ.get("FUSION_BENCH_MODEL", "")
    if not model:
        logger.error("No model specified; set FUSION_BENCH_MODEL or pass model= argument")
        return {"error": "no_model", "message": "Model name required"}

    with FusionBenchClient(base_url=base_url) as client:
        logger.info("Creating benchmark task: model=%s executor=%s", model, executor_key)
        task = client.create_task(
            model=model,
            executor_key=executor_key,
            level=level,
            timeout_seconds=timeout,
        )
        task_id = task.get("task_id", "")
        logger.info("Task created: %s", task_id)

        max_wait = timeout + 60
        start = time.time()
        status = "pending"
        while time.time() - start < max_wait:
            detail = client.get_task(task_id)
            status = detail.get("status", "unknown")
            if status in ("completed", "failed", "cancelled"):
                break
            time.sleep(5)

        result = client.get_result(task_id) if status == "completed" else {"status": status}

        if gate_tier:
            gate_result = client.check_gates(task_id, tier=gate_tier)
            result["gates"] = gate_result

        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write(f"task_id={task_id}\n")
                f.write(f"status={status}\n")
                metric = result.get("metric_value", 0)
                f.write(f"metric_value={metric}\n")

        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
                f.write("## Fusion-Bench Result\n")
                f.write(f"- **Model**: {model}\n")
                f.write(f"- **Executor**: {executor_key}\n")
                f.write(f"- **Status**: {status}\n")
                f.write(f"- **Task ID**: {task_id}\n")
                if result.get("metric_value") is not None:
                    f.write(f"- **Metric**: {result.get('metric_name', '')} = {result['metric_value']}\n")

        logger.info("Benchmark complete: task=%s status=%s", task_id, status)
        return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    model = os.environ.get("INPUT_MODEL", os.environ.get("FUSION_BENCH_MODEL", ""))
    executor = os.environ.get("INPUT_EXECUTOR", "speed")
    level = os.environ.get("INPUT_LEVEL", "L1")
    base_url = os.environ.get("INPUT_BASE_URL", "http://localhost:11467")
    gate_tier = os.environ.get("INPUT_GATE_TIER", "")
    timeout = int(os.environ.get("INPUT_TIMEOUT", "600"))

    result = run_benchmark(
        model=model or None,
        executor_key=executor,
        level=level,
        base_url=base_url,
        gate_tier=gate_tier or None,
        timeout=timeout,
    )

    if result.get("status") == "failed" or result.get("error"):
        logger.error("Benchmark failed: %s", json.dumps(result, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
