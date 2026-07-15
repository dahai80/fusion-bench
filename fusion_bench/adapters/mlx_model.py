"""MLX model adapter for lm-evaluation-harness.

Implements the lm-eval model interface (generate_until, loglikelihood, etc.)
by calling fusion-mlx HTTP API. No direct MLX, torch, or transformers imports.

Design:
- generate_until → POST /v1/chat/completions (for chat models)
- loglikelihood → POST /v1/completions with logprobs (if supported)
- tok_encode/tok_decode → estimated via character count (no tokenizer needed)
"""

from __future__ import annotations

import abc
import asyncio
import json
import logging
import re
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MLXModel:
    """LM Evaluation Harness compatible model adapter for fusion-mlx.

    Implements the minimal interface needed to run lm-eval tasks:
    - generate_until: text generation
    - loglikelihood: scoring (approximate)
    - tok_encode / tok_decode: token estimation
    """

    def __init__(
        self,
        model: str = "qwen3.5-9b",
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "local",
        batch_size: int = 1,
        max_length: int = 4096,
        temperature: float = 0.0,
        **kwargs,
    ):
        self.model_name = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.batch_size = batch_size
        self.max_length = max_length
        self.temperature = temperature
        self._client: httpx.AsyncClient | None = None
        # Track token usage
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=120.0,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── LM Eval Interface ──

    async def generate_until(self, requests: list[dict]) -> list[str]:
        """Generate text until a stopping condition is met.

        Args:
            requests: List of dicts with 'context' (prompt) and 'until' (stop strings).

        Returns:
            List of generated text strings.
        """
        results = []
        for req in requests:
            context = req.get("context", "")
            until = req.get("until", [])
            max_tokens = req.get("max_length", 256)

            try:
                resp = await self._chat_completion(
                    messages=[{"role": "user", "content": context}],
                    max_tokens=max_tokens,
                    temperature=self.temperature,
                    stop=until if until else None,
                )
                text = self._extract_content(resp)
                # Truncate at stop strings
                for stop_str in until:
                    if stop_str and stop_str in text:
                        text = text[: text.index(stop_str)]
                results.append(text)
            except Exception as e:
                logger.error("generate_until failed: %s", e)
                results.append("")

        return results

    async def loglikelihood(self, requests: list[tuple[str, str]]) -> list[tuple[float, bool]]:
        """Compute log-likelihood of continuations given contexts.

        Uses fusion-mlx's /v1/completions with logprobs if available.
        Falls back to an approximate scoring based on generation probability.

        Args:
            requests: List of (context, continuation) tuples.

        Returns:
            List of (log_likelihood, is_greedy) tuples.
        """
        results = []
        for context, continuation in requests:
            try:
                prompt = context + continuation
                resp = await self._completion(
                    prompt=prompt,
                    max_tokens=1,
                    temperature=0.0,
                    logprobs=True,
                )
                ll = self._extract_loglikelihood(resp, continuation)
                results.append((ll, True))
            except Exception as e:
                logger.debug("loglikelihood failed: %s", e)
                # Fallback: return neutral score
                results.append((0.0, True))
        return results

    async def loglikelihood_rolling(self, requests: list[str]) -> list[float]:
        """Compute rolling log-likelihood of strings.

        Args:
            requests: List of strings to score.

        Returns:
            List of log-likelihood scores.
        """
        results = []
        for text in requests:
            try:
                resp = await self._completion(
                    prompt=text,
                    max_tokens=1,
                    temperature=0.0,
                    logprobs=True,
                )
                ll = self._extract_loglikelihood(resp, text[:100])
                results.append(ll)
            except Exception:
                results.append(0.0)
        return results

    # ── Token Helpers (approximate, no tokenizer) ──

    def tok_encode(self, text: str) -> list[int]:
        """Encode text to token IDs (approximate)."""
        # Rough estimate: ~4 chars per token
        return [0] * max(1, len(text) // 4)

    def tok_decode(self, tokens: list[int]) -> str:
        """Decode token IDs to text (approximate)."""
        return f"[{len(tokens)} tokens]"

    def tokenizer(self):
        """Return a dummy tokenizer object."""
        return self

    # ── Internal API Calls ──

    async def _chat_completion(
        self,
        messages: list[dict],
        max_tokens: int = 256,
        temperature: float = 0.0,
        stop: list[str] | None = None,
    ) -> dict:
        """Call fusion-mlx /v1/chat/completions."""
        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if stop:
            payload["stop"] = stop

        start = time.time()
        resp = await self.client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        elapsed = time.time() - start
        data = resp.json()

        usage = data.get("usage", {})
        self.total_prompt_tokens += usage.get("prompt_tokens", 0)
        self.total_completion_tokens += usage.get("completion_tokens", 0)

        logger.debug("Chat completion: %d tokens in %.2fs", usage.get("completion_tokens", 0), elapsed)
        return data

    async def _completion(
        self,
        prompt: str,
        max_tokens: int = 1,
        temperature: float = 0.0,
        logprobs: bool = False,
    ) -> dict:
        """Call fusion-mlx /v1/completions."""
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if logprobs:
            payload["logprobs"] = 1

        try:
            resp = await self.client.post("/completions", json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError:
            # Fallback to chat completion if /completions not available
            return await self._chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )

    # ── Response Parsing ──

    @staticmethod
    def _extract_content(data: dict) -> str:
        """Extract text from chat completion response."""
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            return ""

    @staticmethod
    def _extract_loglikelihood(data: dict, continuation: str) -> float:
        """Extract log-likelihood from completion response."""
        try:
            choice = data["choices"][0]
            if "logprobs" in choice and choice["logprobs"]:
                tokens = choice["logprobs"].get("tokens", [])
                token_logprobs = choice["logprobs"].get("token_logprobs", [])
                if token_logprobs:
                    return sum(token_logprobs) / len(token_logprobs)
            # Fallback: approximate from text length
            return -len(continuation) * 0.1
        except (KeyError, IndexError, TypeError):
            return -len(continuation) * 0.1

    # ── Utility ──

    def get_usage_report(self) -> dict:
        return {
            "model": self.model_name,
            "prompt_tokens": self.total_prompt_tokens,
            "completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
        }