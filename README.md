<div align="center">

# Fusion-Bench

**MLX Model Performance Benchmarking & Auto-Tuning Workbench**

Run, benchmark, and auto-tune AI models on Apple Silicon — entirely local, no cloud, no data leaving your device.

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-122-success.svg)](tests/)

[Quick Start](#quick-start) · [CLI Reference](#cli-reference) · [Architecture](#architecture) · [Documentation](docs/)

</div>

---

## Why Fusion-Bench?

| Feature | Fusion-Bench | lm-eval-harness | opencompass |
|---------|-------------|-----------------|-------------|
| **MLX native** | ✅ fusion-mlx API | ❌ torch/HF | ❌ torch/HF |
| **Apple Silicon optimized** | ✅ Metal monitor | ❌ | ❌ |
| **Quantization comparison** | ✅ 4/8/16-bit | ❌ | ❌ |
| **Auto parameter tuning** | ✅ | ❌ | ❌ |
| **Benchmark tasks** | 2082 (lm-eval compatible) | 2082 | 100+ |
| **Local offline** | ✅ 100% | ✅ | ✅ |
| **bench.dpdns.org integration** | ✅ Direct DB write | ❌ | ❌ |

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
| `fusion-bench run <task> [--model] [--max-samples]` | Run a single evaluation task |
| `fusion-bench tune [--model] [--max-combinations]` | Auto-tune model parameters |
| `fusion-bench compare --models <m1,m2> [--tasks]` | Compare multiple models |
| `fusion-bench speed [--model] [--runs]` | Benchmark model speed |
| `fusion-bench quant [--model] [--levels]` | Compare quantization levels |

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--mlx-url` | `http://localhost:11434/v1` | fusion-mlx API URL |
| `--model` | `qwen3.5-9b` | Model name to benchmark |
| `--output` | `""` | Output file path (JSON) |

---

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                        Fusion-Bench CLI                        │
│  run · list-tasks · tune · compare · speed · quant             │
└───────────────────────────┬───────────────────────────────────┘
                            │
┌───────────────────────────▼───────────────────────────────────┐
│                   Benchmark Engine                              │
│  ┌────────────────┐  ┌────────────────┐  ┌─────────────────┐  │
│  │ LMEvalTaskRunner│  │ BenchmarkRunner│  │ ParameterTuner  │  │
│  │ (2082 tasks)    │  │ (speed/memory) │  │ (auto-tuning)   │  │
│  └───────┬────────┘  └───────┬────────┘  └────────┬────────┘  │
└──────────┼──────────────────┼─────────────────────┼────────────┘
           │                  │                     │
┌──────────▼──────────────────▼─────────────────────▼────────────┐
│                   MLXModel Adapter                              │
│  generate_until · loglikelihood · tok_encode/decode             │
│           ↓ HTTP API (never imports MLX directly)               │
└────────────────────────────────────────────────────────────────┘
           │
┌──────────▼────────────────────────────────────────────────────┐
│  fusion-mlx (/v1/chat/completions, /v1/completions, /v1/models)│
│           ↓                                                    │
│  Apple Silicon MLX Runtime (Metal GPU)                        │
└────────────────────────────────────────────────────────────────┘
```

### Key Modules

| Module | File | Description |
|--------|------|-------------|
| **Benchmark Engine** | `engine/benchmark.py` | Speed, memory, stability, max context probing |
| **Task Runner** | `engine/task_runner.py` | lm-evaluation-harness task loader (2082 tasks) |
| **Metal Monitor** | `engine/metal_monitor.py` | GPU info via system_profiler + MLX stats |
| **MLX Adapter** | `adapters/mlx_model.py` | lm-eval compatible model interface |
| **Parameter Tuner** | `optimizer/tuner.py` | Auto-traverses batch/tokens/temperature |
| **Quant Comparison** | `optimizer/quant_bench.py` | Multi-quantization speed/accuracy comparison |
| **Report Generator** | `reporter/report.py` | JSON, Markdown, Chart, Config template |
| **BenchSite DB** | `reporter/bench_site_db.py` | Direct write to bench.dpdns.org database |
| **Cache** | `cache.py` | SQLite benchmark cache |
| **CLI** | `cli.py` | Command-line interface |

---

## Integration with bench.dpdns.org

Fusion-Bench writes benchmark results directly into [bench.dpdns.org](https://bench.dpdns.org)'s database. After running a benchmark, results are immediately visible on the website.

```python
from fusion_bench.reporter.bench_site_db import BenchSiteDB

db = BenchSiteDB()
db.insert_from_metrics(metrics, model_name="qwen3.5-9b", quantization="mxfp4")
# → https://bench.dpdns.org/benchmarks/{id}
```

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
- **122 tests**, 0 failures
- **96%+ statement coverage** (core modules)
- **Python 3.12+** compatible

---

## Comparison with Alternatives

| Dimension | lm-eval-harness | opencompass | **Fusion-Bench** |
|-----------|----------------|-------------|-----------------|
| **MLX native** | ❌ torch/HF | ❌ torch/HF | ✅ fusion-mlx API |
| **Metal monitoring** | ❌ | ❌ | ✅ system_profiler |
| **Quantization comparison** | ❌ | ❌ | ✅ 4/8/16-bit |
| **Auto parameter tuning** | ❌ | ❌ | ✅ |
| **Benchmark tasks** | 2082 | 100+ | 2082 (compatible) |
| **Local offline** | ✅ | ✅ | ✅ 100% |
| **bench.dpdns.org** | ❌ | ❌ | ✅ Direct DB write |

---

## License

MIT

## Acknowledgments

- [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness) — Evaluation framework reference
- [fusion-mlx](https://github.com/dahai80/fusion-mlx) — Apple Silicon model serving
- [bench.dpdns.org](https://bench.dpdns.org) — Community benchmark platform