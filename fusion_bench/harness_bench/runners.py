"""Agent-loop runners for harness comparison (issue #48).

Both runners speak the identical prompt protocol (tasks.SYSTEM_PROMPT,
bash-only action, DONE terminator) so the model sees the same interface and
the harness — the loop machinery — is the only variable:

- MiniSweRunner: mini-swe-agent style baseline (~100-line genre): linear
  append-only history, single bash tool, no admission machinery.
- FusionHarnessRunner: same loop but every LLM call is gated/metered by the
  fusion-harness kernel LLMFunnel and every tool call is admitted through
  ToolFunnel with a PermissionEngine + hard token budget.

fusion_harness is an optional pure-stdlib dependency; FusionHarnessRunner
reports availability via fusion_harness_importable().
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .model_client import ModelClient
from .tasks import SYSTEM_PROMPT, HarnessTask

logger = logging.getLogger(__name__)

MAX_OBS_CHARS = 2000
BASH_FENCE_RE = re.compile(r"```(?:bash|sh)?\s*\n(.*?)```", re.DOTALL)
DONE_RE = re.compile(r"^\s*DONE\s*$", re.MULTILINE)


def fusion_harness_importable() -> bool:
    try:
        import fusion_harness  # noqa: F401

        return True
    except Exception:
        return False


@dataclass
class HarnessRunResult:
    """Outcome of one harness run on one task."""

    task_id: str
    harness: str
    passed: bool = False
    verify_detail: str = ""
    steps: int = 0
    actions: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    llm_calls: int = 0
    cache_hits: int = 0
    wall_s: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "harness": self.harness,
            "passed": self.passed,
            "verify_detail": self.verify_detail,
            "steps": self.steps,
            "actions": self.actions,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "llm_calls": self.llm_calls,
            "cache_hits": self.cache_hits,
            "wall_s": round(self.wall_s, 4),
            "error": self.error,
        }


def extract_action(text: str) -> str | None:
    """Parse one model reply: bash command from a fence, or DONE."""
    if DONE_RE.search(text):
        return "DONE"
    match = BASH_FENCE_RE.search(text)
    if match:
        command = match.group(1).strip()
        return command or None
    return None


def run_bash(command: str, workspace: Path) -> tuple[str, bool]:
    """Execute one bash command inside the workspace; return (output, is_error)."""
    try:
        proc = subprocess.run(
            ["bash", "-c", command],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (proc.stdout + proc.stderr).strip()
        is_error = proc.returncode != 0
    except subprocess.TimeoutExpired:
        output = "ERROR: command timed out after 30s"
        is_error = True
    except Exception as e:
        output = f"ERROR: {e}"
        is_error = True
    if len(output) > MAX_OBS_CHARS:
        output = output[:MAX_OBS_CHARS] + "...[truncated]"
    return output, is_error


class BaseRunner:
    """Shared agent loop. Subclasses customize LLM gating and tool admission."""

    harness = "base"

    def __init__(self, client: ModelClient, max_steps: int = 8, system_prompt: str = ""):
        self.client = client
        self.max_steps = max_steps
        # Empty = the canonical #48 protocol prompt; callers may override for
        # engine-workaround variants (see compare_suite, fusion-mlx#1665).
        self.system_prompt = system_prompt or SYSTEM_PROMPT

    async def _llm(self, messages: list[dict]) -> tuple[str, int, int, bool]:
        turn = await self.client.chat(messages)
        return turn.text, turn.prompt_tokens, turn.completion_tokens, turn.cached

    async def _execute(self, command: str, workspace: Path) -> tuple[str, bool]:
        return run_bash(command, workspace)

    async def run(self, task: HarnessTask, workspace: Path) -> HarnessRunResult:
        result = HarnessRunResult(task_id=task.task_id, harness=self.harness)
        start = time.monotonic()
        task.materialize(workspace)
        messages: list[dict] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Task: {task.instruction}"},
        ]
        try:
            for step in range(1, self.max_steps + 1):
                text, tin, tout, cached = await self._llm(messages)
                result.llm_calls += 1
                result.tokens_in += tin
                result.tokens_out += tout
                result.cache_hits += 1 if cached else 0
                if not text:
                    logger.warning("harness %s empty reply task=%s step=%d", self.harness, task.task_id, step)
                action = extract_action(text)
                if action == "DONE":
                    break
                if action is None:
                    messages.append({"role": "assistant", "content": text or "(empty)"})
                    messages.append(
                        {"role": "user", "content": "No bash block found. Reply with ONE ```bash command or DONE."}
                    )
                    continue
                result.actions.append(action)
                result.steps += 1
                output, is_error = await self._execute(action, workspace)
                messages.append({"role": "assistant", "content": f"```bash\n{action}\n```"})
                messages.append({"role": "user", "content": output or "(no output)"})
            passed, detail = task.verifier(workspace)
            result.passed = passed
            result.verify_detail = detail
        except Exception as e:
            logger.exception("harness %s crashed task=%s", self.harness, task.task_id)
            result.error = str(e)
        finally:
            result.wall_s = time.monotonic() - start
        logger.info(
            "harness=%s task=%s passed=%s steps=%d tokens=%d/%d wall=%.2fs",
            self.harness,
            task.task_id,
            result.passed,
            result.steps,
            result.tokens_in,
            result.tokens_out,
            result.wall_s,
        )
        return result


class MiniSweRunner(BaseRunner):
    """Neutral baseline: mini-swe-agent genre — bash-only, linear history."""

    harness = "mini-swe"


class _SimpleBudget:
    """Duck-typed fusion-harness budget: hard cap on total tokens per run."""

    def __init__(self, max_tokens: int):
        self.max_tokens = max_tokens
        self.spent_tokens = 0

    def record_usage(self, prompt_tokens: int, completion_tokens: int, graph_id: str = "") -> None:
        self.spent_tokens += prompt_tokens + completion_tokens

    def is_exceeded(self, graph_id: str = "") -> bool:
        return self.spent_tokens >= self.max_tokens


class FusionHarnessRunner(BaseRunner):
    """Agent loop routed through the fusion-harness kernel (funnels + permissions + budget)."""

    harness = "fusion-harness"

    def __init__(self, client: ModelClient, max_steps: int = 8, budget_tokens: int = 100000, system_prompt: str = ""):
        super().__init__(client, max_steps, system_prompt=system_prompt)
        self.budget_tokens = budget_tokens
        # One runner instance = one run; the hard per-run budget (#A10 funnel
        # semantics) is a harness variable the baseline intentionally lacks.
        self._budget = _SimpleBudget(budget_tokens)

    async def run(self, task: HarnessTask, workspace: Path) -> HarnessRunResult:
        if not fusion_harness_importable():
            result = HarnessRunResult(task_id=task.task_id, harness=self.harness)
            result.error = "fusion_harness not installed (pip install -e fusion-harness)"
            logger.warning("fusion-harness arm skipped task=%s: module missing", task.task_id)
            return result
        return await super().run(task, workspace)

    async def _llm(self, messages: list[dict]) -> tuple[str, int, int, bool]:
        from fusion_harness.funnels import LLMFunnel

        funnel = LLMFunnel(budget_ref=self._budget)
        proceed, reason, _ = await funnel.pre_llm(
            ctx=None, node_label="harness-bench", model=self.client.model, messages=messages
        )
        if not proceed:
            logger.warning("fusion-harness LLM funnel stopped loop: %s", reason)
            return "", 0, 0, False
        text, tin, tout, cached = await super()._llm(messages)
        funnel.post_llm(
            ctx=None,
            node_label="harness-bench",
            model=self.client.model,
            usage={"prompt_tokens": tin, "completion_tokens": tout},
            content=text,
        )
        return text, tin, tout, cached

    async def _execute(self, command: str, workspace: Path) -> tuple[str, bool]:
        from fusion_harness.funnels import ToolFunnel
        from fusion_harness.permissions import PermissionEngine, PermissionMode

        funnel = ToolFunnel(permissions=PermissionEngine(mode=PermissionMode.BYPASS), budget_ref=self._budget)
        outcome = await funnel.admit(ctx=None, tool_name="bash", args={"command": command}, node_label="harness-bench")
        if not outcome.allowed:
            logger.warning("fusion-harness tool funnel denied command: %s (%s)", command, outcome.reason)
            return f"ERROR: tool admission denied: {outcome.reason or outcome.blocked_by}", True
        output, is_error = await super()._execute(command, workspace)
        await funnel.record_result(None, "bash", {"command": command}, output, is_error, node_label="harness-bench")
        return output, is_error
