"""fusion-mlx chat client for harness comparison runs.

Request hygiene inherited from #47: every call goes through
engine.bench_http.bench_client so the fusion-mlx response cache can never
serve a repeat. Sampling is deterministic (temperature 0 + fixed seed).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from fusion_core.config import client_key

from ..engine.bench_http import bench_client, cache_status

logger = logging.getLogger(__name__)


@dataclass
class ChatTurn:
    text: str
    prompt_tokens: int
    completion_tokens: int
    cached: bool
    latency_s: float
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.error == ""


class ModelClient:
    """Thin async chat-completions client; one call = one ChatTurn."""

    def __init__(self, base_url: str, model: str, seed: int = 42, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.seed = seed
        self.timeout = timeout

    async def chat(self, messages: list[dict], max_tokens: int = 512) -> ChatTurn:
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "seed": self.seed,
            "stream": False,
        }
        start = time.monotonic()
        try:
            async with bench_client(base_url=self.base_url, timeout=self.timeout) as client:
                resp = await client.post(
                    "/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {client_key()}"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("chat call failed model=%s err=%s", self.model, e)
            return ChatTurn(
                text="",
                prompt_tokens=0,
                completion_tokens=0,
                cached=False,
                latency_s=time.monotonic() - start,
                error=str(e),
            )
        latency = time.monotonic() - start
        choice = (data.get("choices") or [{}])[0]
        usage = data.get("usage") or {}
        cached = cache_status(resp).lower() == "hit"
        if cached:
            # #47 hygiene: a cache hit inside a bench run is a defect; surface it.
            logger.warning("cache hit on bench request model=%s — bypass header ignored?", self.model)
        return ChatTurn(
            text=str(choice.get("message", {}).get("content") or ""),
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            cached=cached,
            latency_s=latency,
        )
