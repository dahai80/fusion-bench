---
doc_id: fusion-bench/architecture
product: fusion-bench
class: platform
entry: service
audience: engineer
status: draft
version: 0.4.35
updated: 2026-11-19
owner: "@dahai"
doc_type: architecture
source_of_truth:
  - docs/design-dual-control-51.md
title: { zh: "双控智能体评测设计（tau2-bench 方法）", en: "Dual-control agent eval design (tau2-bench method)" }
---

# Dual-control agent eval (issue #51, tau2-bench method)

## Problem

fusion-bench measures single-actor runs. tau2-bench (arXiv:2506.07982) adds the
missing axis: the agent AND a simulated user both act on a shared world state
(Dec-POMDP framing). User-agent coordination becomes the tested capability, and
programmatically generated task families give regression power for harness
changes (compaction, approval, steering) beyond fixed task lists. Method is
general — this is NOT a port of the telecom domain.

## Architecture

```
DualControlRunner (runner.py)
  ├─ World (world.py)          shared, deterministic, seedable state
  ├─ SimulatedUser (user_sim.py)  scripted policy first; LLM user behind flag
  ├─ Agent (LLM via ModelClient, bench_client cache-bypass per #47)
  └─ TaskGenerator (generator.py)  compositional tasks + end-state checks
        ↓
DualControlExecutor (executors/dual_control_executor.py)  L4 plugin
        ↓
fusion-bench dual-control CLI (cli.py)
```

## Components

### World model (world.py)

Small deterministic "order management" world — method-generic entity/attribute
shape, one concrete family for v1:

- State: `customers{id:{name,tier}}`, `orders{id:{customer,status,items,refund,notes}}`
- Actions (registry, each returns ok/error + message):
  `get_order`, `update_order_status`, `issue_refund`, `add_note`, `get_customer`
- All mutations logged to an episode action ledger (who did what, when)
- Seedable: `World.from_seed(seed, task)` builds identical initial state every run

### Simulated user (user_sim.py)

`SimulatedUser` protocol: `reply(history, world) -> UserTurn`. Implementations:

1. **ScriptedUser** (default, deterministic): finite-state policy derived from
   the task — opens with the goal statement, answers agent questions from a
   scripted fact table, confirms/denies per policy rules, never improvises.
   Fully offline, zero tokens.
2. **LLMUser** (behind `--llm-user` flag): LLM plays the user with the task's
   persona + hidden facts in the system prompt; scripted fallback on error/timeout
   (tau2-style). Flag off by default — scripted user is the regression-stable arm.

### Task generator (generator.py)

Compositional, verifiable:

- Sample 1-3 requirements from a requirement grammar: each requirement =
  `(action, entity, target_state, user_facts)` — e.g. "order o-1001 must end
  status=refunded with refund=29.9, user knows order id + paid amount"
- Seeded sampling → task family: `task_id = dc-{seed}-{k}req`, regenerable
- End-state check: pure predicate over final world state + ledger
  (required mutations present, no forbidden mutations e.g. refund > paid)
- Difficulty knob: number of requirements, distractor entities, policy rules
  (e.g. "refund requires explicit user confirmation")

### Runner (runner.py)

Alternating turns on shared world:

1. User opens (goal statement) → agent sees transcript
2. Agent turn: either a natural-language reply OR an action block
   `{"action": ..., "args": {...}}` (JSON parsed leniently; malformed = invalid
   action, counted, no state change)
3. Action applied to world if permitted; user policy reacts to agent messages
4. Episode ends: agent declares `done`, max turns, or user aborts
5. Score: end-state check (primary), plus turns / invalid actions / actions
   count / token usage / wall time as diagnostics

Metrics: `dual_success_rate` (primary), `dual_turns_mean`,
`dual_invalid_actions_mean`, `dual_tokens_total`.

## Integration target

Harness team / HumanGate scenarios are the first consumers: the SimulatedUser
interface is exactly the HumanGate seat — a scripted deterministic user lets
harness changes (compaction, approval gates, steering) be regression-tested
without an LLM in the loop. Consumer interface: `SimulatedUser.reply()` +
`World` action registry, both importable standalone.

## Non-goals (v1)

- Telecom domain data (method only)
- Multi-user / multi-agent worlds
- LLM-judge of conversation quality (end-state checks are deterministic)

## Verification plan

- Offline tests: world determinism, scripted policy paths, generator
  composition + checks, runner loop with a mock agent (no network)
- Live: scripted-user episodes against a real fusion-mlx model @ 11434,
  cache bypassed; report to `benchmarks/results/dual-control/`
