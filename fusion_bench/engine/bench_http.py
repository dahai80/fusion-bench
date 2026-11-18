"""Bench request hygiene (#47): fusion-mlx response-cache bypass.

fusion-mlx force-caches non-streaming T=0 chat completions keyed on the
full request fingerprint — a repeated-prompt bench measures the cache,
not the model. Every bench request therefore carries `X-Cache: bypass`
(first-class per fusion-mlx api-reference): never read, never store.
Streaming requests never touch the cache and need no header, but sending
it is harmless.

Also provides `cache_status(resp)` to read the `X-Cache` response header
for provenance.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

CACHE_BYPASS_HEADERS = {"X-Cache": "bypass"}


def bench_client(
    base_url: str = "",
    timeout: float = 120.0,
    headers: dict[str, str] | None = None,
    **kwargs,
) -> httpx.AsyncClient:
    merged = dict(CACHE_BYPASS_HEADERS)
    if headers:
        merged.update(headers)
    return httpx.AsyncClient(base_url=base_url, timeout=timeout, headers=merged, **kwargs)


def cache_status(resp: httpx.Response) -> str:
    return str(resp.headers.get("X-Cache", ""))


__all__ = ["CACHE_BYPASS_HEADERS", "bench_client", "cache_status"]
