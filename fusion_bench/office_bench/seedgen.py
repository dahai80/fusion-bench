"""Seed-file generation for office tasks (issue #56).

Office libraries (openpyxl / python-docx / python-pptx) live in the
repo-root venv, not the fusion-bench venv — seeds are built by executing each
task's seed snippet with that interpreter (cwd = workspace). Deterministic:
same snippet -> same seed bytes. CI without the root venv skips
seed-dependent tests.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT_PYTHON = Path.home() / "fusion" / ".venv" / "bin" / "python"


def root_python_available() -> bool:
    ok = ROOT_PYTHON.is_file()
    logger.info("root venv python %s: %s", ROOT_PYTHON, "available" if ok else "missing")
    return ok


def materialize_seeds(snippets: dict[str, str], workspace: Path) -> None:
    """Run every seed snippet (path -> python code) in the workspace."""
    workspace.mkdir(parents=True, exist_ok=True)
    if not root_python_available():
        raise RuntimeError(f"seed generation needs office libs in {ROOT_PYTHON}")
    for rel, code in snippets.items():
        target = workspace / rel
        if target.exists():
            target.unlink()
        proc = subprocess.run(
            [str(ROOT_PYTHON), "-c", code],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"seed snippet failed for {rel}: {proc.stderr[-300:]}")
        if not target.is_file():
            raise RuntimeError(f"seed snippet produced no file for {rel}")
        logger.info("seed generated: %s", target)
