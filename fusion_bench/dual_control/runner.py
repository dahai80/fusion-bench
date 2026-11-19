"""Dual-control episode runner (issue #51).

Alternating turns: the LLM agent and the simulated user both act on the same
World. Agent turns are either plain text (talked to user) or a JSON action
block applied to the world. Episode ends on DONE, max turns, or user abort.
Scoring is the deterministic end-state check — no judge model.
"""

from __future__ import annotations

import json
import logging
import re
import time

from .generator import DualTask, check_end_state
from .user_sim import ScriptedUser, UserTurn
from .world import World, world_from_state

logger = logging.getLogger(__name__)

DONE_RE = re.compile(r"\bdone\b\.?\s*$", re.IGNORECASE)
JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def user_message(history: list[dict]) -> list[dict]:
    """Transcript restricted to user/assistant turns (the LLM chat view)."""
    return [{"role": m["role"], "content": m["content"]} for m in history if m["role"] in ("user", "assistant")]


def parse_action(text: str) -> tuple[str, dict] | None:
    """Extract an action block from an agent reply; None = plain message."""
    m = JSON_RE.search(text)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or "action" not in obj:
        return None
    return str(obj["action"]), dict(obj.get("args") or {})


async def run_episode(
    task: DualTask,
    model: str,
    client,
    max_turns: int = 12,
    sim_user=None,
) -> dict:
    """One episode: returns success, transcript stats, and the final world."""
    sim = sim_user or ScriptedUser()
    world: World = world_from_state(task.initial_state)
    history: list[dict] = []
    user_open: UserTurn = sim.open(task)
    history.append({"role": "user", "content": user_open.text, "actor": "user"})

    invalid_actions = 0
    action_count = 0
    tokens_in = 0
    tokens_out = 0
    start = time.monotonic()
    done = False
    turns = 0
    while turns < max_turns:
        turns += 1
        agent_reply = await client.chat(
            [{"role": "system", "content": task.system_prompt()}] + user_message(history),
            max_tokens=256,
        )
        if not agent_reply.ok:
            logger.warning("episode %s: agent call failed: %s", task.task_id, agent_reply.error)
            break
        tokens_in += agent_reply.prompt_tokens
        tokens_out += agent_reply.completion_tokens
        text = agent_reply.text.strip()
        history.append({"role": "assistant", "content": text, "actor": "agent"})

        if DONE_RE.search(text):
            # tau2-style: the user gets the final word on DONE — pending
            # undisclosed requirements keep the episode open.
            pending = getattr(sim, "pending_extras", lambda _t: 0)(task)
            user_turn = await _user_reply(sim, task, history, world, client)
            history.append({"role": "user", "content": user_turn.text, "actor": "user"})
            if pending > 0:
                continue
            done = True
            break
        parsed = parse_action(text)
        if parsed is not None:
            action, args = parsed
            result = world.apply("agent", action, args)
            action_count += 1
            if not result.ok:
                invalid_actions += 1
            history.append(
                {"role": "user", "content": f"[system] action {action}: {result.message}", "actor": "system"}
            )
            continue
        user_turn = await _user_reply(sim, task, history, world, client)
        history.append({"role": "user", "content": user_turn.text, "actor": "user"})
        if user_turn.done:
            break

    success, failures = check_end_state(world, task)
    out = {
        "task_id": task.task_id,
        "model": model,
        "success": success,
        "failures": failures,
        "turns": turns,
        "actions": action_count,
        "invalid_actions": invalid_actions,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "duration_s": round(time.monotonic() - start, 2),
        "done_declared": done,
    }
    logger.info(
        "Episode %s: success=%s turns=%d actions=%d invalid=%d",
        task.task_id,
        success,
        turns,
        action_count,
        invalid_actions,
    )
    return out


async def _user_reply(sim, task: DualTask, history: list[dict], world: World, client) -> UserTurn:
    from .user_sim import LLMUser

    if isinstance(sim, LLMUser):
        return await sim.areply(task, history, world, client)
    return sim.reply(task, history, world)


async def run_suite(
    model: str,
    client,
    seeds: list[int],
    n_requirements: int = 1,
    max_turns: int = 12,
    llm_user: bool = False,
) -> dict:
    """Run a task family; returns aggregate metrics + per-episode rows."""
    from .generator import generate_task
    from .user_sim import LLMUser

    episodes = []
    for seed in seeds:
        task = generate_task(seed, n_requirements=n_requirements)
        sim = LLMUser() if llm_user else ScriptedUser()
        episodes.append(await run_episode(task, model, client, max_turns=max_turns, sim_user=sim))
    total = len(episodes)
    success = sum(1 for e in episodes if e["success"])
    metrics = {
        "dual_success_rate": round(success / total, 4) if total else 0.0,
        "dual_turns_mean": round(sum(e["turns"] for e in episodes) / total, 2) if total else 0.0,
        "dual_invalid_actions_mean": round(sum(e["invalid_actions"] for e in episodes) / total, 2) if total else 0.0,
        "dual_tokens_total": float(sum(e["tokens_in"] + e["tokens_out"] for e in episodes)),
        "dual_episodes": float(total),
    }
    return {"model": model, "metrics": metrics, "episodes": episodes}


__all__ = ["run_episode", "run_suite", "parse_action", "user_message"]
