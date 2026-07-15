"""Benchmark engine — runs MLX model performance benchmarks via fusion-mlx HTTP API.

All model inference goes through fusion-mlx's /v1/chat/completions.
Never imports MLX, mlx-lm, or any engine code directly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SpeedMetrics:
    """Speed metrics for a single benchmark run."""
    prefill_tokens: int = 0
    decode_tokens: int = 0
    prefill_time: float = 0.0
    decode_time: float = 0.0
    prefill_speed: float = 0.0  # tok/s
    decode_speed: float = 0.0  # tok/s
    total_time: float = 0.0
    peak_memory_mb: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "prefill_tokens": self.prefill_tokens,
            "decode_tokens": self.decode_tokens,
            "prefill_time_ms": round(self.prefill_time * 1000, 2),
            "decode_time_ms": round(self.decode_time * 1000, 2),
            "prefill_speed": round(self.prefill_speed, 2),
            "decode_speed": round(self.decode_speed, 2),
            "total_time_s": round(self.total_time, 3),
            "peak_memory_mb": round(self.peak_memory_mb, 1),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }


@dataclass
class BenchmarkResult:
    """Complete benchmark result for a single model/config."""
    model: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    metrics: SpeedMetrics = field(default_factory=SpeedMetrics)
    errors: list[str] = field(default_factory=list)
    stable: bool = True
    max_stable_context: int = 0


class BenchmarkRunner:
    """Runs MLX model benchmarks via fusion-mlx HTTP API.

    Measures prefill/decode speed, memory usage, and stability.
    """

    def __init__(
        self,
        mlx_base_url: str = "http://localhost:11434/v1",
        api_key: str = "local",
        timeout: float = 300.0,
    ):
        self.mlx_base_url = mlx_base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.mlx_base_url,
                timeout=self.timeout,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def list_models(self) -> list[dict[str, Any]]:
        """List available models from fusion-mlx."""
        try:
            resp = await self.client.get("/models")
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
        except Exception as e:
            logger.error("Failed to list models: %s", e)
            return []

    async def run_single(
        self,
        model: str,
        prompt: str = "Hello, please explain what is machine learning in 3 sentences.",
        max_tokens: int = 256,
        temperature: float = 0.7,
        config: dict[str, Any] | None = None,
    ) -> SpeedMetrics:
        """Run a single benchmark for a model with given config."""
        config = config or {}
        metrics = SpeedMetrics()
        prompt_tokens = len(prompt) // 4  # rough estimate

        try:
            start = time.time()
            resp = await self.client.post("/chat/completions", json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False,
                **config,
            })
            elapsed = time.time() - start
            resp.raise_for_status()
            data = resp.json()

            usage = data.get("usage", {})
            metrics.prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
            metrics.completion_tokens = usage.get("completion_tokens", max_tokens)
            metrics.total_time = elapsed
            metrics.decode_speed = metrics.completion_tokens / max(elapsed, 0.001)
            metrics.prefill_speed = metrics.prompt_tokens / max(elapsed * 0.3, 0.001)
            metrics.prefill_tokens = metrics.prompt_tokens
            metrics.decode_tokens = metrics.completion_tokens

            # Get server stats for memory
            try:
                stats_resp = await self.client.get("/stats")
                if stats_resp.status_code == 200:
                    stats = stats_resp.json()
                    mem_str = stats.get("model_memory_used_formatted", "0B")
                    metrics.peak_memory_mb = self._parse_memory(mem_str)
            except Exception:
                pass

        except httpx.TimeoutException:
            logger.warning("Benchmark timed out for %s", model)
            metrics.total_time = self.timeout
        except Exception as e:
            logger.error("Benchmark failed for %s: %s", model, e)

        return metrics

    async def run_stability(
        self,
        model: str,
        rounds: int = 30,
        prompt: str = "Hello, what is 2+2?",
        max_tokens: int = 64,
    ) -> BenchmarkResult:
        """Run stability test — N consecutive rounds, check for crashes."""
        result = BenchmarkResult(model=model, config={"rounds": rounds})
        success = 0
        errors = []

        for i in range(rounds):
            try:
                metrics = await self.run_single(
                    model=model, prompt=prompt,
                    max_tokens=max_tokens, temperature=0.0,
                )
                if metrics.total_time > 0:
                    success += 1
                await asyncio.sleep(0.1)
            except Exception as e:
                errors.append(f"Round {i+1}: {e}")

        result.stable = success >= rounds * 0.9
        result.errors = errors
        return result

    async def probe_max_context(
        self,
        model: str,
        max_context: int = 131072,
        step: int = 4096,
    ) -> int:
        """Probe the maximum stable context length for a model."""
        last_valid = 4096
        for ctx in range(step, max_context + step, step):
            prompt = "Hello " * (ctx // 10)
            try:
                metrics = await self.run_single(
                    model=model, prompt=prompt,
                    max_tokens=16, temperature=0.0,
                    config={"max_tokens": 16},
                )
                if metrics.total_time > 0:
                    last_valid = ctx
            except Exception:
                break
            await asyncio.sleep(0.1)
        return last_valid

    async def benchmark(
        self,
        model: str,
        configs: list[dict[str, Any]] | None = None,
        prompt: str = "",
        max_tokens: int = 256,
        runs: int = 3,
    ) -> list[BenchmarkResult]:
        """Run full benchmark for a model across multiple configs."""
        if not prompt:
            prompt = "Explain the concept of neural networks in detail. Include examples of forward propagation and backpropagation."

        if not configs:
            configs = [{}]

        results = []
        for cfg in configs:
            result = BenchmarkResult(model=model, config=cfg)
            run_metrics = []

            for i in range(runs):
                metrics = await self.run_single(
                    model=model, prompt=prompt,
                    max_tokens=max_tokens, config=cfg,
                )
                if metrics.total_time > 0:
                    run_metrics.append(metrics)

            if run_metrics:
                # Average the metrics
                avg = SpeedMetrics()
                for m in run_metrics:
                    avg.decode_speed += m.decode_speed
                    avg.prefill_speed += m.prefill_speed
                    avg.total_time += m.total_time
                    avg.peak_memory_mb += m.peak_memory_mb
                    avg.prompt_tokens = m.prompt_tokens
                    avg.completion_tokens = m.completion_tokens
                n = len(run_metrics)
                avg.decode_speed /= n
                avg.prefill_speed /= n
                avg.total_time /= n
                avg.peak_memory_mb /= n
                result.metrics = avg

            results.append(result)

        return results

    @staticmethod
    def _parse_memory(mem_str: str) -> float:
        """Parse memory string like '12.5 GB' to MB."""
        try:
            parts = mem_str.split()
            value = float(parts[0])
            unit = parts[1].upper() if len(parts) > 1 else "GB"
            if "KB" in unit:
                return value / 1024
            elif "MB" in unit:
                return value
            elif "GB" in unit:
                return value * 1024
            elif "TB" in unit:
                return value * 1024 * 1024
            return value
        except (ValueError, IndexError):
            return 0.0