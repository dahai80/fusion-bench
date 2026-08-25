"""Judge configuration — defines how an LLM-as-judge blends with rule scoring."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class JudgeInput:
    prompt: str
    expected: str | None
    actual: str
    criteria: list[str] = field(default_factory=list)
    rubric: str = ""


@dataclass
class JudgeVerdict:
    score: float
    reasoning: str = ""
    per_criterion: dict[str, float] = field(default_factory=dict)


@dataclass
class JudgeConfig:
    judge_model: str
    judge_type: str = "hybrid"  # llm | rule | hybrid
    weight: float = 0.5
    criteria: list[str] = field(default_factory=list)
    rubric: str = ""
    temperature: float = 0.0

    def to_dict(self) -> dict:
        return {
            "judge_model": self.judge_model,
            "judge_type": self.judge_type,
            "weight": self.weight,
            "criteria": self.criteria,
            "rubric": self.rubric,
            "temperature": self.temperature,
        }

    @classmethod
    def from_dict(cls, d: dict) -> JudgeConfig:
        return cls(
            judge_model=d["judge_model"],
            judge_type=d.get("judge_type", "hybrid"),
            weight=d.get("weight", 0.5),
            criteria=d.get("criteria", []),
            rubric=d.get("rubric", ""),
            temperature=d.get("temperature", 0.0),
        )
