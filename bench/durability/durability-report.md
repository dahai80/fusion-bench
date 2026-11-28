---
doc_id: fusion-bench/durability-report
product: fusion-bench
class: platform
entry: service
doc_type: guide
title: { zh: "编排耐久性基准报告", en: "Orchestration Durability Report" }
audience: engineer
status: draft
version: 1
updated: 2026-11-28
owner: "@dahai"
source_of_truth:
  - bench/durability/durability-report.json
  - fusion_bench/durability/report.py
---

# Orchestration durability report (A6, issue #70)

Generated: 2026-11-28T08:33:26.975234+00:00

Sources: 1 supervisor run(s), 7 cowork audit trail(s), 99 scheduled task(s). All numbers come from real run records; `insufficient` marks metrics whose denominator is below the published sufficiency floor — never estimated.

| metric | value | num/den | status |
|---|---|---|---|
| long_task_survival_rate | n/a | 0/0 | insufficient |
| failure_recovery_rate | n/a | 0/0 | insufficient |
| checkpoint_restore_correctness | n/a | 2/2 | insufficient |
| hours_scale_completion_ratio | n/a | 0/0 | insufficient |

Metric formulas and sufficiency floors: docs/durability-spec-70.md.
Recompute: `fusion-bench durability verify --dataset bench/durability/dataset-v1.json --report <this file's json>`.
