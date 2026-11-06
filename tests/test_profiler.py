"""Issue #40 - backend-abstracted inference profiler tests."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from fusion_bench.engine.profiler import (
    SCHEMA_VERSION,
    InferenceProfiler,
    ProfilerConfig,
    _parse_memory_mb,
)


def _sse(content_chunks, prompt_tokens, completion_tokens):
    lines = []
    for c in content_chunks:
        chunk = {"choices": [{"delta": {"content": c}}]}
        lines.append("data: " + json.dumps(chunk))
    usage = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
    lines.append("data: " + json.dumps({"choices": [], "usage": usage}))
    lines.append("data: [DONE]")
    return lines


class FakeStreamResponse:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class FakeStreamCtx:
    def __init__(self, lines):
        self._lines = lines

    async def __aenter__(self):
        return FakeStreamResponse(self._lines)

    async def __aexit__(self, *exc):
        return False


def make_client(lines):
    client = MagicMock()
    client.stream = MagicMock(return_value=FakeStreamCtx(lines))
    return client


def _prof(runs=2, full=False):
    cfg = ProfilerConfig(full_profile=full, runs=runs, max_tokens=32)
    p = InferenceProfiler(mlx_base_url="http://localhost:11432/v1", config=cfg)
    p._client = make_client(_sse(["a", "b", "c"], 40, 3))
    p._client.aclose = AsyncMock()
    stats = MagicMock()
    stats.status_code = 200
    stats.json.return_value = {"model_memory_used_formatted": "1024.0MB"}
    p._client.get = AsyncMock(return_value=stats)
    return p


class TestUnifiedSchema:
    async def test_lightweight_schema_keys(self):
        p = _prof()
        out = await p.profile("m", "hello world")
        assert out["schema"] == SCHEMA_VERSION
        assert out["backend"] == "mlx"
        assert out["mode"] == "lightweight"
        assert out["engine"]["engine_itl_p50_p99"] is None
        assert out["engine"]["prefill_tok_s"] > 0
        assert out["engine"]["decode_tok_s"] > 0
        assert out["engine"]["engine_ttft_ms"]["p50"] > 0
        assert out["agent"]["agent_e2e_ms"]["p50"] > 0
        assert out["memory"]["peak_memory_mb"] == 1024.0
        await p.close()

    async def test_full_trace_itl_populated(self):
        p = _prof(full=True, runs=1)
        out = await p.profile("m", "hello world")
        assert out["mode"] == "full-trace"
        itl = out["engine"]["engine_itl_p50_p99"]
        assert itl is not None
        assert itl["tokens_sampled"] >= 1
        assert itl["p50"] >= 0
        assert itl["p99"] >= itl["p50"]
        await p.close()

    async def test_all_runs_fail_raises(self):
        p = _prof(runs=1)
        boom = MagicMock(side_effect=RuntimeError("x"))
        p._client.stream = MagicMock(side_effect=boom)
        with pytest.raises(RuntimeError):
            await p.profile("m", "hello world")
        await p.close()


class TestHelpers:
    def test_parse_memory_mb_units(self):
        assert _parse_memory_mb("1024.0MB") == 1024.0
        assert _parse_memory_mb("1.5GB") == 1536.0
        assert _parse_memory_mb("2048KB") == 2.0
        assert _parse_memory_mb("junk") == 0.0
