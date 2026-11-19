"""Top-10 scenario coverage KPI for the golden set (#49).

Measured monthly from ops_prompts: the golden set must cover >= 80% of
the traffic volume in the Top-10 high-frequency categories. Input is a
category histogram export (category -> request count) plus the set of
categories the golden set actually contains.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

KPI_TARGET = 0.80


def coverage_kpi(
    histogram: dict[str, int],
    covered_categories: set[str],
    top_n: int = 10,
) -> dict:
    if not histogram:
        raise ValueError("histogram is empty — export ops_prompts category counts first")
    top = sorted(histogram.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    top_total = sum(c for _, c in top)
    covered_freq = sum(c for cat, c in top if cat in covered_categories)
    missing_top = [cat for cat, _ in top if cat not in covered_categories]
    ratio = round(covered_freq / top_total, 4) if top_total else 0.0
    out = {
        "top_categories": [{"category": cat, "count": c, "covered": cat in covered_categories} for cat, c in top],
        "coverage_ratio": ratio,
        "kpi_target": KPI_TARGET,
        "kpi_met": ratio >= KPI_TARGET,
        "missing_top": missing_top,
    }
    logger.info(
        "Golden coverage KPI: %.1f%% of Top-%d traffic (target %.0f%%, met=%s)",
        ratio * 100,
        top_n,
        KPI_TARGET * 100,
        out["kpi_met"],
    )
    return out


def coverage_from_files(histogram_path: str | Path, golden_path: str | Path, top_n: int = 10) -> dict:
    hist = json.loads(Path(histogram_path).read_text(encoding="utf-8"))
    from .cases import load_cases

    covered = {c.category for c in load_cases(golden_path)}
    return coverage_kpi(hist, covered, top_n)


__all__ = ["coverage_kpi", "coverage_from_files", "KPI_TARGET"]
