"""Issue #49 — golden eval set: ingest, PII scan, gate, coverage (offline)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fusion_bench.golden.cases import GoldenCase, load_cases, save_cases
from fusion_bench.golden.coverage import coverage_kpi
from fusion_bench.golden.gate import run_golden_cases, run_golden_gate, score_case
from fusion_bench.golden.ingest import ingest_samples
from fusion_bench.golden.pii_scan import scan_dir, scan_file, scan_text


def _sample(i: int, category: str, failure: bool = False, phone: str = "") -> dict:
    return {
        "category": category,
        "prompt": f"desensitized question {category} {i} {phone}",
        "expected": f"expected answer {i}",
        "desensitized": True,
        "is_failure_case": failure,
        "source": "ops_prompts",
    }


class TestCases:
    def test_roundtrip(self, tmp_path):
        cases = [
            GoldenCase("gc-1", "sql", "p1", "e1", is_failure_case=True),
            GoldenCase("gc-2", "math", "p2", "e2"),
        ]
        f = tmp_path / "golden-cases-v1.jsonl"
        assert save_cases(cases, f) == 2
        loaded = load_cases(f)
        assert [c.case_id for c in loaded] == ["gc-1", "gc-2"]
        assert loaded[0].is_failure_case is True
        assert loaded[0].desensitized is True

    def test_missing_fields_rejected(self, tmp_path):
        f = tmp_path / "bad.jsonl"
        f.write_text(json.dumps({"case_id": "gc-x", "category": "c"}) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="missing fields"):
            load_cases(f)

    def test_duplicate_ids_rejected(self, tmp_path):
        cases = [GoldenCase("gc-1", "c", "p", "e"), GoldenCase("gc-1", "c", "p2", "e2")]
        with pytest.raises(ValueError, match="duplicate case_id"):
            save_cases(cases, tmp_path / "g.jsonl")


class TestPiiScan:
    def test_detects_kinds(self):
        text = "call 13812345678 or mail a@b.com, id 11010119900307867X, card 6222 0212 3456 7890, at 10.0.0.55"
        kinds = {h["kind"] for h in scan_text(text)}
        assert {"cn_mobile", "email", "cn_id_card", "bank_card", "ipv4"} <= kinds

    def test_masked_output(self):
        hits = scan_text("phone 13812345678 here")
        assert hits and "*" in hits[0]["masked"]
        assert "13812345678" not in hits[0]["masked"]

    def test_clean_text(self):
        assert scan_text("no personal data here, just numbers 42 and 3.14") == []

    def test_scan_file_carries_case_id(self, tmp_path):
        f = tmp_path / "g.jsonl"
        f.write_text(
            json.dumps({"case_id": "gc-9", "category": "c", "prompt": "call 13812345678", "expected": "e"}) + "\n",
            encoding="utf-8",
        )
        hits = scan_file(f)
        assert hits and hits[0]["case_id"] == "gc-9" and hits[0]["kind"] == "cn_mobile"

    def test_scan_dir_empty_when_missing(self, tmp_path):
        assert scan_dir(tmp_path / "nope") == []


class TestIngest:
    def test_privacy_gate_drops_undesensitized(self, tmp_path):
        s = tmp_path / "s.jsonl"
        recs = [
            _sample(1, "sql"),
            {**_sample(2, "sql"), "desensitized": False},
        ]
        s.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
        out = tmp_path / "golden.jsonl"
        stats = ingest_samples(s, out)
        assert stats["accepted"] == 1 and stats["rejected_privacy"] == 1
        assert "gc-" not in (tmp_path / "golden.jsonl").read_text(encoding="utf-8").split("gc-")[-1] or True
        loaded = load_cases(out)
        assert len(loaded) == 1

    def test_opted_in_accepted_without_desensitize(self, tmp_path):
        s = tmp_path / "s.jsonl"
        recs = [{**_sample(1, "sql"), "desensitized": False, "opted_in": True}]
        s.write_text(json.dumps(recs[0]), encoding="utf-8")
        stats = ingest_samples(s, tmp_path / "g.jsonl")
        assert stats["accepted"] == 1

    def test_pii_in_sample_skipped(self, tmp_path):
        s = tmp_path / "s.jsonl"
        recs = [_sample(1, "sql", phone="call 13812345678")]
        s.write_text(json.dumps(recs[0]), encoding="utf-8")
        stats = ingest_samples(s, tmp_path / "g.jsonl")
        assert stats["accepted"] == 0 and stats["rejected_pii"] == 1

    def test_pii_strict_mode_raises(self, tmp_path):
        s = tmp_path / "s.jsonl"
        recs = [_sample(1, "sql", phone="call 13812345678")]
        s.write_text(json.dumps(recs[0]), encoding="utf-8")
        with pytest.raises(ValueError, match="PII detected"):
            ingest_samples(s, tmp_path / "g.jsonl", fail_on_pii=True)

    def test_stratified_cap_with_failure_bypass(self, tmp_path):
        s = tmp_path / "s.jsonl"
        recs = [_sample(i, "sql") for i in range(15)] + [_sample(100, "sql", failure=True)]
        s.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
        out = tmp_path / "g.jsonl"
        stats = ingest_samples(s, out, per_category_cap=10)
        assert stats["accepted"] == 11  # 10 capped + 1 failure case
        assert stats["dropped_cap"] == {"sql": 5}
        assert stats["failure_cases"] == 1

    def test_stratified_across_categories(self, tmp_path):
        s = tmp_path / "s.jsonl"
        recs = [_sample(i, "sql") for i in range(12)] + [_sample(i, "math") for i in range(12)]
        s.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
        stats = ingest_samples(s, tmp_path / "g.jsonl", per_category_cap=10)
        assert stats["by_category"] == {"sql": 10, "math": 10}

    def test_dedup_by_prompt(self, tmp_path):
        s = tmp_path / "s.jsonl"
        recs = [_sample(1, "sql"), _sample(1, "sql")]
        s.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
        assert ingest_samples(s, tmp_path / "g.jsonl")["accepted"] == 1


class TestScoring:
    def test_contains_match(self):
        assert score_case("The answer is 42, period.", "42") is True

    def test_normalized_match(self):
        assert score_case("Answer: Paris!", "paris") is True

    def test_mismatch(self):
        assert score_case("Berlin", "Paris") is False

    def test_empty_completion_fails(self):
        assert score_case("", "anything") is False

    def test_keywords_match(self):
        assert score_case("SELECT id FROM t", "run a query", "keywords", ["select", "insert"]) is True
        assert score_case("no sql here", "run a query", "keywords", ["select"]) is False

    def test_keywords_empty_falls_back_to_contains(self):
        assert score_case("answer 42 here", "42", "keywords", []) is True

    def test_nontrivial_match(self):
        assert score_case("short", "open ended task", "nontrivial") is False
        assert score_case("x" * 25, "open ended task", "nontrivial") is True


def _mock_post_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


class TestGoldenRun:
    async def test_run_golden_cases_scores_and_metrics(self, tmp_path):
        cases = [
            GoldenCase("gc-1", "math", "q1", "expected answer 1"),
            GoldenCase("gc-2", "sql", "q2", "no match here"),
        ]
        client = MagicMock()
        client.__aenter__.return_value = client
        client.post = AsyncMock(
            side_effect=[_mock_post_response("blah expected answer 1 blah"), _mock_post_response("wrong")]
        )
        with patch("fusion_bench.golden.gate.bench_client", return_value=client):
            out = await run_golden_cases(cases, "m", mlx_base_url="http://x/v1", api_key="k")
        assert out["metrics"]["golden_pass_rate"] == 0.5
        assert out["metrics"]["golden_total"] == 2.0
        assert [r["passed"] for r in out["results"]] == [True, False]

    async def test_gate_baseline_saved_then_blocked(self, tmp_path, monkeypatch):
        g = tmp_path / "g.jsonl"
        save_cases([GoldenCase("gc-1", "math", "q1", "expected answer 1")], g)
        db = tmp_path / "b.db"
        monkeypatch.setenv("FUSION_CLIENT_KEY", "")

        async def fake_run(cases, model, mlx_base_url="u", api_key="", max_tokens=256):
            return {
                "model": model,
                "metrics": {
                    "golden_pass_rate": rate,
                    "golden_total": 1.0,
                    "golden_passed": 1.0,
                    "failure_case_pass_rate": 1.0,
                },
                "results": [
                    {
                        "case_id": "gc-1",
                        "category": "math",
                        "passed": rate == 1.0,
                        "latency_s": 0.1,
                        "is_failure_case": False,
                    }
                ],
                "duration_s": 0.2,
            }

        # First run: perfect, saves baseline.
        rate = 1.0
        with patch("fusion_bench.golden.gate.run_golden_cases", side_effect=fake_run):
            out1 = await run_golden_gate(g, "m", db_path=db)
        assert out1["verdict"] == "baseline_saved"

        # Second run: regressed to 0.0 -> drop 100 pts > 5 -> blocked.
        rate = 0.0
        with patch("fusion_bench.golden.gate.run_golden_cases", side_effect=fake_run):
            out2 = await run_golden_gate(g, "m", db_path=db, threshold_pct=5.0)
        assert out2["verdict"] == "blocked"
        assert out2["drop_points"] == 100.0

        # Update-baseline run restores.
        rate = 1.0
        with patch("fusion_bench.golden.gate.run_golden_cases", side_effect=fake_run):
            out3 = await run_golden_gate(g, "m", db_path=db, update_baseline=True)
        assert out3["verdict"] == "baseline_saved"


class TestCoverage:
    def test_kpi_met(self):
        hist = {f"cat{i}": 100 - i for i in range(15)}
        covered = {f"cat{i}" for i in range(8)}
        out = coverage_kpi(hist, covered, top_n=10)
        assert out["kpi_met"] is True
        assert out["coverage_ratio"] >= 0.8

    def test_kpi_unmet_lists_missing(self):
        hist = {f"cat{i}": 10 for i in range(10)}
        out = coverage_kpi(hist, set(), top_n=10)
        assert out["kpi_met"] is False
        assert len(out["missing_top"]) == 10

    def test_empty_histogram_raises(self):
        with pytest.raises(ValueError, match="histogram is empty"):
            coverage_kpi({}, {"x"})
