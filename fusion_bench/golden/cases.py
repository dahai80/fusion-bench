"""Versioned golden-case storage (#49).

Golden cases live as a JSONL file under benchmarks/golden/ with a schema
header line, so sets are versioned by filename (golden-cases-v1.jsonl)
and diffable in review. Raw result storage of regular benches is never
touched — golden cases are inputs, not results.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA_LINE_PREFIX = "# fusion-bench.golden/v1"
REQUIRED_FIELDS = {"case_id", "category", "prompt", "expected"}


@dataclass
class GoldenCase:
    case_id: str
    category: str
    prompt: str
    expected: str
    is_failure_case: bool = False
    source: str = ""
    desensitized: bool = True
    notes: str = ""
    match_mode: str = "contains"  # contains | keywords | nontrivial
    match_keywords: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def prompt_hash(self) -> str:
        return hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()[:16]


def _validate(raw: dict, idx: int) -> GoldenCase:
    missing = REQUIRED_FIELDS - set(raw)
    if missing:
        raise ValueError(f"golden case line {idx + 1}: missing fields {sorted(missing)}")
    if not str(raw.get("prompt", "")).strip() or not str(raw.get("expected", "")).strip():
        raise ValueError(f"golden case line {idx + 1}: prompt and expected must be non-empty")
    return GoldenCase(
        case_id=str(raw["case_id"]),
        category=str(raw.get("category", "uncategorized")),
        prompt=str(raw["prompt"]),
        expected=str(raw["expected"]),
        is_failure_case=bool(raw.get("is_failure_case", False)),
        source=str(raw.get("source", "")),
        desensitized=bool(raw.get("desensitized", True)),
        notes=str(raw.get("notes", "")),
        match_mode=str(raw.get("match_mode", "contains")),
        match_keywords=[str(k) for k in raw.get("match_keywords", [])],
        meta=raw.get("meta", {}) or {},
    )


def load_cases(path: str | Path) -> list[GoldenCase]:
    """Load a versioned golden-case JSONL (schema header optional, ignored)."""
    cases: list[GoldenCase] = []
    seen: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            case = _validate(json.loads(line), idx)
            if case.case_id in seen:
                raise ValueError(f"duplicate case_id '{case.case_id}' in {path}")
            seen.add(case.case_id)
            cases.append(case)
    logger.info("Loaded %d golden cases from %s", len(cases), path)
    return cases


def save_cases(cases: list[GoldenCase], path: str | Path) -> int:
    """Write the versioned golden-case file with schema header."""
    seen: set[str] = set()
    for c in cases:
        if c.case_id in seen:
            raise ValueError(f"duplicate case_id '{c.case_id}'")
        seen.add(c.case_id)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{SCHEMA_LINE_PREFIX}\n")
        for c in cases:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    logger.info("Saved %d golden cases to %s", len(cases), path)
    return len(cases)
