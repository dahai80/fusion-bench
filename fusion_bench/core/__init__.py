"""Core framework: registry, plugin base, and data models."""

from .models import (
    BenchmarkTask,
    EvalLevel,
    GateResult,
    GateTier,
    QualityGate,
    SuiteResult,
    TaskStatus,
    TraceRecord,
)
from .plugin_base import (
    CaseResult,
    EvalResult,
    ExecutorPlugin,
    ExecutorType,
    TaskConfig,
)
from .registry import (
    Registry,
    executor_registry,
    gate_registry,
    suite_registry,
)

__all__ = [
    # Registry
    "Registry",
    "executor_registry",
    "suite_registry",
    "gate_registry",
    # Plugin base
    "ExecutorPlugin",
    "ExecutorType",
    "TaskConfig",
    "EvalResult",
    "CaseResult",
    # Models
    "EvalLevel",
    "GateTier",
    "TaskStatus",
    "BenchmarkTask",
    "QualityGate",
    "GateResult",
    "SuiteResult",
    "TraceRecord",
]
