"""Executor plugins — each wraps an evaluation tool behind the ExecutorPlugin interface."""

from .agent_executor import AgentExecutor
from .artifact_executor import ArtifactExecutor
from .code_executor import CodeExecutor
from .evalscope_executor import EvalScopeExecutor
from .garak_executor import GarakExecutor
from .helm_adapter import HelmAdapter
from .lm_harness_executor import LMHarnessExecutor
from .opencompass_executor import OpenCompassExecutor
from .quant_executor import QuantExecutor
from .security_executor import SecurityExecutor
from .speed_executor import SpeedExecutor
from .tune_executor import TuneExecutor

__all__ = [
    "SpeedExecutor",
    "LMHarnessExecutor",
    "TuneExecutor",
    "QuantExecutor",
    "SecurityExecutor",
    "OpenCompassExecutor",
    "AgentExecutor",
    "CodeExecutor",
    "ArtifactExecutor",
    "EvalScopeExecutor",
    "HelmAdapter",
    "GarakExecutor",
]


def register_all() -> None:
    from ..core.registry import executor_registry

    _all_executors = [
        SpeedExecutor,
        LMHarnessExecutor,
        TuneExecutor,
        QuantExecutor,
        SecurityExecutor,
        OpenCompassExecutor,
        AgentExecutor,
        CodeExecutor,
        ArtifactExecutor,
        EvalScopeExecutor,
        HelmAdapter,
        GarakExecutor,
    ]
    for cls in _all_executors:
        try:
            instance = cls()
            if instance.is_available():
                executor_registry.register(instance.name, cls)
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning("Skip %s: %s", cls.__name__, e)
