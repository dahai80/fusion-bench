from fusion_bench.watermarks import compare, lookup, markdown_table

# CLAIM: verified by tests/test_watermarks.py


class TestLookup:
    def test_benchmark_filter(self):
        hits = lookup("terminal-bench-2")
        assert len(hits) == 2
        assert all(h["benchmark"] == "terminal-bench-2" for h in hits)

    def test_model_filter_keeps_benchmark_level(self):
        hits = lookup("terminal-bench-2", model="claude-haiku-4.5")
        models = {h["model"] for h in hits}
        assert "" in models and "claude-haiku-4.5" in models

    def test_model_filter_drops_other_model_rows(self):
        hits = lookup("terminal-bench-2", model="qwen3-32b")
        assert all(h["model"] == "" for h in hits)

    def test_normalizes_benchmark_name(self):
        assert lookup("SWE Bench Verified") == lookup("swe-bench-verified")
        assert lookup("unknown-bench") == []


class TestCompare:
    def test_parity_band(self):
        r = compare("swe-bench-verified", 0.81)
        assert r["verdict"] == "parity" and r["watermark"] == 0.85

    def test_gap_and_far_gap(self):
        assert compare("swe-bench-verified", 0.70)["verdict"] == "gap"
        assert compare("swe-bench-verified", 0.50)["verdict"] == "far-gap"

    def test_ahead(self):
        r = compare("swe-bench-verified", 0.90)
        assert r["verdict"] == "ahead" and r["delta"] > 0

    def test_no_watermark(self):
        r = compare("made-up-bench", 0.5)
        assert r["verdict"] == "no-watermark" and r["watermark"] is None

    def test_model_specific_row_used_when_matching(self):
        r = compare("terminal-bench-2", 0.614, model="claude-haiku-4.5")
        assert r["watermark"] == 0.614


class TestMarkdownTable:
    def test_rows_and_filter(self):
        full = markdown_table()
        assert "swe-bench-verified" in full and "terminal-bench-2" in full
        single = markdown_table("swe-bench-verified")
        assert "swe-bench-verified" in single and "terminal-bench-2" not in single
        assert "| benchmark | model | score |" in full
