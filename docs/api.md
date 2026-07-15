# Fusion-Bench API Reference

> Module-level documentation for `fusion_bench` packages.

---

## `fusion_bench.engine.benchmark` — Benchmark Engine

```python
from fusion_bench.engine.benchmark import BenchmarkRunner, SpeedMetrics, BenchmarkResult
```

### BenchmarkRunner

Core benchmark engine. All model inference goes through fusion-mlx HTTP API.

**Constructor:**
```python
BenchmarkRunner(mlx_base_url="http://localhost:11434/v1", api_key="local", timeout=300.0)
```

| Method | Returns | Description |
|--------|---------|-------------|
| `run_single(model, prompt, max_tokens, temperature, config)` | `SpeedMetrics` | Single benchmark run |
| `benchmark(model, configs, prompt, max_tokens, runs)` | `list[BenchmarkResult]` | Multi-run benchmark |
| `run_stability(model, rounds, prompt, max_tokens)` | `BenchmarkResult` | Stability test |
| `probe_max_context(model, max_context, step)` | `int` | Max context length |
| `list_models()` | `list[dict]` | List available models |

### SpeedMetrics

| Field | Type | Description |
|-------|------|-------------|
| `prefill_speed` | `float` | Prefill tokens per second |
| `decode_speed` | `float` | Decode tokens per second |
| `total_time` | `float` | Total elapsed time (seconds) |
| `peak_memory_mb` | `float` | Peak memory usage (MB) |
| `prompt_tokens` | `int` | Prompt token count |
| `completion_tokens` | `int` | Completion token count |

---

## `fusion_bench.engine.task_runner` — LMEval Task Runner

```python
from fusion_bench.engine.task_runner import LMEvalTaskRunner
```

Loads and runs lm-evaluation-harness tasks (2082 tasks) via MLXModel.

**Constructor:**
```python
LMEvalTaskRunner(model="qwen3.5-9b", mlx_base_url="http://localhost:11434/v1")
```

| Method | Returns | Description |
|--------|---------|-------------|
| `list_tasks()` | `list[dict]` | List available tasks |
| `run_task(task_name, num_fewshot, max_samples)` | `dict` | Run a single task |
| `run_benchmark(tasks, num_fewshot)` | `list[dict]` | Run multiple tasks |

---

## `fusion_bench.adapters.mlx_model` — MLX Model Adapter

```python
from fusion_bench.adapters.mlx_model import MLXModel
```

LM Evaluation Harness compatible model adapter. All calls go through fusion-mlx HTTP API.

**Constructor:**
```python
MLXModel(model="qwen3.5-9b", base_url="http://localhost:11434/v1", api_key="local")
```

| Method | Returns | Description |
|--------|---------|-------------|
| `generate_until(requests)` | `list[str]` | Text generation |
| `loglikelihood(requests)` | `list[tuple[float, bool]]` | Scoring |
| `loglikelihood_rolling(requests)` | `list[float]` | Rolling scoring |
| `tok_encode(text)` | `list[int]` | Token encoding (approximate) |
| `tok_decode(tokens)` | `str` | Token decoding (approximate) |

---

## `fusion_bench.engine.metal_monitor` — Metal Monitor

```python
from fusion_bench.engine.metal_monitor import MetalMonitor
```

Collects real GPU performance metrics from Apple Silicon.

| Method | Returns | Description |
|--------|---------|-------------|
| `collect_gpu_info()` | `dict` | GPU hardware info via system_profiler |
| `collect_system_info()` | `dict` | System info via sysctl |
| `collect_mlx_stats(mlx_url)` | `dict` | MLX stats from fusion-mlx |
| `collect_all(mlx_url)` | `dict` | All metrics in one call |
| `format_report(data)` | `str` | Format as readable report |

---

## `fusion_bench.optimizer.tuner` — Parameter Tuner

```python
from fusion_bench.optimizer.tuner import ParameterTuner, TuneResult
```

Auto-tunes model parameters for optimal performance.

**Constructor:**
```python
ParameterTuner(mlx_base_url="http://localhost:11434/v1")
```

| Method | Returns | Description |
|--------|---------|-------------|
| `tune(model, prompt, max_combinations)` | `TuneResult` | Auto-tune a single model |
| `tune_multi_model(models, prompt, max_combinations)` | `dict[str, TuneResult]` | Tune multiple models |

### TuneResult

| Field | Type | Description |
|-------|------|-------------|
| `best_config` | `dict` | Best performing config |
| `best_speed` | `float` | Best decode speed (tok/s) |
| `top3_configs` | `list[dict]` | Top 3 configs |
| `memory_saving_config` | `dict` | Most memory-efficient config |
| `balanced_config` | `dict` | Balanced config |

---

## `fusion_bench.optimizer.quant_bench` — Quantization Benchmark

```python
from fusion_bench.optimizer.quant_bench import QuantBenchmark, QuantResult
```

Compares model performance across quantization levels.

**Constructor:**
```python
QuantBenchmark(mlx_base_url="http://localhost:11434/v1", base_model="qwen3.5-9b")
```

| Method | Returns | Description |
|--------|---------|-------------|
| `run_speed_comparison(levels, runs)` | `list[QuantResult]` | Speed comparison |
| `run_accuracy_comparison(levels, task, max_samples)` | `list[QuantResult]` | Accuracy comparison |
| `generate_report(results, title)` | `str` | Markdown report |

---

## `fusion_bench.reporter.report` — Report Generator

```python
from fusion_bench.reporter.report import ReportGenerator
```

Generates formatted reports from benchmark results.

| Method | Returns | Description |
|--------|---------|-------------|
| `to_json(results, filepath)` | `str` | Export as JSON |
| `to_markdown(results, title)` | `str` | Export as Markdown |
| `generate_chart_path(results, output_path)` | `str` | Generate chart (PNG) |
| `generate_config_template(result)` | `str` | Generate fusion-mlx config |

---

## `fusion_bench.reporter.bench_site_db` — BenchSite Database Writer

```python
from fusion_bench.reporter.bench_site_db import BenchSiteDB, BenchSiteRecord
```

Writes benchmark results directly to bench.dpdns.org database.

**Constructor:**
```python
BenchSiteDB(db_path="")  # Auto-detects bench-site/data/bench.db
```

| Method | Returns | Description |
|--------|---------|-------------|
| `insert(record)` | `int` | Insert a record, returns row ID |
| `insert_from_metrics(metrics, model_name, quantization, ...)` | `int` | Insert from SpeedMetrics |
| `insert_from_benchmark(result, ...)` | `int` | Insert from BenchmarkResult |
| `query(model, chip, limit)` | `list[dict]` | Query records |
| `stats()` | `dict` | Database statistics |

---

## `fusion_bench.cache` — Benchmark Cache

```python
from fusion_bench.cache import BenchmarkCache
```

SQLite-backed cache for benchmark results.

**Constructor:**
```python
BenchmarkCache(db_path="")  # Default: ~/.fusion-bench/cache.db
```

| Method | Returns | Description |
|--------|---------|-------------|
| `get(model, config, task)` | `dict \| None` | Get cached result |
| `set(model, config, task, result)` | `None` | Cache a result |
| `clear(model, task)` | `int` | Clear cache entries |
| `stats()` | `dict` | Cache statistics |