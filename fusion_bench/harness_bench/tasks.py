"""Deterministic agent task suite for harness comparison (issue #48).

Each task is a small, fully offline file-manipulation job executed in a
throwaway sandbox workspace. Verification is deterministic (content checks,
no model judging) so scoring never depends on an LLM. Every task carries a
minimal-action reference trajectory used by the DetourBench-style delta
scoring in detour.py.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an agent working inside a small sandbox workspace.
Available tool: bash. You act by replying with ONE bash command inside a ```bash fenced block.
After each command you will see its combined stdout/stderr output.
When the task is fully complete, reply with exactly: DONE
Never run destructive commands outside the workspace."""


@dataclass
class HarnessTask:
    """One benchmark task with deterministic verifier and reference actions."""

    task_id: str
    instruction: str
    setup_files: dict[str, str] = field(default_factory=dict)
    # Canonical minimal action sequence (DetourBench reference trajectory).
    reference_actions: list[str] = field(default_factory=list)
    verifier: Callable[[Path], tuple[bool, str]] = lambda ws: (False, "no verifier")

    def materialize(self, workspace: Path) -> None:
        workspace.mkdir(parents=True, exist_ok=True)
        for rel, content in self.setup_files.items():
            path = workspace / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        logger.info("task %s materialized %d files in %s", self.task_id, len(self.setup_files), workspace)


def _read(workspace: Path, rel: str) -> str:
    return (workspace / rel).read_text(encoding="utf-8")


def _verify_typo(workspace: Path) -> tuple[bool, str]:
    text = _read(workspace, "greeting.txt")
    if "Helo" in text:
        return False, "typo 'Helo' still present"
    if "Hello world" in text:
        return True, "ok"
    return False, f"unexpected content: {text[:80]!r}"


def _verify_config(workspace: Path) -> tuple[bool, str]:
    try:
        cfg = json.loads(_read(workspace, "config.json"))
    except json.JSONDecodeError as e:
        return False, f"config.json invalid JSON: {e}"
    if cfg.get("version") == 1:
        return True, "ok"
    return False, f"version key missing or wrong: {cfg}"


def _verify_create(workspace: Path) -> tuple[bool, str]:
    path = workspace / "notes.md"
    if not path.exists():
        return False, "notes.md not created"
    if "harness bench" in path.read_text(encoding="utf-8"):
        return True, "ok"
    return False, "notes.md missing expected marker text"


def _verify_two_step(workspace: Path) -> tuple[bool, str]:
    ok_a = "alpha" in _read(workspace, "part_a.txt").lower()
    ok_b = "beta" in _read(workspace, "part_b.txt").lower()
    if ok_a and ok_b:
        return True, "ok"
    return False, f"part_a alpha={ok_a} part_b beta={ok_b}"


def _verify_sum(workspace: Path) -> tuple[bool, str]:
    path = workspace / "sum.txt"
    if not path.exists():
        return False, "sum.txt not created"
    if "391" in path.read_text(encoding="utf-8"):
        return True, "ok"
    return False, "sum.txt does not contain 391"


BUILTIN_TASKS: list[HarnessTask] = [
    HarnessTask(
        task_id="fix-typo",
        instruction="greeting.txt contains a typo. Fix it so it reads 'Hello world'.",
        setup_files={"greeting.txt": "Helo world\n"},
        reference_actions=["sed -i 's/Helo/Hello/' greeting.txt"],
        verifier=_verify_typo,
    ),
    HarnessTask(
        task_id="add-config-key",
        instruction="config.json is missing the version field. Add it with the integer value 1.",
        setup_files={"config.json": '{"name": "demo"}\n'},
        reference_actions=["edit config.json to add version: 1"],
        verifier=_verify_config,
    ),
    HarnessTask(
        task_id="create-notes",
        instruction="Create a file named notes.md containing the line 'harness bench'.",
        setup_files={},
        reference_actions=["echo 'harness bench' > notes.md"],
        verifier=_verify_create,
    ),
    HarnessTask(
        task_id="two-step-edit",
        instruction=(
            "part_a.txt must contain the word 'alpha' and part_b.txt must contain the word 'beta'. Edit both files."
        ),
        setup_files={"part_a.txt": "placeholder a\n", "part_b.txt": "placeholder b\n"},
        reference_actions=["write alpha into part_a.txt", "write beta into part_b.txt"],
        verifier=_verify_two_step,
    ),
    HarnessTask(
        task_id="compute-sum",
        instruction="Compute 17*23 and write only the numeric result to sum.txt.",
        setup_files={},
        reference_actions=["echo 391 > sum.txt"],
        verifier=_verify_sum,
    ),
]


def tasks_by_ids(ids: list[str] | None) -> list[HarnessTask]:
    if not ids:
        return list(BUILTIN_TASKS)
    known = {t.task_id: t for t in BUILTIN_TASKS}
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise ValueError(f"unknown harness-bench tasks: {unknown}; known: {sorted(known)}")
    return [known[i] for i in ids]
