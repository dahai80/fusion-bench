"""Golden-set regression gate (#49).

Runs the golden cases against a model through fusion-mlx (cache-bypass
hygiene per #47), scores expected-behavior matching, and compares against
a stored baseline: a pass-rate regression beyond the threshold fails the
gate (exit-code carrying verdict) — blocking model swaps / pipeline
changes. Metrics persist through the existing BaselineStore.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from ..engine.bench_http import bench_client
from ..storage.baseline_store import BaselineStore
from .cases import GoldenCase, load_cases

logger = logging.getLogger(__name__)

GOLDEN_BASELINE_NAME = "golden-gate"


def _normalize(text: str) -> str:
    text = text.strip().lower()
    out = []
    for ch in text:
        out.append(ch if (ch.isalnum() or ch.isspace()) else " ")
    return " ".join("".join(out).split())


def score_case(
    completion: str,
    expected: str,
    mode: str = "contains",
    keywords: list[str] | None = None,
    min_chars: int = 20,
) -> bool:
    """Deterministic scoring for one golden case.

    - contains: normalized expected text appears in the completion
    - keywords: any of the given keywords appears (case-insensitive)
    - nontrivial: completion is at least min_chars long (behavioral
      annotations where the answer shape is open-ended)
    """
    if mode == "keywords":
        kws = [k.lower() for k in (keywords or [])]
        if kws:
            low = completion.lower()
            return any(k in low for k in kws)
        return score_case(completion, expected, "contains")
    if mode == "nontrivial":
        return len(completion.strip()) >= min_chars
    pred = _normalize(completion)
    target = _normalize(expected)
    return bool(pred) and (target in pred or pred == target)


async def run_golden_cases(
    cases: list[GoldenCase],
    model: str,
    mlx_base_url: str = "http://127.0.0.1:11434/v1",
    api_key: str = "",
    max_tokens: int = 256,
    timeout: float = 120.0,
) -> dict:
    """Generate + score every golden case; returns metrics, no side effects."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
    results: list[dict] = []
    start = time.time()
    async with bench_client(base_url=mlx_base_url, timeout=timeout, headers=headers) as client:
        for case in cases:
            t0 = time.time()
            try:
                resp = await client.post(
                    "/chat/completions",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": case.prompt}],
                        "max_tokens": max_tokens,
                        "temperature": 0,
                    },
                )
                resp.raise_for_status()
                completion = resp.json()["choices"][0]["message"]["content"] or ""
            except Exception as e:
                logger.error("Golden case %s failed: %s", case.case_id, e)
                completion = ""
            passed = score_case(completion, case.expected, case.match_mode, case.match_keywords)
            results.append(
                {
                    "case_id": case.case_id,
                    "category": case.category,
                    "passed": passed,
                    "latency_s": round(time.time() - t0, 3),
                    "is_failure_case": case.is_failure_case,
                }
            )
            logger.info("Golden case %s: %s (%.2fs)", case.case_id, "PASS" if passed else "FAIL", time.time() - t0)

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    by_category: dict[str, dict[str, float]] = {}
    for r in results:
        cat = by_category.setdefault(r["category"], {"total": 0, "passed": 0})
        cat["total"] += 1
        cat["passed"] += int(r["passed"])
    metrics = {
        "golden_pass_rate": round(passed / total, 4) if total else 0.0,
        "golden_total": float(total),
        "golden_passed": float(passed),
        "failure_case_pass_rate": round(
            sum(1 for r in results if r["passed"] and r["is_failure_case"])
            / max(sum(1 for r in results if r["is_failure_case"]), 1),
            4,
        ),
    }
    for cat, c in by_category.items():
        metrics[f"golden_pass_rate::{cat}"] = round(c["passed"] / c["total"], 4)
    return {
        "model": model,
        "metrics": metrics,
        "results": results,
        "duration_s": round(time.time() - start, 2),
    }


async def run_golden_gate(
    golden_path: str | Path,
    model: str,
    mlx_base_url: str = "http://127.0.0.1:11434/v1",
    api_key: str = "",
    threshold_pct: float = 5.0,
    update_baseline: bool = False,
    db_path: str | Path | None = None,
    max_tokens: int = 256,
) -> dict:
    """Full gate: run golden set, diff vs baseline, return verdict.

    Verdict `blocked` means the change regressed the golden pass rate by
    more than threshold_pct points — the pipeline change must not land.
    """
    cases = load_cases(golden_path)
    if not cases:
        raise ValueError(f"No golden cases loaded from {golden_path}")
    run = await run_golden_cases(cases, model, mlx_base_url, api_key, max_tokens=max_tokens)

    store = BaselineStore(db_path)
    try:
        baseline = store.get_baseline(GOLDEN_BASELINE_NAME, model, "golden", "L1")
        verdict = "baseline_saved"
        if baseline and not update_baseline:
            base_rate = float(baseline["metrics"].get("golden_pass_rate", 0.0))
            cur_rate = float(run["metrics"]["golden_pass_rate"])
            drop_points = round((base_rate - cur_rate) * 100, 2)
            verdict = "blocked" if drop_points > threshold_pct else "passed"
            run["baseline_pass_rate"] = base_rate
            run["drop_points"] = drop_points
            run["threshold_pct"] = threshold_pct
        if update_baseline or not baseline:
            store.set_baseline(
                GOLDEN_BASELINE_NAME,
                model,
                "golden",
                "L1",
                run["metrics"],
                description=f"golden set {Path(golden_path).name} ({len(cases)} cases)",
            )
    finally:
        store.close()

    run["verdict"] = verdict
    logger.info(
        "Golden gate verdict: %s (pass_rate=%.4f, model=%s)", verdict, run["metrics"]["golden_pass_rate"], model
    )
    return run


__all__ = ["run_golden_gate", "run_golden_cases", "score_case", "GOLDEN_BASELINE_NAME"]
