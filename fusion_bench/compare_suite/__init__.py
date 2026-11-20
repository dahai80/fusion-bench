"""Shared-task comparison suite vs agent frameworks (issue #53).

Quarterly dynamic benchmark from fusion-insight/docs/benchmark-targets-2026-11-20.md
section 4: same deterministic task set against fusion-harness and rival
frameworks on the identical local fusion-mlx model. Rival for metrics 1-4 is
langgraph (only installed framework); crewai/dify/openhands cells report
`unavailable` rather than being simulated.
"""

from .attacks import AttackCase, grade_case, load_cases
from .compare import run_comparison
from .tasks import SUITE_TASKS, SuiteTask, verify_task

__all__ = [
    "SUITE_TASKS",
    "SuiteTask",
    "verify_task",
    "run_comparison",
    "AttackCase",
    "load_cases",
    "grade_case",
]
