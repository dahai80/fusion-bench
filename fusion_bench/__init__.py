"""Fusion-Bench — MLX model performance benchmarking and auto-tuning workbench.

All model inference goes through fusion-mlx HTTP API (/v1/chat/completions).
Never imports MLX, mlx-lm, or any engine code directly.
"""

from .engine.benchmark import BenchmarkRunner, BenchmarkResult, SpeedMetrics
from .engine.metrics import MetricsCollector
from .engine.task_runner import LMEvalTaskRunner
from .adapters.mlx_model import MLXModel
from .optimizer.tuner import ParameterTuner, TuneResult
from .reporter.report import ReportGenerator

__all__ = [
    "BenchmarkRunner", "BenchmarkResult", "SpeedMetrics",
    "MetricsCollector",
    "LMEvalTaskRunner",
    "MLXModel",
    "ParameterTuner", "TuneResult",
    "ReportGenerator",
]