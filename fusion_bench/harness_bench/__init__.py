"""Harness comparison benchmark (issue #48, insight axis N5/A12).

Same-model harness comparison: the harness, not the model, is the variable.
Runs a deterministic agent task suite against (a) the fusion-harness kernel
loop and (b) a mini-swe-agent style bash-only baseline, both driving the
identical local model served by fusion-mlx. Metrics: success rate, tokens
in/out, cache hit rate, wall time, cost, and DetourBench-style trajectory
delta (detours + one-step misses vs a minimal-action reference).
"""

from .detour import score_trajectory
from .model_client import ChatTurn, ModelClient
from .report import build_report, render_markdown
from .runners import FusionHarnessRunner, HarnessRunResult, MiniSweRunner
from .tasks import BUILTIN_TASKS, HarnessTask

__all__ = [
    "BUILTIN_TASKS",
    "ChatTurn",
    "FusionHarnessRunner",
    "HarnessRunResult",
    "HarnessTask",
    "MiniSweRunner",
    "ModelClient",
    "build_report",
    "render_markdown",
    "score_trajectory",
]
