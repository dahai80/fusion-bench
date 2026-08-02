<div align="center">

# Fusion-Bench

**MLX Model Performance Benchmarking & Auto-Tuning Workbench**

Run, benchmark, and auto-tune AI models on Apple Silicon — entirely local, no cloud, no data leaving your device.

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
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
| **RBAC** | ✅ 3-role 8-permission | ❌ | ❌ |
| **TLS enforcement** | ✅ --tls-enforce | ❌ | ❌ |

**One sentence:** Fusion-Bench is the fastest way to benchmark and auto-tune MLX models on Apple Silicon — with direct integration to [bench.dpdns.org](https://bench.dpdns.org).

---

## Quick Start

### Prerequisites

- macOS with Apple Silicon (M1–M5)
- Python 3.12+
- [fusion-mlx](https://github.com/dahai80/fusion-mlx) running on `localhost:11434`

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

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--mlx-url` | `http://localhost:11434/v1` | fusion-mlx API URL |
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
| **RBAC Auth** | `auth/rbac.py` | Role(ADMIN/OPERATOR/VIEWER) → Permission mapping |
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
npm run dev          # http://localhost:11461
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
- **336 tests**, 0 failures
- **95%+ statement coverage**
- **Python 3.12+** compatible
- **Python 3.12+** compatible

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

MIT

## Changelog

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