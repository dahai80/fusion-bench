"""Scheduler — manages benchmark suite definitions and execution ordering.

Loads suite definitions (lists of tasks with configs) and provides
pre-built suites for common evaluation scenarios.
"""

from __future__ import annotations

import logging
from typing import Any

from ..core.models import BenchmarkTask, EvalLevel

logger = logging.getLogger(__name__)


class Scheduler:
    """Manages benchmark suite definitions and execution ordering.

    Provides pre-built suites and allows custom suite creation.
    """

    def __init__(self):
        self._suites: dict[str, list[BenchmarkTask]] = {}

    def register_suite(self, suite_name: str, tasks: list[BenchmarkTask]) -> None:
        self._suites[suite_name] = tasks
        logger.debug("Registered suite '%s' with %d tasks", suite_name, len(tasks))

    def get_suite(self, suite_name: str) -> list[BenchmarkTask]:
        if suite_name not in self._suites:
            raise KeyError(f"Suite '{suite_name}' not found. Available: {list(self._suites.keys())}")
        return self._suites[suite_name]

    def list_suites(self) -> list[str]:
        return sorted(self._suites.keys())

    def suite_to_task_configs(self, suite_name: str) -> list[dict[str, Any]]:
        """Convert a suite's tasks to the dict format Pipeline.run_suite() expects."""
        tasks = self.get_suite(suite_name)
        return [
            {
                "task_id": t.task_id,
                "executor_key": t.executor_key,
                "dataset": t.dataset,
                "max_samples": t.max_samples,
                "params": t.params,
                "timeout_seconds": t.timeout_seconds,
            }
            for t in tasks
        ]

    def load_default_suites(self) -> None:
        """Register built-in benchmark suites for common scenarios."""
        # L1 — Model baseline
        self.register_suite("l1-quick", [
            BenchmarkTask("l1-speed", "Speed benchmark", EvalLevel.L1_MODEL, "speed",
                           params={"runs": 3}),
        ])
        self.register_suite("l1-full", [
            BenchmarkTask("l1-speed", "Speed benchmark", EvalLevel.L1_MODEL, "speed",
                           params={"runs": 3}),
            BenchmarkTask("l1-accuracy", "Accuracy (MMLU)", EvalLevel.L1_MODEL, "lm_harness",
                           dataset="mmlu", params={"task_name": "mmlu", "num_fewshot": 5}),
            BenchmarkTask("l1-quant", "Quantization comparison", EvalLevel.L1_MODEL, "quant"),
        ])

        # L1 — Tuning
        self.register_suite("l1-tune", [
            BenchmarkTask("l1-tune", "Parameter tuning", EvalLevel.L1_MODEL, "tune",
                           params={"max_combinations": 12}),
        ])

        # L3 — Application security
        self.register_suite("l3-security", [
            BenchmarkTask("l3-injection", "Injection probes", EvalLevel.L3_APP, "security",
                           params={"probe_set": "injection"}),
            BenchmarkTask("l3-harmful", "Harmful content probes", EvalLevel.L3_APP, "security",
                           params={"probe_set": "harmful"}),
            BenchmarkTask("l3-pii", "PII leakage probes", EvalLevel.L3_APP, "security",
                           params={"probe_set": "pii"}),
        ])

        # Full — All levels
        self.register_suite("full", [
            BenchmarkTask("full-speed", "Speed benchmark", EvalLevel.L1_MODEL, "speed",
                           params={"runs": 3}),
            BenchmarkTask("full-accuracy", "Accuracy (MMLU)", EvalLevel.L1_MODEL, "lm_harness",
                           dataset="mmlu", params={"task_name": "mmlu", "num_fewshot": 5}),
            BenchmarkTask("full-security", "Security probes", EvalLevel.L3_APP, "security",
                           params={"probe_set": "injection"}),
        ])

        logger.info("Loaded %d default suites: %s", len(self._suites), list(self._suites.keys()))
