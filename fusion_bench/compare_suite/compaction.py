"""Metric 4 — post-compaction resume correctness (issue #53).

Deterministic recall probe, no LLM: a synthetic transcript carries a pinned
task goal, numbered facts, and a latest instruction. Each side compacts at
threshold; the compacted state is probed for what survived. Score = probes
found / probes total (pinned goal, latest instruction, fact retention).
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

PINNED_GOAL = "Deploy the payments service to staging before Friday"
LATEST_INSTRUCTION = "Finalize the release notes and ping the on-call"
FACT_COUNT = 8
KEEP_RECENT = 2

FILLER = (
    "Reviewed the {name} dashboard and noted the trend line",
    "Synced with the {name} team about the migration plan",
    "Drafted the {name} section of the weekly update",
    "Checked the {name} alerts; nothing actionable",
)


def build_transcript(seed: int = 53) -> list[dict]:
    """Fixed transcript: goal first, filler facts, latest instruction last."""
    names = ["billing", "ingress", "storage", "search", "compute", "metrics", "billing", "ingress"]
    msgs: list[dict] = [
        {"role": "user", "content": f"Task goal: {PINNED_GOAL}"},
        {"role": "assistant", "content": "Understood, I will keep that goal pinned."},
    ]
    for i in range(FACT_COUNT):
        fact = f"fact-{i:02d}: budget line is {4000 + 100 * i} USD, owner {names[i % len(names)]}"
        msgs.append({"role": "user", "content": FILLER[i % len(FILLER)].format(name=names[i % len(names)])})
        msgs.append({"role": "assistant", "content": fact})
    msgs.append({"role": "user", "content": LATEST_INSTRUCTION})
    logger.info("transcript built: %d messages, %d facts, seed=%d", len(msgs), FACT_COUNT, seed)
    return msgs


def probe_state(messages: list[dict]) -> dict:
    """Which probes survived compaction into `messages`."""
    text = " ".join(str(m.get("content", "")) for m in messages)
    facts_found = sum(1 for i in range(FACT_COUNT) if f"fact-{i:02d}" in text)
    probes = {
        "pinned_goal": PINNED_GOAL in text,
        "latest_instruction": LATEST_INSTRUCTION in text,
        "facts_retained": facts_found,
    }
    probes["recall_score"] = round((probes["pinned_goal"] + probes["latest_instruction"]) / 2, 4)
    logger.info("probe: %s", json.dumps(probes))
    return probes


def compact_harness(messages: list[dict]) -> list[dict]:
    """Ours: fusion-harness Compactor at the warning threshold."""
    from fusion_harness import CompactionConfig, Compactor

    cfg = CompactionConfig(keep_recent_rounds=KEEP_RECENT, pin_task_goal=True)
    compactor = Compactor(config=cfg)
    level = compactor.should_compact(messages)
    # The probe transcript is small by design; force the warning threshold so
    # compaction actually runs (should_compact returns "none" below buffer).
    if level not in ("warning", "error"):
        level = "warning"
    compacted = compactor.compact(messages, level=level)
    logger.info("harness compaction: %d -> %d messages (level=%s)", len(messages), len(compacted), level)
    return compacted


def compact_langgraph(messages: list[dict]) -> list[dict]:
    """Rival: the extractive summarize node from langgraph_rival (no SummarizationNode in 1.2.10)."""
    from .langgraph_rival import build_summary_graph

    graph = build_summary_graph(model=None, keep_recent=KEEP_RECENT)
    msgs = []
    from langchain_core.messages import AIMessage, HumanMessage

    for m in messages:
        msgs.append(HumanMessage(content=m["content"]) if m["role"] == "user" else AIMessage(content=m["content"]))
    state = graph.invoke({"messages": msgs}, {})
    out = [
        {"role": "assistant" if isinstance(m, AIMessage) else "user", "content": str(m.content)}
        for m in state["messages"]
    ]
    logger.info("langgraph summarization: %d -> %d messages", len(messages), len(out))
    return out
