"""Orchestration durability benchmark (issue #70, plan ruling A6).

Public metric position: long-horizon agent workflow durability. Consumes
REAL run records (fusion-supervisor run history + fusion-cowork audit
trails and scheduled-task stats) — published reports never carry
synthetic-only numbers; metrics with insufficient denominators are
reported as insufficient, not estimated.
"""

from .metrics import compute_metrics
from .records import (
    load_cowork_audits,
    load_cowork_scheduled,
    load_supervisor_runs,
)
from .report import build_report, render_markdown, verify_report, write_report

__all__ = [
    "compute_metrics",
    "load_cowork_audits",
    "load_cowork_scheduled",
    "load_supervisor_runs",
    "build_report",
    "render_markdown",
    "verify_report",
    "write_report",
]
