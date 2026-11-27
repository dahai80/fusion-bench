---
doc_id: fusion-bench/architecture
product: fusion-bench
class: platform
entry: service
audience: engineer
status: draft
doc_type: architecture
version: "1.0"
title: { zh: "FusionOffice-Bench（#56）", en: "FusionOffice-Bench (#56)" }
updated: 2026-11-25
owner: "@dahai"
source_of_truth:
  - fusion_bench/office_bench
---

# Design — FusionOffice-Bench (issue #56)

## Intent

Office-domain eval gate for the fusion-trainer flywheel: the registry's 6
rounds are all code-repair by_type; office models cannot be promoted without
an office gate. Deliverable = versioned office testset + deterministic
validators + a runner that emits a fusion-eval-compatible summary.json the
existing `ft flywheel record` ingests unchanged.

## Goals / Non-goals

- 32 tasks across office_xlsx / office_docx / office_pptx (apps x steps
  difficulty axis, steps 1-3), file-level edit tasks, deterministic graders
- Validators reuse the fusion-trainer #90 implementations (same structural
  checks); provenance-marked vendored copy — fusion-trainer is not a
  fusion-bench dependency (not on PyPI, heavy import chain), so the three
  pure-stdlib OOXML validators are vendored with a keep-in-sync note
- Baseline run on the pinned local model, recorded via `ft flywheel record
  --baseline`
- Non-goals: rival arms (#53/#54 cover capability/security), rubric_judge
  (LLM judge, not deterministic), trainer code changes (read-only consumer)

## Approach

`fusion_bench/office_bench/`:

- `validators.py` — vendored #90 structural checks (xlsx: openable zip +
  required sheets + formula policy; docx: required sections; pptx: min
  slides + required titles), adapted to `validate(task_type, path, args) ->
  (score, detail)`; pure stdlib zipfile+ET, CI-testable
- `seedgen.py` — deterministic seed-file generation; office libs live in the
  repo-root venv (openpyxl / python-docx / python-pptx), so seeds are built
  by shelling a generated python snippet to that interpreter; CI (no
  root-venv) skips seed-dependent tests
- `tasks.py` — 32 task defs: id, task_type, app, steps, instruction, seed
  spec, result filename, validator args; instructions point the agent at
  `/Users/dahai/fusion/.venv/bin/python` for the office libs
- `runner.py` — FusionHarnessRunner (+RetryingClient, office SYSTEM_PROMPT
  variant reworded off the fusion-mlx#1665 crash path) per task; grade via
  validators; aggregate fusion-eval layout summary.json
  `{"run_id", "created_at", "models": {arm}, "arms": {arm: {total, passed,
  pass_rate, by_type}}}`

## Success criteria

- 32 tasks, by_type has all 3 office axes; offline tests green
- Live baseline run recorded: `ft flywheel record` exits 0, `ft flywheel
  status` shows the office baseline round in the registry
