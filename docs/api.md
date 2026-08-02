# Fusion-Bench API Reference

> Module-level documentation for `fusion_bench` packages.
> REST API documentation for the FastAPI server (PRD Section 8).

---

## REST API

Base URL: `http://localhost:11450` (default)

### Task Management

#### `POST /api/v1/tasks` — Create Task

Create and start an async benchmark task.

**Request body** (`TaskCreateRequest`):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `task_type` | `str` | `"model"` | Task type: model/agent/code/security/artifact |
| `model` | `str` | `"qwen3.5-9b"` | Model name |
| `suite_id` | `str \| null` | `null` | Suite to associate with |
| `executor_key` | `str` | `"speed"` | Executor plugin key |
| `params` | `dict` | `{}` | Extra executor params |
| `dataset` | `str \| null` | `null` | Dataset override |
| `max_samples` | `int \| null` | `null` | Max evaluation samples |
| `timeout_seconds` | `int` | `600` | Timeout in seconds |
| `level` | `str` | `"L1"` | Evaluation level (L1–L4) |

**Response** (`TaskResponse`, 201):

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | Generated task ID |
| `status` | `str` | `"pending"` |
| `model` | `str` | Model name |
| `executor_key` | `str` | Executor key |
| `level` | `str` | Eval level |
| `created_at` | `str` | ISO timestamp |

---

#### `GET /api/v1/tasks` — List Tasks

**Query params**: `page` (1+), `page_size` (1–100), `status`, `model`

**Response**: `list[TaskResponse]`

---

#### `GET /api/v1/tasks/{task_id}` — Get Task Detail

**Response** (`TaskDetailResponse`):

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | Task ID |
| `status` | `str` | pending/running/completed/failed/cancelled |
| `model` | `str` | Model name |
| `executor_key` | `str` | Executor key |
| `level` | `str` | Eval level |
| `created_at` | `str` | ISO timestamp |
| `progress` | `float` | 0.0–1.0 |
| `result` | `dict \| null` | EvalResult dict (if completed) |
| `error` | `str \| null` | Error message (if failed) |
| `duration_seconds` | `float` | Run duration |

---

#### `POST /api/v1/tasks/{task_id}/cancel` — Cancel Task

Cancels a pending or running task.

**Response**: `{"task_id": "...", "status": "cancelled"}`

---

#### `POST /api/v1/tasks/{task_id}/retry` — Retry Task

Creates a new task from a failed/cancelled task's original request.

**Response**: `TaskResponse` (new task)

---

#### `GET /api/v1/tasks/{task_id}/logs` — Get Task Logs

**Query params**: `line_count` (1–500, default 50)

**Response**: `{"task_id": "...", "lines": ["..."]}`

---

### Suite Management

#### `GET /api/v1/suites` — List Suites

**Response**: `list[SuiteInfoResponse]`

| Field | Type | Description |
|-------|------|-------------|
| `suite_id` | `str` | Suite identifier |
| `name` | `str` | Display name |
| `task_count` | `int` | Number of tasks |
| `level` | `str` | Eval level |

---

#### `GET /api/v1/suites/{suite_id}` — Get Suite Detail

**Response**:

| Field | Type | Description |
|-------|------|-------------|
| `suite_id` | `str` | Suite identifier |
| `name` | `str` | Display name |
| `tasks` | `list[dict]` | Task definitions |
| `task_count` | `int` | Number of tasks |

---

### Results & Analysis

#### `GET /api/v1/results/{task_id}` — Get Result

**Response** (`ResultResponse`):

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | Task ID |
| `model` | `str` | Model name |
| `executor_key` | `str` | Executor key |
| `level` | `str` | Eval level |
| `metric_name` | `str` | Primary metric |
| `metric_value` | `float` | Metric value |
| `pass_rate` | `float` | Pass rate |
| `num_cases` | `int` | Cases evaluated |
| `duration_seconds` | `float` | Run duration |
| `errors` | `list[str]` | Error messages |
| `meta` | `dict` | Extra metadata |

---

#### `POST /api/v1/results/compare` — Compare Results

**Request body**: `{"task_ids": ["id1", "id2", ...]}` (minimum 2)

**Response**: `{"compared": [{"task_id": "...", "result": {...}}, ...]}`

---

#### `POST /api/v1/results/{task_id}/export` — Export Result

**Query params**: `format` (`"json"` or `"markdown"`)

**Response**: `{"format": "json|markdown", "content": "..."}`

---

#### `GET /api/v1/results/trend` — Get Trend Data

**Query params**: `model`, `executor_key`, `level`, `limit` (1–200, default 50)

**Response**: `list[TrendPoint]`

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | `str` | ISO timestamp |
| `metric_value` | `float` | Metric value |
| `model` | `str` | Model name |
| `executor_key` | `str` | Executor key |

---

### Quality Gates

#### `POST /api/v1/gates/check` — Check Gates

Evaluate quality gates for a task result.

**Request body** (`GateCheckRequest`):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `task_id` | `str` | — | Task to check |
| `gate_id` | `str \| null` | `null` | Filter to specific gate |
| `tier` | `str \| null` | `null` | Filter to tier (experimental/business/production) |

**Response** (`GateCheckResponse`):

| Field | Type | Description |
|-------|------|-------------|
| `passed` | `bool` | All gates passed |
| `gates` | `list[dict]` | Per-gate results with `gate_id`, `passed`, `action`, `approved_by` |

---

#### `GET /api/v1/gates` — List Gates

**Query params**: `tier`, `level`

**Response**: `{"gates": [...]}`

---

#### `POST /api/v1/gates` — Create Custom Gate

**Request body** (`GateRuleCreate`):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | — | Gate display name |
| `tier` | `str` | `"experimental"` | experimental/business/production |
| `metric_name` | `str` | — | Metric to check |
| `operator` | `str` | `">="` | Comparison operator |
| `threshold` | `float` | `0.0` | Threshold value |
| `executor_key` | `str \| null` | `null` | Filter by executor |
| `level` | `str \| null` | `null` | Filter by eval level |

**Response** (201): `{"gate_id": "custom-...", "gate": {...}}`

---

#### `POST /api/v1/gates/{gate_id}/approve` — Approve Blocked Gate

**Request body** (`GateApproveRequest`):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `approver` | `str` | — | Approver identifier |
| `remark` | `str` | `""` | Optional remark |

**Response**: `{"gate_id": "...", "approved": true, "approver": "..."}`

---

### System Management

#### `GET /api/v1/system/health` — Health Check

**Response** (`HealthResponse`):

| Field | Type | Description |
|-------|------|-------------|
| `status` | `str` | `"ok"` |
| `uptime_seconds` | `float` | Server uptime |
| `active_tasks` | `int` | Currently running tasks |
| `store_total` | `int` | Total trace records |

---

#### `GET /api/v1/system/resources` — System Resources

Returns GPU hardware info from Apple Silicon.

**Response**: `{"gpu": {...}}` (MetalMonitor output)

---

#### `GET /api/v1/system/audit-logs` — Audit Logs

**Query params**: `page` (1+), `page_size` (1–100)

**Response**:

| Field | Type | Description |
|-------|------|-------------|
| `total` | `int` | Total records |
| `page` | `int` | Current page |
| `items` | `list[dict]` | `trace_id`, `model`, `executor_key`, `status`, `timestamp` |

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