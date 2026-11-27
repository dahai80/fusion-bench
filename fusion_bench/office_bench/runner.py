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
from .boundary import write_boundary
from .tasks import NEGATIVE_PROBES, OFFICE_TASKS, SYSTEM_PROMPT, OfficeTask

logger = logging.getLogger(__name__)

ARM = "fusion-harness"


def _snapshot(workspace: Path) -> dict[str, str]:
    import hashlib

    snap: dict[str, str] = {}
    if not workspace.is_dir():
        return snap
    for p in sorted(workspace.rglob("*")):
        if p.is_file():
            snap[str(p.relative_to(workspace))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return snap


def grade_negative(before: dict[str, str], workspace: Path) -> tuple[float, str]:
    """#64: pass iff the workspace is byte-identical after the episode."""
    after = _snapshot(workspace)
    created = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    modified = sorted(k for k in set(after) & set(before) if after[k] != before[k])
    if created or removed or modified:
        bits = []
        if created:
            bits.append(f"created={created}")
        if removed:
            bits.append(f"removed={removed}")
        if modified:
            bits.append(f"modified={modified}")
        return 0.0, "over-trigger: " + "; ".join(bits)
    return 1.0, "suppressed (workspace unchanged)"


SVCTL = Path.home() / "fusion" / "fusion-supervisor" / "target" / "release" / "fusion-sv"
MLXCTL = Path.home() / "fusion" / "fusion-mlx" / "start.sh"


def _probe(mlx_url: str) -> bool:
    try:
        return httpx.get(f"{mlx_url}/models", timeout=10.0).status_code in (200, 401)
    except httpx.HTTPError as exc:
        logger.warning("engine probe %s failed: %s", mlx_url, exc)
        return False


def _wait_ready(mlx_url: str, deadline_s: float) -> bool:
    deadline = time.monotonic() + deadline_s
    while time.monotonic() < deadline:
        time.sleep(10)
        if _probe(mlx_url):
            time.sleep(20)
            return True
    return False


def ensure_engine(mlx_url: str, babysit: bool = False) -> bool:
    """Bounded engine probe; restarts only with explicit opt-in (#60).

    Default: probe up to 3x (a slow engine under co-tenant load is not a
    dead engine) and report reachability — never restart anything. With
    babysit=True (issue #56 original behavior, now opt-in): restart via
    fusion-sv, fall back to start.sh; a missing lifecycle binary degrades
    to a warning + False, never a crash. A benchmark harness must never
    unilaterally restart a shared engine.
    """
    for attempt in range(1, 4):
        if _probe(mlx_url):
            return True
        logger.warning("engine probe %s unreachable (attempt %d/3)", mlx_url, attempt)
        if attempt < 3:
            time.sleep(5)
    if not babysit:
        logger.warning("engine unreachable and babysit disabled (--babysit-engine) — continuing without restart")
        return False
    for attempt in range(1, 3):
        if SVCTL.is_file():
            logger.warning("babysit: restarting fusion-mlx via fusion-sv (attempt %d)", attempt)
            subprocess.run([str(SVCTL), "restart", "fusion-mlx"], capture_output=True, text=True, timeout=300)
            if _wait_ready(mlx_url, 180):
                logger.info("engine back after fusion-sv restart (attempt %d)", attempt)
                return True
        else:
            logger.warning("babysit: fusion-sv binary missing at %s — skipping supervisor restart", SVCTL)
        if MLXCTL.is_file():
            logger.warning("babysit: falling back to start.sh lifecycle (attempt %d)", attempt)
            subprocess.run([str(MLXCTL), "stop"], capture_output=True, text=True, timeout=120)
            subprocess.run([str(MLXCTL), "start"], capture_output=True, text=True, timeout=300)
            if _wait_ready(mlx_url, 180):
                logger.info("engine back after start.sh fallback (attempt %d)", attempt)
                return True
        else:
            logger.warning("babysit: start.sh missing at %s — no lifecycle binary available", MLXCTL)
    logger.warning("babysit exhausted restart attempts — engine stays unreachable")
    return False


def to_harness_task(task: OfficeTask, verifier=None) -> HarnessTask:
    if verifier is None:

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
    core = [row for row in results if not row.get("negative_probe")]
    neg = [row for row in results if row.get("negative_probe")]
    passed = sum(1 for row in core if row["passed"])
    total = len(core)
    harness_errors = sum(1 for row in core if row.get("harness_error"))
    suppressed = sum(1 for row in neg if row["passed"])
    return {
        "run_id": run_id,
        "created_at": created_at,
        "models": {ARM: core[0].get("model", "") if core else ""},
        "arms": {
            ARM: {
                "total": total,
                "passed": passed,
                "pass_rate": round(passed / total, 4) if total else 0.0,
                "harness_errors": harness_errors,
                "by_type": _by_type(core),
                "negative_probes": {
                    "total": len(neg),
                    "suppressed": suppressed,
                    "suppression_rate": round(suppressed / len(neg), 4) if neg else 0.0,
                },
            }
        },
    }


async def run_office(mlx_url: str, model: str, out_dir: Path, max_steps: int = 8, babysit: bool = False) -> dict:
    client = ModelClient(base_url=mlx_url, model=model)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"office-{uuid.uuid4().hex[:8]}"
    results: list[dict] = []
    for idx, task in enumerate(OFFICE_TASKS, start=1):
        engine_ok = ensure_engine(mlx_url, babysit=babysit)
        if not engine_ok:
            logger.error("task %s skipped: engine unreachable, no babysit (#60)", task.task_id)
            results.append(
                {
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "app": task.app,
                    "steps": task.steps,
                    "passed": False,
                    "score": 0.0,
                    "verify_detail": "engine unreachable, no babysit binary/opt-in",
                    "run_error": "engine unreachable",
                    "harness_error": True,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "wall_s": 0.0,
                    "model": model,
                }
            )
            (out_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
            continue
        workspace = out_dir / "workspaces" / task.task_id
        task.materialize(workspace)
        runner = FusionHarnessRunner(RetryingClient(client), max_steps=max_steps, system_prompt=SYSTEM_PROMPT)
        result = await runner.run(to_harness_task(task), workspace)
        # Engine can die mid-task (connection-refused flaps) and the retry
        # window is shorter than a fusion-mlx cold start — re-run the task
        # once after engine recovery instead of recording a dead cell. The
        # re-run (and any recovery restart) only happens when the engine is
        # reachable again or babysit is explicitly enabled (#60).
        if result.llm_calls == 0 or result.error:
            logger.warning(
                "task %s produced no LLM traffic (%s) — re-probing engine before re-run",
                task.task_id,
                result.error or "0 calls",
            )
            engine_ok = ensure_engine(mlx_url, babysit=babysit)
            if engine_ok:
                result = await runner.run(to_harness_task(task), workspace)
        score, detail = task.grade(workspace)
        # #61: zero tokens in AND out with no error means the model was never
        # consulted (per-task HTTP starved in the engine queue under
        # co-tenant saturation). Score the attempt as a harness-error, not a
        # model failure — validator output against an empty attempt is a
        # queueing artifact, not a capability signal.
        harness_error = not result.error and result.tokens_in == 0 and result.tokens_out == 0
        if harness_error:
            logger.warning(
                "task %s classified harness-error: model never responded (tokens_in=0, tokens_out=0)",
                task.task_id,
            )
            score, detail = 0.0, "harness-error: model never responded (tokens_in=0, tokens_out=0)"
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
                "harness_error": harness_error,
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
    # Negative probes (#64): correct behavior is NOT mutating the workspace.
    # Reading via tools is fine — only byte-level mutations fail suppression.
    for task in NEGATIVE_PROBES:
        engine_ok = ensure_engine(mlx_url, babysit=babysit)
        if not engine_ok:
            logger.error("negative probe %s skipped: engine unreachable", task.task_id)
            results.append(
                {
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "app": task.app,
                    "steps": task.steps,
                    "passed": False,
                    "score": 0.0,
                    "verify_detail": "engine unreachable, no babysit binary/opt-in",
                    "run_error": "engine unreachable",
                    "harness_error": True,
                    "negative_probe": True,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "wall_s": 0.0,
                    "model": model,
                }
            )
            continue
        workspace = out_dir / "workspaces" / task.task_id
        task.materialize(workspace)
        before = _snapshot(workspace)
        runner = FusionHarnessRunner(RetryingClient(client), max_steps=max_steps, system_prompt=SYSTEM_PROMPT)
        result = await runner.run(to_harness_task(task, verifier=lambda ws, b=before: grade_negative(b, ws)), workspace)
        if result.llm_calls == 0 or result.error:
            engine_ok = ensure_engine(mlx_url, babysit=babysit)
            if engine_ok:
                result = await runner.run(
                    to_harness_task(task, verifier=lambda ws, b=before: grade_negative(b, ws)), workspace
                )
        score, detail = grade_negative(before, workspace)
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
                "harness_error": False,
                "negative_probe": True,
                "tokens_in": result.tokens_in,
                "tokens_out": result.tokens_out,
                "wall_s": round(result.wall_s, 2),
                "model": model,
            }
        )
        logger.info(
            "negative probe %s suppressed=%s detail=%s",
            task.task_id,
            results[-1]["passed"],
            detail,
        )
    summary = build_summary(results, run_id, datetime.now(UTC).isoformat())
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    write_boundary(out_dir, results)
    arm = summary["arms"][ARM]
    logger.info(
        "office run done: %s total=%d passed=%d pass_rate=%.2f",
        run_id,
        arm["total"],
        arm["passed"],
        arm["pass_rate"],
    )
    return summary
