"""Judge module — LLM-as-Judge scoring for subjective evaluation.

JudgeConfig + JudgeStore are canonical in fusion_bench.core.judge_config and
re-exported here. JudgeInput/JudgeVerdict are judge DTOs (judge/config.py).
"""

from __future__ import annotations

import os

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

    base_url = os.environ.get("FUSION_MLX_URL", "http://localhost:11432/v1")
    return LLMJudge(config, base_url=base_url)
