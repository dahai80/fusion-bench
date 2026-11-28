"""Durability report build/render/verify (issue #70)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from .metrics import compute_metrics

logger = logging.getLogger(__name__)

VERIFY_TOLERANCE = 1e-9


def build_report(supervisor_runs: list[dict], cowork_audits: list[dict], scheduled: dict) -> dict:
    metrics = compute_metrics(supervisor_runs, cowork_audits, scheduled)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "spec": "docs/durability-spec-70.md",
        "issue": "dahai80/fusion-bench#70 (plan ruling A6, fusion-horizon position)",
        "sources": {
            "supervisor_runs": len(supervisor_runs),
            "cowork_audit_trails": len(cowork_audits),
            "scheduled_task_stats": scheduled,
        },
        "metrics": metrics,
    }


def render_markdown(report: dict) -> str:
    m = report["metrics"]
    generated_date = str(report["generated_at"])[:10]
    lines = [
        "---",
        "doc_id: fusion-bench/durability-report",
        "product: fusion-bench",
        "class: platform",
        "entry: service",
        "doc_type: guide",
        'title: { zh: "编排耐久性基准报告", en: "Orchestration Durability Report" }',
        "audience: engineer",
        "status: draft",
        "version: 1",
        f"updated: {generated_date}",
        'owner: "@dahai"',
        "source_of_truth:",
        "  - bench/durability/durability-report.json",
        "  - fusion_bench/durability/report.py",
        "---",
        "",
        "# Orchestration durability report (A6, issue #70)",
        "",
        f"Generated: {report['generated_at']}",
        "",
        f"Sources: {report['sources']['supervisor_runs']} supervisor run(s), "
        f"{report['sources']['cowork_audit_trails']} cowork audit trail(s), "
        f"{report['sources']['scheduled_task_stats']['task_count']} scheduled task(s). "
        "All numbers come from real run records; `insufficient` marks metrics whose "
        "denominator is below the published sufficiency floor — never estimated.",
        "",
        "| metric | value | num/den | status |",
        "|---|---|---|---|",
    ]
    for key in (
        "long_task_survival_rate",
        "failure_recovery_rate",
        "checkpoint_restore_correctness",
        "hours_scale_completion_ratio",
    ):
        met = m[key]
        value = met["value"] if met["value"] is not None else "n/a"
        status = "ok" if met["sufficient"] else "insufficient"
        lines.append(f"| {key} | {value} | {met['num']}/{met['den']} | {status} |")
    lines.append("")
    lines.append("Metric formulas and sufficiency floors: docs/durability-spec-70.md.")
    lines.append(
        "Recompute: `fusion-bench durability verify --dataset bench/durability/dataset-v1.json --report <this file's json>`."
    )
    return "\n".join(lines)


def verify_report(dataset: dict, report: dict, tolerance: float = VERIFY_TOLERANCE) -> tuple[bool, list[str]]:
    """Independent recomputation gate (acceptance criterion 3): recompute all
    metrics from the published dataset and diff against the report. Deterministic
    code paths make the tolerance effectively exact."""
    recomputed = compute_metrics(dataset["supervisor_runs"], dataset["cowork_audits"], dataset["scheduled_task_stats"])
    drifts = []
    for key, met in recomputed.items():
        if key == "scheduled_task_stats":
            continue
        published = report["metrics"].get(key, {})
        for field in ("value", "num", "den", "sufficient"):
            want, got = published.get(field), met.get(field)
            if isinstance(want, float) and isinstance(got, float):
                if abs(want - got) > tolerance:
                    drifts.append(f"{key}.{field}: report={want} recomputed={got}")
            elif want != got:
                drifts.append(f"{key}.{field}: report={want} recomputed={got}")
    stats_want = report["metrics"].get("scheduled_task_stats", {})
    if stats_want != recomputed["scheduled_task_stats"]:
        drifts.append(f"scheduled_task_stats: report={stats_want} recomputed={recomputed['scheduled_task_stats']}")
    logger.info("durability verify: %s (%d drift(s))", "pass" if not drifts else "FAIL", len(drifts))
    return not drifts, drifts


def write_report(report: dict, out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "durability-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (out_dir / "durability-report.md").write_text(render_markdown(report) + "\n", encoding="utf-8")
    logger.info("durability report written to %s", out_dir)
