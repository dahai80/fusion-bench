"""Tests for Judge config + store."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from fusion_bench.core.plugin_base import TaskConfig
from fusion_bench.executors.agent_executor import AgentExecutor, AgentScenario, TurnRecord
from fusion_bench.executors.artifact_executor import (
    ArtifactCriteria,
    ArtifactExecutor,
    ArtifactTestCase,
)
from fusion_bench.judge import get_judge
from fusion_bench.judge.config import JudgeConfig, JudgeInput, JudgeVerdict
from fusion_bench.judge.llm_judge import LLMJudge
from fusion_bench.storage.judge_store import JudgeStore


class TestJudgeConfig:
    def test_defaults(self):
        cfg = JudgeConfig(model="qwen")
        assert cfg.judge_type == "hybrid"
        assert cfg.weight == 0.5
        assert cfg.temperature == 0
        assert cfg.criteria == []

    def test_to_dict_roundtrip(self):
        cfg = JudgeConfig(model="m", judge_type="llm", weight=0.7, criteria=["correctness"], rubric="strict")
        d = cfg.to_dict()
        assert d["judge_type"] == "llm"
        cfg2 = JudgeConfig.from_dict(d)
        assert cfg2.weight == 0.7
        assert cfg2.criteria == ["correctness"]


class TestJudgeStore:
    def test_save_and_get(self, tmp_path):
        store = JudgeStore(db_path=str(tmp_path / "judge.db"))
        cfg = JudgeConfig(model="qwen", criteria=["helpfulness"])
        store.save("default", cfg)
        got = store.get("default")
        assert got is not None
        assert got.model == "qwen"
        assert got.criteria == ["helpfulness"]
        store.close()

    def test_get_missing_returns_none(self, tmp_path):
        store = JudgeStore(db_path=str(tmp_path / "judge.db"))
        assert store.get("nope") is None
        store.close()

    def test_list_and_delete(self, tmp_path):
        store = JudgeStore(db_path=str(tmp_path / "judge.db"))
        store.save("a", JudgeConfig(model="m1"))
        store.save("b", JudgeConfig(model="m2"))
        names = store.list()
        assert set(names) == {"a", "b"}
        assert store.delete("a") is True
        assert store.get("a") is None
        assert store.delete("missing") is False
        store.close()

    def test_overwrite_on_save(self, tmp_path):
        store = JudgeStore(db_path=str(tmp_path / "judge.db"))
        store.save("x", JudgeConfig(model="old"))
        store.save("x", JudgeConfig(model="new"))
        assert store.get("x").model == "new"
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
        cfg = JudgeConfig(model="qwen", judge_type="llm")
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
        cfg = JudgeConfig(model="qwen", judge_type="llm")
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
        cfg = JudgeConfig(model="qwen", judge_type="llm")
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
        cfg = JudgeConfig(model="qwen", judge_type="llm")
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
        cfg = JudgeConfig(model="qwen", judge_type="llm")
        judge = get_judge(cfg)
        assert isinstance(judge, LLMJudge)

    def test_get_judge_factory_rule_raises(self):
        cfg = JudgeConfig(model="qwen", judge_type="rule")
        with pytest.raises(ValueError):
            get_judge(cfg)


class TestAgentJudgeBlend:
    @pytest.mark.asyncio
    async def test_hybrid_blend_applies_judge(self, tmp_path, monkeypatch):
        # Seed a hybrid judge config; mock the judge call to a fixed verdict.
        store = JudgeStore(db_path=str(tmp_path / "j.db"))
        store.save("hybrid-j", JudgeConfig(model="qwen", judge_type="hybrid", weight=0.5))
        monkeypatch.setattr("fusion_bench.executors.agent_executor.JudgeStore", lambda *a, **k: store)

        async def fake_judge(judge_input):
            return JudgeVerdict(score=1.0, reasoning="perfect")

        monkeypatch.setattr("fusion_bench.executors.agent_executor.get_judge", lambda cfg: type("J", (), {"judge": staticmethod(fake_judge)})())

        executor = AgentExecutor()
        cfg = TaskConfig(
            task_id="t", model="qwen", executor_key="agent", params={"scenarios": [], "judge": "hybrid-j"},
        )
        scenario = AgentScenario(scenario_id="s1", instruction="hi", expected_behavior="x", max_turns=1)

        async def fake_turns(sc, tc):
            return [TurnRecord(turn=0, role="assistant", content="done")]
        monkeypatch.setattr(executor, "_run_multi_turn", fake_turns)
        monkeypatch.setattr(executor, "_eval_response", lambda sc, resp: {"score": 0.0, "passed": False, "details": {}})
        monkeypatch.setattr(
            "fusion_bench.executors.agent_executor.TrajectoryScorer.score",
            lambda turns, scenario: {"trajectory_score": 0.0},
        )
        result = await executor._evaluate_scenario(scenario, cfg)
        # rule_score = 0.5*0 + 0.5*0 = 0.0 (criteria 0, traj 0). hybrid = 0.5*1.0 + 0.5*0 = 0.5
        assert abs(result.score - 0.5) < 1e-6
        store.close()

    @pytest.mark.asyncio
    async def test_no_judge_param_unchanged(self, monkeypatch):
        # No judge key -> pure rule scoring, zero behavior change.
        executor = AgentExecutor()
        scenario = AgentScenario(scenario_id="s1", instruction="hi", expected_behavior="x", max_turns=1)

        async def fake_turns(sc, tc):
            return [TurnRecord(turn=0, role="assistant", content="done")]
        monkeypatch.setattr(executor, "_run_multi_turn", fake_turns)
        monkeypatch.setattr(executor, "_eval_response", lambda sc, resp: {"score": 0.8, "passed": True, "details": {}})
        monkeypatch.setattr(
            "fusion_bench.executors.agent_executor.TrajectoryScorer.score",
            lambda turns, scenario: {"trajectory_score": 0.0},
        )
        cfg = TaskConfig(task_id="t", model="qwen", executor_key="agent", params={"scenarios": []})
        result = await executor._evaluate_scenario(scenario, cfg)
        # rule_score = 0.5*0.8 + 0.5*0 = 0.4
        assert abs(result.score - 0.4) < 1e-6
        assert result.meta.get("judge_source") is None


class TestArtifactJudgeBlend:
    @pytest.mark.asyncio
    async def test_hybrid_blend_applies_judge(self, tmp_path, monkeypatch):
        store = JudgeStore(db_path=str(tmp_path / "j.db"))
        store.save("art-j", JudgeConfig(model="qwen", judge_type="hybrid", weight=0.5))
        monkeypatch.setattr("fusion_bench.executors.artifact_executor.JudgeStore", lambda *a, **k: store)

        async def fake_judge(judge_input):
            return JudgeVerdict(score=1.0, reasoning="good")
        monkeypatch.setattr(
            "fusion_bench.executors.artifact_executor.get_judge",
            lambda cfg: type("J", (), {"judge": staticmethod(fake_judge)})(),
        )

        executor = ArtifactExecutor()
        tc = ArtifactTestCase(
            test_id="t1",
            artifact_type="json",
            prompt="make config",
            criteria=[ArtifactCriteria(name="valid_json", description="x", auto_check="json_valid")],
            min_length=5,
        )
        cfg = TaskConfig(task_id="t", model="qwen", executor_key="artifact", params={"judge": "art-j"})

        async def fake_gen(test_case, task_config):
            return '{"host": "x"}'
        monkeypatch.setattr(executor, "_generate_artifact", fake_gen)
        monkeypatch.setattr(executor, "_eval_artifact", lambda tc, art: {"score": 0.0, "passed": False, "details": {}})
        result = await executor._evaluate_artifact(tc, cfg)
        # rule 0.0, judge 1.0, hybrid weight 0.5 -> 0.5*1.0 + 0.5*0 = 0.5
        assert abs(result.score - 0.5) < 1e-6
        assert result.meta.get("judge_source") == "hybrid"
        store.close()

    @pytest.mark.asyncio
    async def test_no_judge_param_unchanged(self, monkeypatch):
        executor = ArtifactExecutor()
        tc = ArtifactTestCase(test_id="t1", artifact_type="json", prompt="p", min_length=5)

        async def fake_gen(test_case, task_config):
            return '{"a": 1}'
        monkeypatch.setattr(executor, "_generate_artifact", fake_gen)
        monkeypatch.setattr(executor, "_eval_artifact", lambda tc, art: {"score": 0.7, "passed": True, "details": {"k": True}})
        cfg = TaskConfig(task_id="t", model="qwen", executor_key="artifact", params={})
        result = await executor._evaluate_artifact(tc, cfg)
        assert abs(result.score - 0.7) < 1e-6
        assert result.meta.get("judge_source") is None
