---
doc_id: fusion-bench/changelog
product: fusion-bench
class: platform
entry: service
doc_type: changelog
title: { zh: "Fusion-Bench 变更日志", en: "Fusion-Bench Changelog" }
audience: engineer
status: draft
version: 0.4.25
updated: 2026-11-07
owner: @dahai
source_of_truth:
  - README.md
  - pyproject.toml
---

# Changelog

zh — 版本号以 `pyproject.toml` 为单一事实源，由 `scripts/release.sh` 保持 git tag、GitHub Release 与代码内版本一致。此处保留近期条目，完整历史见 [README.md](README.md) 的 Changelog 一节。en — the version in `pyproject.toml` is the single source of truth, kept aligned with the git tag, the GitHub Release and in-code versions by `scripts/release.sh`. This file keeps recent entries; the full history lives in the Changelog section of [README.md](README.md).

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
