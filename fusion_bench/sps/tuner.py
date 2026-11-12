"""SPS sweep executor (#43) — widths x batch sizes against fusion-mlx.

Scoring per candidate: median over warm repeats of
(total completion tokens / total wall time) for a concurrent batch of
requests — wall time includes prefill and request overhead, matching
the DSpine reference mechanic. Draft width rides the request body
("speculative": {"draft_tokens": W}).

Width application is verified through the engine's response echo
(fusion-mlx >= 0.10.59, upstream #1528): the engine honors per-request
widths on the single-request pure-decode path only — batched traffic
falls back to the server default and reports it in the echo. Per
candidate we record the share of requests whose width was applied;
the profile flips engine_spec_support to "verified" once any echo
confirms application. Acceptance length comes from /stats
`spec_decode.<strategy>.acceptance_length` (counters active only when
the engine runs with native MTP enabled).
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
    # Widths 1-4: fusion-mlx >= 0.10.59 accepts per-request draft_tokens
    # in [1, 4] (pydantic rejects out-of-range at parse time, #1528).
    widths: list[int] = field(default_factory=lambda: [1, 2, 4])
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
    # Share of successful responses whose speculative echo matches the
    # requested width (1.0 = applied, 0.0 = engine fell back).
    width_applied_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "batch_size": self.batch_size,
            "median_tok_s": round(self.median_tok_s, 2),
            "repeats_tok_s": [round(x, 2) for x in self.repeats_tok_s],
            "width_applied_rate": round(self.width_applied_rate, 2),
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

    async def _one_request(
        self, client: httpx.AsyncClient, model: str, prefix: SPrefix, width: int
    ) -> tuple[int, bool]:
        # Returns (completion tokens, width_applied) for one request;
        # (0, False) on failure. width_applied = speculative echo match
        # (fusion-mlx >= 0.10.59 echoes the applied spec config).
        try:
            resp = await client.post("/chat/completions", json=self._payload(model, prefix, width))
            resp.raise_for_status()
            body = resp.json()
            usage = body.get("usage") or {}
            echo = body.get("speculative")
            applied = echo == {"draft_tokens": width}
            return int(usage.get("completion_tokens", 0)), applied
        except Exception as e:
            logger.warning("SPS request failed (width=%d): %s", width, e)
            return 0, False

    async def _timed_pass(
        self, client: httpx.AsyncClient, model: str, prefixes: list[SPrefix], width: int, batch: int
    ) -> tuple[float, int, int]:
        # One concurrent batch; tok/s = total completion tokens / wall
        # time. Also reports (successful, applied) request counts for
        # width-verification.
        picked = [prefixes[i % len(prefixes)] for i in range(batch)]
        start = time.perf_counter()
        results = await asyncio.gather(*(self._one_request(client, model, p, width) for p in picked))
        wall = time.perf_counter() - start
        tokens = sum(t for t, _ in results)
        ok = sum(1 for t, _ in results if t > 0)
        applied = sum(1 for _, a in results if a)
        if wall <= 0 or tokens == 0:
            return 0.0, ok, applied
        return tokens / wall, ok, applied

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
        runs = []
        ok_total = 0
        applied_total = 0
        for _ in range(self.config.repeats):
            rate, ok, applied = await self._timed_pass(client, model, prefixes, width, batch)
            runs.append(rate)
            ok_total += ok
            applied_total += applied
        runs = [r for r in runs if r > 0]
        applied_rate = applied_total / ok_total if ok_total else 0.0
        if not runs:
            logger.error("SPS candidate width=%d batch=%d produced no successful runs", width, batch)
            return SpsCandidateResult(width=width, batch_size=batch, median_tok_s=0.0)
        med = statistics.median(runs)
        logger.info(
            "SPS width=%d batch=%d: median %.1f tok/s (%d repeats, width applied %d/%d)",
            width,
            batch,
            med,
            len(runs),
            applied_total,
            ok_total,
        )
        return SpsCandidateResult(
            width=width,
            batch_size=batch,
            median_tok_s=med,
            repeats_tok_s=runs,
            width_applied_rate=applied_rate,
        )

    async def _acceptance_length(self, client: httpx.AsyncClient) -> float | None:
        # fusion-mlx >= 0.10.59: /stats carries spec_decode.<strategy>
        # snapshots; counters are meaningful only when the strategy is
        # active (verifies > 0). /v1/metrics Prometheus lines are the
        # secondary source.
        root = self.mlx_base_url[: -len("/v1")] if self.mlx_base_url.endswith("/v1") else self.mlx_base_url
        try:
            resp = await client.get(f"{root}/stats")
            if resp.status_code == 200:
                spec = resp.json().get("spec_decode") or {}
                for strategy, snap in spec.items():
                    if not isinstance(snap, dict):
                        continue
                    if snap.get("verifies", 0) > 0 and snap.get("acceptance_length"):
                        val = float(snap["acceptance_length"])
                        logger.info("Acceptance length from /stats[%s]: %.2f", strategy, val)
                        return val
        except Exception as e:
            logger.warning("Failed to read /stats spec_decode: %s", e)
        try:
            resp = await client.get(f"{root}/v1/metrics")
            if resp.status_code == 200:
                for line in resp.text.splitlines():
                    if line.startswith("fusion_mlx_spec_decode_acceptance_length") and "{" not in line.split(" ")[0]:
                        continue
                    if "fusion_mlx_spec_decode_acceptance_length" in line and not line.startswith("#"):
                        tail = line.rsplit(" ", 1)[-1]
                        val = float(tail)
                        if val > 0:
                            logger.info("Acceptance length from /v1/metrics: %.2f", val)
                            return val
        except Exception as e:
            logger.warning("Failed to read /v1/metrics: %s", e)
        logger.info("No active spec-decode counters (engine may run without native MTP)")
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

        verified = any(r.width_applied_rate > 0 for r in results)
        profile = SpsProfile(
            model=model,
            backend=self.BACKEND,
            chip=chip,
            ram_gb=ram_gb,
            engine_base_url=self.mlx_base_url,
            engine_version=engine_version,
            input_digest=file_digest(prefix_path),
            width_transport="request_body",
            engine_spec_support="verified" if verified else "unverified",
            max_tokens=cfg.max_tokens,
            repeats=cfg.repeats,
            best=best,
            table=[r.to_dict() for r in results],
            acceptance_length=acceptance,
            notes=(
                "Width axis transported in the request body; honored by fusion-mlx "
                ">= 0.10.59 on the single-request pure-decode path only (upstream "
                "fusion-mlx#1528) — batched traffic falls back to the server default "
                "and the echo reports it (width_applied_rate). "
                "Retune when hardware, model or workload digest changes."
            ),
        )
        logger.info("SPS sweep done: %d candidates, best=%s", len(results), best)
        return profile


__all__ = ["SpsCandidateResult", "SpsConfig", "SpsTuner"]
