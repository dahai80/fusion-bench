"""Judge module — LLM-as-Judge scoring for subjective evaluation.

JudgeConfig + JudgeStore are canonical in fusion_bench.core.judge_config and
re-exported here. JudgeInput/JudgeVerdict are judge DTOs (judge/config.py).
"""

from __future__ import annotations

from fusion_bench.core.judge_config import JudgeConfig, JudgeStore

from .base import Judge
from .config import JudgeInput, JudgeVerdict

__all__ = ["Judge", "JudgeConfig", "JudgeStore", "JudgeInput", "JudgeVerdict", "get_judge"]


def get_judge(config: JudgeConfig) -> Judge:
    # Factory: LLMJudge serves llm/hybrid. judge_type="rule" has no LLM judge —
    # executor uses rule_score directly and never calls get_judge. Guard fails
    # visibly (Rule 12) if a rule config is passed here by mistake.
    if config.judge_type == "rule":
        raise ValueError("judge_type='rule' has no LLM judge; executor uses rule_score directly")
    from .llm_judge import LLMJudge
    return LLMJudge(config)
