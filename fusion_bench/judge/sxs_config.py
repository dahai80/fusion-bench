"""SxS judge configuration — double-blind pairwise LLM judge (spec §399-402).

Criteria (1-5 score each):
- Socratic Guidance: guided questioning vs direct answer (5=guided, 1=lecture)
- BNUP Misconception Alignment: accurate prediagnosis of textbook error patterns
- DSL Feasibility: thinking chain matches generated DSL entity types
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_CRITERIA = ["socratic_guidance", "bnup_misconception_alignment", "dsl_feasibility"]


@dataclass
class SxSConfig:
    judge_model: str = "qwen2.5-32b-instruct"
    criteria: list[str] = field(default_factory=lambda: list(DEFAULT_CRITERIA))
    temperature: float = 0.0
    seed: int = 42
    max_tokens: int = 1024

    def __post_init__(self):
        if not self.criteria:
            self.criteria = list(DEFAULT_CRITERIA)


@dataclass
class SxSVerdict:
    # winner references the TRUE model identity (a/b/tie), not the shuffled slot.
    winner: str  # "a" | "b" | "tie"
    scores_a: dict[str, int] = field(default_factory=dict)
    scores_b: dict[str, int] = field(default_factory=dict)
    rationale: str = ""
    position_map: dict[str, str] = field(default_factory=dict)  # slot->true_id
    raw_response: str = ""

    @property
    def avg_a(self) -> float:
        return sum(self.scores_a.values()) / len(self.scores_a) if self.scores_a else 0.0

    @property
    def avg_b(self) -> float:
        return sum(self.scores_b.values()) / len(self.scores_b) if self.scores_b else 0.0

    def to_dict(self) -> dict:
        return {
            "winner": self.winner,
            "scores_a": self.scores_a,
            "scores_b": self.scores_b,
            "avg_a": self.avg_a,
            "avg_b": self.avg_b,
            "rationale": self.rationale,
        }


def aggregate_verdicts(verdicts: list[SxSVerdict]) -> dict[str, float]:
    # Win/loss/tie rate from model_a's perspective.
    if not verdicts:
        return {"win_rate": 0.0, "loss_rate": 0.0, "tie_rate": 0.0, "count": 0}
    wins = sum(1 for v in verdicts if v.winner == "a")
    losses = sum(1 for v in verdicts if v.winner == "b")
    ties = sum(1 for v in verdicts if v.winner == "tie")
    n = len(verdicts)
    return {
        "win_rate": wins / n,
        "loss_rate": losses / n,
        "tie_rate": ties / n,
        "count": n,
        "avg_score_a": sum(v.avg_a for v in verdicts) / n,
        "avg_score_b": sum(v.avg_b for v in verdicts) / n,
    }


__all__ = ["SxSConfig", "SxSVerdict", "DEFAULT_CRITERIA", "aggregate_verdicts"]
