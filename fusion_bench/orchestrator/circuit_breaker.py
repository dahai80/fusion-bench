"""Circuit breaker — protects pipeline from cascading failures.

Opens after N consecutive failures for a given executor_key,
preventing new tasks from running. Auto-recovers after cooldown.
Imported by Pipeline in orchestrator/pipeline.py. Schema: _circuits dict keyed by executor_key.
User instruction: "把所有没完全做完，没启动做，有差距的全部启动补齐" (P2-18).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitInfo:
    executor_key: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    last_failure_msg: str = ""


class CircuitBreaker:
    """Circuit breaker for executor tasks.

    Opens after `failure_threshold` consecutive failures,
    auto-recovers after `cooldown_seconds` (half-open → allow one attempt).
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 60.0,
        success_threshold: int = 2,
    ):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.success_threshold = success_threshold
        self._circuits: dict[str, CircuitInfo] = {}
        self._half_open_successes: dict[str, int] = {}

    def _get_circuit(self, executor_key: str) -> CircuitInfo:
        if executor_key not in self._circuits:
            self._circuits[executor_key] = CircuitInfo(executor_key=executor_key)
        return self._circuits[executor_key]

    def can_execute(self, executor_key: str) -> bool:
        circuit = self._get_circuit(executor_key)
        if circuit.state == CircuitState.CLOSED:
            return True
        if circuit.state == CircuitState.OPEN:
            elapsed = time.time() - circuit.last_failure_time
            if elapsed >= self.cooldown_seconds:
                circuit.state = CircuitState.HALF_OPEN
                self._half_open_successes[executor_key] = 0
                logger.info("Circuit %s: OPEN -> HALF_OPEN (cooldown elapsed)", executor_key)
                return True
            logger.warning(
                "Circuit %s: OPEN (cooldown %.0fs remaining)",
                executor_key,
                self.cooldown_seconds - elapsed,
            )
            return False
        return True

    def record_success(self, executor_key: str) -> None:
        circuit = self._get_circuit(executor_key)
        circuit.failure_count = 0
        if circuit.state == CircuitState.HALF_OPEN:
            count = self._half_open_successes.get(executor_key, 0) + 1
            self._half_open_successes[executor_key] = count
            if count >= self.success_threshold:
                circuit.state = CircuitState.CLOSED
                logger.info("Circuit %s: HALF_OPEN -> CLOSED (recovered)", executor_key)
            else:
                logger.info(
                    "Circuit %s: HALF_OPEN success %d/%d",
                    executor_key,
                    count,
                    self.success_threshold,
                )
        else:
            circuit.state = CircuitState.CLOSED

    def record_failure(self, executor_key: str, error_msg: str = "") -> None:
        circuit = self._get_circuit(executor_key)
        circuit.failure_count += 1
        circuit.last_failure_time = time.time()
        circuit.last_failure_msg = error_msg[:200]
        if circuit.state == CircuitState.HALF_OPEN:
            circuit.state = CircuitState.OPEN
            logger.warning("Circuit %s: HALF_OPEN -> OPEN (failure during recovery)", executor_key)
            return
        if circuit.failure_count >= self.failure_threshold:
            circuit.state = CircuitState.OPEN
            logger.warning(
                "Circuit %s: CLOSED -> OPEN (%d consecutive failures): %s",
                executor_key,
                circuit.failure_count,
                error_msg[:100],
            )

    def get_state(self, executor_key: str) -> dict[str, Any]:
        circuit = self._get_circuit(executor_key)
        return {
            "executor_key": executor_key,
            "state": circuit.state.value,
            "failure_count": circuit.failure_count,
            "last_failure_time": circuit.last_failure_time,
            "last_failure_msg": circuit.last_failure_msg,
        }

    def list_circuits(self) -> list[dict[str, Any]]:
        return [self.get_state(k) for k in self._circuits]

    def reset(self, executor_key: str = "") -> None:
        if executor_key:
            if executor_key in self._circuits:
                self._circuits[executor_key] = CircuitInfo(executor_key=executor_key)
                logger.info("Circuit %s: reset to CLOSED", executor_key)
        else:
            self._circuits.clear()
            self._half_open_successes.clear()
            logger.info("All circuits reset to CLOSED")
