"""Issue #40 — backend-abstracted inference profiler.

One interface over hardware differences; the only implemented backend is
MLX (fusion-mlx HTTP API — this codebase never imports MLX directly).
Output is one unified JSON schema ("fusion-bench.profiler/v1") consumed
by the report module.

Two modes (AC 1):
- lightweight (default, always on): TTFT, prefill/decode tok/s, agent-side
  end-to-end, peak memory. One clock read per run boundary — negligible
  overhead (<0.1% of a multi-second request).
- full-trace (opt-in, --enable-full-profile / full_profile=True, kept OFF
  in CI): additionally records one timestamp per streamed token to compute
  engine-side inter-token latency p50/p99. Overhead is one
  time.perf_counter() call plus a list append per token — at the slowest
  observed decode rates (>10 ms/token) this is <0.1% of token time; it is
  real overhead, so it stays gated.

Latency keys are split engine-side vs agent-side and never merged (AC 4):
- engine_ttft_ms / engine_itl_p50_p99 — measured at the HTTP stream
  boundary of fusion-mlx (queue + HTTP overhead included).
- agent_e2e_ms — full client wall-clock per request.
Cross-backend numbers must never be averaged into one headline without
the per-backend breakdown (the "backend" key is mandatory).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from fusion_core.config import client_key

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "fusion-bench.profiler/v1"


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(int(len(sorted_values) * pct / 100.0), len(sorted_values) - 1)
    return sorted_values[idx]


@dataclass
class ProfilerConfig:
    # full-trace adds per-token timestamp collection (see module docstring
    # for the overhead accounting). Default off = lightweight mode.
    full_profile: bool = False
    runs: int = 3
    max_tokens: int = 128
    temperature: float = 0.7
    timeout: float = 300.0


@dataclass
class RunSample:
    ttft_ms: float = 0.0
    e2e_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    token_intervals_ms: list[float] = field(default_factory=list)


def _parse_memory_mb(mem_str: str) -> float:
    # fusion-mlx /stats formats like "1234.5MB" / "1.2GB"
    try:
        s = mem_str.strip().upper()
        if s.endswith("GB"):
            return float(s[:-2]) * 1024.0
        if s.endswith("MB"):
            return float(s[:-2])
        if s.endswith("KB"):
            return float(s[:-2]) / 1024.0
        if s.endswith("B"):
            return float(s[:-1]) / (1024.0 * 1024.0)
    except ValueError:
        pass
    return 0.0


class InferenceProfiler:
    """Backend-abstracted profiler. MLX backend via fusion-mlx HTTP."""

    BACKEND = "mlx"

    def __init__(
        self,
        mlx_base_url: str = "http://localhost:11432/v1",
        api_key: str = "",
        config: ProfilerConfig | None = None,
    ):
        if not api_key:
            api_key = client_key()
        self.mlx_base_url = mlx_base_url.rstrip("/")
        self.api_key = api_key
        self.config = config or ProfilerConfig()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            # Anonymous dev mode (empty client_key) omits the header —
            # httpx rejects "Bearer " with an empty token.
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            self._client = httpx.AsyncClient(
                base_url=self.mlx_base_url,
                timeout=self.config.timeout,
                headers=headers,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _profile_run(
        self,
        client: httpx.AsyncClient,
        model: str,
        prompt: str,
    ) -> RunSample:
        cfg = self.config
        sample = RunSample()
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": cfg.max_tokens,
            "temperature": cfg.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        start = time.perf_counter()
        first_token_at = 0.0
        last_token_at = 0.0
        usage: dict[str, Any] = {}
        content_chunks = 0

        async with client.stream("POST", "/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if not data_str or data_str == "[DONE]":
                    continue
                try:
                    chunk = json.loads(data_str)
                except ValueError:
                    continue
                if usage == {} and chunk.get("usage"):
                    usage = chunk["usage"]
                choices = chunk.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        now = time.perf_counter()
                        if first_token_at == 0.0:
                            first_token_at = now
                        elif cfg.full_profile:
                            sample.token_intervals_ms.append((now - last_token_at) * 1000.0)
                        last_token_at = now
                        content_chunks += 1

        end = time.perf_counter()
        sample.ttft_ms = (first_token_at - start) * 1000.0 if first_token_at else 0.0
        sample.e2e_ms = (end - start) * 1000.0
        sample.prompt_tokens = usage.get("prompt_tokens", len(prompt) // 4)
        sample.completion_tokens = usage.get("completion_tokens", content_chunks)
        return sample

    async def _peak_memory_mb(self, client: httpx.AsyncClient) -> float:
        # /stats lives at the service root, but the client base_url ends in
        # /v1 (httpx merges relative paths onto it) — use the absolute root.
        root = self.mlx_base_url[: -len("/v1")] if self.mlx_base_url.endswith("/v1") else self.mlx_base_url
        try:
            resp = await client.get(f"{root}/stats")
            if resp.status_code == 200:
                stats = resp.json()
                # fusion-mlx direct /stats reports bytes (current_model_memory);
                # some gateway builds report a formatted string.
                raw = stats.get("current_model_memory")
                if isinstance(raw, (int, float)):
                    return float(raw) / (1024.0 * 1024.0)
                return _parse_memory_mb(str(stats.get("model_memory_used_formatted", "0B")))
        except Exception as e:
            logger.warning("Failed to read fusion-mlx /stats: %s", e)
        return 0.0

    async def profile(
        self,
        model: str,
        prompt: str = "Explain what machine learning is in 3 sentences.",
    ) -> dict[str, Any]:
        """Run the configured number of profiled runs and emit the unified
        JSON schema (fusion-bench.profiler/v1)."""
        cfg = self.config
        client = await self._get_client()
        samples: list[RunSample] = []
        for _ in range(max(cfg.runs, 1)):
            try:
                samples.append(await self._profile_run(client, model, prompt))
            except Exception as e:
                logger.error("Profile run failed for %s: %s", model, e)
        if not samples:
            raise RuntimeError(f"profile: all runs failed for {model}")

        peak_mb = await self._peak_memory_mb(client)
        ttfts = sorted(s.ttft_ms for s in samples if s.ttft_ms > 0)
        e2es = sorted(s.e2e_ms for s in samples)
        decode_tok_s = sorted(
            s.completion_tokens / max((s.e2e_ms - s.ttft_ms) / 1000.0, 0.001)
            for s in samples
            if s.e2e_ms > s.ttft_ms > 0
        )
        prefill_tok_s = sorted(s.prompt_tokens / max(s.ttft_ms / 1000.0, 0.001) for s in samples if s.ttft_ms > 0)

        mode = "full-trace" if cfg.full_profile else "lightweight"
        result: dict[str, Any] = {
            "schema": SCHEMA_VERSION,
            "model": model,
            "backend": self.BACKEND,
            "mode": mode,
            "runs": len(samples),
            "engine": {
                # Engine-side latency keys — never merged with agent_e2e_ms.
                "engine_ttft_ms": {
                    "p50": round(_percentile(ttfts, 50), 2),
                    "p99": round(_percentile(ttfts, 99), 2),
                },
                "prefill_tok_s": round(_percentile(prefill_tok_s, 50), 2),
                "decode_tok_s": round(_percentile(decode_tok_s, 50), 2),
                "engine_itl_p50_p99": None,
            },
            "agent": {
                "agent_e2e_ms": {
                    "p50": round(_percentile(e2es, 50), 2),
                    "p99": round(_percentile(e2es, 99), 2),
                },
            },
            "memory": {"peak_memory_mb": round(peak_mb, 1)},
        }
        if cfg.full_profile:
            intervals = sorted(i for s in samples for i in s.token_intervals_ms if i > 0)
            result["engine"]["engine_itl_p50_p99"] = {
                "p50": round(_percentile(intervals, 50), 2),
                "p99": round(_percentile(intervals, 99), 2),
                "tokens_sampled": len(intervals),
            }
        logger.info(
            "profile %s [%s/%s]: %d runs, ttft p50=%.1fms, decode=%.1f tok/s",
            model,
            self.BACKEND,
            mode,
            len(samples),
            result["engine"]["engine_ttft_ms"]["p50"],
            result["engine"]["decode_tok_s"],
        )
        return result
