"""Abstract base class for executor plugins.

Every evaluation tool integrated into fusion-bench implements this interface,
providing a unified run(task_config) -> result contract.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ExecutorType(str, Enum):
    MODEL = "model"
    AGENT = "agent"
    CODE = "code"
    SECURITY = "security"
    ARTIFACT = "artifact"
    SPEED = "speed"
    QUANT = "quant"


@dataclass
class TaskConfig:
    """Unified task configuration passed to every executor plugin."""
    task_id: str
    model: str
    executor_key: str
    params: dict[str, Any] = field(default_factory=dict)
    dataset: str | None = None
    max_samples: int | None = None
    random_seed: int = 42
    timeout_seconds: int = 600

    def get(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)


@dataclass
class CaseResult:
    """Result of a single test case / sample."""
    input_text: str
    expected: str | None = None
    actual: str | None = None
    score: float = 0.0
    passed: bool = False
    latency_ms: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalResult:
    """Unified evaluation result returned by every executor plugin."""
    task_id: str
    executor_key: str
    model: str
    level: str = "L1"
    metric_name: str = "accuracy"
    metric_value: float = 0.0
    cases: list[CaseResult] = field(default_factory=list)
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def pass_rate(self) -> float:
        if not self.cases:
            return 0.0
        return sum(1 for c in self.cases if c.passed) / len(self.cases)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "executor_key": self.executor_key,
            "model": self.model,
            "level": self.level,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "pass_rate": self.pass_rate,
            "num_cases": len(self.cases),
            "duration_seconds": self.duration_seconds,
            "errors": self.errors,
            "meta": self.meta,
        }


class ExecutorPlugin(ABC):
    """Base class for all executor plugins.

    Subclasses must:
    1. Set `name` and `executor_type` class attributes
    2. Implement `run(task_config) -> EvalResult`
    3. Optionally override `is_available()` for dependency checks
    """

    name: str = ""
    executor_type: ExecutorType = ExecutorType.MODEL

    @abstractmethod
    async def run(self, config: TaskConfig) -> EvalResult:
        ...

    def is_available(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, type={self.executor_type.value})"
