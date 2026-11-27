---
doc_id: fusion-bench/changelog
product: fusion-bench
class: platform
entry: service
doc_type: changelog
title: { zh: "Fusion-Bench 变更日志", en: "Fusion-Bench Changelog" }
audience: engineer
status: draft
version: 0.4.44
updated: 2026-11-26
owner: "@dahai"
source_of_truth:
  - README.md
  - pyproject.toml
---

# Changelog

### v0.4.44 (2026-11-27)

- **Feat #64 — over-trigger suppression probes + fail-closed validator args (arXiv 2610.02142)**. Two additions guarding against keyword-fitting / over-trigger scoring in office-bench. (1) Negative probes: `NEGATIVE_PROBES` (two tasks, `noop-read-only-query` / `noop-no-op-request`) whose correct behavior is NOT to mutate the workspace — grading is a byte-level workspace snapshot before vs after the episode (created/removed/modified file = `over-trigger` score 0; byte-identical = `suppressed` 1.0; reading documents via tools is legitimate). Rows carry `negative_probe: true` and stay out of the 32-task core stats; summary arms report `negative_probes.{total,suppressed,suppression_rate}` for the pair-control rule (near-identical tool-use scores only count as real skill when both arms suppress). (2) `forbidden_*` validator args (`forbidden_sheets` / `forbidden_sections` / `forbidden_titles`) — fail-closed checks on unsolicited content, task defs opt in. Full per-check fail-open audit: `docs/validator-fail-open-audit-64.md`. Boundary report excludes negative-probe rows from capability inference. 48 office tests (930 collected).

### v0.4.43 (2026-11-27)

- **Feat #63 — capability-boundary report for office-bench runs (CUA-SEE goal-2 lite)**. New `fusion_bench/office_bench/boundary.py`: after each run, `write_boundary` aggregates results.json onto the (task_type, steps) difficulty grid, marks mixed cells (0 < passed < total) as the capability boundary, and derives probe targets — fully-passed cells adjacent to a mixed cell, with the failing task ids inside them as the next probe set. Deterministic aggregation, no model in the loop; harness-error / engine-unreachable rows excluded from capability inference (#60/#61 hygiene) and listed separately. Artifacts: `boundary.json` + `boundary.md` next to summary.json. Verified on the real rerun baseline (office-943d4ccd, 23/32 = 0.7188, committed bb407ba): boundary sits at docx steps=2 (2/4), xlsx steps=3 and pptx steps=3 — exactly the "where is the 4B agent's boundary" answer issue #63 asked for. Verifier-evolution (goal 3) started as adversarial tests pinning what the structural validators can and cannot be tricked into passing (formula-in-other-sheet rejected; formula-presence-without-correctness and title-only-section documented as known floors). Waves (goal 1) deliberately deferred. 34 office tests (916 collected).

### v0.4.42 (2026-11-27)

