"""Issue #43 - SPS tuner tests (offline, mocked engine)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from fusion_bench.sps import (
    SCHEMA_VERSION,
    SpsConfig,
    SpsProfile,
    SpsTuner,
    is_stale,
    load_prefixes,
)


class TestPrefixLoader:
    def test_load_prompt_rows(self, tmp_path):
        p = tmp_path / "prefixes.jsonl"
        p.write_text(
            "\n".join(
                [
                    json.dumps({"prompt": "question one", "sampling_params": {"temperature": 0.0}}),
                    json.dumps({"prompt": "plain"}),
                ]
            ),
            encoding="utf-8",
        )
        out = load_prefixes(p)
        assert len(out) == 2
        assert out[0].sampling_params == {"temperature": 0.0}
        assert out[1].sampling_params == {}

    def test_rejects_bad_rows_and_empty(self, tmp_path):
        p = tmp_path / "bad.jsonl"
        p.write_text("not json\n", encoding="utf-8")
        with pytest.raises(ValueError, match="invalid JSON"):
            load_prefixes(p)
        p2 = tmp_path / "empty.jsonl"
        p2.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="no usable prefixes"):
            load_prefixes(p2)

    def test_input_ids_skipped_with_warning(self, tmp_path):
        p = tmp_path / "tok.jsonl"
        p.write_text(json.dumps({"input_ids": [1, 2, 3]}) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="no usable prefixes"):
            load_prefixes(p)


def _resp(tokens, width=None):
    r = MagicMock()
    r.status_code = 200
    r.raise_for_status = MagicMock()
    body = {"usage": {"completion_tokens": tokens}}
    if width is not None:
        body["speculative"] = {"draft_tokens": width}
    r.json.return_value = body
    return r


def _prof(repeats=2, widths=(4, 8), batch=(1,), echo_width=False):
    cfg = SpsConfig(widths=list(widths), batch_sizes=list(batch), repeats=repeats, max_tokens=32)
    t = SpsTuner(mlx_base_url="http://localhost:11432/v1", config=cfg)
    t._client = MagicMock()
    # Echo only when the engine would apply the width (serial path).
    if echo_width:
        t._client.post = AsyncMock(side_effect=lambda url, json: _resp(64, json["speculative"]["draft_tokens"]))
    else:
        t._client.post = AsyncMock(return_value=_resp(64))
    t._client.aclose = AsyncMock()
    metrics = MagicMock()
    metrics.status_code = 404
    t._client.get = AsyncMock(return_value=metrics)
    return t


class TestSweep:
    async def test_sweep_emits_profile(self, tmp_path):
        p = tmp_path / "prefixes.jsonl"
        p.write_text("\n".join(json.dumps({"prompt": f"q{i}"}) for i in range(10)), encoding="utf-8")
        prefixes = load_prefixes(p)
        t = _prof()
        profile = await t.sweep("m", prefixes, str(p))
        await t.close()
        assert profile.schema == SCHEMA_VERSION
        assert profile.backend == "mlx"
        assert profile.model == "m"
        assert len(profile.table) == 2  # widths x batches
        assert all(c["median_tok_s"] > 0 for c in profile.table)
        assert profile.best.get("1") in (4, 8)
        assert profile.acceptance_length is None  # engine 404 -> null
        assert profile.engine_spec_support == "unverified"
        assert len(profile.input_digest) == 16

    async def test_width_rides_request_body(self, tmp_path):
        p = tmp_path / "prefixes.jsonl"
        p.write_text(json.dumps({"prompt": "hello"}) + "\n", encoding="utf-8")
        t = _prof(widths=(12,), batch=(1,), repeats=1)
        await t.sweep("m", load_prefixes(p), str(p))
        body = t._client.post.call_args.kwargs["json"]
        await t.close()
        assert body["speculative"] == {"draft_tokens": 12}
        assert body["max_tokens"] == 32

    async def test_echo_marks_support_verified(self, tmp_path):
        p = tmp_path / "prefixes.jsonl"
        p.write_text(json.dumps({"prompt": "q"}) + "\n", encoding="utf-8")
        t = _prof(widths=(4,), batch=(1,), repeats=1, echo_width=True)
        profile = await t.sweep("m", load_prefixes(p), str(p))
        await t.close()
        assert profile.engine_spec_support == "verified"
        assert profile.table[0]["width_applied_rate"] == 1.0

    async def test_no_echo_keeps_unverified(self, tmp_path):
        p = tmp_path / "prefixes.jsonl"
        p.write_text(json.dumps({"prompt": "q"}) + "\n", encoding="utf-8")
        t = _prof(widths=(4,), batch=(1,), repeats=1, echo_width=False)
        profile = await t.sweep("m", load_prefixes(p), str(p))
        await t.close()
        assert profile.engine_spec_support == "unverified"
        assert profile.table[0]["width_applied_rate"] == 0.0

    async def test_acceptance_from_stats(self, tmp_path):
        p = tmp_path / "prefixes.jsonl"
        p.write_text(json.dumps({"prompt": "q"}) + "\n", encoding="utf-8")
        t = _prof(widths=(4,), batch=(1,), repeats=1)
        stats_resp = MagicMock()
        stats_resp.status_code = 200
        stats_resp.json.return_value = {
            "spec_decode": {"mtp_native": {"verifies": 40, "accepted": 60, "acceptance_length": 2.5}}
        }

        async def fake_get(path):
            return stats_resp if path.endswith("/stats") else MagicMock(status_code=404)

        t._client.get = AsyncMock(side_effect=fake_get)
        profile = await t.sweep("m", load_prefixes(p), str(p))
        await t.close()
        assert profile.acceptance_length == 2.5

    async def test_best_picks_fastest_width(self, tmp_path):
        p = tmp_path / "prefixes.jsonl"
        p.write_text(json.dumps({"prompt": "q"}) + "\n", encoding="utf-8")
        t = _prof(widths=(4, 8), batch=(1,), repeats=2)
        seen = []

        async def fake_timed_pass(client, model, prefixes, width, batch):
            seen.append(width)
            rate = 100.0 if width == 8 else 50.0
            return rate, 1, 1

        t._timed_pass = fake_timed_pass
        profile = await t.sweep("m", load_prefixes(p), str(p))
        await t.close()
        assert profile.best["1"] == 8


class TestProfileRoundtripAndStaleness:
    def test_save_load_roundtrip(self, tmp_path):
        prof = SpsProfile(model="m", chip="Apple M4 Pro", ram_gb=48.0, input_digest="abc123")
        f = tmp_path / "sps.json"
        prof.save(f)
        loaded = SpsProfile.load(f)
        assert loaded.schema == SCHEMA_VERSION
        assert loaded.chip == "Apple M4 Pro"
        assert loaded.ram_gb == 48.0

    def test_staleness_reasons(self, tmp_path, monkeypatch):
        monkeypatch.setattr("fusion_bench.sps.profile.current_hardware", lambda: ("Apple M4 Pro", 48.0))
        prof = SpsProfile(chip="Apple M2 Ultra", ram_gb=192.0, input_digest="old")
        reasons = is_stale(prof)
        assert any("hardware changed" in r for r in reasons)
        assert any("RAM changed" in r for r in reasons)
        assert any("unverified" in r for r in reasons)

    def test_fresh_when_all_match(self, tmp_path, monkeypatch):
        monkeypatch.setattr("fusion_bench.sps.profile.current_hardware", lambda: ("Apple M4 Pro", 48.0))
        prof = SpsProfile(
            chip="Apple M4 Pro",
            ram_gb=48.0,
            input_digest="x",
            engine_spec_support="verified",
        )
        assert is_stale(prof) == []


class TestSiteSubmission:
    def test_profile_to_records(self, tmp_path):
        from fusion_bench.sps.report import profile_to_records

        prof = SpsProfile(
            model="mlx-community--Qwen3-0.6B-4bit",
            chip="Apple M5 Max",
            ram_gb=128.0,
            engine_version="0.10.55",
            input_digest="abc12345",
            best={"1": 2},
            table=[
                {
                    "width": 2,
                    "batch_size": 1,
                    "median_tok_s": 29149.43,
                    "repeats_tok_s": [1.0],
                    "width_applied_rate": 1.0,
                }
            ],
            acceptance_length=None,
            engine_spec_support="unverified",
        )
        recs = profile_to_records(prof)
        assert len(recs) == 1
        r = recs[0]
        assert r.benchmark_type == "sps"
        assert r.task_name == "sps-tune"
        assert r.metric_name == "median_tok_s_w2_b1"
        assert r.metric_value == 29149.43
        assert r.chip_name == "Apple M5 Max"
        assert r.memory_gb == 128
        assert r.quantization == "4bit"
        assert r.submission_group == "sps-abc12345"
        detail = json.loads(r.detail)
        assert detail["width"] == 2
        assert detail["input_digest"] == "abc12345"

    def test_submit_profile_roundtrip(self, tmp_path):
        from fusion_bench.sps.report import submit_profile

        db_file = tmp_path / "bench.db"
        prof = SpsProfile(
            model="m-4bit",
            chip="Apple M5 Max",
            ram_gb=128.0,
            input_digest="d1",
            table=[
                {
                    "width": 1,
                    "batch_size": 1,
                    "median_tok_s": 100.0,
                    "repeats_tok_s": [100.0],
                    "width_applied_rate": 0.0,
                }
            ],
        )
        n = submit_profile(prof, db_path=str(db_file))
        assert n == 1
        from fusion_bench.reporter.bench_site_db import BenchSiteDB

        db = BenchSiteDB(str(db_file))
        try:
            rows = db.query(benchmark_type="sps")
            assert len(rows) == 1
            assert rows[0]["metric_name"] == "median_tok_s_w1_b1"
        finally:
            db.close()
