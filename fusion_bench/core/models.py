"""Unified data models for the four-level evaluation system.

L1 Model baseline, L2 Agent capability, L3 Application scenario,
L4 Artifact quality — all share these core data structures.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class EvalLevel(StrEnum):
    L1_MODEL = "L1"
    L2_AGENT = "L2"
    L3_APP = "L3"
    L4_ARTIFACT = "L4"


class GateTier(StrEnum):
    EXPERIMENTAL = "experimental"
    BUSINESS = "business"
    PRODUCTION = "production"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class BenchmarkTask:
    """A single benchmark task definition."""

    task_id: str
    name: str
    level: EvalLevel
    executor_key: str
    dataset: str | None = None
    max_samples: int | None = None
    params: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    timeout_seconds: int = 600

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "level": self.level.value,
            "executor_key": self.executor_key,
            "dataset": self.dataset,
            "max_samples": self.max_samples,
            "params": self.params,
            "tags": self.tags,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class QualityGate:
    """Quality gate rule with automatic pass/fail threshold."""

    gate_id: str
    name: str
    tier: GateTier
    metric_name: str
    operator: str = ">="
    threshold: float = 0.0
    executor_key: str | None = None
    level: EvalLevel | None = None
    action: str = "warn"
    on_fail_callback: str | None = None

    def evaluate(self, metric_value: float) -> bool:
        ops = {
            ">=": lambda a, b: a >= b,
            ">": lambda a, b: a > b,
            "<=": lambda a, b: a <= b,
            "<": lambda a, b: a < b,
            "==": lambda a, b: abs(a - b) < 1e-9,
        }
        op_fn = ops.get(self.operator)
        if op_fn is None:
            logger.error("QualityGate[%s]: unknown operator '%s'", self.gate_id, self.operator)
            return False
        return op_fn(metric_value, self.threshold)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "name": self.name,
            "tier": self.tier.value,
            "metric_name": self.metric_name,
            "operator": self.operator,
            "threshold": self.threshold,
            "executor_key": self.executor_key,
            "level": self.level.value if self.level else None,
            "action": self.action,
            "on_fail_callback": self.on_fail_callback,
        }


@dataclass
class GateResult:
    """Result of evaluating a quality gate against a metric."""

    gate_id: str
    gate_name: str
    tier: GateTier
    metric_name: str
    metric_value: float
    threshold: float
    passed: bool
    action: str = "warn"
    approved_by: str = ""
    approved_at: str = ""

    @property
    def is_blocking(self) -> bool:
        return self.action == "block" and not self.passed and not self.approved_by

    @property
    def is_approved(self) -> bool:
        return bool(self.approved_by)

    def approve(self, approver: str) -> None:
        self.approved_by = approver
        from datetime import datetime

        self.approved_at = datetime.now().isoformat()
        logger.info("Gate %s approved by %s at %s", self.gate_id, approver, self.approved_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "gate_name": self.gate_name,
            "tier": self.tier.value,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "passed": self.passed,
            "action": self.action,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "is_blocking": self.is_blocking,
        }


@dataclass
class SuiteResult:
    """Result of running an entire benchmark suite."""

    suite_id: str
    model: str
    level: EvalLevel
    results: list[dict[str, Any]] = field(default_factory=list)
    gate_results: list[GateResult] = field(default_factory=list)
    overall_passed: bool = False
    duration_seconds: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "model": self.model,
            "level": self.level.value,
            "results": self.results,
            "gate_results": [g.to_dict() for g in self.gate_results],
            "overall_passed": self.overall_passed,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp,
            "meta": self.meta,
        }


@dataclass
class TraceRecord:
    """Full trace record for a benchmark run — stored and queryable."""

    trace_id: str
    model: str
    level: EvalLevel
    executor_key: str
    task_id: str
    status: TaskStatus
    eval_result: dict[str, Any] | None = None
    gate_results: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None
    duration_seconds: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    host_info: dict[str, Any] = field(default_factory=dict)
    agent_version: str = ""
    app_version: str = ""
    tenant_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "model": self.model,
            "level": self.level.value,
            "executor_key": self.executor_key,
            "task_id": self.task_id,
            "status": self.status.value,
            "eval_result": self.eval_result,
            "gate_results": self.gate_results,
            "error_message": self.error_message,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp,
            "host_info": self.host_info,
            "agent_version": self.agent_version,
            "app_version": self.app_version,
            "tenant_id": self.tenant_id,
        }
