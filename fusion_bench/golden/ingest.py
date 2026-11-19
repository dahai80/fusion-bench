"""Ingest sampled production traffic into golden cases (#49).

Input: JSONL export from the ops pipeline (one record per line). The
export is produced upstream from `ops_prompts`; this module never reads
another project's database.

Privacy gate: records are only accepted when `desensitized` is true or
`opted_in` is true — anything else is counted and dropped, never written.

Stratified sampling: per-category cap (default 10) on regular records;
failure cases (`is_failure_case`) always pass through the cap, per the
flywheel rule "bug-class failure samples are always included".
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from pathlib import Path

from .cases import GoldenCase
from .pii_scan import scan_text

logger = logging.getLogger(__name__)


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]


def ingest_samples(
    samples_path: str | Path,
    out_path: str | Path,
    per_category_cap: int = 10,
    fail_on_pii: bool = False,
) -> dict:
    """Read the sampled export, privacy-gate, stratify, write golden JSONL."""
    records: list[dict] = []
    with open(samples_path, encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"sample line {idx + 1}: invalid JSON: {e}") from e
            records.append(rec)

    accepted: list[GoldenCase] = []
    rejected_privacy = 0
    rejected_pii = 0
    dropped_overflow: dict[str, int] = defaultdict(int)
    seen_prompts: set[str] = set()
    per_cat_counts: dict[str, int] = defaultdict(int)

    for rec in records:
        category = str(rec.get("category", "uncategorized"))
        prompt = str(rec.get("prompt", "")).strip()
        expected = str(rec.get("expected", "")).strip()
        is_failure = bool(rec.get("is_failure_case", False))
        opted_in = bool(rec.get("opted_in", False))
        desensitized = bool(rec.get("desensitized", False))

        if not prompt or not expected:
            logger.warning("Ingest: dropped record with empty prompt/expected (category=%s)", category)
            continue

        # Privacy gate — hard, never bypassed by the cap logic.
        if not (desensitized or opted_in):
            rejected_privacy += 1
            logger.warning("Ingest: privacy-gated record dropped (category=%s)", category)
            continue

        # PII backstop at ingest time: a desensitization miss must not land.
        hits = scan_text(prompt + " " + expected)
        if hits:
            rejected_pii += 1
            logger.error(
                "Ingest: PII scan hit (%s) in category=%s — record dropped; fix desensitization upstream",
                ",".join(sorted({h["kind"] for h in hits})),
                category,
            )
            if fail_on_pii:
                raise ValueError(f"PII detected in sample (category={category}); run desensitize v1 before ingest")
            continue

        ph = _short_hash(prompt)
        if ph in seen_prompts:
            continue
        if not is_failure and per_cat_counts[category] >= per_category_cap:
            dropped_overflow[category] += 1
            continue
        seen_prompts.add(ph)
        per_cat_counts[category] += 1
        accepted.append(
            GoldenCase(
                case_id=f"gc-{ph}",
                category=category,
                prompt=prompt,
                expected=expected,
                is_failure_case=is_failure,
                source=str(rec.get("source", "ops_prompts")),
                desensitized=True,
                notes=str(rec.get("notes", "")),
                match_mode=str(rec.get("match_mode", "contains")),
                match_keywords=[str(k) for k in rec.get("match_keywords", [])],
                meta={"opted_in": opted_in, "desensitized": desensitized},
            )
        )

    from .cases import save_cases

    n = save_cases(accepted, out_path)
    stats = {
        "accepted": n,
        "rejected_privacy": rejected_privacy,
        "rejected_pii": rejected_pii,
        "dropped_cap": dict(dropped_overflow),
        "by_category": dict(per_cat_counts),
        "failure_cases": sum(1 for c in accepted if c.is_failure_case),
    }
    logger.info("Ingest complete: %s", stats)
    return stats
