"""Office file validators (issue #56).

Vendored from fusion-trainer#90 `rlsl/reward_plugins.py` (office_xlsx /
office_docx / office_pptx) — same structural checks, adapted to a
bench-facing signature `validate(task_type, path, args) -> (score, detail)`.
Keep in sync with the upstream plugin family; pure stdlib zipfile + ElementTree
over OOXML, deterministic, CI-testable.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

_NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_WML = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def validate(task_type: str, path: Path, args: dict) -> tuple[float, str]:
    if task_type == "office_xlsx":
        return _validate_xlsx(path, args)
    if task_type == "office_docx":
        return _validate_docx(path, args)
    if task_type == "office_pptx":
        return _validate_pptx(path, args)
    return 0.0, f"unknown task_type: {task_type}"


def _normalize(parts: list[tuple[str, bool, str]]) -> tuple[float, str]:
    failed = [f"{name}: {detail}" for name, ok, detail in parts if not ok]
    return (1.0, "ok") if not failed else (0.0, "; ".join(failed))


# issue #64: negative probes. A positive-only validator fails open — it can
# credit a run whose only merit is keyword/artifact presence, including
# over-trigger (unsolicited edits the task never asked for, the small-model
# failure mode documented in arXiv 2610.02142). The forbidden_* args below
# let a task assert absence: the artifact must NOT contain the listed
# sheet/section/title. Combined with no-op probe tasks they gate
# over-trigger and keyword false positives.


def _sheet_target(zf: zipfile.ZipFile, sheet_name: str, sheets: dict[str, str]) -> str | None:
    rid = sheets.get(sheet_name, "")
    for rel in ET.fromstring(zf.read("xl/_rels/workbook.xml.rels")).iter(f"{{{_NS_PKG_REL}}}Relationship"):
        if rel.get("Id") == rid:
            target = rel.get("Target", "worksheets/sheet1.xml").lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    return None


def _sheet_formula_counts(zf: zipfile.ZipFile, target: str) -> tuple[int, int]:
    root = ET.fromstring(zf.read(target))
    ns = {"m": _NS_MAIN}
    formulas = len(root.findall(".//m:f", ns))
    values = 0
    for c in root.findall(".//m:c", ns):
        if c.get("t") == "str" or c.find("m:f", ns) is not None:
            continue
        v = c.find("m:v", ns)
        if v is not None and v.text and re.fullmatch(r"-?\d+(\.\d+)?", v.text.strip()):
            values += 1
    return formulas, values


def _validate_xlsx(path: Path, args: dict) -> tuple[float, str]:
    required = [str(s) for s in (args.get("required_sheets") or [])]
    checks: list[tuple[str, bool, str]] = []
    try:
        with zipfile.ZipFile(path) as zf:
            wb = ET.fromstring(zf.read("xl/workbook.xml"))
            sheets = {
                sh.get("name", ""): sh.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", ""
                )
                for sh in wb.findall("m:sheets/m:sheet", {"m": _NS_MAIN})
            }
            for name in required:
                checks.append((f"sheet:{name}", name in sheets, f"sheets={sorted(sheets)}"))
            for name in [str(s) for s in (args.get("forbidden_sheets") or [])]:
                checks.append((f"!sheet:{name}", name not in sheets, f"forbidden sheet {name!r} present"))
            policy = str(args.get("formula_policy", "") or "")
            if policy and required:
                target = _sheet_target(zf, required[0], sheets)
                if target is None:
                    checks.append(("formulas", False, "sheet part unresolved"))
                else:
                    formulas, values = _sheet_formula_counts(zf, target)
                    ok = formulas > 0 and (policy != "strict" or values == 0)
                    checks.append(
                        ("formulas", ok, f"policy={policy} formula_cells={formulas} constant_numeric={values}")
                    )
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        checks.append(("open", False, f"not a readable xlsx: {exc}"))
    score, detail = _normalize(checks)
    logger.info("office_xlsx validate score=%.1f file=%s detail=%s", score, path, detail)
    return score, detail


def _validate_docx(path: Path, args: dict) -> tuple[float, str]:
    required = [str(s) for s in (args.get("required_sections") or [])]
    checks: list[tuple[str, bool, str]] = []
    try:
        with zipfile.ZipFile(path) as zf:
            doc = ET.fromstring(zf.read("word/document.xml"))
            text = "\n".join(
                "".join(t.text or "" for t in p.iter(f"{{{_NS_WML}}}t")) for p in doc.iter(f"{{{_NS_WML}}}p")
            )
            for sec in required:
                checks.append((f"section:{sec}", sec.lower() in text.lower(), f"{sec!r} not found in document text"))
            for sec in [str(s) for s in (args.get("forbidden_sections") or [])]:
                checks.append(
                    (f"!section:{sec}", sec.lower() not in text.lower(), f"forbidden section {sec!r} present")
                )
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        checks.append(("open", False, f"not a readable docx: {exc}"))
    score, detail = _normalize(checks)
    logger.info("office_docx validate score=%.1f file=%s detail=%s", score, path, detail)
    return score, detail


def _validate_pptx(path: Path, args: dict) -> tuple[float, str]:
    min_slides = int(args.get("min_slides", 1))
    required_titles = [str(t) for t in (args.get("required_titles") or [])]
    checks: list[tuple[str, bool, str]] = []
    try:
        with zipfile.ZipFile(path) as zf:
            slides = sorted(n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))
            checks.append(("slides", len(slides) >= min_slides, f"{len(slides)} < {min_slides}"))
            joined = "\n".join(
                " ".join(
                    el.text or ""
                    for el in ET.fromstring(zf.read(name)).iter()
                    if isinstance(el.tag, str) and el.tag.endswith("}t")
                ).lower()
                for name in slides
            )
            for title in required_titles:
                checks.append((f"title:{title}", title.lower() in joined, f"{title!r} not found on any slide"))
            for title in [str(t) for t in (args.get("forbidden_titles") or [])]:
                checks.append((f"!title:{title}", title.lower() not in joined, f"forbidden title {title!r} present"))
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        checks.append(("open", False, f"not a readable pptx: {exc}"))
    score, detail = _normalize(checks)
    logger.info("office_pptx validate score=%.1f file=%s detail=%s", score, path, detail)
    return score, detail
