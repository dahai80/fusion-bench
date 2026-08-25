"""LLM-as-Judge — calls fusion-mlx /chat/completions, parses JSON verdict."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from .base import Judge
from .config import JudgeConfig, JudgeInput, JudgeVerdict

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_NEUTRAL_SCORE = 0.5


def _extract_json(content: str) -> dict[str, Any] | None:
    # Try fenced block first, then raw JSON object, then whole-string parse.
    m = _JSON_FENCE_RE.search(content)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(content.strip())
    except json.JSONDecodeError:
        pass
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None


class LLMJudge(Judge):
    # Scores output via fusion-mlx LLM call. Deterministic at temperature=0.

    def __init__(self, config: JudgeConfig, base_url: str = "http://localhost:11432/v1"):
        self.config = config
        self.base_url = base_url.rstrip("/")

    async def judge(self, judge_input: JudgeInput) -> JudgeVerdict:
        prompt = self._build_prompt(judge_input)
        try:
            content = await self._call_llm(prompt)
            parsed = _extract_json(content)
            if not parsed:
                logger.warning("Judge parse failure; neutral fallback. raw=%s", content[:200])
                return JudgeVerdict(score=_NEUTRAL_SCORE, reasoning="judge parse failure; neutral fallback")
            score = float(parsed.get("score", _NEUTRAL_SCORE))
            score = max(0.0, min(1.0, score))
            reasoning = str(parsed.get("reasoning", ""))
            per_criterion = {}
            raw_pc = parsed.get("per_criterion", {})
            if isinstance(raw_pc, dict):
                for k, v in raw_pc.items():
                    try:
                        per_criterion[str(k)] = max(0.0, min(1.0, float(v)))
                    except (TypeError, ValueError):
                        continue
            return JudgeVerdict(score=score, reasoning=reasoning, per_criterion=per_criterion)
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            logger.warning("Judge LLM call failed: %s; neutral fallback", e)
            return JudgeVerdict(score=_NEUTRAL_SCORE, reasoning=f"judge call failed: {e}")
        except Exception as e:
            # Never crash a suite on judge error (spec failure handling).
            logger.error("Judge unexpected error: %s; neutral fallback", e)
            return JudgeVerdict(score=_NEUTRAL_SCORE, reasoning=f"judge error: {e}")

    def _build_prompt(self, judge_input: JudgeInput) -> str:
        criteria_text = ", ".join(judge_input.criteria) if judge_input.criteria else "overall quality"
        parts = [
            "You are an impartial judge. Score the response.",
            f"Prompt: {judge_input.prompt}",
        ]
        if judge_input.expected is not None:
            parts.append(f"Expected: {judge_input.expected}")
        parts.append(f"Actual: {judge_input.actual}")
        parts.append(f"Criteria: {criteria_text}")
        if judge_input.rubric:
            parts.append(f"Rubric: {judge_input.rubric}")
        parts.append('Respond ONLY with JSON: {"score": <0.0-1.0>, "reasoning": "<brief>"}')
        return "\n".join(parts)

    async def _call_llm(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": "You are an evaluation judge. Output valid JSON only."},
            {"role": "user", "content": prompt},
        ]
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.config.judge_model,
                    "messages": messages,
                    "max_tokens": 512,
                    "temperature": self.config.temperature,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
