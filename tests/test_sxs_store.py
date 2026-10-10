"""Tests for SxS verdict SQLite persistence (#18)."""

from __future__ import annotations

from fusion_bench.judge.sxs_config import SxSVerdict
from fusion_bench.storage.sxs_store import SxSStore


def _verdict(winner: str = "a", sa: dict | None = None, sb: dict | None = None) -> SxSVerdict:
    return SxSVerdict(
        winner=winner,
        scores_a=sa or {"socratic_guidance": 4, "dsl_feasibility": 5},
        scores_b=sb or {"socratic_guidance": 3, "dsl_feasibility": 3},
        rationale="ok",
        position_map={"slot1": "a", "slot2": "b"},
    )


class TestSaveAndList:
    def test_save_and_retrieve(self, tmp_path):
        store = SxSStore(db_path=tmp_path / "sxs.db")
        vid = store.save_verdict("sess-1", "modelA", "modelB", "prompt", _verdict("a"))
        assert vid.startswith("sxs-")
        rows = store.list_verdicts("sess-1")
        assert len(rows) == 1
        assert rows[0]["verdict_id"] == vid
        assert rows[0]["model_a"] == "modelA"
        assert rows[0]["winner"] == "a"
        assert rows[0]["scores_a"]["socratic_guidance"] == 4
        store.close()

    def test_list_without_session(self, tmp_path):
        store = SxSStore(db_path=tmp_path / "sxs.db")
        store.save_verdict("s1", "a", "b", "p", _verdict("a"))
        store.save_verdict("s2", "a", "b", "p", _verdict("b"))
        rows = store.list_verdicts()
        assert len(rows) == 2
        store.close()

    def test_list_empty(self, tmp_path):
        store = SxSStore(db_path=tmp_path / "sxs.db")
        assert store.list_verdicts("nope") == []
        store.close()


class TestAggregate:
    def test_aggregate_rates(self, tmp_path):
        store = SxSStore(db_path=tmp_path / "sxs.db")
        store.save_verdict("s", "a", "b", "p", _verdict("a"))
        store.save_verdict("s", "a", "b", "p", _verdict("b"))
        store.save_verdict("s", "a", "b", "p", _verdict("tie"))
        agg = store.get_aggregate("s")
        assert agg["count"] == 3
        assert abs(agg["win_rate"] - 1 / 3) < 1e-6
        assert abs(agg["loss_rate"] - 1 / 3) < 1e-6
        assert abs(agg["tie_rate"] - 1 / 3) < 1e-6
        store.close()

    def test_aggregate_filter_by_model(self, tmp_path):
        store = SxSStore(db_path=tmp_path / "sxs.db")
        store.save_verdict("s", "a", "b", "p", _verdict("a"))
        store.save_verdict("s", "x", "y", "p", _verdict("a"))
        agg = store.get_aggregate("s", model_a="a", model_b="b")
        assert agg["count"] == 1
        store.close()

    def test_aggregate_empty(self, tmp_path):
        store = SxSStore(db_path=tmp_path / "sxs.db")
        agg = store.get_aggregate("empty")
        assert agg["count"] == 0
        assert agg["win_rate"] == 0.0
        store.close()


class TestPersistence:
    def test_survives_reopen(self, tmp_path):
        db = tmp_path / "sxs.db"
        store = SxSStore(db_path=db)
        store.save_verdict("s", "a", "b", "p", _verdict("a"))
        store.close()
        store2 = SxSStore(db_path=db)
        rows = store2.list_verdicts("s")
        assert len(rows) == 1
        store2.close()
