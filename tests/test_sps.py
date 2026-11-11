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


def _resp(tokens):
    r = MagicMock()
    r.status_code = 200
    r.raise_for_status = MagicMock()
    r.json.return_value = {"usage": {"completion_tokens": tokens}}
    return r


def _prof(repeats=2, widths=(4, 8), batch=(1,)):
    cfg = SpsConfig(widths=list(widths), batch_sizes=list(batch), repeats=repeats, max_tokens=32)
    t = SpsTuner(mlx_base_url="http://localhost:11432/v1", config=cfg)
    t._client = MagicMock()
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

    async def test_best_picks_fastest_width(self, tmp_path):
        p = tmp_path / "prefixes.jsonl"
        p.write_text(json.dumps({"prompt": "q"}) + "\n", encoding="utf-8")
        t = _prof(widths=(4, 8), batch=(1,), repeats=2)
        seen = []

        async def fake_timed_pass(client, model, prefixes, width, batch):
            seen.append(width)
            rate = 100.0 if width == 8 else 50.0
            return rate

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
