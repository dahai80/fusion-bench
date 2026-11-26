"""FusionOffice-Bench runner (issue #56).

Runs the 32 office tasks through the fusion-harness loop
(harness_bench.FusionHarnessRunner + RetryingClient, office SYSTEM_PROMPT
variant reworded off the fusion-mlx#1665 crash path), grades each result file
with the vendored structural validators, and aggregates a fusion-eval-layout
summary.json ingested unchanged by `ft flywheel record`.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

from ..compare_suite.own_runner import RetryingClient
from ..harness_bench.model_client import ModelClient
from ..harness_bench.runners import FusionHarnessRunner
from ..harness_bench.tasks import HarnessTask
from .tasks import OFFICE_TASKS, SYSTEM_PROMPT, OfficeTask

logger = logging.getLogger(__name__)

ARM = "fusion-harness"

SVCTL = Path.home() / "fusion" / "fusion-supervisor" / "target" / "release" / "fusion-sv"
MLXCTL = Path.home() / "fusion" / "fusion-mlx" / "start.sh"


def ensure_engine(mlx_url: str, restarts: int = 2) -> bool:
    """Per-task engine babysit (upstream fusion-mlx#1665 wedges under
    sustained agent traffic): probe /models; on failure restart fusion-mlx
    via fusion-sv (authoritative lifecycle owner) and wait for readiness +
    warmup before the next task."""
    for attempt in range(1, restarts + 2):
        try:
            status = httpx.get(f"{mlx_url}/models", timeout=10.0).status_code
            if status in (200, 401):
                return True
            logger.warning("engine probe %s returned %d (attempt %d)", mlx_url, status, attempt)
        except httpx.HTTPError as exc:
            logger.warning("engine probe %s failed (attempt %d): %s", mlx_url, attempt, exc)
        if attempt > restarts:
            break
        logger.warning("restarting fusion-mlx via fusion-sv")
        subprocess.run([str(SVCTL), "restart", "fusion-mlx"], capture_output=True, text=True, timeout=300)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            time.sleep(10)
            try:
                if httpx.get(f"{mlx_url}/models", timeout=10.0).status_code in (200, 401):
                    time.sleep(20)
                    logger.info("engine back after restart (attempt %d)", attempt)
                    break
            except httpx.HTTPError:
                continue
        else:
            # fusion-sv may have the service in a stopped/unmanaged state —
            # fall back to the project's own start.sh lifecycle.
            logger.warning("fusion-sv restart did not revive engine — falling back to start.sh")
            subprocess.run([str(MLXCTL), "stop"], capture_output=True, text=True, timeout=120)
            subprocess.run([str(MLXCTL), "start"], capture_output=True, text=True, timeout=300)
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                time.sleep(10)
                try:
                    if httpx.get(f"{mlx_url}/models", timeout=10.0).status_code in (200, 401):
                        time.sleep(20)
                        logger.info("engine back after start.sh fallback (attempt %d)", attempt)
                        break
                except httpx.HTTPError:
                    continue
    return False


def to_harness_task(task: OfficeTask) -> HarnessTask:
    def verifier(workspace: Path) -> tuple[bool, str]:
        score, detail = task.grade(workspace)
        return score >= 1.0, detail

    return HarnessTask(
        task_id=task.task_id,
        instruction=task.instruction,
        setup_files={},
        reference_actions=[],
        verifier=verifier,
    )


def _by_type(results: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in results:
        bucket = out.setdefault(row["task_type"], {"passed": 0, "total": 0})
        bucket["total"] += 1
        bucket["passed"] += 1 if row["passed"] else 0
    for stats in out.values():
        stats["pass_rate"] = round(stats["passed"] / stats["total"], 4) if stats["total"] else 0.0
    return out


def build_summary(results: list[dict], run_id: str, created_at: str) -> dict:
    passed = sum(1 for row in results if row["passed"])
    total = len(results)
    return {
        "run_id": run_id,
        "created_at": created_at,
        "models": {ARM: results[0].get("model", "") if results else ""},
        "arms": {
            ARM: {
                "total": total,
                "passed": passed,
                "pass_rate": round(passed / total, 4) if total else 0.0,
                "by_type": _by_type(results),
            }
        },
    }


async def run_office(mlx_url: str, model: str, out_dir: Path, max_steps: int = 8) -> dict:
    client = ModelClient(base_url=mlx_url, model=model)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"office-{uuid.uuid4().hex[:8]}"
    results: list[dict] = []
    for idx, task in enumerate(OFFICE_TASKS, start=1):
        ensure_engine(mlx_url)
        workspace = out_dir / "workspaces" / task.task_id
        runner = FusionHarnessRunner(RetryingClient(client), max_steps=max_steps, system_prompt=SYSTEM_PROMPT)
        result = await runner.run(to_harness_task(task), workspace)
        # Engine can die mid-task (connection-refused flaps) and the retry
        # window is shorter than a fusion-mlx cold start — re-run the task
        # once after ensure_engine recovery instead of recording a dead cell.
        if result.llm_calls == 0 or result.error:
            logger.warning(
                "task %s produced no LLM traffic (%s) — recovering engine and re-running",
                task.task_id,
                result.error or "0 calls",
            )
            ensure_engine(mlx_url)
            result = await runner.run(to_harness_task(task), workspace)
        score, detail = task.grade(workspace)
        results.append(
            {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "app": task.app,
                "steps": task.steps,
                "passed": score >= 1.0,
                "score": score,
                "verify_detail": detail,
                "run_error": result.error or "",
                "tokens_in": result.tokens_in,
                "tokens_out": result.tokens_out,
                "wall_s": round(result.wall_s, 2),
                "model": model,
            }
        )
        logger.info(
            "office task %d/%d %s passed=%s detail=%s",
            idx,
            len(OFFICE_TASKS),
            task.task_id,
            results[-1]["passed"],
            detail,
        )
        (out_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    summary = build_summary(results, run_id, datetime.now(UTC).isoformat())
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    arm = summary["arms"][ARM]
    logger.info(
        "office run done: %s total=%d passed=%d pass_rate=%.2f",
        run_id,
        arm["total"],
        arm["passed"],
        arm["pass_rate"],
    )
    return summary
