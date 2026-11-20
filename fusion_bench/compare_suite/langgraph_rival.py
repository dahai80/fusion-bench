"""langgraph rival arm (issue #53).

- run_task: create_react_agent + run_bash tool on the shared task set
  (metrics 1-2: completion rate, token cost).
- build_gate_graph: minimal StateGraph with an interrupt() node for the HITL
  pause/resume metric (metric 3). Machinery-only on purpose: the variable
  under test is the checkpoint/interrupt machinery, not the model.
- build_summary_graph: hand-rolled summarization node (langgraph 1.2.10 has
  no SummarizationNode prebuilt) for the post-compaction recall metric
  (metric 4).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_OBS_CHARS = 2000


def run_bash_output(command: str, workspace: Path) -> str:
    """Execute one bash command inside the workspace (same sandbox rules as ours)."""
    try:
        proc = subprocess.run(
            ["bash", "-c", command],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (proc.stdout + proc.stderr).strip()
    except subprocess.TimeoutExpired:
        output = "ERROR: command timed out after 30s"
    except Exception as e:
        output = f"ERROR: {e}"
    if len(output) > MAX_OBS_CHARS:
        output = output[:MAX_OBS_CHARS] + "...[truncated]"
    return output


def build_agent(model: Any, workspace: Path, checkpointer: Any = None) -> Any:
    from langchain_core.tools import tool
    from langgraph.prebuilt import create_react_agent

    @tool
    def run_bash(cmd: str) -> str:
        """Run one bash command inside the sandbox workspace and return its output."""

        return run_bash_output(cmd, workspace)

    graph = create_react_agent(model, [run_bash], checkpointer=checkpointer)
    logger.info("langgraph react agent built (checkpointer=%s)", type(checkpointer).__name__ if checkpointer else None)
    return graph


def run_task(graph: Any, instruction: str, thread_id: str = "bench") -> dict:
    """Run one react-agent episode; usage comes from the bound model copy
    (bind_tools returns model_copy, so the original never sees the calls)."""
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 40}
    start = time.monotonic()
    state = graph.invoke({"messages": [("user", f"Task: {instruction}")]}, config)
    wall = time.monotonic() - start
    bound = getattr(getattr(graph.nodes.get("agent", None), "bound", None), "usage", None)
    usage = dict(bound) if isinstance(bound, dict) else {}
    logger.info(
        "langgraph episode done wall=%.2fs messages=%d tokens=%d/%d",
        wall,
        len(state["messages"]),
        usage.get("input_tokens", 0),
        usage.get("output_tokens", 0),
    )
    return {"wall_s": wall, "message_count": len(state["messages"]), "usage": usage}


def sqlite_saver(path: str) -> Any:
    """Durable checkpointer for kill/resume fault injection."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    conn = sqlite3.connect(path, check_same_thread=False)
    saver = SqliteSaver(conn)
    logger.info("SqliteSaver ready at %s", path)
    return saver


def build_gate_graph(checkpointer: Any, result_path: str) -> Any:
    """3-node machinery graph: plan -> gate(interrupt) -> apply(writes result)."""
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import interrupt
    from typing_extensions import TypedDict

    class GateState(TypedDict):
        step: str

    def plan(state: GateState) -> dict:
        return {"step": "planned"}

    def gate(state: GateState) -> dict:
        answer = interrupt({"question": "approve the destructive step?"})
        return {"step": f"gate:{answer}"}

    def apply(state: GateState) -> dict:
        Path(result_path).write_text(json.dumps({"approved": state["step"], "applied": True}), encoding="utf-8")
        return {"step": "applied"}

    g = StateGraph(GateState)
    g.add_node("plan", plan)
    g.add_node("gate", gate)
    g.add_node("apply", apply)
    g.add_edge(START, "plan")
    g.add_edge("plan", "gate")
    g.add_edge("gate", "apply")
    g.add_edge("apply", END)
    graph = g.compile(checkpointer=checkpointer)
    logger.info("langgraph gate graph built")
    return graph


def build_summary_graph(model: Any, keep_recent: int = 2) -> Any:
    """chat -> summarize (deterministic extractive summary) -> recall."""
    from langgraph.graph import END, START, StateGraph
    from typing_extensions import TypedDict

    class MsgState(TypedDict):
        messages: list

    def summarize(state: MsgState) -> dict:
        msgs = state["messages"]
        if len(msgs) <= keep_recent + 1:
            return {}
        tail = msgs[-keep_recent:]
        digest = "; ".join(str(m.content)[:80] for m in msgs[1:-keep_recent])
        from langchain_core.messages import SystemMessage

        summary = SystemMessage(content=f"[summary of {len(msgs) - keep_recent - 1} earlier messages] {digest}")
        return {"messages": [summary] + tail}

    g = StateGraph(MsgState)
    g.add_node("summarize", summarize)
    g.add_edge(START, "summarize")
    g.add_edge("summarize", END)
    graph = g.compile()
    logger.info("langgraph summary graph built")
    return graph
