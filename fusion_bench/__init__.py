"""Fusion-Bench — MLX model performance benchmarking and auto-tuning workbench.

All model inference goes through fusion-mlx HTTP API (/v1/chat/completions).
Never imports MLX, mlx-lm, or any engine code directly.

Architecture:
    core/        — Registry, PluginBase, DataModels
    executors/   — ExecutorPlugins (speed, lm_harness, tune, quant, security)
    orchestrator/— Pipeline, GateEngine, Scheduler
    storage/     — TraceStore (SQLite)
    engine/      — Legacy engines (BenchmarkRunner, TaskRunner, etc.)
    adapters/    — MLXModel adapter
    optimizer/   — Tuner, QuantBench
    reporter/    — ReportGenerator, BenchSite
"""

# Legacy exports (backward compatible)
from .adapters.mlx_model import MLXModel
from .core.models import (
    BenchmarkTask,
    EvalLevel,
    GateResult,
    GateTier,
    QualityGate,
    SuiteResult,
    TaskStatus,
    TraceRecord,
)
from .core.plugin_base import (
    CaseResult,
    EvalResult,
    ExecutorPlugin,
    ExecutorType,
    TaskConfig,
)

# New architecture exports
from .core.registry import Registry, executor_registry, gate_registry, suite_registry
from .engine.benchmark import BenchmarkResult, BenchmarkRunner, SpeedMetrics
from .engine.metrics import MetricsCollector
from .engine.task_runner import LMEvalTaskRunner
from .optimizer.tuner import ParameterTuner, TuneResult
from .orchestrator.gate_engine import GateEngine
from .orchestrator.pipeline import Pipeline
from .orchestrator.scheduler import Scheduler
from .reporter.report import ReportGenerator
from .storage.trace_store import TraceStore

__all__ = [
    # Legacy
    "BenchmarkRunner",
    "BenchmarkResult",
    "SpeedMetrics",
    "MetricsCollector",
    "LMEvalTaskRunner",
    "MLXModel",
    "ParameterTuner",
    "TuneResult",
    "ReportGenerator",
    # Core
    "Registry",
    "executor_registry",
    "suite_registry",
    "gate_registry",
    "ExecutorPlugin",
    "ExecutorType",
    "TaskConfig",
    "EvalResult",
    "CaseResult",
    "EvalLevel",
    "GateTier",
    "TaskStatus",
    "BenchmarkTask",
    "QualityGate",
    "GateResult",
    "SuiteResult",
    "TraceRecord",
    # Orchestrator
    "Pipeline",
    "GateEngine",
    "Scheduler",
    # Storage
    "TraceStore",
]
