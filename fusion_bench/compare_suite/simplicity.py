"""Metric 6 — simplicity score (issue #53): cowork vs Dify.

Cowork measured live: runtime dep count from pyproject, LOC per node type
(python LOC in the nodes/ tree / registered node types), cold-start import
time. Dify is not installed — the cell uses the frozen structural numbers
from fusion-insight/docs/benchmark-targets-2026-11-20.md, flagged
`offline-frozen`, and its dynamic cells stay `unavailable`.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)

COWORK_ROOT = Path.home() / "fusion" / "fusion-cowork"
NODES_DIR = COWORK_ROOT / "fusion_cowork" / "nodes"

# Frozen 2026-11-20 in the targets doc (structural baseline v1, PyPI fetched
# live that day). Dynamic simplicity cells for dify stay unavailable.
DIFY_FROZEN = {
    "repo": "dify",
    "dep_count": None,
    "loc_per_node_type": None,
    "cold_start_s": None,
    "source": "offline-frozen: app distribution, not on PyPI; not installed locally",
}


def _cowork_dep_count() -> int:
    pyproject = COWORK_ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    deps = data.get("project", {}).get("dependencies", [])
    logger.info("cowork runtime deps: %d", len(deps))
    return len(deps)


def _count_loc(root: Path) -> int:
    total = 0
    for f in root.rglob("*.py"):
        try:
            total += sum(1 for line in f.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip())
        except OSError as e:
            logger.warning("unreadable %s: %s", f, e)
    return total


def _cowork_loc_per_node_type() -> tuple[float, int, int]:
    import re

    loc = _count_loc(NODES_DIR)
    pattern = re.compile(r"class\s+\w+\((?:.*)?BaseNode")
    node_types = 0
    for f in NODES_DIR.rglob("*.py"):
        node_types += len(pattern.findall(f.read_text(encoding="utf-8", errors="replace")))
    per = round(loc / node_types, 1) if node_types else 0.0
    logger.info("cowork nodes/ LOC=%d node classes=%d loc_per_node_file=%.1f", loc, node_types, per)
    return per, loc, node_types


def _cowork_cold_start() -> float:
    code = "import time; t=time.monotonic(); import fusion_cowork.engine; print(time.monotonic()-t)"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    cold = float(proc.stdout.strip().splitlines()[-1]) if proc.returncode == 0 else -1.0
    logger.info("cowork cold-start import: %.3fs (rc=%d)", cold, proc.returncode)
    return round(cold, 4)


def measure() -> dict:
    per, loc, node_files = _cowork_loc_per_node_type()
    cowork = {
        "repo": "fusion-cowork",
        "dep_count": _cowork_dep_count(),
        "loc_nodes_total": loc,
        "loc_per_node_file": per,
        "node_files": node_files,
        "cold_start_s": _cowork_cold_start(),
        "source": "measured live",
    }
    result = {"cowork": cowork, "dify": DIFY_FROZEN}
    logger.info("simplicity: %s", json.dumps(result))
    return result
