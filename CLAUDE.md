# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Fusion-Bench is an MLX model benchmarking and auto-tuning workbench for Apple Silicon. It benchmarks models served by [fusion-mlx](https://github.com/dahai80/fusion-mlx) via HTTP API — **no direct MLX/torch/transformers imports**. Results integrate directly with [bench.dpdns.org](https://bench.dpdns.org).

## Build & Test Commands

```bash
# Activate project environment
source .venv/bin/activate

# Install (editable with test deps)
pip install -e ".[test]"

# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=fusion_bench

# Run a single test file
pytest tests/test_core.py

# Run a specific test
pytest tests/test_core.py::test_something -v

# CLI commands (require fusion-mlx running on localhost:11434)
fusion-bench list-tasks
fusion-bench speed --model qwen3.5-9b
fusion-bench run mmlu --model qwen3.5-9b
fusion-bench tune --model qwen3.5-9b
fusion-bench compare --models qwen3.5-9b,deepseek-v4 --tasks mmlu,gsm8k
fusion-bench quant --model qwen3.5-9b
```

## Architecture

```
CLI v2 (cli.py)
  ↓
Orchestrator Layer ──────────────────────────────────────────────
  orchestrator/pipeline.py  (Pipeline — concurrent suite execution)
  orchestrator/gate_engine.py (GateEngine — 3-tier quality gates)
  orchestrator/scheduler.py (Scheduler — suite definitions)
  ↓
Core Layer ──────────────────────────────────────────────────────
  core/registry.py (Registry[T] — plugin/suite/gate registration)
  core/plugin_base.py (ExecutorPlugin ABC, TaskConfig, EvalResult)
  core/models.py (BenchmarkTask, QualityGate, SuiteResult, TraceRecord)
  ↓
Executor Plugins ────────────────────────────────────────────────
  executors/speed_executor.py    (SpeedExecutor — L1 speed/memory)
  executors/lm_harness_executor.py (LMHarnessExecutor — L1 accuracy)
  executors/tune_executor.py     (TuneExecutor — L1 parameter tuning)
  executors/quant_executor.py    (QuantExecutor — L1 quant comparison)
  executors/security_executor.py (SecurityExecutor — L3 security probes)
  ↓                                    ↓
Engine Layer (legacy compat)       Storage Layer
  engine/benchmark.py              storage/trace_store.py (TraceStore — SQLite)
  engine/task_runner.py
  engine/metal_monitor.py          Reporter Layer
  engine/metrics.py                reporter/report.py
  optimizer/tuner.py               reporter/bench_site_db.py
  optimizer/quant_bench.py         reporter/bench_site.py
  ↓
Adapter Layer
  adapters/mlx_model.py (MLXModel)
  ↓
fusion-mlx HTTP API (localhost:11434/v1)
  /chat/completions, /completions, /models, /stats
```

**Key data flow:** CLI → Orchestrator/Pipeline → Executor Plugins → Engine/Adapter → HTTP to fusion-mlx. Results flow through GateEngine (quality gates) → TraceStore (persistence) → Reporter/BenchSiteDB.

**Critical constraint:** All model inference goes through fusion-mlx HTTP API. The codebase never imports MLX, mlx-lm, torch, or transformers directly.

## Module Responsibilities

| Module | Core Classes | Purpose |
|--------|-------------|---------|
| **core/registry.py** | `Registry[T]`, `executor_registry`, `suite_registry`, `gate_registry` | Type-safe plugin registration (inspired by lm-eval-harness) |
| **core/plugin_base.py** | `ExecutorPlugin`, `ExecutorType`, `TaskConfig`, `EvalResult`, `CaseResult` | Abstract plugin interface: `run(task_config) → EvalResult` |
| **core/models.py** | `BenchmarkTask`, `QualityGate`, `GateResult`, `SuiteResult`, `TraceRecord` | Four-level evaluation data models (L1–L4) |
| **orchestrator/pipeline.py** | `Pipeline` | Concurrent suite execution with quality gates and trace recording |
| **orchestrator/gate_engine.py** | `GateEngine` | 3-tier gate evaluation (Experimental/Business/Production) |
| **orchestrator/scheduler.py** | `Scheduler` | Suite definitions (l1-quick, l1-full, l1-tune, l3-security, full) |
| **storage/trace_store.py** | `TraceStore` | SQLite-backed trace persistence and querying |
| **executors/speed_executor.py** | `SpeedExecutor` | Speed/memory benchmark plugin (wraps BenchmarkRunner) |
| **executors/lm_harness_executor.py** | `LMHarnessExecutor` | lm-evaluation-harness task plugin (wraps LMEvalTaskRunner) |
| **executors/tune_executor.py** | `TuneExecutor` | Parameter auto-tuning plugin (wraps ParameterTuner) |
| **executors/quant_executor.py** | `QuantExecutor` | Quantization comparison plugin (wraps QuantBenchmark) |
| **executors/security_executor.py** | `SecurityExecutor` | Security probes (injection/harmful/PII) — never uses exec()/eval() |
| `engine/benchmark.py` | `BenchmarkRunner`, `SpeedMetrics`, `BenchmarkResult` | Speed/memory/stability/max-context benchmarks via HTTP |
| `engine/task_runner.py` | `LMEvalTaskRunner` | Load YAML task defs from lm-evaluation-harness, evaluate via MLXModel |
| `engine/metal_monitor.py` | `MetalMonitor` | GPU info via `system_profiler`/`sysctl` + MLX stats |
| `engine/metrics.py` | `SystemMetrics`, `MetricsCollector` | Real-time metrics collection from fusion-mlx `/stats` |
| `adapters/mlx_model.py` | `MLXModel` | lm-eval compatible interface: `generate_until`, `loglikelihood`, `tok_encode/decode` |
| `optimizer/tuner.py` | `ParameterTuner`, `TuneResult` | Auto-traverses batch_size/max_tokens/temperature combos |
| `optimizer/quant_bench.py` | `QuantBenchmark`, `QuantResult` | Multi-quantization speed/accuracy comparison |
| `reporter/report.py` | `ReportGenerator` | JSON/Markdown/Chart/Config template output |
| `reporter/bench_site_db.py` | `BenchSiteDB`, `BenchSiteRecord` | Direct SQLite write to bench-site database |
| `reporter/bench_site.py` | `BenchSiteReporter`, `BenchSiteSubmitter` | Format + HTTP submit to bench.dpdns.org API |
| `cache.py` | `BenchmarkCache` | SQLite cache keyed by model+config+task |
| `cli.py` | `main()` + `cmd_*` functions | argparse CLI v2 with subcommands: list-tasks, list-suites, list-executors, run, suite, speed, tune, quant, security, gates, traces, compare |

## Key Conventions

- **Async-first:** Engine and adapter code uses `async/await` with `httpx.AsyncClient`. CLI dispatches via `asyncio.run()`.
- **Quantization naming:** Model names embed quant level (e.g., `qwen3.5-9b-mxfp4`). Code parses this from model name when reporting.
- **BenchSiteDB paths:** Auto-detects `~/claude-home/bench-site/data/bench.db`; falls back to `~/.fusion-bench/bench-site.db`.
- **Task directory:** LMEvalTaskRunner looks for `~/bench/lm-evaluation-harness/lm_eval/tasks` for YAML task definitions.
- **Token estimation:** MLXModel uses approximate token counting (~4 chars/token) since no tokenizer is loaded.
- **pytest-asyncio:** `asyncio_mode = "auto"` in pyproject.toml — async test functions work without explicit markers.
