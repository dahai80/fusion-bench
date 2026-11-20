"""Ours arm for metrics 1-2 (issue #53): fusion-harness loop on the shared tasks.

Thin adapter over harness_bench.FusionHarnessRunner — the kernel-routed loop
from issue #48 — with SuiteTask converted to the HarnessTask shape.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from ..harness_bench.model_client import ChatTurn, ModelClient
from ..harness_bench.runners import FusionHarnessRunner
from ..harness_bench.tasks import HarnessTask
from .tasks import SYSTEM_PROMPT, SuiteTask

logger = logging.getLogger(__name__)


class RetryingClient:
    """ModelClient wrapper: retries failed/empty turns (upstream fusion-mlx#1665
    prompt-dependent 500s can wedge the engine until it recovers)."""

    def __init__(self, inner: ModelClient, attempts: int = 5, backoff_s: float = 3.0):
        self.inner = inner
        self.attempts = attempts
        self.backoff_s = backoff_s
        self.model = inner.model

    async def chat(self, messages: list[dict], max_tokens: int = 512) -> ChatTurn:
        turn = ChatTurn(text="", prompt_tokens=0, completion_tokens=0, cached=False, latency_s=0.0, error="unset")
        for attempt in range(1, self.attempts + 1):
            turn = await self.inner.chat(messages, max_tokens=max_tokens)
            if turn.text or not turn.error:
                return turn
            logger.warning("own arm chat attempt %d failed: %s", attempt, turn.error)
            if attempt < self.attempts:
                await asyncio.sleep(self.backoff_s * attempt)
        return turn


def to_harness_task(task: SuiteTask) -> HarnessTask:
    return HarnessTask(
        task_id=task.task_id,
        instruction=task.instruction,
        setup_files=dict(task.setup_files),
        reference_actions=[],
        verifier=task.verifier,
    )


async def run_own_task(client: ModelClient, task: SuiteTask, workspace: Path, max_steps: int = 8) -> dict:
    runner = FusionHarnessRunner(RetryingClient(client), max_steps=max_steps, system_prompt=SYSTEM_PROMPT)
    result = await runner.run(to_harness_task(task), workspace)
    data = result.to_dict()
    data["side"] = "fusion-harness"
    logger.info(
        "own arm task=%s passed=%s tokens=%d/%d wall=%.2fs",
        task.task_id,
        result.passed,
        result.tokens_in,
        result.tokens_out,
        result.wall_s,
    )
    return data
