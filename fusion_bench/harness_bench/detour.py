"""DetourBench-style trajectory delta scoring (issue #48).

Against the task's minimal-action reference trajectory:
- detours: executed actions that match no reference action (greedy similarity
  matching, each reference action consumed at most once).
- one_step_misses: runs that solved the task but carried exactly one avoidable
  action — the cheapest documented failure shape (arXiv 2611.20844 genre).
- minimal_delta: detours + unmatched references (path length overhead).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

MATCH_THRESHOLD = 0.6

_WORD_RE = re.compile(r"[a-z0-9]+")


def _normalize(action: str) -> str:
    return " ".join(_WORD_RE.findall(action.lower()))


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def score_trajectory(
    executed_actions: list[str],
    reference_actions: list[str],
    passed: bool,
) -> dict:
    """Deterministic trajectory score. Pure function — no I/O, no RNG."""
    unmatched_refs = set(range(len(reference_actions)))
    detours = 0
    matches: list[dict] = []
    for action in executed_actions:
        best_i, best_score = -1, MATCH_THRESHOLD
        for i in unmatched_refs:
            score = _similarity(action, reference_actions[i])
            if score > best_score:
                best_i, best_score = i, score
        if best_i >= 0:
            unmatched_refs.discard(best_i)
            matches.append(
                {"executed": action, "reference": reference_actions[best_i], "similarity": round(best_score, 3)}
            )
        else:
            detours += 1
    one_step_miss = 1 if (passed and detours == 1) else 0
    return {
        "detours": detours,
        "one_step_misses": one_step_miss,
        "minimal_delta": detours + len(unmatched_refs),
        "reference_steps": len(reference_actions),
        "executed_steps": len(executed_actions),
        "matches": matches,
    }
