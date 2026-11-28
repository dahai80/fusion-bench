---
doc_id: fusion-bench/architecture
product: fusion-bench
class: platform
entry: service
audience: engineer
status: draft
doc_type: architecture
version: "1.0"
title: { zh: "校验器 fail-open 审计（#64）", en: "Validator fail-open audit (#64)" }
updated: 2026-11-27
owner: "@dahai"
source_of_truth:
  - fusion_bench/office_bench/validators.py
---

# Validator fail-open audit (issue #64, arXiv 2610.02142)

Per-check enumeration of the office-bench validators and their exposure to
the "keyword presence without real tool execution" failure mode.

## Structural validators (fusion_bench/office_bench/validators.py)

All validators grade **final workspace state** (a real file on disk), not
tool-call traces or reply text. A pass therefore always requires an actual
document mutation — a keyword-only reply with no file write scores 0 by
construction. The fail-open surface is narrower: *minimal-effort* mutations
that satisfy the structural check without doing the semantic task.

| check | pass condition | fail-open? | mitigation |
|---|---|---|---|
| xlsx `sheet:<name>` | sheet present in workbook.xml | requires real file mutation, but trivially satisfiable | documented floor |
| xlsx `!sheet:<name>` (forbidden) | forbidden sheet absent — fail-closed on unsolicited content | n/a (negative check) | task defs opt in |
| xlsx `formulas` (require) | ≥1 `<f>` cell **in the required sheet** | formula-in-other-sheet shortcut rejected (pinned: `TestValidatorAdversarial`) | strict mode also rejects constant numerics |
| xlsx `formulas` (strict) | formula present AND zero constant numerics in the sheet | cannot detect wrong cached `<v>` (structure, not math) | pinned as known floor; semantic grading needs an executor |
| docx `section:<s>` | substring in document text | title-only section passes (pinned: `TestValidatorAdversarial`) | known floor |
| docx `!section:<s>` (forbidden) | forbidden section absent | n/a (negative check) | task defs opt in |
| pptx `slides` | slide part count ≥ min | trivially satisfiable | documented floor |
| pptx `title:<t>` | substring across slide `<a:t>` runs | title-only slides pass | known floor |
| pptx `!title:<t>` (forbidden) | forbidden title absent | n/a (negative check) | task defs opt in |

## Negative probes (new, #64)

`NEGATIVE_PROBES` in tasks.py: two tasks whose correct behavior is **not**
to mutate the workspace (`noop-read-only-query`, `noop-no-op-request`).
Grading = byte-level workspace snapshot before vs after the episode; any
created/removed/modified file scores 0 (`over-trigger`), byte-identical
workspace scores 1.0 (`suppressed`). Reading documents via tools is
legitimate — only mutations count. Results stay out of the 32-task core
stats; summary arms report `negative_probes.suppression_rate`.

## Pair control

When two models score near-identically on a tool-use category, treat the
parity as real skill only if both pass the negative probes (suppression
rate ≥ the pair-control bar). Rationale: over-trigger is a documented
small-model failure mode (suppression as low as 0.09, arXiv 2610.02142),
so equal scores under a fail-open validator may be equal keyword fitting.
Enforced socially for now (report-reading rule), not gated in code — a
future gate can block `compare` verdicts on pairs with low suppression.
