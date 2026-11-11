"""SPS sweep executor (#43) — widths x batch sizes against fusion-mlx.

Scoring per candidate: median over warm repeats of
(total completion tokens / total wall time) for a concurrent batch of
requests — wall time includes prefill and request overhead, matching
the DSpine reference mechanic. Batch size is real client-side
concurrency (works today); draft width rides the request body
("speculative": {"draft_tokens": W}) and is applied once the engine
gains per-request spec support (upstream fusion-mlx#1528) — until then
the sweep degrades to the batch axis and says so in the profile.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from fusion_core.config import client_key

from .prefixes import SPrefix
from .profile import SpsProfile, current_hardware, file_digest

logger = logging.getLogger(__name__)


@dataclass
class SpsConfig:
    widths: list[int] = field(default_factory=lambda: [4, 8, 12, 16])
    batch_sizes: list[int] = field(default_factory=lambda: [1])
    repeats: int = 3
    max_tokens: int = 128
    timeout: float = 300.0


@dataclass
class SpsCandidateResult:
    width: int
    batch_size: int
    median_tok_s: float
    repeats_tok_s: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "batch_size": self.batch_size,
            "median_tok_s": round(self.median_tok_s, 2),
            "repeats_tok_s": [round(x, 2) for x in self.repeats_tok_s],
        }


class SpsTuner:
    BACKEND = "mlx"

    def __init__(
        self,
        mlx_base_url: str = "http://localhost:11432/v1",
        api_key: str = "",
        config: SpsConfig | None = None,
    ):
        if not api_key:
            api_key = client_key()
        self.mlx_base_url = mlx_base_url.rstrip("/")
        self.api_key = api_key
        self.config = config or SpsConfig()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            self._client = httpx.AsyncClient(base_url=self.mlx_base_url, timeout=self.config.timeout, headers=headers)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _payload(self, model: str, prefix: SPrefix, width: int) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prefix.prompt}],
            "max_tokens": self.config.max_tokens,
            # Width rides the body: forward-compatible with per-request
            # speculative support (upstream fusion-mlx#1528).
            "speculative": {"draft_tokens": width},
        }
        sp = prefix.sampling_params or {"temperature": 0.0}
        body.update({k: v for k, v in sp.items() if k in ("temperature", "top_p", "seed")})
        return body

    async def _one_request(self, client: httpx.AsyncClient, model: str, prefix: SPrefix, width: int) -> int:
        # Returns completion tokens for one request (0 on failure).
        try:
            resp = await client.post("/chat/completions", json=self._payload(model, prefix, width))
            resp.raise_for_status()
            usage = resp.json().get("usage") or {}
            return int(usage.get("completion_tokens", 0))
        except Exception as e:
            logger.warning("SPS request failed (width=%d): %s", width, e)
            return 0

    async def _timed_pass(
        self, client: httpx.AsyncClient, model: str, prefixes: list[SPrefix], width: int, batch: int
    ) -> float:
        # One concurrent batch; tok/s = total completion tokens / wall time.
        picked = [prefixes[i % len(prefixes)] for i in range(batch)]
        start = time.perf_counter()
        results = await asyncio.gather(*(self._one_request(client, model, p, width) for p in picked))
        wall = time.perf_counter() - start
        tokens = sum(results)
        if wall <= 0 or tokens == 0:
            return 0.0
        return tokens / wall

    async def _candidate(
        self,
        client: httpx.AsyncClient,
        model: str,
        prefixes: list[SPrefix],
        width: int,
        batch: int,
    ) -> SpsCandidateResult:
        # Warm pass (untimed) then repeats timed passes; median scored.
        await self._timed_pass(client, model, prefixes, width, batch)
        runs = [await self._timed_pass(client, model, prefixes, width, batch) for _ in range(self.config.repeats)]
        runs = [r for r in runs if r > 0]
        if not runs:
            logger.error("SPS candidate width=%d batch=%d produced no successful runs", width, batch)
            return SpsCandidateResult(width=width, batch_size=batch, median_tok_s=0.0)
        med = statistics.median(runs)
        logger.info("SPS width=%d batch=%d: median %.1f tok/s (%d repeats)", width, batch, med, len(runs))
        return SpsCandidateResult(width=width, batch_size=batch, median_tok_s=med, repeats_tok_s=runs)

    async def _acceptance_length(self, client: httpx.AsyncClient) -> float | None:
        # Engine exposes acceptance counters only internally today
        # (upstream fusion-mlx#1528); probe the likely endpoints, else None.
        root = self.mlx_base_url[: -len("/v1")] if self.mlx_base_url.endswith("/v1") else self.mlx_base_url
        for path in (f"{root}/v1/metrics", f"{root}/metrics"):
            try:
                resp = await client.get(path)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                for k, v in data.items():
                    if "acceptance" in k.lower() and isinstance(v, (int, float)):
                        return float(v)
            except Exception as e:
                logger.warning("Failed to read engine metrics %s: %s", path, e)
        logger.info("Acceptance counters not exposed by engine (upstream fusion-mlx#1528)")
        return None

    async def sweep(self, model: str, prefixes: list[SPrefix], prefix_path: str) -> SpsProfile:
        cfg = self.config
        client = await self._get_client()
        results: list[SpsCandidateResult] = []
        for batch in cfg.batch_sizes:
            for width in cfg.widths:
                results.append(await self._candidate(client, model, prefixes, width, batch))
        acceptance = await self._acceptance_length(client)

        best: dict[str, int] = {}
        for batch in cfg.batch_sizes:
            group = [r for r in results if r.batch_size == batch and r.median_tok_s > 0]
            if group:
                top = max(group, key=lambda r: r.median_tok_s)
                best[str(batch)] = top.width

        chip, ram_gb = current_hardware()
        engine_version = ""
        try:
            stats = await client.get("/models")
            if stats.status_code == 200:
                payload = stats.json()
                engine_version = str(payload.get("version") or "")
        except Exception as e:
            logger.warning("Failed to read engine version: %s", e)

        profile = SpsProfile(
            model=model,
            backend=self.BACKEND,
            chip=chip,
            ram_gb=ram_gb,
            engine_base_url=self.mlx_base_url,
            engine_version=engine_version,
            input_digest=file_digest(prefix_path),
            width_transport="request_body",
            engine_spec_support="unverified",
            max_tokens=cfg.max_tokens,
            repeats=cfg.repeats,
            best=best,
            table=[r.to_dict() for r in results],
            acceptance_length=acceptance,
            notes=(
                "Width axis transported in the request body; applied only when the "
                "engine accepts per-request speculative params (upstream fusion-mlx#1528). "
                "Retune when hardware, model or workload digest changes."
            ),
        )
        logger.info("SPS sweep done: %d candidates, best=%s", len(results), best)
        return profile


__all__ = ["SpsCandidateResult", "SpsConfig", "SpsTuner"]
