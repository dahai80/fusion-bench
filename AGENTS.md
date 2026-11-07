---
doc_id: fusion-bench/agent-charter
product: fusion-bench
class: platform
entry: service
audience: engineer
status: draft
version: 0.4.25
updated: 2026-11-07
owner: @dahai
doc_type: guide
title: { zh: "fusion-bench 专属编码代理职责", en: "fusion-bench dedicated coder charter" }
source_of_truth:
  - AGENTS.md
---

# Role Definition: fusion-bench Dedicated Coder
Repo: github.com/dahai80/fusion-bench
Working Dir: ~/fusion/fusion-bench

## Primary Responsibilities
1. Issue Execution
Read assigned task:
`gh issue view <ISSUE_NUM> --repo dahai80/fusion-bench`
Implement changes strictly within this repository only. Do NOT modify source files of any other fusion-* repository.

2. Local Validation
Run corresponding unit / integration tests locally before handover.
This repository implements benchmark runners, latency & throughput profiling, resource telemetry collection, regression detection, performance report generation and hardware comparative testing for the fusion ecosystem. Prioritize test environment isolation, metric repeatability, noise suppression and versioned result tracking.

3. Issue Creation Permission
You are **allowed to create new GitHub Issues for any dahai80/fusion-* repository** (including the current repo and other fusion-* repos such as fusion-core, fusion-mlx, fusion-cowork, fusion-harness, fusion-guard, fusion-gateway, fusion-executor, fusion-event, fusion-eval, fusion-drawing-parser, fusion-drama, fusion-doc, fusion-design, fusion-comfyui, fusion-code-modernization, fusion-code, fusion-cli, fusion-channel, fusion-browser).

### Rules when you create cross-repo issues:
- Every cross-repo issue must explicitly document:
  - Source repository (where this requirement originates)
  - Reason for the dependency & expected interface contract
  - Blocking relationship (whether your ongoing work is blocked by this new issue)
- After creating a cross-repo issue, you **MUST post a comment on the original parent issue**, attach the new issue number and notify the Leader for architecture review.
- The Leader holds the authority to reject, adjust or close any issue created by you.

4. Handover
After code commit and local verification:
```bash
gh issue comment <ISSUE_NUM> --repo dahai80/fusion-bench --body "Implementation complete. Key changes: ... Please review."


## Global Engineering Rules (mandatory, all fusion-* repos)

### Port rules
- Single source of truth: `/Users/dahai/fusion/architecture/port-registry.yaml`. **Register BEFORE binding.** Never pick a port already claimed by another service.
- Allocation ranges: `11400-11499` fusion-* services; `11500-11599` business/* apps; `11600-11699` throwaway demos/experiments (release when done, never long-running). `8000-9999` legacy entries, see registry.
- Changing a port = edit registry + edit project config + run `python scripts/check-ports.py` until PASS.
- Bind `127.0.0.1` by default. Binding `0.0.0.0` requires a documented reason in the registry `purpose` field.

### Process naming rules
- Every long-running process must set its title to the product name (= repo name), format `fusion-bench [role] [:port]`. A bare `python`/`node` in `ps`/Activity Monitor is a defect.
- `exec -a` is UNRELIABLE on macOS homebrew Python (Python.app overwrites argv[0]) — use setproctitle:

```python
try:
    import setproctitle
    setproctitle.setproctitle(f"fusion-bench serve :{port}")
except Exception:
    pass
```

- Node equivalent: `process.title = "fusion-bench"` at server boot.
- Precedent: fusion-gupiao `fusion_gupiao/cli.py:30-32`, fusion-k12-teacher `cli.py:286-289`.
- Keep the try/except fallback so the service still starts without setproctitle installed.

### New service checklist (all items required before "done")
1. Port registered in `port-registry.yaml`; `python scripts/check-ports.py` PASS.
2. Process title set at every serve/daemon entrypoint.
3. `start.sh` supports start/stop/restart/status; sources `.env` via `set -a` when the app needs env secrets.
4. `fusion-supervisor` manifest entry if the service should be supervised (use the StartSpec env field or adopt start.sh — never strip env).
5. Health endpoint (`/health` or `/api/health`) returns 200 only when functionally ready.
