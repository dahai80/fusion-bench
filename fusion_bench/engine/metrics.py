"""Metrics collection — gathers performance metrics from fusion-mlx server stats."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class SystemMetrics:
    """System-level metrics from fusion-mlx server."""
    models_loaded: int = 0
    models_discovered: int = 0
    total_requests: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    model_memory_used: str = "0B"
    model_memory_max: str = "unlimited"
    uptime_seconds: int = 0
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "models_loaded": self.models_loaded,
            "models_discovered": self.models_discovered,
            "total_requests": self.total_requests,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "model_memory_used": self.model_memory_used,
            "model_memory_max": self.model_memory_max,
            "uptime_seconds": self.uptime_seconds,
            "timestamp": self.timestamp,
        }


class MetricsCollector:
    """Collects real-time metrics from fusion-mlx server via HTTP API."""

    def __init__(self, mlx_base_url: str = "http://localhost:11434/v1"):
        self.base_url = mlx_base_url.rstrip("/")

    async def collect(self) -> SystemMetrics:
        """Collect current system metrics from fusion-mlx."""
        metrics = SystemMetrics(timestamp=time.time())
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/stats")
                if resp.status_code == 200:
                    data = resp.json()
                    metrics.models_loaded = data.get("models_loaded", 0)
                    metrics.models_discovered = data.get("models_discovered", 0)
                    metrics.total_requests = data.get("total_requests", 0)
                    metrics.total_prompt_tokens = data.get("total_prompt_tokens", 0)
                    metrics.total_completion_tokens = data.get("total_tokens_generated", 0)
                    metrics.model_memory_used = data.get("model_memory_used_formatted", "0B")
                    metrics.model_memory_max = data.get("model_memory_max_formatted", "unlimited")
        except Exception:
            pass
        return metrics

    async def collect_series(self, duration: float = 10.0, interval: float = 1.0) -> list[SystemMetrics]:
        """Collect a time series of metrics."""
        series = []
        start = time.time()
        while time.time() - start < duration:
            metrics = await self.collect()
            series.append(metrics)
            await asyncio.sleep(interval)
        return series


import asyncio