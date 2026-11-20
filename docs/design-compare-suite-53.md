---
doc_id: fusion-bench/architecture
product: fusion-bench
class: platform
entry: service
audience: engineer
status: draft
version: 0.4.37
updated: 2026-11-20
owner: "@dahai"
doc_type: architecture
title: { zh: "共享任务对比套件（issue #53）", en: "Shared-task comparison suite (issue #53)" }
source_of_truth:
  - fusion_bench/compare_suite/
  - docs/design-compare-suite-53.md
---

# Shared-task comparison suite (issue #53)

## Intent

Quarterly dynamic benchmark from fusion-insight/docs/benchmark-targets-2026-11-20.md
section 4: run the SAME deterministic task set against fusion-harness and rival
agent frameworks, same local model, and record completion rate, token cost,
HITL kill/resume reliability, post-compaction resume correctness, DAG node
recovery, and simplicity.

## Scope decisions

- Rival for metrics 1-4: **langgraph** (primary rival per targets doc). Only
  framework installed locally (langgraph 1.2.10 + langgraph-checkpoint 4.1.1 +
  langgraph-checkpoint-sqlite; PyPI latest 1.2.24 recorded in the freeze doc).
- crewai / dify / openhands: NOT installed locally. Per the no-network-LLM and
  no-fabrication rules their cells are reported as `unavailable` (visible
  error), never simulated. Metric 6 (Dify) uses the frozen structural numbers
  from the targets doc, flagged `offline-frozen`.
- Model: local fusion-mlx `:11434` only, `mlx-community--Qwen3.5-4B-MLX-4bit`
  pinned for the quarter, `X-Cache: bypass` on every request.
- Determinism: fixed task texts, fixed seeds, temperature 0.

## Design

Package `fusion_bench/compare_suite/`:

| module | role |
|---|---|
| `tasks.py` | 3 shared tasks (typo-fix, config-write, count-words), fixed texts, pure filesystem verifiers |
| `rival_chat.py` | `MlxChatModel(BaseChatModel)` — fusion-mlx /chat/completions with native tool_calls + usage accumulation |
| `langgraph_rival.py` | `create_react_agent` + `run_bash` tool + SqliteSaver; `run_task` / `run_hitl` / summary-node graph |
| `own_runner.py` | thin adapter over `harness_bench.FusionHarnessRunner` (metrics 1-2) and harness `HumanGate`+`CheckpointStore` / `Compactor` (metrics 3-4) |
| `hitl.py` | metric 3: subprocess workers, marker-file SIGKILL mid-wait, resume from durable store, success + wall time |
| `compaction.py` | metric 4: threshold-trigger compaction/summarization, recall probe after resume |
| `dag_recovery.py` | metric 5: cowork `WorkflowEngine` fault injection; dify cell `unavailable` |
| `simplicity.py` | metric 6: cowork dep count / LOC per node-type / cold-start; dify from frozen doc |
| `compare.py` | orchestrator -> `benchmarks/results/compare-suite/report.{json,md}` |

CLI: `fusion-bench compare-suite [--metrics completion,tokens,hitl,compaction,dag,simplicity] [--smoke] [--mlx-url]`.

## Approaches considered

1. **Reuse harness_bench loop for own side** (chosen): identical prompt
   protocol already exists (#48), FusionHarnessRunner carries usage accounting.
2. Reimplement own loop inside compare_suite: duplicated kernel wiring, no.
3. Run rivals as subprocess CLIs (crewai/openhands style): only needed for
   rivals that are CLI apps; langgraph is a library, in-process is exact.

## Non-goals

- No network LLM calls; no fabricating rival numbers.
- No bench-site schema change; results are local artifacts + issue comment.
- Baseline-doc v2 update lives in fusion-insight (upstream) — reported in the
  issue comment with ready-to-paste v2 table, not edited cross-repo.

## CI smoke

Offline pytest subset (1 task x 1 rival, fake chat model) runs in the normal
CI suite; live quarterly run is manual (`compare-suite --smoke` on :11434).
