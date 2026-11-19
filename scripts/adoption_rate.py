"""Adoption-rate metric for the fusion-harness public API (issue #52, G1 gate).

Measures the consumer wiring rate per harness release: root exports consumed
by >= 1 consumer / total public names. Consumers: local checkouts passed via
--consumer (grep of fusion_harness import/attribute usage) plus the console,
counted through a hand-maintained sidecar method -> kernel-call mapping
table. Tier A/B per the API stability policy (fusion-insight/docs/
harness-api-stability-policy-2026-11-19.md): A = consumed, B = zero
consumers. Run manually per harness minor release; snapshot committed to
docs/ so the trend line is visible.

Usage:
    python scripts/adoption_rate.py \
        --harness-root ~/fusion/fusion-harness \
        --consumer ~/fusion/fusion-agent-studio --consumer ~/fusion/fusion-cowork \
        --console-root ~/fusion/fusion-console \
        --out-dir docs
"""

from __future__ import annotations

import argparse
import datetime
import importlib
import io
import json
import logging
import re
import sys
import tokenize
from pathlib import Path

logger = logging.getLogger("adoption_rate")

SOURCE_EXTS = {".py", ".go", ".ts", ".tsx", ".js", ".rs"}
SKIP_DIRS = {
    "tests",
    "test",
    "tests_unit",
    "mutants",
    ".venv",
    "venv",
    "node_modules",
    ".git",
    "dist",
    "target",
    ".pytest_cache",
    "benchmarks",
    "docs",
    ".github",
}

# Console-sidecar method -> kernel export names (hand-maintained; verify
# against fusion-console/sidecar/harnessd.py after each sidecar change).
CONSOLE_METHOD_KERNEL_MAP = {
    "ping": [],
    "pre_llm": ["LLMFunnel", "LifecycleBus", "Compactor", "CompactionConfig"],
    "post_llm": ["LLMFunnel", "Compactor", "CompactionConfig", "LifecycleBus"],
    "tool_admit": ["ToolFunnel", "PermissionEngine", "PermissionRule", "LifecycleBus"],
    "reset": [],
}
CONSUMER_AGENT_STUDIO = "agent-studio"
CONSUMER_COWORK = "cowork"
CONSUMER_CONSOLE = "console"

ROOT_IMPORT_RE = re.compile(r"from\s+fusion_harness\s+import\s*\(([^)]*)\)|from\s+fusion_harness\s+import\s+([^\n(]+)")
SUBMODULE_STAR_RE = re.compile(r"from\s+fusion_harness\.(\w+)\s+import\s+\*")
SUBMODULE_IMPORT_RE = re.compile(
    r"from\s+fusion_harness\.(\w+)\s+import\s*\(([^)]*)\)|from\s+fusion_harness\.(\w+)\s+import\s+([^\n(*]+)"
)
ATTR_RE_TEMPLATE = r"fusion_harness(?:\.\w+)*\.{name}\b"


def _purge_fusion_harness_modules() -> None:
    """Drop cached fusion_harness modules so a different checkout reimports."""
    for name in [n for n in sys.modules if n == "fusion_harness" or n.startswith("fusion_harness.")]:
        del sys.modules[name]


def collect_exports(harness_root: str) -> list[str]:
    """Import fusion_harness from the given checkout and walk root exports."""
    root = Path(harness_root).expanduser().resolve()
    _purge_fusion_harness_modules()
    sys.path.insert(0, str(root))
    try:
        importlib.invalidate_caches()
        mod = importlib.import_module("fusion_harness")
    finally:
        sys.path.pop(0)
    names = getattr(mod, "__all__", None)
    if not names:
        import types

        names = [n for n in dir(mod) if not n.startswith("_") and not isinstance(getattr(mod, n), types.ModuleType)]
        logger.warning("fusion_harness has no __all__; fell back to public non-module dir() (%d names)", len(names))
    logger.info("Collected %d root exports from %s", len(names), root)
    return sorted(set(names))


