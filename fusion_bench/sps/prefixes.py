"""Prefix-set loader for the SPS tuner (#43).

JSONL, one prefix per line. Accepted shapes:
- {"prompt": "...", "sampling_params": {"temperature": 0.0, ...}}
- {"prompt": "..."} (sampling_params default from the tuner config)
- {"input_ids": [...]} — logged and SKIPPED: the bench is HTTP-only and
  never loads a tokenizer (critical constraint); re-run the export with
  decoded prompts instead.

DSpine guidance: >= 8 distinct prefixes covering context lengths, tasks
and reasoning levels. The loader warns below that and errors on empty
sets; greedy and temperature sampling should be tuned as separate runs.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

MIN_DISTINCT_PREFIXES = 8


@dataclass
class SPrefix:
    prompt: str
    sampling_params: dict = field(default_factory=dict)


def load_prefixes(path: str | Path) -> list[SPrefix]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"prefix file not found: {p}")
    prefixes: list[SPrefix] = []
    skipped = 0
    with p.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError as e:
                raise ValueError(f"prefix file line {lineno}: invalid JSON: {e}") from e
            if not isinstance(row, dict):
                raise ValueError(f"prefix file line {lineno}: expected a JSON object")
            if isinstance(row.get("prompt"), str) and row["prompt"].strip():
                prefixes.append(
                    SPrefix(
                        prompt=row["prompt"],
                        sampling_params=dict(row.get("sampling_params") or {}),
                    )
                )
            elif "input_ids" in row:
                skipped += 1
            else:
                raise ValueError(f"prefix file line {lineno}: missing 'prompt' (or 'input_ids')")
    if skipped:
        logger.warning(
            "Skipped %d tokenized-only prefixes (input_ids): the bench never "
            "loads a tokenizer — export decoded prompts instead",
            skipped,
        )
    if not prefixes:
        raise ValueError(f"prefix file has no usable prefixes: {p}")
    distinct = len({x.prompt for x in prefixes})
    if distinct < MIN_DISTINCT_PREFIXES:
        logger.warning(
            "Only %d distinct prefixes (DSpine guidance: >= %d covering context "
            "lengths, tasks, reasoning levels) — tuned budgets may not generalize",
            distinct,
            MIN_DISTINCT_PREFIXES,
        )
    logger.info("Loaded %d prefixes (%d distinct) from %s", len(prefixes), distinct, p)
    return prefixes
