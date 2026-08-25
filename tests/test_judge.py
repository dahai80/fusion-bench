"""Tests for Judge config + store."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from fusion_bench.judge import get_judge
from fusion_bench.judge.config import JudgeConfig, JudgeInput
from fusion_bench.judge.llm_judge import LLMJudge
from fusion_bench.storage.judge_store import JudgeStore


class TestJudgeConfig:
    def test_defaults(self):
        cfg = JudgeConfig(judge_model="qwen")
        assert cfg.judge_type == "hybrid"
        assert cfg.weight == 0.5
        assert cfg.temperature == 0
        assert cfg.criteria == []

    def test_to_dict_roundtrip(self):
        cfg = JudgeConfig(judge_model="m", judge_type="llm", weight=0.7, criteria=["correctness"], rubric="strict")
        d = cfg.to_dict()
        assert d["judge_type"] == "llm"
        cfg2 = JudgeConfig.from_dict(d)
        assert cfg2.weight == 0.7
        assert cfg2.criteria == ["correctness"]


class TestJudgeStore:
    def test_save_and_get(self, tmp_path):
        store = JudgeStore(db_path=str(tmp_path / "judge.db"))
        cfg = JudgeConfig(judge_model="qwen", criteria=["helpfulness"])
        store.save("default", cfg)
        got = store.get("default")
        assert got is not None
        assert got.judge_model == "qwen"
        assert got.criteria == ["helpfulness"]
        store.close()

    def test_get_missing_returns_none(self, tmp_path):
        store = JudgeStore(db_path=str(tmp_path / "judge.db"))
        assert store.get("nope") is None
        store.close()

    def test_list_and_delete(self, tmp_path):
        store = JudgeStore(db_path=str(tmp_path / "judge.db"))
        store.save("a", JudgeConfig(judge_model="m1"))
        store.save("b", JudgeConfig(judge_model="m2"))
        names = store.list()
        assert set(names) == {"a", "b"}
        assert store.delete("a") is True
        assert store.get("a") is None
        assert store.delete("missing") is False
        store.close()

    def test_overwrite_on_save(self, tmp_path):
        store = JudgeStore(db_path=str(tmp_path / "judge.db"))
        store.save("x", JudgeConfig(judge_model="old"))
        store.save("x", JudgeConfig(judge_model="new"))
        assert store.get("x").judge_model == "new"
        store.close()


def _mock_response(content: str) -> httpx.Response:
    request = MagicMock(spec=httpx.Request)
    return httpx.Response(
        status_code=200,
        request=request,
        json={"choices": [{"message": {"content": content}}]},
    )


class TestLLMJudge:
    @pytest.mark.asyncio
    async def test_parse_valid_json(self):
        cfg = JudgeConfig(judge_model="qwen", judge_type="llm")
        judge = LLMJudge(cfg)
        content = '{"score": 0.8, "reasoning": "mostly correct"}'
        with patch("fusion_bench.judge.llm_judge.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=_mock_response(content))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client
            verdict = await judge.judge(JudgeInput(prompt="p", expected="e", actual="a", criteria=["correctness"]))
        assert verdict.score == 0.8
        assert "mostly correct" in verdict.reasoning

    @pytest.mark.asyncio
    async def test_parse_malformed_fallback_neutral(self):
        cfg = JudgeConfig(judge_model="qwen", judge_type="llm")
        judge = LLMJudge(cfg)
        with patch("fusion_bench.judge.llm_judge.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=_mock_response("not json at all"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client
            verdict = await judge.judge(JudgeInput(prompt="p", expected="e", actual="a"))
        assert verdict.score == 0.5
        assert verdict.reasoning != ""

    @pytest.mark.asyncio
    async def test_timeout_fallback_neutral(self):
        cfg = JudgeConfig(judge_model="qwen", judge_type="llm")
        judge = LLMJudge(cfg)
        with patch("fusion_bench.judge.llm_judge.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client
            verdict = await judge.judge(JudgeInput(prompt="p", expected="e", actual="a"))
        assert verdict.score == 0.5

    @pytest.mark.asyncio
    async def test_score_clamped_to_unit_interval(self):
        cfg = JudgeConfig(judge_model="qwen", judge_type="llm")
        judge = LLMJudge(cfg)
        content = '{"score": 1.5, "reasoning": "over"}'
        with patch("fusion_bench.judge.llm_judge.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=_mock_response(content))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client
            verdict = await judge.judge(JudgeInput(prompt="p", expected="e", actual="a"))
        assert verdict.score == 1.0

    def test_get_judge_factory_llm(self):
        cfg = JudgeConfig(judge_model="qwen", judge_type="llm")
        judge = get_judge(cfg)
        assert isinstance(judge, LLMJudge)

    def test_get_judge_factory_rule_raises(self):
        cfg = JudgeConfig(judge_model="qwen", judge_type="rule")
        with pytest.raises(ValueError):
            get_judge(cfg)
