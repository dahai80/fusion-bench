"""Metric 3 — HITL pause/resume reliability (issue #53).

Protocol per side: worker process pauses on an approval gate and writes a
marker file; the parent SIGKILLs it mid-wait; a fresh worker resumes from the
side's durable store and must complete the approval (result file present with
resumed=True semantics). Success rate over repeats + resume wall time.
"""

from __future__ import annotations

import json
import logging
import signal
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

KILL_TIMEOUT_S = 60.0
RESUME_TIMEOUT_S = 60.0


def _worker_cmd(side: str, phase: str, store: str, workdir: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "fusion_bench.compare_suite.hitl_worker",
        "--side",
        side,
        "--phase",
        phase,
        "--store",
        store,
        "--marker",
        str(workdir / f"{side}-marker.json"),
        "--result",
        str(workdir / f"{side}-result.json"),
    ]


REPO_ROOT = Path(__file__).resolve().parents[2]


def _spawn(cmd: list[str]) -> subprocess.Popen:
    logger.info("spawn: %s", " ".join(cmd))
    # Worker must import fusion_bench regardless of the caller's cwd.
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(REPO_ROOT))


def run_hitl_side(side: str, workdir: Path, repeats: int = 1) -> dict:
    """Kill mid-wait + resume, `repeats` times; return reliability stats."""
    workdir.mkdir(parents=True, exist_ok=True)
    successes = 0
    resume_walls: list[float] = []
    failures: list[str] = []
    for i in range(repeats):
        run_dir = workdir / f"run-{i}"
        run_dir.mkdir(parents=True, exist_ok=True)
        store = str(run_dir / ("lg.db" if side == "langgraph" else "gate"))
        marker = run_dir / f"{side}-marker.json"
        result = run_dir / f"{side}-result.json"
        for p in (marker, result):
            p.unlink(missing_ok=True)

        start = _spawn(_worker_cmd(side, "start", store, run_dir))
        waited = 0.0
        while not marker.exists() and waited < KILL_TIMEOUT_S:
            if start.poll() is not None:
                break
            time.sleep(0.2)
            waited += 0.2
        if not marker.exists():
            out = start.stdout.read() if start.stdout else ""
            failures.append(f"run {i}: no marker, worker exit={start.poll()} out={out[-300:]}")
            if start.poll() is None:
                start.kill()
            continue
        # SIGKILL mid-wait, exactly the fault injection the metric demands.
        start.send_signal(signal.SIGKILL)
        start.wait()
        kill_s = waited

        resume_start = time.monotonic()
        resume = _spawn(_worker_cmd(side, "resume", store, run_dir))
        deadline = time.monotonic() + RESUME_TIMEOUT_S
        while not result.exists() and time.monotonic() < deadline:
            if resume.poll() is not None:
                break
            time.sleep(0.2)
        if resume.poll() is None:
            resume.kill()
        wall = time.monotonic() - resume_start
        if result.exists():
            data = json.loads(result.read_text(encoding="utf-8"))
            if side == "langgraph" or data.get("resumed"):
                successes += 1
                resume_walls.append(wall)
                logger.info("hitl %s run %d OK kill_after=%.1fs resume_wall=%.2fs", side, i, kill_s, wall)
                continue
        out = resume.stdout.read() if resume.stdout else ""
        failures.append(f"run {i}: resume failed exit={resume.poll()} wall={wall:.1f}s out={out[-300:]}")
        logger.warning("hitl %s run %d FAILED: %s", side, i, failures[-1])

    stats = {
        "side": side,
        "repeats": repeats,
        "resumed_ok": successes,
        "resume_rate": round(successes / repeats, 4) if repeats else 0.0,
        "resume_wall_s_mean": round(sum(resume_walls) / len(resume_walls), 4) if resume_walls else None,
        "failures": failures,
    }
    logger.info("hitl side=%s stats=%s", side, json.dumps(stats))
    return stats
