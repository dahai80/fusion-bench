"""Tests for Judge config + store."""

from __future__ import annotations

from fusion_bench.judge.config import JudgeConfig
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
