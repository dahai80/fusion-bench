"""Issue #47 — dual-metric acceptance split + cache-proof bench requests."""

from __future__ import annotations

from fusion_bench.engine.bench_http import CACHE_BYPASS_HEADERS, bench_client, cache_status
from fusion_bench.reporter.acceptance import format_split_markdown, split_acceptance


class TestSplitAcceptance:
    def test_all_three_buckets(self):
        baseline = {"mmlu": 0.70, "gsm8k": 0.0, "math": 0.50, "arc": 0.60}
        candidate = {"mmlu": 0.75, "gsm8k": 0.30, "math": 0.40, "arc": 0.60}
        split = split_acceptance(baseline, candidate)
        assert [e["task"] for e in split["elicitation"]] == ["mmlu"]
        assert [e["task"] for e in split["expansion"]] == ["gsm8k"]
        assert [e["task"] for e in split["regression"]] == ["math"]
        assert split["summary"]["elicitation_gain"] == 0.05
        assert split["summary"]["expansion_gain"] == 0.30

    def test_never_blended(self):
        split = split_acceptance({"a": 0.5}, {"a": 0.9, "b": 0.9})
        s = split["summary"]
        # No single combined score key exists — the two gains stay separate.
        assert "blended" not in s and "total_gain" not in s
        assert "elicitation_gain" in s and "expansion_gain" in s

    def test_unchanged_task_in_no_bucket(self):
        split = split_acceptance({"a": 0.5}, {"a": 0.5})
        assert split["elicitation"] == [] and split["expansion"] == [] and split["regression"] == []

    def test_missing_sides_default_zero(self):
        split = split_acceptance({}, {"new_task": 0.4})
        assert [e["task"] for e in split["expansion"]] == ["new_task"]

    def test_markdown_lists_each_bucket(self):
        split = split_acceptance({"a": 0.5, "b": 0.0, "c": 0.4}, {"a": 0.6, "b": 0.2, "c": 0.1})
        md = format_split_markdown(split)
        assert "[elicitation] a" in md
        assert "[expansion] b" in md
        assert "[regression] c" in md
        assert "Elicitation: 1 task(s)" in md and "Expansion: 1 task(s)" in md


class TestBenchClientCacheHeaders:
    def test_bypass_header_always_present(self):
        client = bench_client(timeout=5.0)
        try:
            assert client.headers.get("X-Cache") == "bypass"
        finally:
            pass

    def test_auth_headers_merged_not_replaced(self):
        client = bench_client(headers={"Authorization": "Bearer k"})
        try:
            assert client.headers.get("X-Cache") == "bypass"
            assert client.headers.get("Authorization") == "Bearer k"
        finally:
            pass

    def test_cache_status_reads_header(self):
        import httpx

        resp = httpx.Response(200, headers={"X-Cache": "HIT"})
        assert cache_status(resp) == "HIT"
        assert cache_status(httpx.Response(200)) == ""

    def test_bypass_constant(self):
        assert CACHE_BYPASS_HEADERS == {"X-Cache": "bypass"}
