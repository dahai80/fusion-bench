"""SxS double-blind pairwise LLM judge (spec §399-402, #18).

Randomly shuffles model_a/model_b into slot positions 1/2 before building the
judge prompt (avoids position bias), then maps the judge's slot-winner back to
the true model identity. Parses JSON verdict {rationale, scores, winner}.
Reuses the _extract_json fallback pattern from llm_judge.py.
"""

from __future__ import annotations

import json
import logging
import random
import re
from typing import Any

import httpx

from .base import Judge
from .sxs_config import SxSConfig, SxSVerdict

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

_CRITERION_LABELS = {
    "socratic_guidance": "Socratic Guidance (5=guided questioning, 1=direct lecture)",
    "bnup_misconception_alignment": "BNUP Misconception Alignment (5=accurate textbook error prediagnosis)",
    "dsl_feasibility": "DSL Feasibility (5=thinking chain matches DSL entities)",
}


def _extract_json(content: str) -> dict[str, Any] | None:
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


class SxSJudge(Judge):
    # Double-blind pairwise judge. Deterministic shuffle at fixed seed.

    def __init__(self, config: SxSConfig, base_url: str = "http://localhost:11432/v1", api_key: str | None = None):
        self.config = config
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "local"

    async def judge_pair(
        self,
        model_a_output: str,
        model_b_output: str,
        prompt: str,
    ) -> SxSVerdict:
        rng = random.Random(self.config.seed)
        outputs = [("a", model_a_output), ("b", model_b_output)]
        rng.shuffle(outputs)
        slot1_true, slot1_text = outputs[0]
        slot2_true, slot2_text = outputs[1]
        position_map = {"slot1": slot1_true, "slot2": slot2_true}

        judge_prompt = self._build_prompt(prompt, slot1_text, slot2_text)
        try:
            content = await self._call_llm(judge_prompt)
            parsed = _extract_json(content)
            if not parsed:
                logger.warning("SxS judge parse failure; neutral fallback. raw=%s", content[:200])
                return SxSVerdict(winner="tie", position_map=position_map, raw_response=content)
            return self._map_verdict(parsed, position_map)
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            logger.warning("SxS judge LLM call failed: %s; tie fallback", e)
            return SxSVerdict(winner="tie", position_map=position_map)
        except Exception as e:
            logger.error("SxS judge unexpected error: %s; tie fallback", e)
            return SxSVerdict(winner="tie", position_map=position_map)

    def _build_prompt(self, user_prompt: str, slot1_text: str, slot2_text: str) -> str:
        criteria_lines = "\n".join(f"- {c}: {_CRITERION_LABELS.get(c, c)}" for c in self.config.criteria)
        return (
            "You are an impartial double-blind judge comparing two model outputs.\n"
            f"Original prompt: {user_prompt}\n\n"
            f"Output 1:\n{slot1_text}\n\n"
            f"Output 2:\n{slot2_text}\n\n"
            f"Score each output 1-5 on these criteria:\n{criteria_lines}\n\n"
            "Respond ONLY with JSON:\n"
            '{"rationale": "<brief>", '
            '"scores": {"slot1": {"<criterion>": <1-5>}, "slot2": {"<criterion>": <1-5>}}, '
            '"winner": "slot1" | "slot2" | "tie"}'
        )

    def _map_verdict(self, parsed: dict[str, Any], position_map: dict[str, str]) -> SxSVerdict:
        raw_scores = parsed.get("scores", {})
        if not isinstance(raw_scores, dict):
            raw_scores = {}
        slot1_scores = self._coerce_scores(raw_scores.get("slot1", {}))
        slot2_scores = self._coerce_scores(raw_scores.get("slot2", {}))
        true_scores_a, true_scores_b = self._remap_scores(slot1_scores, slot2_scores, position_map)
        winner_slot = str(parsed.get("winner", "tie")).lower()
        true_winner = self._remap_winner(winner_slot, position_map)
        return SxSVerdict(
            winner=true_winner,
            scores_a=true_scores_a,
            scores_b=true_scores_b,
            rationale=str(parsed.get("rationale", "")),
            position_map=position_map,
            raw_response=json.dumps(parsed),
        )

    def _coerce_scores(self, raw: Any) -> dict[str, int]:
        if not isinstance(raw, dict):
            return {}
        out: dict[str, int] = {}
        for k, v in raw.items():
            try:
                out[str(k)] = max(1, min(5, int(v)))
            except (TypeError, ValueError):
                continue
        return out

    def _remap_scores(
        self,
        slot1: dict[str, int],
        slot2: dict[str, int],
        position_map: dict[str, str],
    ) -> tuple[dict[str, int], dict[str, int]]:
        if position_map["slot1"] == "a":
            return slot1, slot2
        return slot2, slot1

    def _remap_winner(self, winner_slot: str, position_map: dict[str, str]) -> str:
        if winner_slot == "slot1":
            return position_map["slot1"]
        if winner_slot == "slot2":
            return position_map["slot2"]
        return "tie"

    async def _call_llm(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": "You are a double-blind evaluation judge. Output valid JSON only."},
            {"role": "user", "content": prompt},
        ]
        async with httpx.AsyncClient(
            timeout=120.0,
            headers={"Authorization": f"Bearer {self.api_key}"},
        ) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.config.judge_model,
                    "messages": messages,
                    "max_tokens": self.config.max_tokens,
                    "temperature": self.config.temperature,
                    "seed": self.config.seed,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    # Judge ABC compatibility — single-output scoring uses model_a as actual.
    async def judge(self, judge_input) -> SxSVerdict:  # type: ignore[override]
        return await self.judge_pair(judge_input.actual, judge_input.expected or "", judge_input.prompt)
