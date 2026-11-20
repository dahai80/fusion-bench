"""HITL pause/resume worker (issue #53 metric 3).

Run as a subprocess: `python -m fusion_bench.compare_suite.hitl_worker --side ...`.
Phase start: set up the pause, write the marker file, then wait for the
parent's SIGKILL. Phase resume: recover from the durable store, complete the
approval, write the result file. Exit 0 + result file = resumed OK.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

logger = logging.getLogger("hitl_worker")


def _wait_forever() -> None:
    while True:
        time.sleep(0.5)


def _langgraph_start(db: str, marker: str, result: str) -> int:
    from .langgraph_rival import build_gate_graph, sqlite_saver

    saver = sqlite_saver(db)
    graph = build_gate_graph(saver, result)
    config = {"configurable": {"thread_id": "hitl"}}
    res = graph.invoke({"step": "start"}, config)
    interrupted = "__interrupt__" in res
    Path(marker).write_text(json.dumps({"interrupted": interrupted}), encoding="utf-8")
    logger.info("langgraph start phase done interrupted=%s", interrupted)
    if not interrupted:
        return 2
    _wait_forever()
    return 0


def _langgraph_resume(db: str, marker: str, result: str) -> int:
    from langgraph.types import Command

    from .langgraph_rival import build_gate_graph, sqlite_saver

    saver = sqlite_saver(db)
    graph = build_gate_graph(saver, result)
    config = {"configurable": {"thread_id": "hitl"}}
    graph.invoke(Command(resume={"approved": True}), config)
    ok = Path(result).exists()
    logger.info("langgraph resume phase done result_exists=%s", ok)
    return 0 if ok else 3


def _harness_start(state_dir: str, marker: str, result: str) -> int:
    from fusion_harness import HumanGate

    gate = HumanGate(state_dir)
    q = gate.ask("hitl", "approve the destructive step?")
    Path(marker).write_text(json.dumps({"question_id": q.id}), encoding="utf-8")
    logger.info("harness start phase done question=%s", q.id)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        r = gate.take_reply(q.id)
        if r is not None:
            Path(result).write_text(json.dumps({"approved": r, "resumed": False}), encoding="utf-8")
            return 0
        time.sleep(0.2)
    return 4


def _harness_resume(state_dir: str, marker: str, result: str) -> int:
    from fusion_harness import HumanGate

    gate = HumanGate(state_dir)
    pending = gate.pending("hitl")
    if not pending:
        logger.error("harness resume found no pending question")
        return 5
    q = pending[0]
    gate.reply(q.id, {"approved": True})
    r = gate.take_reply(q.id)
    Path(result).write_text(json.dumps({"approved": r, "resumed": True}), encoding="utf-8")
    logger.info("harness resume phase done question=%s", q.id)
    return 0 if r is not None else 6


def main() -> int:
    parser = argparse.ArgumentParser(description="HITL fault-injection worker (issue #53)")
    parser.add_argument("--side", required=True, choices=["langgraph", "harness"])
    parser.add_argument("--phase", required=True, choices=["start", "resume"])
    parser.add_argument("--store", required=True, help="sqlite db (langgraph) or state dir (harness)")
    parser.add_argument("--marker", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    Path(args.marker).parent.mkdir(parents=True, exist_ok=True)
    if args.side == "langgraph":
        return (
            _langgraph_start(args.store, args.marker, args.result)
            if args.phase == "start"
            else _langgraph_resume(args.store, args.marker, args.result)
        )
    return (
        _harness_start(args.store, args.marker, args.result)
        if args.phase == "start"
        else _harness_resume(args.store, args.marker, args.result)
    )


if __name__ == "__main__":
    sys.exit(main())
