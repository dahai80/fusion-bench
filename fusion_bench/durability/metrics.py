"""Durability metric formulas (issue #70, spec docs/durability-spec-70.md).

Every metric returns {value, num, den, sufficient}. `sufficient` is a
denominator floor — a metric computed from too few real records is
reported as insufficient (value null) rather than estimated. Published
reports carry only real-record numbers.
"""

from __future__ import annotations

import logging
from datetime import datetime

from .records import RUN_FAILED, RUN_TERMINAL_OK, TRACE_FAILURE_STATUSES

logger = logging.getLogger(__name__)

MIN_RUNS = 5
MIN_FAILURES = 5
MIN_REVISIONS = 10
MIN_HOURS_ATTEMPTS = 3

SUFFICIENCY = {
    "long_task_survival_rate": MIN_RUNS,
    "failure_recovery_rate": MIN_FAILURES,
    "checkpoint_restore_correctness": MIN_REVISIONS,
    "hours_scale_completion_ratio": MIN_HOURS_ATTEMPTS,
}


def _metric(num: int, den: int, key: str) -> dict:
    den = max(den, 0)
    sufficient = den >= SUFFICIENCY[key]
    value = round(num / den, 4) if den and sufficient else None
    return {"value": value, "num": num, "den": den, "sufficient": sufficient}


def _run_duration_hours(run: dict) -> float | None:
    try:
        start = datetime.fromisoformat(run["started_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(run["ended_at"].replace("Z", "+00:00"))
    except (ValueError, KeyError, AttributeError):
        return None
    return (end - start).total_seconds() / 3600.0


def compute_metrics(supervisor_runs: list[dict], cowork_audits: list[dict], scheduled: dict) -> dict:
    """Four A6 metrics over real records only."""
    # 1. long-task survival rate: terminal-OK runs / terminal runs.
    terminal = [r for r in supervisor_runs if str(r.get("status", "")).lower() in RUN_TERMINAL_OK | RUN_FAILED]
    survived = sum(1 for r in terminal if str(r.get("status", "")).lower() in RUN_TERMINAL_OK)
    survival = _metric(survived, len(terminal), "long_task_survival_rate")

    # 2. failure recovery rate: runs that recorded node-trace failures but
    # still reached a terminal-OK status / runs with node-trace failures.
    failing = [r for r in supervisor_runs if any(t["status"] in TRACE_FAILURE_STATUSES for t in r["node_traces"])]
    recovered = sum(1 for r in failing if str(r.get("status", "")).lower() in RUN_TERMINAL_OK)
    recovery = _metric(recovered, len(failing), "failure_recovery_rate")

    # 3. checkpoint-restore correctness: digest-chain links that hold
    # (prev_digest of revision N+1 == digest of revision N) / total links.
    links = 0
    intact = 0
    for wf in cowork_audits:
        revs = sorted(
            (r for r in wf["revisions"] if r.get("digest")),
            key=lambda r: r.get("at") or 0,
        )
        for prev, cur in zip(revs, revs[1:], strict=False):
            if not prev.get("digest") or not cur.get("prev_digest"):
                continue
            links += 1
            intact += 1 if cur["prev_digest"] == prev["digest"] else 0
    checkpoint = _metric(intact, links, "checkpoint_restore_correctness")

    # 4. hours-scale completion ratio: runs observed at >= 1h wall time that
    # reached terminal-OK / runs observed at >= 1h. Runs shorter than 1h are
    # out of scope for the hours-scale axis (documented in the spec).
    long_runs = [r for r in supervisor_runs if (d := _run_duration_hours(r)) is not None and d >= 1.0]
    long_ok = sum(1 for r in long_runs if str(r.get("status", "")).lower() in RUN_TERMINAL_OK)
    hours_ratio = _metric(long_ok, len(long_runs), "hours_scale_completion_ratio")

    metrics = {
        "long_task_survival_rate": survival,
        "failure_recovery_rate": recovery,
        "checkpoint_restore_correctness": checkpoint,
        "hours_scale_completion_ratio": hours_ratio,
        "scheduled_task_stats": {
            "task_count": scheduled.get("task_count", 0),
            "active_count": scheduled.get("active_count", 0),
            "total_runs": scheduled.get("total_runs", 0),
            "total_failures": scheduled.get("total_failures", 0),
        },
    }
    logger.info(
        "durability metrics: survival=%s recovery=%s checkpoint=%s hours=%s",
        survival["value"],
        recovery["value"],
        checkpoint["value"],
        hours_ratio["value"],
    )
    return metrics
