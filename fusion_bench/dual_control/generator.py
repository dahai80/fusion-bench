"""Compositional dual-control task generator (issue #51).

Seeded sampling over a small requirement grammar. Each requirement pairs a
world mutation with the user facts the scripted user holds about it, so the
agent must both act correctly and coordinate with the user to learn the
missing arguments. End-state checks are pure predicates over the final world
state and the action ledger — deterministic, no judge model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .world import build_initial_state

logger = logging.getLogger(__name__)


@dataclass
class Requirement:
    action: str  # world action the agent must perform on the focal order
    target: dict  # expected end-state contribution, e.g. {"status": "refunded"}
    user_facts: dict  # facts the simulated user knows and can disclose


@dataclass
class DualTask:
    task_id: str
    seed: int
    n_requirements: int
    initial_state: dict
    requirements: list[Requirement]
    policy_rules: list[str] = field(default_factory=list)
    forbidden: list[dict] = field(default_factory=list)  # mutations that must NOT happen

    def system_prompt(self) -> str:
        rules = "\n".join(f"- {r}" for r in self.policy_rules) or "- (none)"
        return (
            "You are a customer-service agent. You share an order-management system with the user.\n"
            "Resolve the user's request. Available actions:\n"
            'get_order {"order_id"} | get_customer {"customer_id"} | update_order_status {"order_id","status"} | '
            'issue_refund {"order_id","amount"} | add_note {"order_id","note"}\n'
            'To call an action, reply with ONLY a JSON object: {"action": "<name>", "args": {...}}.\n'
            "To talk to the user, reply with plain text (no JSON).\n"
            "When the request is fully resolved, reply with ONLY: DONE\n"
            f"Policy rules:\n{rules}"
        )


def generate_task(seed: int, n_requirements: int = 1, n_distractors: int = 2) -> DualTask:
    state = build_initial_state(seed, n_distractors=n_distractors)
    focal = state["focal_order"]
    order = state["orders"][focal]
    requirements: list[Requirement] = []
    policy_rules: list[str] = []

    # Requirement 1 is always the refund core: the agent must learn the amount
    # from the user (coordination axis) before the mutation is possible.
    amount = round(order["paid"], 2)
    requirements.append(
        Requirement(
            action="issue_refund",
            target={"refund": amount},
            user_facts={"order_id": focal, "amount": amount, "wants": "refund"},
        )
    )
    policy_rules.append("A refund requires the exact amount confirmed by the user before issuing.")

    if n_requirements >= 2:
        status = "cancelled"
        requirements.append(
            Requirement(
                action="update_order_status",
                target={"status": status},
                user_facts={"also": f"set the order status to {status}"},
            )
        )
    if n_requirements >= 3:
        requirements.append(
            Requirement(
                action="add_note",
                target={"note_contains": "confirmed by user"},
                user_facts={"also": "note the resolution was confirmed"},
            )
        )

    forbidden = [{"action": "issue_refund", "check": "amount_exceeds_paid"}]
    task = DualTask(
        task_id=f"dc-{seed}-{n_requirements}req",
        seed=seed,
        n_requirements=n_requirements,
        initial_state=state,
        requirements=requirements,
        policy_rules=policy_rules,
        forbidden=forbidden,
    )
    logger.info("Generated task %s (%d requirements)", task.task_id, n_requirements)
    return task


def check_end_state(world, task: DualTask) -> tuple[bool, list[str]]:
    """Pure end-state check: required mutations present, forbidden ones absent."""
    focal = task.initial_state["focal_order"]
    order = world.orders.get(focal)
    if order is None:
        return False, [f"focal order {focal} missing from world"]
    failures: list[str] = []
    for req in task.requirements:
        if "refund" in req.target and abs(order["refund"] - req.target["refund"]) > 1e-6:
            failures.append(f"refund != {req.target['refund']} (got {order['refund']})")
        if "status" in req.target and order["status"] != req.target["status"]:
            failures.append(f"status != {req.target['status']} (got {order['status']})")
        if "note_contains" in req.target:
            joined = " ".join(order["notes"])
            if req.target["note_contains"] not in joined:
                failures.append(f"no note containing '{req.target['note_contains']}'")
    # Forbidden: any refund exceeding paid (ledger check, regardless of clamping)
    paid = task.initial_state["orders"][focal]["paid"]
    for entry in world.ledger:
        if entry.action == "issue_refund" and entry.ok and float(entry.args.get("amount", 0)) > paid + 1e-9:
            failures.append(f"forbidden: refund {entry.args.get('amount')} exceeds paid {paid}")
    return (len(failures) == 0), failures


__all__ = ["DualTask", "Requirement", "generate_task", "check_end_state"]
