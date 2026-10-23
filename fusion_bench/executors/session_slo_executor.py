"""Session SLO executor — pulls agent-studio long-session SLO baselines.

Issue #24 (sync of fusion-agent-studio#350, PRD opti-1016 §6.3 N11):
POST /v1/rpc {"method": "telemetry.session_slo"} returns sessions_completed,
compactions_total, approvals_total, avg/p99 approval latency, avg/p99
session duration. Each metric lands as a baseline CaseResult so the
long-session suite records duration / compaction frequency / approval
latency percentiles into the trace store.
"""

from __future__ import annotations

import logging
import os
import time

import httpx

from ..core.plugin_base import (
    CaseResult,
    EvalResult,
    ExecutorPlugin,
    ExecutorType,
    TaskConfig,
)

logger = logging.getLogger(__name__)

# Baseline metrics pulled from telemetry.session_slo, in report order.
_SLO_METRICS = (
    "sessions_completed",
    "compactions_total",
    "approvals_total",
    "avg_approval_latency_ms",
    "p99_approval_latency_ms",
    "avg_session_duration_ms",
    "p99_session_duration_ms",
)


class SessionSloExecutor(ExecutorPlugin):
    """L3 App executor — records agent-studio long-session SLO baselines."""

    name = "session_slo"
    executor_type = ExecutorType.SESSION_SLO

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or os.environ.get("FUSION_AGENT_STUDIO_URL", "http://127.0.0.1:11442")).rstrip("/")
        self.api_key = os.environ.get("FUSION_AGENT_STUDIO_API_KEY", "")

    def is_available(self) -> bool:
        return True

    async def run(self, task_config: TaskConfig) -> EvalResult:
        start = time.time()
        base_url = task_config.get("agent_studio_url", self.base_url).rstrip("/")
        api_key = task_config.get("agent_studio_api_key", self.api_key)
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        logger.info(
            "SessionSloExecutor: pulling telemetry.session_slo from %s (task=%s)",
            base_url,
            task_config.task_id,
        )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{base_url}/v1/rpc",
                    json={"method": "telemetry.session_slo", "params": {}},
                    headers=headers,
                )
                resp.raise_for_status()
                summary = resp.json()
        except Exception as e:
            logger.error("SessionSloExecutor: session_slo RPC failed: %s", e)
            return EvalResult(
                task_id=task_config.task_id,
                executor_key=self.name,
                model=task_config.model,
                level="L3",
                metric_name="p99_approval_latency_ms",
                metric_value=0.0,
                duration_seconds=time.time() - start,
                errors=[f"telemetry.session_slo RPC failed: {e}"],
            )

        rpc_latency_ms = (time.time() - start) * 1000
        missing = [m for m in _SLO_METRICS if m not in summary]
        if missing:
            logger.warning("SessionSloExecutor: missing SLO keys %s", missing)

        cases: list[CaseResult] = []
        for metric in _SLO_METRICS:
            raw = summary.get(metric, 0)
            try:
                value = float(raw)
            except (TypeError, ValueError):
                value = 0.0
            cases.append(
                CaseResult(
                    input_text=f"baseline:{metric}",
                    expected="recorded",
                    actual=str(raw),
                    score=value,
                    passed=True,
                    latency_ms=rpc_latency_ms,
                    meta={"metric": metric},
                )
            )
            logger.info("SessionSloExecutor baseline %s=%s", metric, raw)

        # Headline SLO: p99 approval latency — the latency percentile the
        # long-session baselines trend on. Full summary in meta.
        p99_approval = summary.get("p99_approval_latency_ms", 0.0)
        try:
            headline = round(float(p99_approval), 2)
        except (TypeError, ValueError):
            headline = 0.0

        return EvalResult(
            task_id=task_config.task_id,
            executor_key=self.name,
            model=task_config.model,
            level="L3",
            metric_name="p99_approval_latency_ms",
            metric_value=headline,
            cases=cases,
            duration_seconds=time.time() - start,
            meta={
                "slo_summary": {m: summary.get(m, 0) for m in _SLO_METRICS},
                "agent_studio_url": base_url,
            },
        )
