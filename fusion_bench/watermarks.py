"""Public benchmark watermarks — curated reference scores for comparison.

Purpose: anchor internal fusion-bench numbers to public watermarks so a run
can be read against the state of the art instead of in isolation. Entries are
added only with a public source; per-model rows are added when a public score
for the exact model+benchmark pair exists (never estimated).

Lookup: watermarks.lookup(benchmark, model="") -> list[dict]
Comparison: watermarks.compare(benchmark, score, model="") -> dict
CLI: fusion-bench watermark [benchmark] [--score X]
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Each entry: benchmark id, optional model filter (substring match on the
# served model name, "" = benchmark-level), score as a fraction of 1.0,
# source URL, and the date the score was published (YYYY-MM).
WATERMARKS: list[dict] = [
    {
        "benchmark": "swe-bench-verified",
        "model": "",
        "score": 0.85,
        "who": "frontier agentic scaffolds (Claude / GPT families)",
        "source": "https://www.swebench.com",
        "date": "2026-02",
        "note": "low-to-mid 80s, near saturation; community shifting to SWE-bench Pro/Multilingual",
    },
    {
        "benchmark": "terminal-bench-2",
        "model": "",
        "score": 0.60,
        "who": "top agents",
        "source": "https://www.tbench.ai",
        "date": "2026-01",
        "note": "89 tasks, Harbor framework; see arXiv 2505.16054",
    },
    {
        "benchmark": "terminal-bench-2",
        "model": "claude-haiku-4.5",
        "score": 0.614,
        "who": "Anthropic claim",
        "source": "https://www.anthropic.com/news/claude-haiku-4-5",
        "date": "2025-10",
        "note": "vendor-reported; treat as upper band, not independent",
    },
]


def _norm(name: str) -> str:
    return (name or "").strip().lower().replace(" ", "-").replace("_", "-")


def lookup(benchmark: str, model: str = "") -> list[dict]:
    # Entries for a benchmark; model filter keeps benchmark-level rows plus
    # rows whose model id appears in the served model name.
    bench = _norm(benchmark)
    hits = [w for w in WATERMARKS if _norm(w["benchmark"]) == bench]
    if model:
        m = model.lower()
        hits = [w for w in hits if not w["model"] or w["model"].lower() in m]
    return hits


def compare(benchmark: str, score: float, model: str = "") -> dict:
    # Internal score vs the best matching watermark. Verdict is a band, not a
    # judgement: within 5 points = parity, below 20 points = gap, above = ahead.
    hits = lookup(benchmark, model)
    if not hits:
        logger.warning("watermarks: no entry for benchmark=%s model=%s", benchmark, model)
        return {"benchmark": benchmark, "score": score, "watermark": None, "delta": None, "verdict": "no-watermark"}
    top = max(hits, key=lambda w: w["score"])
    delta = score - top["score"]
    if delta >= -0.05:
        verdict = "parity"
    elif delta >= -0.20:
        verdict = "gap"
    else:
        verdict = "far-gap"
    if delta > 0:
        verdict = "ahead"
    return {
        "benchmark": benchmark,
        "score": score,
        "watermark": top["score"],
        "watermark_source": top["source"],
        "delta": round(delta, 4),
        "verdict": verdict,
    }


def markdown_table(benchmark: str = "", model: str = "") -> str:
    # Markdown rendering for reports; benchmark="" lists everything.
    rows = [w for w in WATERMARKS if not benchmark or _norm(w["benchmark"]) == _norm(benchmark)]
    if model:
        m = model.lower()
        rows = [w for w in rows if not w["model"] or w["model"].lower() in m]
    lines = [
        "| benchmark | model | score | who | source | date |",
        "|---|---|---|---|---|---|",
    ]
    for w in rows:
        lines.append(
            f"| {w['benchmark']} | {w['model'] or '(benchmark-level)'} | {w['score']:.1%} | {w['who']} | {w['source']} | {w['date']} |"
        )
    return "\n".join(lines)
