"""Type-safe plugin registry — inspired by lm-evaluation-harness Registry[T] pattern.

Central registration point for all executor plugins, benchmark suites,
and quality gate rules. Supports runtime discovery and lazy loading.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Registry[T]:
    """Generic type-safe registry for named items.

    Usage:
        executor_registry = Registry[ExecutorPlugin]("executors")
        executor_registry.register("lm_harness", LMHarnessExecutor)
        cls = executor_registry.get("lm_harness")
    """

    def __init__(self, name: str):
        self.name = name
        self._items: dict[str, type[T]] = {}

    def register(self, key: str, item: type[T]) -> None:
        if key in self._items:
            logger.warning("Registry[%s]: overwriting existing key '%s'", self.name, key)
        self._items[key] = item
        logger.debug("Registry[%s]: registered '%s'", self.name, key)

    def get(self, key: str) -> type[T] | None:
        return self._items.get(key)

    def get_or_raise(self, key: str) -> type[T]:
        if key not in self._items:
            raise KeyError(
                f"Registry[{self.name}]: no item registered as '{key}'. Available: {list(self._items.keys())}"
            )
        return self._items[key]

    def list_keys(self) -> list[str]:
        return sorted(self._items.keys())

    def list_items(self) -> dict[str, type[T]]:
        return dict(self._items)

    def has(self, key: str) -> bool:
        return key in self._items

    def unregister(self, key: str) -> None:
        if key in self._items:
            del self._items[key]
            logger.debug("Registry[%s]: unregistered '%s'", self.name, key)

    def __contains__(self, key: str) -> bool:
        return key in self._items

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"Registry({self.name}, keys={self.list_keys()})"


# ── Global registries ──

executor_registry = Registry("executors")
suite_registry = Registry("benchmark_suites")
gate_registry = Registry("quality_gates")