def iter_source_files(repo: str) -> list[Path]:
    repo_path = Path(repo).expanduser().resolve()
    files: list[Path] = []
    for p in repo_path.rglob("*"):
        if not p.is_file() or p.suffix not in SOURCE_EXTS:
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(repo_path).parts):
            continue
        files.append(p)
    logger.info("Scanned %d source files in %s", len(files), repo_path)
    return files


def python_imported_names(text: str) -> tuple[set[str], set[str]]:
    """Names imported from fusion_harness (root or submodule), multiline aware.

    Returns (named imports, wildcard submodule names). Wildcard imports are
    resolved to the submodule public surface by the caller.
    """
    found: set[str] = set()
    stars: set[str] = set()
    for m in ROOT_IMPORT_RE.finditer(text):
        clause = m.group(1) or m.group(2) or ""
        for part in clause.split(","):
            name = part.strip().split(" as ")[0].strip()
            if re.fullmatch(r"[A-Za-z_]\w*", name or ""):
                found.add(name)
    for m in SUBMODULE_STAR_RE.finditer(text):
        stars.add(m.group(1))
    for m in SUBMODULE_IMPORT_RE.finditer(text):
        clause = m.group(2) or m.group(4) or ""
        for part in clause.split(","):
            name = part.strip().split(" as ")[0].strip()
            if re.fullmatch(r"[A-Za-z_]\w*", name or ""):
                found.add(name)
    return found, stars


def strip_python_comments(text: str) -> str:
    """Comment-free source so docstring/comment name mentions never count."""
    try:
        tokens = []
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type not in (tokenize.COMMENT,):
                tokens.append(tok)
        return tokenize.untokenize(tokens)
    except (tokenize.TokenError, IndentationError, SyntaxError) as e:
        logger.debug("tokenize failed (%s); using raw text", e)
        return text


def attribute_names(text: str, exports: list[str]) -> set[str]:
    found: set[str] = set()
    for name in exports:
        if re.search(ATTR_RE_TEMPLATE.format(name=re.escape(name)), text):
            found.add(name)
    return found


def submodule_public_names(harness_root: str, module: str) -> set[str]:
    """Public surface of a fusion_harness submodule (for wildcard shims)."""
    root = Path(harness_root).expanduser().resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        _purge_fusion_harness_modules()
        mod = importlib.import_module(f"fusion_harness.{module}")
        names = getattr(mod, "__all__", None)
        if not names:
            names = [n for n in dir(mod) if not n.startswith("_")]
        return set(names)
    except Exception as e:
        logger.warning("cannot resolve fusion_harness.%s: %s", module, e)
        return set()


def scan_consumer(repo: str, label: str, exports: list[str], harness_root: str) -> set[str]:
    """Names consumed anywhere in the repo (import clauses + attribute refs).

    Indirect consumption counts: `from fusion_harness.<mod> import *` shims
    attribute the whole submodule public surface to the consumer.
    """
    consumed: set[str] = set()
    star_modules: set[str] = set()
    for f in iter_source_files(repo):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.warning("unreadable file skipped: %s (%s)", f, e)
            continue
        if f.suffix == ".py":
            text = strip_python_comments(text)
            named, stars = python_imported_names(text)
            consumed |= named
            star_modules |= stars
        consumed |= attribute_names(text, exports)
    for module in star_modules:
        surface = submodule_public_names(harness_root, module)
        logger.info("Wildcard shim fusion_harness.%s -> %d names", module, len(surface))
        consumed |= surface & set(exports)
    logger.info("Consumer %s: %d names consumed", label, len(consumed))
    return consumed


def console_consumed(exports: list[str]) -> set[str]:
    """Console consumption via the sidecar method -> kernel mapping table."""
    consumed = {n for names in CONSOLE_METHOD_KERNEL_MAP.values() for n in names}
    stale = consumed - set(exports)
    if stale:
        logger.warning("Mapping table names not in current exports (stale?): %s", sorted(stale))
    logger.info("Console (mapping table): %d names consumed", len(consumed - stale))
    return consumed - stale


