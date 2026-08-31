"""LLM-as-Judge end-to-end test against a live fusion-mlx server.

Skipped unless FUSION_MLX_URL + FUSION_MLX_API_KEY + FUSION_BENCH_JUDGE_E2E=1
are set — so CI without a running model server never fails. Run locally:

    FUSION_MLX_URL=http://localhost:11434/v1 \\
    FUSION_MLX_API_KEY=dahai168 \\
    FUSION_BENCH_JUDGE_E2E=1 pytest tests/test_judge_e2e.py -v -s
"""

from __future__ import annotations

import os

import pytest

from fusion_bench.judge.config import JudgeConfig, JudgeInput
from fusion_bench.judge.llm_judge import LLMJudge

pytestmark = pytest.mark.skipif(
    os.environ.get("FUSION_BENCH_JUDGE_E2E") != "1",
    reason="set FUSION_BENCH_JUDGE_E2E=1 (with FUSION_MLX_URL/API_KEY) to run live judge e2e",
)

_BASE = os.environ.get("FUSION_MLX_URL", "http://localhost:11434/v1")
_KEY = os.environ.get("FUSION_MLX_API_KEY", "")
_MODEL = os.environ.get("FUSION_BENCH_JUDGE_MODEL", "Qwen3-0.6B-4bit")


@pytest.mark.asyncio
async def test_judge_returns_valid_verdict():
    config = JudgeConfig(name="e2e", model=_MODEL, judge_type="llm", temperature=0.0)
    judge = LLMJudge(config, base_url=_BASE, api_key=_KEY)
    verdict = await judge.judge(
        JudgeInput(
            prompt="What is 2+2?",
            expected="4",
            actual="4",
            criteria=["correctness"],
        )
    )
    assert 0.0 <= verdict.score <= 1.0
    assert verdict.reasoning  # non-empty
    print(f"\n[judge e2e] score={verdict.score} reasoning={verdict.reasoning[:120]}")


@pytest.mark.asyncio
async def test_judge_scores_wrong_answer_lower():
    # Correct answer should score at least as high as a wrong one.
    config = JudgeConfig(name="e2e2", model=_MODEL, judge_type="llm", temperature=0.0)
    judge = LLMJudge(config, base_url=_BASE, api_key=_KEY)
    good = await judge.judge(
        JudgeInput(prompt="capital of France?", expected="Paris", actual="Paris", criteria=["correctness"])
    )
    bad = await judge.judge(
        JudgeInput(prompt="capital of France?", expected="Paris", actual="London", criteria=["correctness"])
    )
    print(f"\n[judge e2e] good={good.score:.2f} bad={bad.score:.2f}")
    assert good.score >= bad.score


@pytest.mark.asyncio
async def test_judge_neutral_fallback_on_bad_url():
    # Unreachable base_url must not crash — neutral fallback (Rule 12).
    config = JudgeConfig(name="e2e3", model=_MODEL, judge_type="llm")
    judge = LLMJudge(config, base_url="http://127.0.0.1:9/v1", api_key="x")
    verdict = await judge.judge(JudgeInput(prompt="x", expected="y", actual="z", criteria=["c"]))
    assert verdict.score == 0.5
