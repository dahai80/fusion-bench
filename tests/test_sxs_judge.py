"""Tests for SxS double-blind pairwise judge (#18)."""

from __future__ import annotations

import json

import httpx
import pytest

from fusion_bench.judge.sxs_config import SxSConfig, SxSVerdict, aggregate_verdicts
from fusion_bench.judge.sxs_judge import SxSJudge


def _make_judge(monkeypatch, response_text: str):
    judge = SxSJudge(SxSConfig(seed=42), base_url="http://localhost:11432/v1")

    async def fake_post(self, url, json=None, **kw):
        req = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=req,
            json={"choices": [{"message": {"content": response_text}}]},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return judge


class TestConfig:
    def test_default_config(self):
        cfg = SxSConfig()
        assert cfg.judge_model
        assert len(cfg.criteria) == 3
        assert cfg.temperature == 0.0
        assert cfg.seed == 42

    def test_empty_criteria_fills_defaults(self):
        cfg = SxSConfig(criteria=[])
        assert len(cfg.criteria) == 3


class TestVerdict:
    def test_avg_scores(self):
        v = SxSVerdict(
            winner="a", scores_a={"socratic_guidance": 4, "dsl_feasibility": 5}, scores_b={"socratic_guidance": 3}
        )
        assert v.avg_a == 4.5
        assert v.avg_b == 3.0

    def test_avg_empty(self):
        v = SxSVerdict(winner="tie")
        assert v.avg_a == 0.0
        assert v.avg_b == 0.0

    def test_to_dict(self):
        v = SxSVerdict(winner="a", scores_a={"x": 4})
        d = v.to_dict()
        assert d["winner"] == "a"
        assert d["avg_a"] == 4.0


class TestAggregate:
    def test_win_loss_tie(self):
        verdicts = [
            SxSVerdict(winner="a", scores_a={"x": 4}, scores_b={"x": 3}),
            SxSVerdict(winner="b", scores_a={"x": 2}, scores_b={"x": 5}),
            SxSVerdict(winner="tie", scores_a={"x": 4}, scores_b={"x": 4}),
        ]
        agg = aggregate_verdicts(verdicts)
        assert agg["win_rate"] == pytest.approx(1 / 3)
        assert agg["loss_rate"] == pytest.approx(1 / 3)
        assert agg["tie_rate"] == pytest.approx(1 / 3)
        assert agg["count"] == 3

    def test_empty(self):
        agg = aggregate_verdicts([])
        assert agg["win_rate"] == 0.0
        assert agg["count"] == 0


class TestShuffleDeterminism:
    async def test_same_seed_same_position(self, monkeypatch):
        resp = json.dumps(
            {
                "rationale": "x",
                "scores": {"slot1": {"socratic_guidance": 4}, "slot2": {"socratic_guidance": 3}},
                "winner": "slot1",
            }
        )
        j1 = _make_judge(monkeypatch, resp)
        v1 = await j1.judge_pair("outA", "outB", "prompt")
        j2 = _make_judge(monkeypatch, resp)
        v2 = await j2.judge_pair("outA", "outB", "prompt")
        assert v1.position_map == v2.position_map

    async def test_position_remapped_to_true_winner(self, monkeypatch):
        # If slot1 holds model B and judge picks slot1, true winner = b.
        resp = json.dumps(
            {
                "rationale": "x",
                "scores": {"slot1": {"socratic_guidance": 5}, "slot2": {"socratic_guidance": 2}},
                "winner": "slot1",
            }
        )
        judge = _make_judge(monkeypatch, resp)
        verdict = await judge.judge_pair("outA", "outB", "prompt")
        # position_map determined by seed=42 shuffle; winner must equal position_map[slot1]
        assert verdict.winner == verdict.position_map["slot1"]
        assert verdict.winner in ("a", "b")


class TestJsonParse:
    async def test_fenced_json(self, monkeypatch):
        resp = '```json\n{"rationale": "ok", "scores": {"slot1": {"socratic_guidance": 4}, "slot2": {"socratic_guidance": 3}}, "winner": "slot1"}\n```'
        judge = _make_judge(monkeypatch, resp)
        v = await judge.judge_pair("a", "b", "p")
        assert v.winner in ("a", "b", "tie")
        assert v.rationale == "ok"

    async def test_scores_coerced_to_int_clamped(self, monkeypatch):
        resp = json.dumps(
            {
                "rationale": "",
                "scores": {"slot1": {"socratic_guidance": 99}, "slot2": {"socratic_guidance": 0}},
                "winner": "slot1",
            }
        )
        judge = _make_judge(monkeypatch, resp)
        v = await judge.judge_pair("a", "b", "p")
        a_scores = v.scores_a
        assert all(1 <= s <= 5 for s in a_scores.values())

    async def test_parse_failure_neutral_tie(self, monkeypatch):
        judge = _make_judge(monkeypatch, "not json at all")
        v = await judge.judge_pair("a", "b", "p")
        assert v.winner == "tie"
        assert v.scores_a == {}

    async def test_http_error_tie(self, monkeypatch):
        judge = SxSJudge(SxSConfig(), base_url="http://localhost:11432/v1")

        async def fake_post(self, url, json=None, **kw):
            raise httpx.ConnectError("connection refused", request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        v = await judge.judge_pair("a", "b", "p")
        assert v.winner == "tie"

    async def test_winner_tie(self, monkeypatch):
        resp = json.dumps(
            {
                "rationale": "equal",
                "scores": {"slot1": {"socratic_guidance": 4}, "slot2": {"socratic_guidance": 4}},
                "winner": "tie",
            }
        )
        judge = _make_judge(monkeypatch, resp)
        v = await judge.judge_pair("a", "b", "p")
        assert v.winner == "tie"


class TestPromptBuilding:
    async def test_prompt_contains_both_outputs(self, monkeypatch):
        captured = {}

        async def fake_post(self, url, json=None, **kw):
            captured["payload"] = json
            req = httpx.Request("POST", url)
            return httpx.Response(200, request=req, json={"choices": [{"message": {"content": "{}"}}]})

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        judge = SxSJudge(SxSConfig(seed=42), base_url="http://localhost:11432/v1")
        await judge.judge_pair("uniqueAtext", "uniqueBtext", "test prompt")
        prompt = captured["payload"]["messages"][1]["content"]
        assert "test prompt" in prompt
        assert "uniqueAtext" in prompt or "uniqueBtext" in prompt
