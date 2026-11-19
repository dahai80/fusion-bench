"""Issue #51 — dual-control agent eval: world, generator, user sim, runner (offline)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fusion_bench.dual_control.generator import check_end_state, generate_task
from fusion_bench.dual_control.runner import parse_action, run_episode, run_suite, user_message
from fusion_bench.dual_control.user_sim import ScriptedUser
from fusion_bench.dual_control.world import build_initial_state, world_from_state


class TestWorld:
    def test_deterministic_initial_state(self):
        a = build_initial_state(seed=7)
        b = build_initial_state(seed=7)
        assert a == b

    def test_refund_and_status_mutations(self):
        state = build_initial_state(seed=1)
        world = world_from_state(state)
        focal = state["focal_order"]
        paid = world.orders[focal]["paid"]
        assert world.apply("agent", "issue_refund", {"order_id": focal, "amount": paid}).ok
        assert world.apply("agent", "update_order_status", {"order_id": focal, "status": "refunded"}).ok
        assert world.orders[focal]["refund"] == paid
        assert world.orders[focal]["status"] == "refunded"

    def test_refund_over_paid_rejected(self):
        state = build_initial_state(seed=1)
        world = world_from_state(state)
        focal = state["focal_order"]
        result = world.apply("agent", "issue_refund", {"order_id": focal, "amount": 99999.0})
        assert not result.ok
        assert world.orders[focal]["refund"] == 0.0
        assert world.ledger[-1].ok is False

    def test_unknown_action_and_bad_args(self):
        world = world_from_state(build_initial_state(seed=1))
        assert not world.apply("agent", "nuke_everything", {}).ok
        assert not world.apply("agent", "get_order", {"wrong_arg": 1}).ok

    def test_ledger_records_actor(self):
        world = world_from_state(build_initial_state(seed=1))
        world.apply("agent", "get_order", {"order_id": "o-2000"})
        world.apply("user", "get_order", {"order_id": "nope"})
        assert world.ledger[0].actor == "agent" and world.ledger[0].ok
        assert world.ledger[1].actor == "user" and not world.ledger[1].ok


class TestGenerator:
    def test_task_regenerable(self):
        a = generate_task(seed=11, n_requirements=2)
        b = generate_task(seed=11, n_requirements=2)
        assert a.task_id == b.task_id
        assert a.initial_state == b.initial_state
        assert [r.target for r in a.requirements] == [r.target for r in b.requirements]

    def test_requirement_count(self):
        assert len(generate_task(seed=1, n_requirements=1).requirements) == 1
        assert len(generate_task(seed=1, n_requirements=3).requirements) == 3

    def test_check_passes_on_satisfied_world(self):
        task = generate_task(seed=5, n_requirements=1)
        world = world_from_state(task.initial_state)
        focal = task.initial_state["focal_order"]
        amount = task.requirements[0].target["refund"]
        world.apply("agent", "issue_refund", {"order_id": focal, "amount": amount})
        ok, failures = check_end_state(world, task)
        assert ok and failures == []

    def test_check_fails_on_unsatisfied_world(self):
        task = generate_task(seed=5, n_requirements=1)
        world = world_from_state(task.initial_state)
        ok, failures = check_end_state(world, task)
        assert not ok and failures

    def test_check_flags_forbidden_refund(self):
        task = generate_task(seed=5, n_requirements=1)
        state = task.initial_state
        world = world_from_state(state)
        focal = state["focal_order"]
        over = state["orders"][focal]["paid"] + 10.0
        # Direct ledger manipulation emulates an over-refund slipping through.
        from fusion_bench.dual_control.world import LedgerEntry

        world.ledger.append(LedgerEntry("agent", "issue_refund", {"amount": over}, True, "ok"))
        ok, failures = check_end_state(world, task)
        assert not ok and any("forbidden" in f for f in failures)


class TestScriptedUser:
    def test_open_states_goal(self):
        task = generate_task(seed=3, n_requirements=2)
        turn = ScriptedUser().open(task)
        assert "refund" in turn.text

    def test_discloses_facts_when_asked(self):
        task = generate_task(seed=3, n_requirements=1)
        user = ScriptedUser()
        user.open(task)
        history = [{"role": "assistant", "content": "Which order and what amount?"}]
        reply = user.reply(task, history, None)
        assert task.requirements[0].user_facts["order_id"] in reply.text
        assert str(task.requirements[0].user_facts["amount"]) in reply.text

    def test_no_facts_before_ask(self):
        task = generate_task(seed=3, n_requirements=1)
        user = ScriptedUser()
        user.open(task)
        history = [{"role": "assistant", "content": "Hello, how can I help?"}]
        reply = user.reply(task, history, None)
        assert task.requirements[0].user_facts["order_id"] not in reply.text


class TestParseAction:
    def test_plain_text_is_none(self):
        assert parse_action("I'll look into that for you.") is None

    def test_json_block_parsed(self):
        action, args = parse_action('{"action": "get_order", "args": {"order_id": "o-2000"}}')
        assert action == "get_order" and args == {"order_id": "o-2000"}

    def test_json_embedded_in_text(self):
        action, args = parse_action('Sure. {"action": "add_note", "args": {"order_id": "o-1", "note": "x"}} done')
        assert action == "add_note" and args["note"] == "x"

    def test_invalid_json_is_none(self):
        assert parse_action('{"action": get_order}') is None

    def test_non_action_json_is_none(self):
        assert parse_action('{"answer": 42}') is None


def _mock_client(replies: list[str]):
    client = MagicMock()
    turns = []
    for text in replies:
        t = MagicMock()
        t.ok = True
        t.error = ""
        t.text = text
        t.prompt_tokens = 10
        t.completion_tokens = 5
        turns.append(t)
    client.chat = AsyncMock(side_effect=turns)
    return client


class TestRunner:
    async def test_perfect_episode_success(self):
        task = generate_task(seed=9, n_requirements=1)
        focal = task.initial_state["focal_order"]
        amount = task.requirements[0].target["refund"]
        client = _mock_client(
            [
                "Which order and what amount?",
                f'{{"action": "get_order", "args": {{"order_id": "{focal}"}}}}',
                f'{{"action": "issue_refund", "args": {{"order_id": "{focal}", "amount": {amount}}}}}',
                "The refund is complete. Is there anything else?",
                "DONE",
            ]
        )
        out = await run_episode(task, "m", client)
        assert out["success"] is True
        assert out["invalid_actions"] == 0
        assert out["done_declared"] is True
        assert out["tokens_in"] == 50 and out["tokens_out"] == 25

    async def test_do_nothing_episode_fails(self):
        task = generate_task(seed=9, n_requirements=1)
        client = _mock_client(["I can't help with that.", "DONE"])
        out = await run_episode(task, "m", client)
        assert out["success"] is False
        assert out["failures"]

    async def test_invalid_action_counted_not_applied(self):
        task = generate_task(seed=9, n_requirements=1)
        client = _mock_client(['{"action": "issue_refund", "args": {"order_id": "o-9999", "amount": 5}}', "DONE"])
        out = await run_episode(task, "m", client)
        assert out["invalid_actions"] == 1
        assert out["success"] is False

    async def test_max_turns_stop(self):
        task = generate_task(seed=9, n_requirements=1)
        client = MagicMock()
        t = MagicMock()
        t.ok = True
        t.error = ""
        t.text = "thinking..."
        t.prompt_tokens = 1
        t.completion_tokens = 1
        client.chat = AsyncMock(return_value=t)
        out = await run_episode(task, "m", client, max_turns=3)
        assert out["turns"] == 3 and out["success"] is False

    async def test_agent_failure_breaks_episode(self):
        task = generate_task(seed=9, n_requirements=1)
        client = MagicMock()
        t = MagicMock()
        t.ok = False
        t.error = "boom"
        client.chat = AsyncMock(return_value=t)
        out = await run_episode(task, "m", client)
        assert out["success"] is False and out["turns"] == 1

    async def test_user_message_filters_actors(self):
        history = [
            {"role": "user", "content": "a", "actor": "user"},
            {"role": "assistant", "content": "b", "actor": "agent"},
            {"role": "user", "content": "[system] x", "actor": "system"},
        ]
        assert [m["content"] for m in user_message(history)] == ["a", "b", "[system] x"]

    async def test_done_with_pending_extras_keeps_episode_open(self):
        task = generate_task(seed=9, n_requirements=2)
        focal = task.initial_state["focal_order"]
        amount = task.requirements[0].target["refund"]
        status = task.requirements[1].target["status"]
        client = _mock_client(
            [
                "Which order and what amount?",
                f'{{"action": "issue_refund", "args": {{"order_id": "{focal}", "amount": {amount}}}}}',
                "The refund is complete. DONE",
                f'{{"action": "update_order_status", "args": {{"order_id": "{focal}", "status": "{status}"}}}}',
                "Order cancelled as well. DONE",
            ]
        )
        out = await run_episode(task, "m", client)
        assert out["success"] is True
        assert out["done_declared"] is True

    async def test_run_suite_aggregates(self):
        task = generate_task(seed=4, n_requirements=1)
        focal = task.initial_state["focal_order"]
        amount = task.requirements[0].target["refund"]
        replies = [
            # seed 4: perfect
            "Which order and what amount?",
            f'{{"action": "issue_refund", "args": {{"order_id": "{focal}", "amount": {amount}}}}}',
            "Refund issued.",
            "DONE",
            # seed 5: never acts
            "Sorry, no.",
            "DONE",
        ]

        # run_suite drives episodes sequentially through one client
        client = MagicMock()
        turns = []
        for text in replies:
            t = MagicMock()
            t.ok = True
            t.error = ""
            t.text = text
            t.prompt_tokens = 1
            t.completion_tokens = 1
            turns.append(t)
        client.chat = AsyncMock(side_effect=turns)
        out = await run_suite("m", client, seeds=[4, 5])
        assert out["metrics"]["dual_episodes"] == 2.0
        assert out["metrics"]["dual_success_rate"] == 0.5
