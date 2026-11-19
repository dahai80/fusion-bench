"""Shared-state world model for dual-control episodes (issue #51).

Small, deterministic, seedable. The agent and the simulated user both act on
the same World instance; every mutation lands in an action ledger so the
end-state check can verify both what happened and who did it. Domain is a
minimal order-management family — the entity/attribute/action shape is the
general method, not telecom data.
"""

from __future__ import annotations

import copy
import logging
import random
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

STATUSES = ["open", "shipped", "delivered", "refunded", "cancelled"]

ACTION_NAMES = ["get_order", "get_customer", "update_order_status", "issue_refund", "add_note"]


@dataclass
class ActionResult:
    ok: bool
    message: str


@dataclass
class LedgerEntry:
    actor: str  # "agent" | "user"
    action: str
    args: dict
    ok: bool
    message: str


@dataclass
class World:
    customers: dict
    orders: dict
    ledger: list[LedgerEntry] = field(default_factory=list)

    def copy(self) -> World:
        return World(
            customers=copy.deepcopy(self.customers),
            orders=copy.deepcopy(self.orders),
            ledger=list(self.ledger),
        )

    def apply(self, actor: str, action: str, args: dict) -> ActionResult:
        handler = getattr(self, f"_do_{action}", None)
        if handler is None:
            logger.warning("World: unknown action '%s' from %s", action, actor)
            return self._record(actor, action, args, False, f"unknown action '{action}'")
        try:
            result = handler(**args)
        except TypeError as e:
            return self._record(actor, action, args, False, f"bad arguments: {e}")
        return self._record(actor, action, args, result.ok, result.message)

    def _record(self, actor: str, action: str, args: dict, ok: bool, message: str) -> ActionResult:
        self.ledger.append(LedgerEntry(actor=actor, action=action, args=dict(args), ok=ok, message=message))
        return ActionResult(ok=ok, message=message)

    # Read actions -----------------------------------------------------------

    def _do_get_order(self, order_id: str) -> ActionResult:
        order = self.orders.get(order_id)
        if order is None:
            return ActionResult(False, f"order '{order_id}' not found")
        return ActionResult(
            True, f"order {order_id}: status={order['status']} items={order['items']} refund={order['refund']}"
        )

    def _do_get_customer(self, customer_id: str) -> ActionResult:
        customer = self.customers.get(customer_id)
        if customer is None:
            return ActionResult(False, f"customer '{customer_id}' not found")
        return ActionResult(True, f"customer {customer_id}: {customer['name']} tier={customer['tier']}")

    # Write actions ----------------------------------------------------------

    def _do_update_order_status(self, order_id: str, status: str) -> ActionResult:
        order = self.orders.get(order_id)
        if order is None:
            return ActionResult(False, f"order '{order_id}' not found")
        if status not in STATUSES:
            return ActionResult(False, f"invalid status '{status}'")
        order["status"] = status
        logger.info("World: %s -> status=%s (%s)", order_id, status, order["status"])
        return ActionResult(True, f"order {order_id} status set to {status}")

    def _do_issue_refund(self, order_id: str, amount: float) -> ActionResult:
        order = self.orders.get(order_id)
        if order is None:
            return ActionResult(False, f"order '{order_id}' not found")
        if amount <= 0:
            return ActionResult(False, "refund amount must be positive")
        if amount > order["paid"] + 1e-9:
            return ActionResult(False, f"refund {amount} exceeds paid {order['paid']}")
        order["refund"] = round(order["refund"] + amount, 2)
        logger.info("World: refund %.2f on %s (total %.2f)", amount, order_id, order["refund"])
        return ActionResult(True, f"refund {amount} issued on order {order_id}")

    def _do_add_note(self, order_id: str, note: str) -> ActionResult:
        order = self.orders.get(order_id)
        if order is None:
            return ActionResult(False, f"order '{order_id}' not found")
        order["notes"].append(note)
        return ActionResult(True, f"note added to order {order_id}")


def build_initial_state(seed: int, n_distractors: int = 2) -> dict:
    """Deterministic seedable world with one focal order + distractors."""
    rng = random.Random(seed)
    customers = {}
    orders = {}
    for i in range(n_distractors + 1):
        cid = f"c-{1000 + i}"
        customers[cid] = {"name": f"customer-{i}", "tier": rng.choice(["basic", "gold", "vip"])}
        oid = f"o-{2000 + i}"
        paid = round(rng.uniform(10, 200), 2)
        orders[oid] = {
            "customer": cid,
            "status": rng.choice(["delivered", "shipped"]),
            "items": [f"item-{rng.randint(1, 99)}"],
            "paid": paid,
            "refund": 0.0,
            "notes": [],
        }
    focal = "o-2000"
    return {"customers": customers, "orders": orders, "focal_order": focal}


def world_from_state(state: dict) -> World:
    return World(customers=state["customers"], orders=state["orders"])


__all__ = [
    "World",
    "ActionResult",
    "LedgerEntry",
    "STATUSES",
    "ACTION_NAMES",
    "build_initial_state",
    "world_from_state",
]
