"""Judge configuration — re-exports canonical JudgeConfig from core + judge DTOs.

JudgeConfig + JudgeStore live in fusion_bench.core.judge_config (single source
of truth). JudgeInput/JudgeVerdict are judge-evaluation DTOs local to the
judge/ package (consumed by the Judge ABC + LLMJudge + executors).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fusion_bench.core.judge_config import JudgeConfig, JudgeStore


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


__all__ = ["JudgeConfig", "JudgeStore", "JudgeInput", "JudgeVerdict"]
