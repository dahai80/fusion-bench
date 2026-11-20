"""Metric 5 — DAG node-failure recovery (issue #53).

Cowork arm: WorkflowEngine with a flaky middle node (fails N-1 attempts via a
counter file, then succeeds) and NodeConfig(max_retries). Recovery = the run
completes with the downstream node SUCCESS and the flaky node retried.
Dify arm: NOT installed locally — reported `unavailable`, never simulated.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

FLAKY_FAILS = 2


def _make_nodes(counter_path: Path) -> dict:
    from fusion_cowork.engine import BaseNode, NodeConfig, NodeResult, NodeStatus, register_node

    class PassNode(BaseNode):
        name = "pass"
        node_type = "pass"
        display_name = "pass"

        async def execute(self, inputs):  # noqa: ANN001
            return NodeResult(status=NodeStatus.SUCCESS, data={"done": True}, summary="pass")

    class FlakyNode(BaseNode):
        name = "flaky"
        node_type = "flaky"
        display_name = "flaky"

        async def execute(self, inputs):  # noqa: ANN001
            count = json.loads(counter_path.read_text()) if counter_path.exists() else 0
            count += 1
            counter_path.write_text(json.dumps(count))
            if count <= FLAKY_FAILS:
                return NodeResult(
                    status=NodeStatus.FAILED, error=f"Injected transient failure #{count}", summary="fail"
                )
            return NodeResult(status=NodeStatus.SUCCESS, data={"recovered_on_attempt": count}, summary="recovered")

    # Re-runs in one process would double-register; duplicates are harmless here.
    for cls in (PassNode, FlakyNode):
        try:
            register_node(cls)
        except Exception as e:
            logger.debug("node type %s already registered: %s", getattr(cls, "node_type", "?"), e)

    # Business failure (FAILED NodeResult) needs explicit opt-in to retry
    # (cowork issue #182 semantics); transient faults are the metric's subject.
    cfg_pass = NodeConfig(max_retries=0)
    cfg_flaky = NodeConfig(max_retries=FLAKY_FAILS + 1, retry_delay=0.1, retry_on_business_failure=True)
    return {
        "a": PassNode(node_id="a", config=cfg_pass),
        "flaky": FlakyNode(node_id="flaky", config=cfg_flaky),
        "c": PassNode(node_id="c", config=cfg_pass),
    }


def run_cowork_recovery(workdir: Path) -> dict:
    """a -> flaky -> c with injected transient failures; measure recovery."""
    import asyncio

    from fusion_cowork.engine import Workflow, WorkflowEngine

    workdir.mkdir(parents=True, exist_ok=True)
    counter = workdir / "flaky-counter.json"
    counter.unlink(missing_ok=True)
    nodes = _make_nodes(counter)
    registry_ok = True

    wf = Workflow(name="recovery-probe")
    for node in nodes.values():
        wf.add_node(node)
    wf.connect("a", "flaky")
    wf.connect("flaky", "c")

    engine = WorkflowEngine()
    start = time.monotonic()
    execution = asyncio.run(engine.execute(wf, initial_input={"seed": 1}))
    wall = time.monotonic() - start

    steps = {}
    for attr in ("steps", "step_results", "results"):
        maybe = getattr(execution, attr, None)
        if maybe:
            steps = maybe
            break
    detail: dict[str, dict] = {}
    for step in steps or []:
        node_id = getattr(step, "node_id", "?")
        detail[node_id] = {
            "status": str(getattr(step, "status", "?")),
            "attempt": getattr(step, "attempt", 1),
            "error": getattr(step, "error", None),
        }
    statuses = [v["status"] for v in detail.values()]
    recovered = all("SUCCESS" in s for s in statuses) and detail.get("flaky", {}).get("attempt", 0) > FLAKY_FAILS
    result = {
        "side": "cowork",
        "injected_failures": FLAKY_FAILS,
        "recovered": recovered,
        "wall_s": round(wall, 4),
        "steps": detail,
        "registry_used": registry_ok,
    }
    logger.info("cowork recovery: %s", json.dumps(result))
    return result


DIFY_UNAVAILABLE = {
    "side": "dify",
    "recovered": None,
    "error": "unavailable: dify is not installed locally and no network LLM/setup calls are allowed in the freeze window",
}
