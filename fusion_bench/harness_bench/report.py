"""Markdown rendering for the harness comparison report (issue #48).

Output artifact: per-task comparison table (harness x metric) plus a
per-run cost table. English-only, terminal/PR friendly.
"""

from __future__ import annotations


def _fmt(value, digits: int = 2) -> str:
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def build_report(report: dict) -> dict:
    """Identity hook kept for API symmetry with reporter/report.py conventions."""
    return report


def render_task_tables(report: dict) -> str:
    lines: list[str] = []
    for task_id, cells in report["tasks"].items():
        lines.append(f"### task: {task_id}")
        lines.append("")
        lines.append(
            "| harness | success | tokens in | tokens out | cache hit | wall s | steps | detours | 1-step miss |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for harness in report["harnesses"]:
            if harness not in cells:
                lines.append(f"| {harness} | (not run) | | | | | | | |")
                continue
            m = cells[harness]["metrics"]
            lines.append(
                f"| {harness} | {_fmt(m['success_rate'])} | {m['tokens_in_mean']} | {m['tokens_out_mean']} "
                f"| {_fmt(m['cache_hit_rate'])} | {_fmt(m['wall_s_mean'], 3)} | {_fmt(m['steps_mean'])} "
                f"| {m['detours_total']} | {m['one_step_misses_total']} |"
            )
        lines.append("")
    return "\n".join(lines)


def render_cost_table(report: dict) -> str:
    lines = [
        "| task | harness | run | tokens in | tokens out | llm calls | cache hits | cost USD |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in report["cost_table"]:
        lines.append(
            f"| {row['task']} | {row['harness']} | {row['run']} | {row['tokens_in']} | {row['tokens_out']} "
            f"| {row['llm_calls']} | {row['cache_hits']} | {row['cost_usd']:.6f} |"
        )
    total_lines = [
        "",
        "Total per harness: " + ", ".join(f"{h} = ${c:.6f}" for h, c in report.get("cost_total", {}).items()),
    ]
    return "\n".join(lines + total_lines)


def render_markdown(report: dict) -> str:
    parts = [
        "# Harness comparison report (issue #48)",
        "",
        f"- model: `{report['model']}` @ {report['mlx_url']}",
        f"- harnesses: {', '.join(report['harnesses'])}",
        f"- runs per cell: {report['runs_per_cell']}, max steps: {report['max_steps']}, seed: {report['seed']}",
        f"- price per Mtok (in/out): ${report['price_in_per_m']} / ${report['price_out_per_m']}",
        "",
        "## Summary (mean across tasks)",
        "",
        "| harness | success rate | tokens in | tokens out | cache hit | wall s | steps | detours | 1-step miss |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for harness in report["harnesses"]:
        s = report["summary"].get(harness)
        if not s:
            parts.append(f"| {harness} | (not run) | | | | | | | |")
            continue
        parts.append(
            f"| {harness} | {_fmt(s['success_rate'])} | {s['tokens_in_mean']} | {s['tokens_out_mean']} "
            f"| {_fmt(s['cache_hit_rate'])} | {_fmt(s['wall_s_mean'], 3)} | {_fmt(s['steps_mean'])} "
            f"| {s['detours_total']} | {s['one_step_misses_total']} |"
        )
    parts += ["", "## Per-task comparison", "", render_task_tables(report)]
    parts += ["## Per-run cost table", "", render_cost_table(report), ""]
    if report.get("errors"):
        parts += ["## Errors", ""] + [f"- {e}" for e in report["errors"]] + [""]
    return "\n".join(parts)
