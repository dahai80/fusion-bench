"""Capability-boundary report for office-bench runs (issue #63).

CUA-SEE goal-2 lite: after each run, locate where the agent's capability
boundary sits on the (task_type, steps) difficulty grid — fully-passed
cells adjacent to mixed/failing cells are the boundary, and the failing
tasks inside them are the next probe targets. Deterministic aggregation
over results.json rows (no model in the loop); harness-error and
engine-unreachable rows are excluded from capability inference (they say
nothing about the model — #61/#60 hygiene).

Verifier-evolution note (goal 3): the structural validators are a floor,
not a ceiling — see the adversarial cases in tests/test_office_bench.py
(TestValidatorAdversarial) documenting what each validator can and cannot
be tricked into passing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _cell_key(row: dict) -> str:
    return f"{row['task_type']}#steps={row['steps']}"


def boundary_report(results: list[dict]) -> dict:
    """Aggregate per-(task_type, steps) pass rates and derive probe targets."""
    cells: dict[str, dict] = {}
    excluded: list[dict] = []
    for row in results:
        if row.get("harness_error") or row.get("run_error"):
            excluded.append({"task_id": row["task_id"], "reason": row.get("run_error") or "harness-error"})
            continue
        key = _cell_key(row)
        cell = cells.setdefault(key, {"passed": 0, "total": 0, "pass_tasks": [], "fail_tasks": []})
        cell["total"] += 1
        if row["passed"]:
            cell["passed"] += 1
            cell["pass_tasks"].append(row["task_id"])
        else:
            cell["fail_tasks"].append(row["task_id"])
    for cell in cells.values():
        cell["pass_rate"] = round(cell["passed"] / cell["total"], 4) if cell["total"] else 0.0
        cell["boundary"] = 0 < cell["passed"] < cell["total"]

    probes = []
    by_type: dict[str, dict[int, dict]] = {}
    for key, cell in cells.items():
        app, _, steps = key.partition("#steps=")
        by_type.setdefault(app, {})[int(steps)] = cell
    for app in sorted(by_type):
        steps_map = by_type[app]
        for steps in sorted(steps_map):
            lower = steps_map.get(steps - 1)
            cur = steps_map[steps]
            if lower and lower["passed"] == lower["total"] and cur["passed"] < cur["total"]:
                probes.append(
                    {
                        "probe": f"{app} steps={steps}",
                        "reason": (
                            f"steps={steps - 1} fully passed ({lower['passed']}/{lower['total']}), "
                            f"steps={steps} mixed ({cur['passed']}/{cur['total']}) — capability boundary sits here"
                        ),
                        "fail_tasks": cur["fail_tasks"],
                    }
                )
    return {
        "cells": dict(sorted(cells.items())),
        "boundary_probes": probes,
        "excluded_tasks": excluded,
    }


def render_markdown(report: dict) -> str:
    lines = ["# Office-bench capability boundary (issue #63)", ""]
    lines.append("| cell | passed | total | pass_rate | boundary |")
    lines.append("|---|---|---|---|---|")
    for key, cell in report["cells"].items():
        lines.append(
            f"| {key} | {cell['passed']} | {cell['total']} | {cell['pass_rate']} | {'yes' if cell['boundary'] else 'no'} |"
        )
    lines += ["", "## Probe targets", ""]
    if report["boundary_probes"]:
        for probe in report["boundary_probes"]:
            lines.append(f"- **{probe['probe']}**: {probe['reason']}")
            lines.append(f"  - failing: {', '.join(probe['fail_tasks'])}")
    else:
        lines.append("- none: no fully-passed cell is adjacent to a mixed cell")
    if report["excluded_tasks"]:
        lines += ["", f"## Excluded from capability inference ({len(report['excluded_tasks'])})", ""]
        for item in report["excluded_tasks"]:
            lines.append(f"- {item['task_id']}: {item['reason']}")
    return "\n".join(lines) + "\n"


def write_boundary(out_dir: Path, results: list[dict]) -> dict:
    report = boundary_report(results)
    (out_dir / "boundary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (out_dir / "boundary.md").write_text(render_markdown(report), encoding="utf-8")
    for probe in report["boundary_probes"]:
        logger.info("boundary probe target: %s — %s", probe["probe"], probe["reason"])
    logger.info(
        "boundary report written: %d cells, %d probe targets, %d excluded tasks",
        len(report["cells"]),
        len(report["boundary_probes"]),
        len(report["excluded_tasks"]),
    )
    return report
