---
doc_id: fusion-bench/durability-spec
product: fusion-bench
class: platform
entry: service
doc_type: architecture
title: { zh: "编排耐久性基准规范", en: "Orchestration Durability Benchmark Spec" }
audience: engineer
status: draft
version: 1
updated: 2026-11-28
owner: "@dahai"
source_of_truth:
  - fusion_bench/durability/metrics.py
---

# Orchestration Durability Benchmark (issue #70, plan ruling A6)

Public-benchmark position: `orchestration durability` — long-horizon survival of agent
workflows. Verified 2026-11-27: Factory.ai / Cursor / Cognition publish no long-horizon
survival metric; SWE-bench is saturated at low-80s. Fusion owns this metric.

## Data sources (real records only)

Published reports never carry synthetic-only numbers. Metrics are computed from:

1. **fusion-supervisor run history** — SQLite `runs` + `run_traces` tables
   (`fusion-supervisor/fsb_data.db`), read-only.
2. **fusion-cowork audit trails** — `~/.fusion-cowork/web/assets/*/audit.jsonl`
   digest chains (plan revisions with `prev_digest -> digest` links).
3. **fusion-cowork scheduled-task stats** — `~/.fusion-cowork/scheduled_tasks.json`
   run/fail counters (chaos-injection results land here via cowork#386).

A metric whose denominator is below the sufficiency floor is published as
`insufficient` (value `n/a`) — never estimated. The sufficiency floor is itself
published so third parties can audit the claim.

## Metric formulas

Implementation: `fusion_bench/durability/metrics.py` (single source of truth).

### 1. long_task_survival_rate

```
survival = |{runs : status ∈ terminal_ok}| / |{runs : status ∈ terminal_ok ∪ terminal_failed}|
terminal_ok     = {COMPLETED, SUCCEEDED, completed, succeeded, success}
terminal_failed = {FAILED, failed, ERROR, error}
```

### 2. failure_recovery_rate

```
recovery = |{runs : ∃ node trace with status ∈ failures ∧ run ∈ terminal_ok}|
         / |{runs : ∃ node trace with status ∈ failures}|
failures = {failed, error, crashed, timeout, killed}
```

Covers chaos-injection results (cowork#386 fault matrix): an injected node failure
counts as recovered when the run still reached a terminal-OK state.

### 3. checkpoint_restore_correctness

```
correctness = |{links : rev[N+1].prev_digest == rev[N].digest}| / |{links}|
links = consecutive digest-chain pairs in cowork audit trails (chronological,
both endpoints present)
```

A broken link means the checkpoint chain no longer replays — restore correctness.

### 4. hours_scale_completion_ratio

```
ratio = |{runs : wall ≥ 1h ∧ status ∈ terminal_ok}| / |{runs : wall ≥ 1h}|
wall = ended_at − started_at (ISO timestamps)
```

Runs shorter than 1h are out of scope for the hours-scale axis.

## Sufficiency floors

| metric | floor (min denominator) |
|---|---|
| long_task_survival_rate | 5 terminal runs |
| failure_recovery_rate | 5 failing runs |
| checkpoint_restore_correctness | 10 digest links |
| hours_scale_completion_ratio | 3 runs ≥ 1h |

## Reproducibility (acceptance criterion 3)

```bash
# export the published dataset from live sources
fusion-bench durability dataset --out bench/durability/dataset-v1.json
# produce the report
fusion-bench durability report --out bench/durability/
# third-party recompute gate (exit 1 on drift, tolerance 1e-9)
fusion-bench durability verify \
  --dataset bench/durability/dataset-v1.json \
  --report bench/durability/durability-report.json
```

The verification recomputes all four metrics from the dataset alone and diffs the
published report. Deterministic code paths make the tolerance effectively exact.

## Nightly

- **CI (public, recomputation gate)**: `.github/workflows/durability.yml` runs the
  verify command nightly on the committed dataset + report; drift fails the run.
- **Local (fresh records)**: `scripts/durability-nightly.sh` regenerates the report
  from live supervisor/cowork sources on the machine that owns the data, then runs
  the same verify gate before committing refreshed artifacts.

## Dataset provenance

`bench/durability/dataset-v1.json` is exported verbatim from the sources above
(no normalization beyond the record schema in `records.py`). The seed long-horizon
plan is the cowork#386 34-round delivery-pipeline acceptance; chaos-suite results
attach as supervisor run/trace records as that suite lands.
