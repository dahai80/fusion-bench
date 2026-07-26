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
from .engine.benchmark import BenchmarkRunner, BenchmarkResult, SpeedMetrics
from .engine.metrics import MetricsCollector
from .engine.task_runner import LMEvalTaskRunner
from .adapters.mlx_model import MLXModel
from .optimizer.tuner import ParameterTuner, TuneResult
from .reporter.report import ReportGenerator

# New architecture exports
from .core.registry import Registry, executor_registry, suite_registry, gate_registry
from .core.plugin_base import ExecutorPlugin, ExecutorType, TaskConfig, EvalResult, CaseResult
from .core.models import (
    EvalLevel, GateTier, TaskStatus,
    BenchmarkTask, QualityGate, GateResult, SuiteResult, TraceRecord,
)
from .orchestrator.pipeline import Pipeline
from .orchestrator.gate_engine import GateEngine
from .orchestrator.scheduler import Scheduler
from .storage.trace_store import TraceStore

__all__ = [
    # Legacy
    "BenchmarkRunner", "BenchmarkResult", "SpeedMetrics",
    "MetricsCollector",
    "LMEvalTaskRunner",
    "MLXModel",
    "ParameterTuner", "TuneResult",
    "ReportGenerator",
    # Core
    "Registry", "executor_registry", "suite_registry", "gate_registry",
    "ExecutorPlugin", "ExecutorType", "TaskConfig", "EvalResult", "CaseResult",
    "EvalLevel", "GateTier", "TaskStatus",
    "BenchmarkTask", "QualityGate", "GateResult", "SuiteResult", "TraceRecord",
    # Orchestrator
    "Pipeline", "GateEngine", "Scheduler",
    # Storage
    "TraceStore",
]