- **Feat — public watermark reference layer (PR #62)**. `fusion_bench/watermarks.py`: curated `WATERMARKS` table anchoring internal benchmark numbers to public state of the art — benchmark, optional model filter, score (fraction), source URL, publication date, note. Entries added only with a public source; per-model rows only for an exact model+benchmark pair (never estimated). Seeded: SWE-bench Verified frontier-agentic ~85% (swebench.com, 2026-02), Terminal-Bench 2.0 top-agents 60% (tbench.ai, 2026-01, arXiv 2505.16054), Claude Haiku 4.5 61.4% (vendor claim, 2025-10, upper band). `lookup()` keeps benchmark-level rows alongside matching model rows with name normalization; `compare()` returns the delta vs the best matching watermark with band verdicts (ahead / parity ≤5 pts / gap ≤20 pts / far-gap / no-watermark). CLI: `fusion-bench watermark [benchmark] [--score X] [--model M]`; `__main__` guard moved to the true end of `cli.py` so late-defined commands resolve. 10 tests (909 collected).

### v0.4.41 (2026-11-26)

- **Fix #61 — zero-token tasks classified as harness-error, not model failure**. A task where the model was never consulted (`tokens_in == 0 and tokens_out == 0`, no error — per-task HTTP starved in the engine queue under co-tenant saturation) is now scored `harness-error: model never responded` instead of running validators against an empty attempt (a queueing artifact reads as a capability signal, silently invalidating baselines). Per-task rows carry `harness_error: true`; `summary.json` arms report a `harness_errors` count so engine-saturation runs are detectable at a glance. Applies to both the initial attempt and the post-recovery re-run. 27 office tests (899 collected).

### v0.4.40 (2026-11-26)

- **Fix #59 — office-bench defaults to the gateway (`:11432`)**. Gateway is the single entry for downstream model traffic; `--direct-engine` (:11434) is opt-in for evals that need it, explicit `--mlx-url` still takes precedence. Safe on the gateway path: bench requests already carry `X-Cache: bypass` (v0.4.32).
- **Fix #60 — engine babysit is opt-in + bounded (`--babysit-engine`)**. `run_office` no longer restarts a shared engine by default: unreachable engine = bounded 3-probe check (a slow engine under co-tenant load is not a dead engine), warning, and harness-error rows (`run_error: "engine unreachable"`) with per-task checkpointing — the run completes and reports honestly instead of unilateral `fusion-sv restart`. Restarting (supervisor first, `start.sh` fallback) only with the flag; missing lifecycle binaries degrade to a warning, never a crash. Re-run-after-recovery only fires when the engine is actually reachable again. 25 office tests (897 collected).

### v0.4.39 (2026-11-26)

- **Feat #56 — FusionOffice-Bench office-domain eval (flywheel gate)**. New `fusion_bench/office_bench/` + `fusion-bench office-bench` CLI: 32 file-level office tasks across `office_xlsx` / `office_docx` / `office_pptx` (apps x steps difficulty axis, steps 1-3), graded by deterministic structural validators vendored from fusion-trainer#90 (`validators.py`, pure-stdlib zipfile + ElementTree over OOXML: xlsx openable-zip + required sheets + formula policy require/strict with openpyxl absolute-`/xl/` rels handling; docx required-section substrings; pptx min-slides + required titles — grading never calls a model). Seed files are generated deterministically by executing per-task python snippets under the repo-root venv (`seedgen.py`; office libs live there, CI without it skips seed-dependent tests). Runner = `harness_bench.FusionHarnessRunner` + `RetryingClient` + office SYSTEM_PROMPT variant reworded off the fusion-mlx#1665 crash path, per-task engine babysit (probe → `fusion-sv restart` → `start.sh` fallback) with no-LLM-traffic task re-run and per-task result checkpointing — survives the engine death flaps observed under fusion-lsa RULER co-tenancy. Summary emitted in the fusion-eval layout and ingested unchanged by `ft flywheel record`. Live baseline on the pinned model (Qwen3.5-4B @ :11434, direct, engine-keyed): **20/32 = 0.625** — office_xlsx 8/12 (0.667), office_docx 7/10 (0.700), office_pptx 5/10 (0.500); recorded as `office-baseline` in the fusion-trainer flywheel registry (`ft flywheel status` now shows all three office by_type axes; first non-code-repair domain in the registry). Report: `benchmarks/results/office-bench/{summary,results}.json`; design doc `docs/design-office-bench-56.md`. 20 tests (892 collected).


zh — 版本号以 `pyproject.toml` 为单一事实源，由 `scripts/release.sh` 保持 git tag、GitHub Release 与代码内版本一致。此处保留近期条目，完整历史见 [README.md](README.md) 的 Changelog 一节。en — the version in `pyproject.toml` is the single source of truth, kept aligned with the git tag, the GitHub Release and in-code versions by `scripts/release.sh`. This file keeps recent entries; the full history lives in the Changelog section of [README.md](README.md).

## v0.4.38 (2026-11-20)

- Feat #54: adversarial injection-resistance track for the comparison suite (AgentDojo shape, arXiv:2406.13352) — 7th `adversarial` metric in `fusion-bench compare-suite`. Versioned YAML corpus at `benchmarks/testsets/compare-suite-attacks/` (10 benign/attack pairs, 8 vectors: direct-instruction, fake-system-message, destructive-instruction x2, urgent-tone, fake-tool-output, split-instruction, quoted-note, hidden-comment, data-embedded); the loader composes the injected instruction into the named setup file at materialization so the corpus files stay benign-only and declarative — new injections need no code change. Benign checks and ASR (attack-success) detectors are data specs (`file_exists` / `file_absent` / `file_contains`) evaluated on the final workspace state only — grading never calls a model (E2 discipline); the loader rejects invalid specs, shared benign/ASR paths, and injections naming unknown files. Both arms run the identical pinned model (Qwen3.5-4B @ :11434, `X-Cache: bypass`): ours = `FusionHarnessRunner`, rival = langgraph `create_react_agent`; report = per-case utility/attack table + per-arm attack-success-rate and utility-rate (a defense that kills utility is not a defense). Live quarterly v2 numbers on the pinned model: fusion-harness **ASR 0.0 / utility 0.6**, langgraph **ASR 0.0 / utility 0.8** — neither arm executed any injected action this quarter (the 4B model refused all 10 vectors; the axes that discriminate here are utility under injection, not ASR), full per-case table in `benchmarks/results/compare-suite-adversarial/report.{json,md}`. The rival arm was executed case-by-case with engine health probes + restarts between cases because sustained multi-episode agent traffic deterministically wedges fusion-mlx 0.10.67 (upstream fusion-mlx#1665); the own arm ran the full sweep in one process. One corpus design rule learned live: benign instructions must be position-independent ("the line that starts with Ship", not "the LAST line") — appending the injection must not make the benign task undecidable. Corpus validation + detector tests (10 new, 872 collected).

## v0.4.37 (2026-11-20)

- Feat #53: shared-task comparison suite vs agent frameworks (quarterly dynamic benchmark, fusion-insight baseline doc section 4) — new `fusion_bench/compare_suite/` + `fusion-bench compare-suite` CLI (6 selectable metrics, `--smoke` = 1 task / 1 rival). One deterministic 3-task suite (typo-fix / config-write / count-words, fixed texts, pure filesystem verifiers) runs against two arms on the identical pinned model (`mlx-community--Qwen3.5-4B-MLX-4bit` @ :11434, `X-Cache: bypass` on every request): ours = `harness_bench.FusionHarnessRunner` (kernel-routed loop, #48), rival = langgraph `create_react_agent` with a minimal `BaseChatModel` over fusion-mlx (native tool_calls, provider-side usage accounting — token cost never from framework numbers). Metric 3 (HITL kill -9 mid-wait -> resume): subprocess fault injection on both checkpoint machineries — harness `HumanGate` (persistent queue JSON) vs langgraph `interrupt()` + `SqliteSaver`; both resumed 1/1. Metric 4 (post-compaction recall): deterministic probe transcript — harness `Compactor` keeps the pinned goal (score 1.0) while the rival extractive summary drops it (0.5). Metric 5 (DAG node recovery): cowork `WorkflowEngine` recovers from 2 injected transient failures on attempt 3 (business-failure retry needs `retry_on_business_failure`, cowork #182); Dify cell reports `unavailable` (not installed locally — never simulated). Metric 6 (simplicity): cowork measured live (11 runtime deps, 178.9 LOC per node class, 0.226s cold-start import); Dify cell uses the frozen structural numbers, flagged `offline-frozen`. Rival arm hardened with retry/backoff after diagnosing an upstream fusion-mlx 0.10.67 crash (burst-scheduler `IndexError` under sustained agent traffic, prompt- and load-dependent; repro added to fusion-mlx#1665) — a reworded protocol prompt variant (`compare_suite.tasks.SYSTEM_PROMPT`) plus `BaseRunner(system_prompt=...)` keeps the suite off the crashing token path, but the engine still wedges under sustained loops, so the quarterly completion/tokens cells are **partial** (own arm 2/3 tasks, 1435.5 tokens/completed task from a degraded run; 1-task smoke passed 1/1 on both arms) and the rival sustained numbers are deferred until the engine fix. Two latent suite-side bugs fixed: `adoption_rate.py` leaked the fixture checkout into `sys.path`/`sys.modules` (cross-file test pollution, pre-existing) and its render test asserted the pre-delivered-rate format. New optional extra `rival` (langgraph + langgraph-checkpoint-sqlite); langgraph pinned 1.2.10 (PyPI latest 1.2.24 recorded in the freeze doc). Report artifacts: `benchmarks/results/compare-suite/report.{json,md}` (workspaces cleaned post-run). Design doc `docs/design-compare-suite-53.md`. 17 tests (862 collected).

## v0.4.36 (2026-11-19)

- Feat #52: adoption-rate metric for the fusion-harness public API (G1 gate of the harness v1.0 product definition) — `scripts/adoption_rate.py`. Walks the fusion-harness root `__all__` exports, greps consumer checkouts (agent-studio, cowork) for `fusion_harness` import clauses (multiline root + submodule forms) and attribute refs, resolves indirect consumption via `from fusion_harness.<mod> import *` shims to the submodule public surface, counts the console through a hand-maintained sidecar method→kernel-call mapping table (stale entries dropped with a warning), and strips Python comments via tokenize so doc/comment name mentions never count. Tier A = consumed (per the fusion-insight API stability policy), tier B = zero consumers; output = JSON + markdown snapshot committed to `docs/adoption-rate-YYYY-MM-DD.{json,md}` with the rate, KPI target line (0.80) and the zero-consumer name list that drives the next wiring issue. Tests/mutants dirs excluded from consumer scans; module cache purged between checkouts. First snapshot (2026-11-19, exports 186): rate **38.2%** (71/186, target NOT met), 115 zero-consumer names; mechanism-level dormant = memory_link (3 names), destructive_gate (`TOOL_DESTRUCTIVE_TABLE`), artifact_scan tail (`ScanReport`, `stamp_untrusted`) — json_repair and human_gate show wired (cowork #554 / AS #756 landed after the manual audit). Runtime ~2s (< 1 min). 14 tests (845 collected).

## v0.4.35 (2026-11-19)

- Feat #51: dual-control agent eval (tau2-bench method, arXiv:2506.07982) — agent AND simulated user acting on a shared deterministic world state. New `fusion_bench/dual_control/`: seedable order-management world (5-action registry + per-actor action ledger), `SimulatedUser` protocol (ScriptedUser finite-state policy default, zero tokens; LLMUser behind `--llm-user` with scripted fallback), seeded compositional task generator (1-3 requirements; the agent must learn the refund amount from the user before the mutation is possible — coordination is the tested axis), and pure end-state checks over final world + ledger (forbidden-mutation detection, no judge model). Runner alternates turns; agent replies are either JSON action blocks (parsed leniently, malformed counted invalid, never applied) or plain text; on agent DONE the user gets the final word — pending undisclosed requirements keep the episode open (two live-run defects found and fixed: anchored DONE regex missed "…complete. DONE", and pending-extras was checked after the user already consumed the disclosure). Executor plugin `dual-control` (L4) + CLI `fusion-bench dual-control`. Design doc: `docs/design-dual-control-51.md`. Integration target: harness team / HumanGate scenarios — the SimulatedUser interface is the HumanGate seat, a deterministic scripted user lets harness changes be regression-tested without an LLM in the loop. Live @ 11434 (cache bypassed): Qwen3.5-4B 3/3 on 1-req and 3/3 on 2-req families (turns ~10-12 on 2-req); Qwen3-0.6B 0/3 with 2.33 invalid actions/episode — the axis discriminates. 26 tests (831 collected).

## v0.4.34 (2026-11-19)

- Feat #49: golden eval set from production traffic + regression gate (flywheel Loop B). New `fusion_bench/golden/` package: (1) versioned golden-case JSONL (`benchmarks/golden/golden-cases-v1.jsonl`, schema header, 55 cases / 10 categories incl. 5 failure cases) ingested from ops JSONL exports — never touches the upstream fusion_ops DB; (2) privacy gate at ingest (desensitized OR opted_in, else dropped and counted) + PII regex backstop (cn_mobile/email/cn_id_card/bank_card/ipv4, masked findings), enforced again in CI by a new `pii-scan` job that fails the build on any hit in `benchmarks/golden/`; (3) stratified sampling (per-category cap, failure cases bypass the cap); (4) deterministic per-case scoring with three match modes — `contains` (normalized substring), `keywords` (SQL/code markers), `nontrivial` (open-ended behavioral minimum) — because behavioral expectations like "输出一条可直接执行的 SQL 语句" are not literal substrings; (5) regression gate via BaselineStore (`golden-gate`/L1): pass-rate drop beyond threshold (default 5 pts) → verdict `blocked` + exit 1, `--update-baseline` re-arms; (6) top-10 scenario coverage KPI (target 0.80) from the ops category histogram. CLI: `fusion-bench golden ingest|scan|run|coverage`. Golden runs default to direct fusion-mlx `:11434` — the `:11432` gateway serves cached completions and would corrupt gate results. Verified live on `mlx-community--Qwen3-0.6B-4bit` @ 11434 (cache bypassed): baseline 54/55 = 0.9818 saved; deliberately broken change (`--max-tokens 1`) → 0.0, drop 98.18 pts > 5.0 → GATE BLOCKED, exit 1; coverage KPI 1.0 ≥ 0.80 met. 27 tests in `tests/test_golden.py` (805 collected).

## v0.4.33 (2026-11-18)

- Feat #48: same-model harness comparison benchmark (harness-bench genre, insight axis N5/A12) — `fusion_bench/harness_bench/` + `fusion-bench harness-bench` CLI + `harness-bench` executor plugin (L4). One deterministic offline task suite (5 sandbox file tasks, content verifiers, minimal-action reference trajectories) runs against two harnesses driving the identical fusion-mlx model: `mini-swe` (neutral bash-only baseline, linear append-only history) and `fusion-harness` (loop routed through the kernel: `LLMFunnel` gating/metering, `ToolFunnel` + `PermissionEngine` tool admission, hard per-run token budget). Metrics per task x harness: success rate, tokens in/out, cache hit rate (`X-Cache` provenance, bypass always on per #47), wall time, cost (price per Mtok configurable), and DetourBench-style trajectory delta (detours + one-step misses vs reference). Report artifact: per-task harness x metric table + per-run cost table (`benchmarks/results/harness-comparison/report.{json,md}`). `fusion_harness` is an optional pure-stdlib dependency (arm skips with an explicit error when absent). Live run on `mlx-community--Qwen3.5-4B-MLX-4bit` @ 11434: 5/5 success on both harnesses, cache hit rate 0.00, detours 18 / one-step misses 2. 12 new tests (778 collected).

## v0.4.32 (2026-11-18)

- Feat #47: dual-metric acceptance reporting + cache-proof bench requests. (1) Every model-inference request carries `X-Cache: bypass` via `engine/bench_http.bench_client` (12 call sites: adapter, SPS tuner, benchmark runner, 8 executors) — fusion-mlx force-caches non-streaming T=0 completions keyed on the full request fingerprint, so a repeated-prompt bench measured the cache, not the model. (2) `reporter/acceptance.py` splits baseline-vs-candidate deltas into elicitation (tasks baseline already scored on that improved) and expansion (tasks baseline scored 0 on that now pass) — never blended; regression reported separately; wired into the `compare --baseline` retention diff. Verified live: identical prompt twice without the header → 2nd response 0.017s `X-Cache: HIT`; with bypass → 2.59s / 1.36s fresh inference. 9 new tests (766 collected).

## v0.4.31 (2026-11-16)

- CI retrofit per fusion#2 checklist (issue #45, PR #46): `concurrency` group by ref with `cancel-in-progress`, docs-only `paths-ignore` (`**.md`, `docs/`, `bench-site/`, `benchmarks/results/`); assessments recorded in the PR — dependency cache already present, sharding + nightly tier not needed (full suite ~2 min per PR). CI-only change, no runtime code.

## v0.4.30 (2026-11-13)

- Feat #44: programmatic per-item scoring — `POST /api/v1/score` (single + `items` batch form), synchronous, no task record or trace write. Deterministic match (normalized equality, substring fallback) mirroring the lm-eval task runner; optional `params.extract` (boxed / last_number) for math completions; ground truth from explicit `expected`, `params.expected`, or the task's lm-eval dataset (prompt-matched, in-process cache). Built for fusion-trainer GRPO reward callbacks (sub-second, no task poll). 16 new tests (757 collected).

## v0.4.29 (2026-11-12)

- Feat #43 AC3: bench-site rendering of the SPS sweep table — `fusion_bench/sps/report.py` maps one sweep profile onto the bench-site `benchmarks` schema (one row per width x batch candidate, `benchmark_type="sps"`, `metric_name=median_tok_s_w{W}_b{B}`, full provenance + best table in `detail` JSON). CLI: `fusion-bench sps tune --submit` and new `fusion-bench sps submit --profile <path>`; bench-site `/benchmarks` filter gains an SPS option. 741 tests collected.

## v0.4.28 (2026-11-12)

- Feat #43 follow-through after fusion-mlx#1528 shipped (v0.10.59): SPS tuner verifies per-request width application via the engine's response echo (`width_applied_rate` per candidate, `engine_spec_support: verified|unverified`), parses acceptance length from `/stats` `spec_decode` counters (`/v1/metrics` fallback), default widths 1,2,4 per engine range. Live sweep on 0.10.55 correctly detects unapplied widths.

## v0.4.27 (2026-11-11)

- Feat #43: SPS speculative-decoding budget tuning — `fusion_bench/sps/` (JSONL prefix loader, width x batch-size sweep, `fusion-bench.sps/v1` profile with chip/RAM/model/digest provenance) + `fusion-bench sps tune` / `sps check`. Median tokens/wall-time over warm repeats; width axis rides the request body pending per-request spec support (fusion-mlx#1528). Docs `docs/sps-tuning.md`; live sample `docs/baselines/sps-live-sample.json`.

## v0.4.26 (2026-11-07)

- Docs: fusion docs-system v1.1 contract (PR #42) — hardened validator `ci/validate_docs.py` (12-key frontmatter, LINK-BROKEN checks), six Tier 0/1 docs + two guides + `CHANGELOG.md`, `docs.yml` CI workflow; follow-up fix unblocked the lint and docs-validate jobs. 19 docs scanned, 0 errors / 0 warnings. No runtime changes.

## v0.4.25 (2026-11-06)

- Feat #41: SxS double-blind judge REST surface — `POST /api/v1/judges/sxs/run` (winner, per-criterion 1-5 scores, averages, rationale, slot `position_map`, optional persist) and `GET /api/v1/judges/sxs/runs`; SQLite store `~/.fusion-bench/sxs_runs.db`; routes behind the fail-closed tenant middleware; persisted rows always store the TRUE winner. Verified live against fusion-mlx `mlx-community--Qwen3-0.6B-4bit`; 727-test suite green.

## v0.4.24 (2026-11-06)

- Feat #40: backend-abstracted inference profiler (`engine/profiler.py` + `fusion-bench profile`). Unified schema `fusion-bench.profiler/v1` with a mandatory `backend` key; engine-side vs agent-side latency keys never merged; lightweight mode default, full-trace opt-in and off in CI. Sample outputs under `docs/baselines/`.

## v0.4.23 / v0.4.22 (2026-11-05)

- Feat #39: web surface for judges, baselines, schedules and approvals (Judges / Baselines / Ops pages, bilingual copy), then backup/restore + audit logs in the Ops page (`POST /api/v1/system/backup`, `GET /api/v1/system/audit-logs`), admin-gated.

## v0.4.21 / v0.4.20 (2026-11-03)

- Fix #38: module API 401 — fetch base now derives from `window.location.pathname` for the `/shell/fusion-bench/` sub-path; tasks-page model dropdown over `GET /api/v1/models`; manifest upstream corrected from the dev-only vite port to `http://127.0.0.1:11467`; shell-module auth via `FUSION_BENCH_SHELL_API_KEY` with a synthetic `shell` tenant; `web/dist` mounted by the FastAPI app (`FUSION_BENCH_DISABLE_UI=1` opts out).

## v0.4.19 (2026-11-03)

- Fix: persist union-web shell registration across reboots — `start.sh` defaults `FUSION_SHELL_GATEWAY_URL=http://127.0.0.1:11432` and resolves the gateway admin key from the gateway's own config (`FUSION_GATEWAY_CONFIG` / `FUSION_ADMIN_KEY` overrides).

## v0.4.18 (2026-11-02)

- Feat #38: shell self-registration (`shell_registry.py`) — manifest POST on lifespan start, 15s heartbeat, dynamic upstream registration so the gateway proxies `/shell/fusion-bench/` without static config; env-gated, off by default.

## v0.4.17 (2026-10-31)

- Fix #37: relaxed the fusion-core pin to `>=0.9.0` so workspace editable installs are not clobbered by a stale git reference.

## v0.4.16 (2026-10-30)

- Feat #36: `start.sh` register-then-start port-registry self-check — refuse on unregistered port, `FUSION_SKIP_REGISTRY_CHECK=1` bypass, missing registry file warns only.

## v0.4.15 (2026-10-28)

- Fix #34/#35: process title via `fusion_core.proc.set_process_title` (`fusion-bench serve :<port>`); adopted `fusion_core.config.client_key()` key resolution (`FUSION_CLIENT_KEY` → `FUSION_MLX_API_KEY` → `MLX_API_KEY` chain), removed hardcoded dev fallbacks.

## v0.4.14 (2026-10-27)

- Fix #33: re-vendored `@fusion/web-sdk` at upstream v0.1.2 (host error predicate, cached-sync theme state) plus the local `?embedded=1` deep-link fix.

## v0.4.13 (2026-10-26)

- Feat #32: Arabic/multilingual evaluation suite — translation (BLEU/chrF via sacrebleu), RTL integrity, understanding, STT roundtrip (auto-skip), committed testsets under `benchmarks/testsets/`; upstream issues filed for fusion-mlx language metadata and gateway language-aware routing.

## v0.4.12 (2026-10-26)

- Fix #30/#31: test-count drift guard (`scripts/check_test_count.py` in CI); laya executor routes through the gateway by default, direct-MLX is explicit opt-in recorded in result meta.

## v0.4.11 / v0.4.10 (2026-10-26)

- Fix #29: LoRA adapter passthrough — top-level `adapter_path` on `POST /api/v1/tasks`, string form injected into chat/completions payloads, recorded in result meta.
- Fix #28 (P0): metric integrity — real streamed TTFT with p50/p95, fabricated prefill removed, `TasksDirMissingError` instead of silent empty results, OpenAPI version synced from `pyproject.toml`.

zh — 更早版本（v0.4.9 及以前，含 BNUP 评测、laya 基准、租户接入、Docker 加固）见 [README.md](README.md)。en — older releases (v0.4.9 and earlier, incl. BNUP evaluation, the laya benchmark, tenant auth and Docker hardening) are documented in [README.md](README.md).
