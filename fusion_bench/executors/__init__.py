"""Executor plugins — each wraps an evaluation tool behind the ExecutorPlugin interface."""

from .speed_executor import SpeedExecutor
from .lm_harness_executor import LMHarnessExecutor
from .tune_executor import TuneExecutor
from .quant_executor import QuantExecutor
from .security_executor import SecurityExecutor

__all__ = [
    "SpeedExecutor",
    "LMHarnessExecutor",
    "TuneExecutor",
    "QuantExecutor",
    "SecurityExecutor",
]


def register_all() -> None:
    """Auto-register all built-in executor plugins into executor_registry."""
    from ..core.registry import executor_registry

    for cls in [SpeedExecutor, LMHarnessExecutor, TuneExecutor, QuantExecutor, SecurityExecutor]:
        instance = cls()
        if instance.is_available():
            executor_registry.register(instance.name, cls)
