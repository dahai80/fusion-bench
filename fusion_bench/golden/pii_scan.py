"""PII scan for golden-set files (#49).

CI runs this over benchmarks/golden/ and fails the build on any hit —
only samples that passed desensitize v1 (double-channel) or came from
opt-in users may enter golden/, and this re-check is the backstop.
Matchers are regex-based, deterministic, no model involvement.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_PATTERNS: dict[str, re.Pattern] = {
    "cn_mobile": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "cn_id_card": re.compile(
        r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)"
    ),
    "bank_card": re.compile(r"(?<!\d)(?:\d{4}[ -]?){3,4}\d{1,4}(?!\d)"),
    "ipv4": re.compile(
        r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![\d.])"
    ),
}


def scan_text(text: str) -> list[dict]:
    hits: list[dict] = []
    for kind, pat in _PATTERNS.items():
        for m in pat.finditer(text):
            snippet = m.group(0)
            masked = (
                snippet[:2] + "*" * max(len(snippet) - 4, 0) + snippet[-2:] if len(snippet) > 4 else "*" * len(snippet)
            )
            hits.append({"kind": kind, "masked": masked, "start": m.start(), "end": m.end()})
    return hits


def scan_file(path: str | Path) -> list[dict]:
    """Scan a golden JSONL file; hits carry case_id when the line parses."""
    path = Path(path)
    hits: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            case_id = ""
            try:
                case_id = str(json.loads(stripped).get("case_id", ""))
            except json.JSONDecodeError:
                case_id = f"<unparsed line {line_no}>"
            for h in scan_text(stripped):
                hits.append({"file": str(path), "line": line_no, "case_id": case_id, **h})
    return hits


def scan_dir(path: str | Path) -> list[dict]:
    """Scan every file in a directory (golden/); returns all hits."""
    path = Path(path)
    hits: list[dict] = []
    if not path.exists():
        logger.warning("PII scan: directory %s does not exist — nothing to scan", path)
        return hits
    for f in sorted(path.rglob("*")):
        if f.is_file():
            hits.extend(scan_file(f))
    if hits:
        logger.error("PII scan: %d hit(s) in %s — build must fail", len(hits), path)
    else:
        logger.info("PII scan: clean (%s)", path)
    return hits


__all__ = ["scan_text", "scan_file", "scan_dir"]
