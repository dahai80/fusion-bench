"""Record ingestion for the durability benchmark (issue #70).

Normalizes three REAL sources into one record schema:
- fusion-supervisor run history (SQLite: runs + run_traces, fsb_data.db)
- fusion-cowork workflow audit trails (audit.jsonl digest chains)
- fusion-cowork scheduled-task stats (scheduled_tasks.json)

Pure readers — no synthesis, no defaults invented for missing fields.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

RUN_TERMINAL_OK = {"COMPLETED", "SUCCEEDED", "completed", "succeeded", "success"}
RUN_FAILED = {"FAILED", "failed", "ERROR", "error"}
TRACE_FAILURE_STATUSES = {"failed", "error", "crashed", "timeout", "killed"}


def load_supervisor_runs(db_path: Path) -> list[dict]:
    """Supervisor run history: one record per run with its node traces."""
    records: list[dict] = []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for run_id, _ws, wf_id, data in conn.execute("SELECT runId, wsId, wfId, data FROM runs"):
            run = json.loads(data)
            traces = []
            for _tid, node_id, seq, tdata in conn.execute(
                "SELECT traceId, nodeId, seq, data FROM run_traces WHERE runId = ? ORDER BY seq", (run_id,)
            ):
                t = json.loads(tdata)
                traces.append(
                    {
                        "node_id": node_id,
                        "seq": seq,
                        "status": str(t.get("status", "")).lower(),
                        "enter": t.get("enterTime", ""),
                        "exit": t.get("exitTime", ""),
                    }
                )
            records.append(
                {
                    "run_id": run_id,
                    "workflow_id": wf_id,
                    "status": str(run.get("status", "")),
                    "started_at": run.get("startTime", ""),
                    "ended_at": run.get("endTime", ""),
                    "trigger": run.get("triggerType", ""),
                    "node_traces": traces,
                }
            )
    finally:
        conn.close()
    logger.info("durability: loaded %d supervisor run(s) from %s", len(records), db_path)
    return records


def load_cowork_audits(assets_dir: Path) -> list[dict]:
    """Cowork audit trails: digest-chain revisions per workflow. The chain
    (prev_digest -> digest) is what checkpoint-restore correctness verifies."""
    records: list[dict] = []
    for audit in sorted(Path(assets_dir).glob("*/audit.jsonl")):
        revisions = []
        for line in audit.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            revisions.append(
                {
                    "at": row.get("at"),
                    "digest": row.get("digest", ""),
                    "prev_digest": row.get("prev_digest", ""),
                    "status": row.get("status", ""),
                }
            )
        records.append({"workflow_id": audit.parent.name, "revisions": revisions})
    logger.info("durability: loaded %d cowork audit trail(s) from %s", len(records), assets_dir)
    return records


def load_cowork_scheduled(path: Path) -> dict:
    """Cowork scheduled-task aggregate: run/fail counters (survival denominator)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    tasks = raw if isinstance(raw, list) else list(raw.values())
    total_runs = sum(int(t.get("run_count", 0)) for t in tasks)
    total_fails = sum(int(t.get("fail_count", 0)) for t in tasks)
    active = sum(1 for t in tasks if t.get("status") == "active")
    record = {
        "task_count": len(tasks),
        "active_count": active,
        "total_runs": total_runs,
        "total_failures": total_fails,
    }
    logger.info("durability: scheduled stats %s from %s", record, path)
    return record
