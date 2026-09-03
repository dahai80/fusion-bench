<div align="center">

# Fusion-Bench

**MLX Model Performance Benchmarking & Auto-Tuning Workbench**

Run, benchmark, and auto-tune AI models on Apple Silicon — entirely local, no cloud, no data leaving your device.

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-336-success.svg)](tests/)
[![CI](https://github.com/dahai80/fusion-bench/actions/workflows/ci.yml/badge.svg)](https://github.com/dahai80/fusion-bench/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

[Quick Start](#quick-start) · [CLI Reference](#cli-reference) · [Architecture](#architecture) · [API Docs](docs/api/) · [Documentation](docs/)

</div>

---

## Why Fusion-Bench?

| Feature | Fusion-Bench | lm-eval-harness | opencompass |
|---------|-------------|-----------------|-------------|
| **MLX native** | ✅ fusion-mlx API | ❌ torch/HF | ❌ torch/HF |
| **Apple Silicon optimized** | ✅ Metal monitor | ❌ | ❌ |
| **Quantization comparison** | ✅ 4/8/16-bit | ❌ | ❌ |
| **Auto parameter tuning** | ✅ | ❌ | ❌ |
| **Quality gates** | ✅ 3-tier (Exp/Biz/Prod) | ❌ | ❌ |
| **Security probes** | ✅ injection/harmful/PII | ❌ | ❌ |
| **Plugin architecture** | ✅ Registry[T] pattern | ✅ | ❌ |
| **Trace store** | ✅ SQLite persistent | ❌ | ❌ |
| **Benchmark tasks** | 2082 (lm-eval compatible) | 2082 | 100+ |
| **Local offline** | ✅ 100% | ✅ | ✅ |
| **bench.dpdns.org integration** | ✅ Direct DB write | ❌ | ❌ |
| **Pipeline pause/resume** | ✅ asyncio.Event | ❌ | ❌ |
| **GPU overload detection** | ✅ pre-task check | ❌ | ❌ |
| **Root cause analysis** | ✅ 8 pattern categories | ❌ | ❌ |
| **Conditional triggers** | ✅ metric-based | ❌ | ❌ |
| **Multi-format export** | ✅ JSON/MD/PDF/Excel/HTML | ❌ | ❌ |
| **Radar chart** | ✅ 5-dimension radar | ❌ | ❌ |
| **Trend chart** | ✅ Time-series by model | ❌ | ❌ |
| **Custom suite API** | ✅ POST /suites + cases | ❌ | ❌ |
| **SDK** | ✅ Python httpx client | ❌ | ❌ |
| **CI/CD** | ✅ GitHub Action | ❌ | ❌ |
| **Remote distribution** | ✅ HTTP dispatch | ❌ | ❌ |
| **Tenant Auth** | ✅ fusion-identity JWT + tenant isolation | ❌ | ❌ |
| **TLS enforcement** | ✅ --tls-enforce | ❌ | ❌ |

**One sentence:** Fusion-Bench is the fastest way to benchmark and auto-tune MLX models on Apple Silicon — with direct integration to [bench.dpdns.org](https://bench.dpdns.org).

---

## Quick Start

### Prerequisites

- macOS with Apple Silicon (M1–M5)
- Python 3.12+
- [fusion-mlx](https://github.com/dahai80/fusion-mlx) running on `localhost:11432`

### Install

```bash
git clone https://github.com/dahai80/fusion-bench.git
cd fusion-bench
pip install -e ".[test]"
```

### Run a Benchmark

```bash
# List available tasks
fusion-bench list-tasks

# Benchmark model speed
fusion-bench speed --model qwen3.5-9b

# Run an evaluation task (requires lm-evaluation-harness)
fusion-bench run mmlu --model qwen3.5-9b

# Auto-tune model parameters
fusion-bench tune --model qwen3.5-9b

# Compare multiple models
fusion-bench compare --models qwen3.5-9b,deepseek-v4 --tasks mmlu,gsm8k

# Compare quantization levels
fusion-bench quant --model qwen3.5-9b
```

### Submit Results to bench.dpdns.org

```python
from fusion_bench.reporter.bench_site_db import BenchSiteDB
from fusion_bench.engine.benchmark import BenchmarkRunner

import asyncio

async def main():
    # 1. Run benchmark
    runner = BenchmarkRunner()
    results = await runner.benchmark("qwen3.5-9b")
    
    # 2. Write directly to bench-site database
    db = BenchSiteDB()
    for r in results:
        db.insert_from_benchmark(r)
    
    # 3. Results are immediately visible at https://bench.dpdns.org
    print(f"Submitted! Stats: {db.stats()}")

asyncio.run(main())
```

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `fusion-bench list-tasks [--pattern]` | List available evaluation tasks from lm-eval |
| `fusion-bench list-suites` | List benchmark suites (l1-quick, l1-full, l3-security…) |
| `fusion-bench list-executors` | List registered executor plugins |
| `fusion-bench run <task> [--model] [--max-samples]` | Run a single evaluation task |
| `fusion-bench suite <name> [--model] [--tier]` | Run a suite with quality gates |
| `fusion-bench speed [--model] [--runs]` | Benchmark model speed |
| `fusion-bench tune [--model] [--max-combinations]` | Auto-tune model parameters |
| `fusion-bench quant [--model] [--levels]` | Compare quantization levels |
| `fusion-bench security [--model] [--probe-set]` | Run security probes (injection/harmful/pii) |
| `fusion-bench gates [--tier]` | Show quality gate thresholds |
| `fusion-bench traces [--model] [--executor]` | Query trace store |
| `fusion-bench compare --models <m1,m2> [--tasks]` | Compare multiple models |
| `fusion-bench bench-site <action> [options]` | Manage bench-site web UI (dev/build/deploy/stats) |
| `fusion-bench api-key [options]` | Prints retirement guidance — API keys now issued by fusion-identity (#16) |
| `fusion-bench cache <stats\|clear> [--model] [--task]` | Inspect/clear benchmark result cache |
| `fusion-bench judge <create\|list\|show\|delete> [options]` | Manage LLM-as-Judge scoring configs (R1 JUDGE) |

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--mlx-url` | `http://localhost:11432/v1` | fusion-mlx API URL |
| `--model` | `qwen3.5-9b` | Model name to benchmark |
| `--output` | `""` | Output file path (JSON) |

---

## Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                         Fusion-Bench CLI v2                       │
│  run · suite · speed · tune · quant · security · gates · traces   │
└───────────────────────────────┬───────────────────────────────────┘
                                │
┌───────────────────────────────▼───────────────────────────────────┐
│                      Orchestrator Layer                            │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │   Pipeline    │  │  GateEngine  │  │      Scheduler          │ │
│  │ (concurrent)  │  │ (3-tier gate)│  │ (l1-quick, l1-full…)   │ │
│  └──────┬───────┘  └──────────────┘  └─────────────────────────┘ │
└─────────┼─────────────────────────────────────────────────────────┘
          │
┌─────────▼─────────────────────────────────────────────────────────┐
│               Executor Plugins (Registry[T])                      │
│  ┌─────────┐ ┌───────────┐ ┌──────┐ ┌──────┐ ┌──────────────┐   │
│  │  speed  │ │ lm_harness│ │ tune │ │ quant│ │  security    │   │
│  └────┬────┘ └─────┬─────┘ └──┬───┘ └──┬───┘ └──────┬───────┘   │
└───────┼────────────┼──────────┼────────┼────────────┼────────────┘
        │            │          │        │            │
┌───────▼────────────▼──────────▼────────▼────────────▼────────────┐
│              Engine / Adapter Layer (legacy compat)               │
│  BenchmarkRunner · LMEvalTaskRunner · ParameterTuner · QuantBench │
│                    MLXModel Adapter (HTTP API)                     │
└───────────────────────────┬───────────────────────────────────────┘
                            │
┌───────────────────────────▼───────────────────────────────────────┐
│  fusion-mlx (/v1/chat/completions, /v1/completions, /v1/models)  │
│           ↓                                                      │
│  Apple Silicon MLX Runtime (Metal GPU)                           │
└──────────────────────────────────────────────────────────────────┘
```

### Key Modules

| Module | File | Description |
|--------|------|-------------|
| **Core Registry** | `core/registry.py` | Type-safe `Registry[T]` for plugins, suites, gates |
| **Plugin Base** | `core/plugin_base.py` | `ExecutorPlugin` ABC + `TaskConfig`/`EvalResult`/`CaseResult` |
| **Data Models** | `core/models.py` | `BenchmarkTask`, `QualityGate`, `SuiteResult`, `TraceRecord` |
| **Pipeline** | `orchestrator/pipeline.py` | Concurrent suite execution with quality gates, pause/resume, GPU monitor, triggers |
| **Gate Engine** | `orchestrator/gate_engine.py` | 3-tier gate evaluation (Experimental/Business/Production), webhook on failure |
| **Root Cause** | `orchestrator/root_cause.py` | Failure pattern matching + optimization suggestions |
| **Circuit Breaker** | `orchestrator/circuit_breaker.py` | Auto-open on N consecutive failures, cooldown recovery |
| **Distributed** | `orchestrator/distributed.py` | TaskDistributor ABC + LocalDistributor + RemoteDistributor (HTTP) |
| **Scheduler** | `orchestrator/scheduler.py` | Suite definitions (l1-quick, l1-full, l3-security…) |
| **Trace Store** | `storage/trace_store.py` | SQLite-backed trace persistence and querying |
| **Speed Executor** | `executors/speed_executor.py` | Speed/memory benchmark plugin |
| **LM Harness Executor** | `executors/lm_harness_executor.py` | lm-evaluation-harness task plugin |
| **Tune Executor** | `executors/tune_executor.py` | Parameter auto-tuning plugin |
| **Quant Executor** | `executors/quant_executor.py` | Quantization comparison plugin |
| **Security Executor** | `executors/security_executor.py` | Injection/harmful/PII security probes |
| **Benchmark Engine** | `engine/benchmark.py` | Speed, memory, stability, max context probing |
| **Task Runner** | `engine/task_runner.py` | lm-evaluation-harness task loader (2082 tasks) |
| **MLX Adapter** | `adapters/mlx_model.py` | lm-eval compatible model interface |
| **Parameter Tuner** | `optimizer/tuner.py` | Auto-traverses batch/tokens/temperature |
| **Quant Comparison** | `optimizer/quant_bench.py` | Multi-quantization speed/accuracy comparison |
| **Report Generator** | `reporter/report.py` | JSON, Markdown, Chart, PDF, Excel, HTML, Radar/Trend chart, Config template |
| **BenchSite DB** | `reporter/bench_site_db.py` | Direct write to bench.dpdns.org database |
| **SSE Progress** | `api/sse.py` | Server-Sent Events real-time progress stream |
| **Webhook** | `api/webhook.py` | HMAC-signed webhook notifications on gate failure |
| **GPU Monitor** | `api/gpu_monitor.py` | Real-time GPU utilization, memory, temperature |
| **Tenant Auth** | `auth/tenant.py` + `auth/rbac.py` | fusion-identity JWT verify + X-Tenant-Id isolation; role→permission matrix |
| **SDK** | `sdk.py` | Python httpx client for all /api/v1/* endpoints |
| **CI/CD** | `cicd/github_action.py` | GitHub Action composite action for CI benchmarks |
| **CLI** | `cli.py` | Command-line interface v2 |

---

## Integration with bench.dpdns.org

Fusion-Bench writes **all 5 benchmark types** (speed, accuracy, security, quant, tune) directly into [bench.dpdns.org](https://bench.dpdns.org)'s database. Each type gets type-specific metrics and detail views on the website.

```python
from fusion_bench.reporter.bench_site_db import BenchSiteDB

db = BenchSiteDB()

# Speed benchmarks
db.insert_from_metrics(metrics, model_name="qwen3.5-9b", quantization="mxfp4")

# Any executor result (accuracy, security, quant, tune)
db.insert_from_eval_result(eval_result, executor_key="accuracy")

# → https://bench.dpdns.org/benchmarks/{id}
```

---

## Bench-Site (Web UI)

Bench-site is the public web interface at [bench.dpdns.org](https://bench.dpdns.org), bundled as a subdirectory of this repository. It supports **all 5 benchmark types** with type-specific detail views:
- **Speed** — tg_tps/pp_tps/TTFT/peak memory + batching table
- **Accuracy** — accuracy/pass_rate/num_fewshot metrics
- **Security** — safety_rate/probe_set/safe_count/total_probes
- **Quant** — quantization level comparison table (speed/accuracy/memory per level)
- **Tune** — best configuration + top-3 configs table + memory saving

**Tech stack:** Next.js 16, React 19, better-sqlite3, drizzle-orm, Tailwind CSS, recharts.

### Quick Start

```bash
# Start dev server
fusion-bench bench-site dev

# Build for production
fusion-bench bench-site build

# Deploy to production server
fusion-bench bench-site deploy

# View database statistics
fusion-bench bench-site stats
```

### Manual (without CLI)

```bash
cd bench-site
npm install
npm run dev          # http://localhost:3000 (manual) — CLI `fusion-bench bench-site dev` uses 11468
./deploy.sh         # Build + deploy to production
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/benchmarks` | POST | Submit benchmark result (any type) |
| `/api/benchmarks` | GET | Query with filtering/sorting/pagination (supports `benchmark_type`, `task_name` filters) |
| `/api/benchmarks/[id]` | GET | Single benchmark detail (parses `detail` JSON) |
| `/api/benchmarks/aggregate` | GET | Aggregate stats by chip/model/quant/type/task (supports `metric_value`) |
| `/api/benchmarks/stats` | GET | Total submissions, chips, models, by_type distribution |

---

## Development

```bash
# Install dev dependencies
pip install -e ".[test]"

# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=fusion_bench
```

### Test Stats
- **475 tests** (+ 3 live judge e2e, gated), 0 failures
- **66% statement coverage** on `api/app.py` (full suite higher)
- **Python 3.12+** compatible

### Releasing

The in-code version (`pyproject.toml` + `app.py` OpenAPI + README Changelog), the Git tag, and the GitHub Release are kept in sync by `scripts/release.sh`. The version in `pyproject.toml` is the single source of truth.

```bash
# 1. Bump the version in all three places, update the README Changelog,
#    commit, and push to main.
git add pyproject.toml fusion_bench/api/app.py README.md
git commit -m "release: vX.Y.Z — <summary>"
git push origin main

# 2. Cut the aligned tag + GitHub release (runs ruff + pytest first).
scripts/release.sh

# A version containing rc/alpha/beta is published as a GitHub prerelease
# (never Latest); a stable version is auto-marked Latest.
```

---

## Comparison with Alternatives

| Dimension | lm-eval-harness | opencompass | **Fusion-Bench** |
|-----------|----------------|-------------|-----------------|
| **MLX native** | ❌ torch/HF | ❌ torch/HF | ✅ fusion-mlx API |
| **Metal monitoring** | ❌ | ❌ | ✅ system_profiler |
| **Quantization comparison** | ❌ | ❌ | ✅ 4/8/16-bit |
| **Auto parameter tuning** | ❌ | ❌ | ✅ |
| **Quality gates** | ❌ | ❌ | ✅ 3-tier (Exp/Biz/Prod) |
| **HTML export** | ❌ | ❌ | ✅ |
| **Radar/Trend chart** | ❌ | ❌ | ✅ 5-dim radar + time-series |
| **Custom suite API** | ❌ | ❌ | ✅ POST /suites + cases |
| **Security probes** | ❌ | ❌ | ✅ injection/harmful/PII |
| **Plugin architecture** | ✅ | ❌ | ✅ Registry[T] pattern |
| **Trace store** | ❌ | ❌ | ✅ SQLite persistent |
| **Benchmark tasks** | 2082 | 100+ | 2082 (compatible) |
| **Local offline** | ✅ | ✅ | ✅ 100% |
| **bench.dpdns.org** | ❌ | ❌ | ✅ Direct DB write |

---

## License

[Apache License 2.0](LICENSE)

## Changelog


### v0.4.0 (2026-09-03)

- **Tenant auth via fusion-identity (#16)**: fusion-identity (port 11470) is now the sole JWT issuer + tenant registry. Local `api_keys`/`user_roles` tables and the `IdentityMiddleware`/OAuth resolver are retired. Bench mounts `fusion_core.tenant.install_tenant_middleware` with a fail-closed `verify_jwt` callback that calls `POST /api/v1/auth/verify` — missing `X-Tenant-Id`, missing/invalid token, `jwt.tid` ↔ header mismatch, inactive or revoked tenant all return 401 (no default-tenant degradation). Identity roles (`tenant_admin`/`operator`/`member`/`viewer`) map onto bench's `admin`/`operator`/`viewer` permission matrix; `require_permission` now reads `TenantContext.role`. Trace records gained a `tenant_id` column (auto-migrated) and every `TraceStore.query` call is scoped by tenant, so tenant A cannot read tenant B's traces. Benchmark usage is reported best-effort to identity `POST /api/v1/tenants/{tid}/usage`. The `api-key` CLI subcommand now prints retirement guidance pointing at fusion-identity.
- **Tests**: 485 unit tests green (added cross-tenant isolation, fail-closed verify, role mapping, permission matrix, middleware integration). `ruff check` + `ruff format --check` clean.

### v0.4.0rc3 (2026-08-31)

- **Port conflict fix (#15)**: Moved bench's own listen defaults off ports claimed by sibling services — `serve` 11450→**11467** (11450 belongs to fusion-multi-node-discovery), `bench-site` 11461→**11468** (11461 belongs to fusion-security). Updated all call sites: cli.py `serve`/`bench-site` arg defaults, Dockerfile `ENV`/`EXPOSE`/HEALTHCHECK/CMD, docker-compose port mapping, `FusionBenchClient`/SDK default `base_url`, `run_benchmark` default + `INPUT_BASE_URL` env, `.github/action.yml` `base-url`, docs/api.md. Bench code that *connects* to multi-node/security as a client is untouched.
- **CI lint green**: `ruff format --check .` was red on 14 pre-existing files (line-length wrap drift); reformatted them so the lint job passes. test job already green (475 passed).
- **Doc accuracy**: README + bench-site README/CLAUDE.md listed the wrong port for manual `npm run dev` (11461, but `next dev` binds 3000); corrected to 3000 with a note that the CLI wrapper uses 11468.

### v0.4.0rc2 (2026-08-27)

- **Release tooling hardening**: Added `scripts/release.sh` — single-command release that keeps the Git tag, GitHub Release, and in-code version (pyproject.toml = single source of truth) aligned. Pre-flight gates (tag-not-exists, clean tree, HEAD on origin) plus a pre-release ruff+pytest gate prevent drift; release notes are extracted from the README changelog; rc/alpha/beta versions auto-publish as GitHub prereleases, stable versions auto-marked Latest. Backfilled the missing v0.3.0–v0.3.8 tags/releases and fixed the test-stat in the Development section (336→475).
- **Three-way alignment verified**: code version = v0.4.0rc2, latest tag = v0.4.0rc1 (prior), latest stable release = v0.3.8.

### v0.4.0rc1 (2026-08-26)

- **Release Candidate — R1 hardening + trial deployment**: Promotion of the R1 identity/activation track to a release candidate. All prior R1 work (identity middleware, RBAC, pipeline cache, LLM-as-Judge, Docker) now trial-deployed and verified end-to-end.
- **Docker production fixes**: Dropped `build-essential` apt layer (pure-Python project, all deps ship arm64 wheels → no C compile); added Aliyun PyPI mirror `ARG PIP_INDEX_URL` (build VM PyPI throttled 17 kB/s → mirror 4 MB/s, ~3 min builds); fixed `docker_smoke.sh` ENTRYPOINT/CMD arg double (`fusion-bench fusion-bench --help` → `fusion-bench --help`); replaced curl HEALTHCHECK with stdlib `urllib` (no system packages); pre-created `~/.fusion-bench` + `~/bench` data dirs and chowned to non-root `fusion` user — without this named volumes mount root-owned and the container crashes at startup with `unable to open database file`.
- **Trial deploy verified**: `docker compose up` → container Up (healthy); `GET /api/v1/system/health` 200; `/openapi.json` 39 paths v0.4.0rc1; `POST /api/v1/judges` 201; `GET /api/v1/judges` 200 persisted; volume `fusion:fusion` with WAL files. All test artifacts cleaned up post-verification.
- **Test status**: 475 unit tests + 3 judge e2e (live Qwen3-0.6B-4bit) green; ruff clean.

### v0.3.8 (2026-08-26)

- **Release 1 — Identity & Activation (enterprise track)**: Real authentication (API Key store + OAuth2 JWKS IdP via `IdentityMiddleware`), Pipeline cache integration (executor_key + WAL + TTL + determinism gate), LLM-as-Judge for Agent/Artifact executors (hybrid/llm/rule blend with neutral fallback), Docker hardening (python:3.12-slim, non-root user, port 11450, healthcheck `/api/v1/system/health`, no NVIDIA GPU). New CLI subcommands: `api-key`, `cache`, `judge`. New `/api/v1/judges` CRUD endpoints with RBAC guards.
- **fix(api)**: TLS enforcement middleware referenced nonexistent `BaseRequestMiddleware` — `FUSION_BENCH_TLS_ENFORCE=1` crashed the app at import. Fixed to `BaseHTTPMiddleware`. Added 15 API tests (IdentityMiddleware, /judges CRUD, authz guards, TLS). 446 tests green.

### v0.3.7 (2026-08-07)

- **验收修复 (reliability/docking)**: 统一 executor `is_available()` 语义 — agent/code/artifact/evalscope 不再用 `/models` 200 探测（gateway 401 时会被静默注销），改为依赖检查或 `return True`，与 speed/security/tune 惯例一致。修复后全部 9 个执行器在未授权 gateway 下均可注册。

### v0.3.6 (2026-08-07)

- **Netlayer compliance (#14)**: Unified MLX URL default to gateway `localhost:11432` (reverts #10's 11434 direct-connect). `start.sh` now defaults to 11432; `FUSION_MLX_URL` still overrides for direct eval at 11434. No 11434 remains in any default value.

### v0.3.5 (2026-08-05)

- **Agent executor (#11)**: Multi-turn tool sandbox + trajectory scoring; safe arithmetic parser (no `eval()`); 5 default scenarios
- **Dataset loaders (#12)**: `sharegpt`/`alpaca`/`messages` format validation + `.json`/`.jsonl` file loading; CLI `dataset load` + API `/api/v1/datasets/load`
- **Baselines & gates (#13)**: `fusion-router-light`/`fusion-coder-expert` seed baselines; agent-intent + code-gen quality gates (3 tiers each); CLI `baseline seed` + API `/api/v1/baselines/seed`
- **Bugfix**: `CodeExecutor.run()` now uses real `EvalResult` schema (`code_pass_rate` metric, L3 level)

### v0.3.4 (2026-08-05)

- **Security fix**: Remove hardcoded API key `dahai168` from `scripts/ecosystem_benchmark.py`
- **API key from env**: `MLX_API_KEY` now read from `FUSION_MLX_API_KEY`, fail visibly if unset
- **MLX URL from env**: `MLX_BASE_URL` read from `FUSION_MLX_BASE_URL` (default 11432)

### v0.3.3 (2026-08-04)

- **Netlayer URL migration**: All fusion-mlx references migrated from `localhost:11434` to `localhost:11432`
- **Port assignments**: API=11450, Bench-site dev=11461, SDK=11450, fusion-mlx=11432
- **Housekeeping**: Removed stale analysis docs, refreshed README

### v0.3.2 (2026-08-03)

- **Port standardization**: Serve API 8000→11450, Bench-site 3000→11461, SDK 8900→11450
- **Bind address**: 0.0.0.0 → 127.0.0.1
- **TaskCreateRequest**: add `model_id`, `callback_url`, `suite` fields
- **License**: changed from MIT to Apache 2.0

### v0.3.1 (2026-08-02)

- Lint and format cleanup

### v0.3.0 (2026-07-26)

- **Custom suite API**: `POST /api/v1/suites` — create custom benchmark suites via `Scheduler.register_suite`
- **Case management API**: `POST/GET /api/v1/suites/{id}/cases` — upload and query test cases via `DatasetStore`
- **Result cases API**: `GET /api/v1/results/{id}/cases` — case-level detail with passed/failed filtering
- **HTML report export**: `ReportGenerator.to_html()` — styled responsive HTML reports
- **Radar chart**: `generate_radar_chart()` — 5-dimension normalized radar (Decode/Prefill/Memory/Stability/Context)
- **Trend chart**: `generate_trend_chart()` — time-series line chart grouped by model
- **PRD API coverage**: 23/23 endpoints fully covered (was 19/23)
- **CI/CD**: GitHub Actions CI with ruff lint + pytest
- **336 tests**, all passing

### v0.2.0 (2026-07-25)

- Bench-site integration (direct SQLite write)
- Pipeline pause/resume, GPU overload detection
- Root cause analysis, circuit breaker
- RBAC auth, TLS enforcement
- SDK client, CI/CD composite action

### v0.1.0 (2026-07-24)

- Initial release: 5 executor plugins, quality gates, trace store

## Acknowledgments

- [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness) — Evaluation framework reference
- [fusion-mlx](https://github.com/dahai80/fusion-mlx) — Apple Silicon model serving
- [bench.dpdns.org](https://bench.dpdns.org) — Community benchmark platform