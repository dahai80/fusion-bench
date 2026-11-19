"""Simulated-user interface for dual-control episodes (issue #51).

ScriptedUser is the default: a deterministic finite-state policy derived from
the task — zero tokens, fully offline, regression-stable. LLMUser is behind a
flag and falls back to the scripted policy on any error (tau2-style).
The SimulatedUser protocol is the HumanGate seat for harness-team consumers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from .generator import DualTask

logger = logging.getLogger(__name__)


@dataclass
class UserTurn:
    text: str
    done: bool = False  # scripted user signals episode end (e.g. after abort)


class SimulatedUser(Protocol):
    name: str

    def open(self, task: DualTask) -> UserTurn: ...

    def reply(self, task: DualTask, history: list[dict], world) -> UserTurn: ...


class ScriptedUser:
    """Finite-state policy: disclose facts only when the agent asks for them."""

    name = "scripted"

    def __init__(self):
        self._disclosed_refund = False
        self._confirmed = False
        self._disclosed_extras = 0

    def pending_extras(self, task: DualTask) -> int:
        """Extras not yet disclosed — the runner keeps the episode open for them."""
        return max(len(task.requirements) - 1 - self._disclosed_extras, 0)

    def open(self, task: DualTask) -> UserTurn:
        core = task.requirements[0]
        return UserTurn(f"Hi, I need help with my order. I'd like a {core.user_facts['wants']} please.")

    def reply(self, task: DualTask, history: list[dict], world) -> UserTurn:
        last_agent = ""
        for msg in reversed(history):
            if msg["role"] == "assistant":
                last_agent = msg["content"].lower()
                break
        core = task.requirements[0]
        facts = core.user_facts

        # Final word on agent DONE: disclose any pending extra requirement
        # before letting the episode end (tau2-style user confirmation).
        if "done" in last_agent:
            extras = list(task.requirements[1:])
            if self._disclosed_extras < len(extras):
                extra = extras[self._disclosed_extras]
                self._disclosed_extras += 1
                return UserTurn(f"Wait, one more thing: {extra.user_facts['also']}, please.")
            return UserTurn("Nothing else. Thank you!")

        # Disclose the refund amount when asked about the amount/order.
        if not self._disclosed_refund and any(
            k in last_agent for k in ["amount", "how much", "which order", "order id", "order number"]
        ):
            self._disclosed_refund = True
            return UserTurn(
                f"My order id is {facts['order_id']} and I paid {facts['amount']}. Please refund the full amount."
            )
        if not self._disclosed_refund:
            return UserTurn("Can you look up my order? I can give you the details.")

        # Confirm the refund when the agent asks for confirmation.
        if "refund" in last_agent and any(k in last_agent for k in ["confirm", "proceed", "sure", "ok", "issue"]):
            self._confirmed = True
            return UserTurn("Yes, I confirm the refund.")
        if "refund" in last_agent and "confirmed" not in last_agent and not self._confirmed:
            return UserTurn("Yes, please go ahead and refund the full amount.")

        # Extra requirements: disclose only after the refund is settled.
        if self._confirmed or "refund" in last_agent:
            extras = [r for r in task.requirements[1:]]
            if self._disclosed_extras < len(extras):
                extra = extras[self._disclosed_extras]
                self._disclosed_extras += 1
                return UserTurn(f"Also, {extra.user_facts['also']}, please.")
        return UserTurn("Is everything done? Thank you.")


class LLMUser:
    """LLM plays the user; scripted fallback on any error. Behind --llm-user."""

    name = "llm"

    def __init__(self, fallback: ScriptedUser | None = None):
        self.fallback = fallback or ScriptedUser()

    def _persona(self, task: DualTask) -> str:
        facts = "; ".join(str(f) for r in task.requirements for f in r.user_facts.values())
        return (
            "You are a customer contacting support. Stay in character, be brief.\n"
            f"Your hidden facts (disclose only when asked): {facts}\n"
            "Confirm requests politely when the agent states them correctly."
        )

    async def areply(self, task: DualTask, history: list[dict], world, client) -> UserTurn:
        from .runner import user_message

        messages = [{"role": "system", "content": self._persona(task)}] + user_message(history)
        try:
            turn = await client.chat(messages, max_tokens=128)
            if not turn.ok or not turn.text.strip():
                raise RuntimeError(turn.error or "empty user reply")
            return UserTurn(turn.text.strip())
        except Exception as e:
            logger.warning("LLMUser falling back to scripted policy: %s", e)
            return self.fallback.reply(task, history, world)


__all__ = ["SimulatedUser", "UserTurn", "ScriptedUser", "LLMUser"]