def measure(harness_root: str, consumers: list[tuple[str, str]], console_root: str | None, exports: list[str]) -> dict:
    per_consumer: dict[str, set[str]] = {}
    for repo, label in consumers:
        per_consumer[label] = scan_consumer(repo, label, exports, harness_root)
    if console_root:
        per_consumer[CONSUMER_CONSOLE] = console_consumed(exports)

    rows = []
    for name in exports:
        used_by = [label for label, names in per_consumer.items() if name in names]
        rows.append({"name": name, "consumers": used_by, "tier": "A" if used_by else "B"})
    adopted = sum(1 for r in rows if r["tier"] == "A")
    zero = [r["name"] for r in rows if r["tier"] == "B"]
    return {
        "date": datetime.date.today().isoformat(),
        "total_exports": len(exports),
        "adopted": adopted,
        "adoption_rate": round(adopted / len(exports), 4) if exports else 0.0,
        "target_rate": 0.80,
        "kpi_met": (adopted / len(exports) >= 0.80) if exports else False,
        "per_consumer": {label: sorted(names) for label, names in per_consumer.items()},
        "rows": rows,
        "zero_consumer_names": zero,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "---",
        "doc_id: fusion-bench/architecture",
        "product: fusion-bench",
        "class: platform",
        "entry: service",
        "audience: engineer",
        "status: draft",
        "version: 0.4.36",
        f"updated: {report['date']}",
        'owner: "@dahai"',
        "doc_type: architecture",
        'title: { zh: "fusion-harness 采用率快照", en: "fusion-harness adoption-rate snapshot" }',
        "source_of_truth:",
        "  - docs/adoption-rate-2026-11-19.json",
        "---",
        "",
        f"# fusion-harness adoption-rate snapshot ({report['date']})",
        "",
    ]
    lines += [
        f"- Exports: {report['total_exports']}  |  Adopted: {report['adopted']}  |  **Rate: {report['adoption_rate']:.1%}** (target {report['target_rate']:.0%}, {'met' if report['kpi_met'] else 'NOT met'})",
        f"- Zero-consumer names ({len(report['zero_consumer_names'])}): {', '.join(report['zero_consumer_names']) or '(none)'}",
        "",
        "| name | consumers | tier |",
        "|---|---|---|",
    ]
    for r in report["rows"]:
        lines.append(f"| {r['name']} | {', '.join(r['consumers']) or '-'} | {r['tier']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="fusion-harness adoption-rate metric (issue #52)")
    parser.add_argument("--harness-root", required=True, help="Path to the fusion-harness checkout")
    parser.add_argument("--consumer", action="append", default=[], help="Consumer repo path (repeatable; label=path)")
    parser.add_argument("--console-root", default="", help="Console repo path (consumption via mapping table)")
    parser.add_argument("--out-dir", default="docs", help="Snapshot output directory")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    consumers: list[tuple[str, str]] = []
    for spec in args.consumer:
        label, _, path = spec.partition("=")
        consumers.append((path or label, label if path else Path(label).name))

    exports = collect_exports(args.harness_root)
    console_root = args.console_root or None
    report = measure(args.harness_root, consumers, console_root, exports)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"adoption-rate-{report['date']}.json"
    md_path = out_dir / f"adoption-rate-{report['date']}.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(
        f"Adoption rate: {report['adoption_rate']:.1%} ({report['adopted']}/{report['total_exports']}, target {report['target_rate']:.0%} -> {'MET' if report['kpi_met'] else 'NOT MET'})"
    )
    print(f"Zero-consumer names ({len(report['zero_consumer_names'])}):")
    for name in report["zero_consumer_names"]:
        print(f"  - {name}")
    print(f"Snapshot: {json_path} + {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
