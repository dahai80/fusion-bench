"""Dual-metric acceptance split (#47, arXiv 2610.27889).

Derived at report time from task-level scores — raw result storage is
never changed. Given a baseline and a candidate mapping of task name ->
score (accuracy etc.):

- elicitation: tasks the baseline already scored > 0 on that moved
  ("the task got easier to pick" — capability was already there)
- expansion: tasks the baseline scored 0 on that now score > 0
  ("genuinely new capability")
- regression: tasks that lost score (reported honestly, never blended)

The two gains are never summed into a single blended score.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def split_acceptance(
    baseline: dict[str, float],
    candidate: dict[str, float],
) -> dict:
    tasks = sorted(set(baseline) | set(candidate))
    elicitation: list[dict] = []
    expansion: list[dict] = []
    regression: list[dict] = []
    for t in tasks:
        b = float(baseline.get(t, 0.0))
        c = float(candidate.get(t, 0.0))
        if c > 0 and b == 0:
            expansion.append({"task": t, "baseline": b, "candidate": c, "delta": round(c - b, 6)})
        elif b > 0 and c > b:
            elicitation.append({"task": t, "baseline": b, "candidate": c, "delta": round(c - b, 6)})
        elif b > 0 and c < b:
            regression.append({"task": t, "baseline": b, "candidate": c, "delta": round(c - b, 6)})
    out = {
        "elicitation": elicitation,
        "expansion": expansion,
        "regression": regression,
        "summary": {
            "elicitation_tasks": len(elicitation),
            "expansion_tasks": len(expansion),
            "regression_tasks": len(regression),
            "elicitation_gain": round(sum(e["delta"] for e in elicitation), 6),
            "expansion_gain": round(sum(e["delta"] for e in expansion), 6),
        },
    }
    logger.info(
        "Acceptance split: elicitation %d tasks (%.4f), expansion %d tasks (%.4f), regression %d",
        len(elicitation),
        out["summary"]["elicitation_gain"],
        len(expansion),
        out["summary"]["expansion_gain"],
        len(regression),
    )
    return out


def format_split_markdown(split: dict) -> str:
    s = split["summary"]
    lines = [
        "### Acceptance split (elicitation vs expansion)",
        "",
        f"- Elicitation: {s['elicitation_tasks']} task(s), gain {s['elicitation_gain']:.4f}",
        f"- Expansion: {s['expansion_tasks']} task(s), gain {s['expansion_gain']:.4f}",
        f"- Regression: {s['regression_tasks']} task(s)",
        "",
    ]
    for kind in ("elicitation", "expansion", "regression"):
        for e in split[kind]:
            lines.append(f"- [{kind}] {e['task']}: {e['baseline']:.4f} -> {e['candidate']:.4f} ({e['delta']:+.4f})")
    return "\n".join(lines)


__all__ = ["split_acceptance", "format_split_markdown"]
