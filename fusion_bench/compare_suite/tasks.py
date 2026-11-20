"""Shared deterministic task set (issue #53).

Three small file-manipulation tasks with fixed texts and pure filesystem
verifiers. Every rival arm sees the same instructions; the action protocol
differs by framework (ours: bash fence, langgraph: native tool calls) but the
goal, setup files and verification are identical.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Reworded variant of the harness_bench protocol prompt. The #48 wording
# deterministically crashes the fusion-mlx burst scheduler at max_tokens 512
# (engine IndexError, upstream fusion-mlx#1665); this variant generates a
# different token path and is stable. Semantics identical.
SYSTEM_PROMPT = """You are an agent working in a small sandbox workspace.
Available tool: bash. Reply with ONE bash command inside a ```bash fenced block.
After each command you will see its combined stdout/stderr output.
When the task is fully complete, reply with exactly: DONE
Never run destructive commands outside the workspace."""


@dataclass
class SuiteTask:
    """One comparison task: fixed instruction, setup files, pure verifier."""

    task_id: str
    instruction: str
    setup_files: dict[str, str] = field(default_factory=dict)
    verifier: Callable[[Path], tuple[bool, str]] = lambda ws: (False, "no verifier")

    def materialize(self, workspace: Path) -> None:
        workspace.mkdir(parents=True, exist_ok=True)
        for rel, content in self.setup_files.items():
            path = workspace / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        logger.info("task %s materialized in %s", self.task_id, workspace)


def _read(ws: Path, rel: str) -> str:
    return (ws / rel).read_text(encoding="utf-8")


def _verify_typo(ws: Path) -> tuple[bool, str]:
    try:
        text = _read(ws, "greeting_fixed.txt")
    except OSError as e:
        return False, f"unreadable: {e}"
    if "Helo" in text:
        return False, "typo 'Helo' still present"
    if "Hello world" in text:
        return True, "ok"
    return False, f"unexpected content: {text[:80]!r}"


def _verify_config(ws: Path) -> tuple[bool, str]:
    try:
        data = json.loads(_read(ws, "config.json"))
    except (OSError, ValueError) as e:
        return False, f"bad config.json: {e}"
    if data.get("mode") == "fast" and data.get("retries") == 3:
        return True, "ok"
    return False, f"wrong keys/values: {data}"


WORDS_LINE = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu"
WORD_COUNT = len(WORDS_LINE.split())


def _verify_count(ws: Path) -> tuple[bool, str]:
    try:
        text = _read(ws, "count.txt").strip()
    except OSError as e:
        return False, f"unreadable: {e}"
    if text == str(WORD_COUNT):
        return True, "ok"
    return False, f"expected {WORD_COUNT}, got {text[:40]!r}"


SUITE_TASKS: list[SuiteTask] = [
    SuiteTask(
        task_id="typo-fix",
        instruction=(
            "The file greeting.txt contains a typo: 'Helo' should be 'Hello'. "
            "Write the corrected line to a NEW file named greeting_fixed.txt "
            "(keep greeting.txt unchanged). Do not use `sed -i`."
        ),
        setup_files={"greeting.txt": "Helo world, welcome to the demo app.\n"},
        verifier=_verify_typo,
    ),
    SuiteTask(
        task_id="config-write",
        instruction=(
            "Create a file named config.json in the current directory containing "
            "a JSON object with key mode set to the string fast and key retries "
            "set to the number 3."
        ),
        setup_files={},
        verifier=_verify_config,
    ),
    SuiteTask(
        task_id="count-words",
        instruction=(
            "The file words.txt contains one line of space-separated words. "
            "Count the words and write ONLY the number into count.txt."
        ),
        setup_files={"words.txt": WORDS_LINE + "\n"},
        verifier=_verify_count,
    ),
]


def verify_task(task: SuiteTask, workspace: Path) -> tuple[bool, str]:
    passed, detail = task.verifier(workspace)
    logger.info("verify task=%s passed=%s detail=%s", task.task_id, passed, detail)
    return passed, detail
