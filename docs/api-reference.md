---
doc_id: fusion-bench/api-reference
product: fusion-bench
class: platform
entry: service
doc_type: api-reference
title: { zh: "Fusion-Bench REST API 参考", en: "Fusion-Bench REST API Reference" }
audience: engineer
status: draft
version: 0.4.25
updated: 2026-11-07
owner: "@dahai"
source_of_truth:
  - docs/api.md
  - fusion_bench/api/app.py
  - fusion_bench/sdk.py
  - fusion_bench/auth/tenant.py
---

# REST API 参考 / REST API Reference

zh — Base URL `http://127.0.0.1:11467`（`fusion-bench serve` / `start.sh start` 默认值，端口来自 `architecture/port-registry.yaml`）。完整字段级文档见 [docs/api.md](../docs/api.md)；运行中的服务提供 `/openapi.json`（版本号与 `pyproject.toml` 同步）。en — Base URL `http://127.0.0.1:11467` (default of `fusion-bench serve` / `start.sh start`; port per `architecture/port-registry.yaml`). Field-level detail lives in [docs/api.md](../docs/api.md); a running service exposes `/openapi.json` (version synced from `pyproject.toml`).

## 鉴权 / Auth

zh — 除 `/api/v1/system/health` 外全部 fail-closed：请求必须带 `X-Tenant-Id` 与 `Authorization: Bearer <jwt>`，JWT 由 fusion-identity（`:11470`）签发并在每次请求时经 `POST /api/v1/auth/verify` 校验。`jwt.tid` 与 `X-Tenant-Id` 不一致、租户停用/吊销、缺任一头均返回 401，无默认租户。角色映射：identity 的 `tenant_admin`/`operator`/`member`/`viewer` 对应 bench 的 admin/operator/viewer 权限矩阵。shell 模块代理请求由网关注入 `FUSION_BENCH_SHELL_API_KEY` 对应的模块密钥，服务端合成 `shell` 租户放行，密钥不匹配仍然 401。en — Everything except `/api/v1/system/health` is fail-closed: requests must carry `X-Tenant-Id` and `Authorization: Bearer <jwt>`; the JWT is issued by fusion-identity (`:11470`) and verified per request via `POST /api/v1/auth/verify`. A `jwt.tid`/header mismatch, an inactive or revoked tenant, or either header missing returns 401 with no default tenant. Identity roles (`tenant_admin`/`operator`/`member`/`viewer`) map onto the bench admin/operator/viewer permission matrix. Shell-proxy requests are admitted with the module key (`FUSION_BENCH_SHELL_API_KEY`) injected by the gateway under a synthetic `shell` tenant; a mismatched key still returns 401.

## 任务 / Tasks

| Method & Path | zh 说明 / en description |
|---|---|
| `POST /api/v1/tasks` | zh 创建并启动异步评测任务（201）。en create and start an async benchmark task (201). |
| `GET /api/v1/tasks` | zh 分页列出任务（`page`, `page_size` 1–100, `status`, `model`）。en list tasks with pagination. |
| `GET /api/v1/tasks/{task_id}` | zh 任务详情：状态、进度 0.0–1.0、结果、错误、耗时。en task detail: status, progress, result, error, duration. |
| `POST /api/v1/tasks/{task_id}/cancel` | zh 取消 pending/running 任务。en cancel a pending/running task. |
| `POST /api/v1/tasks/{task_id}/retry` | zh 从失败/取消任务重建新任务。en retry a failed/cancelled task as a new task. |
| `GET /api/v1/tasks/{task_id}/logs` | zh 任务日志（`line_count` 1–500，默认 50）。en task logs (`line_count` 1–500, default 50). |

`POST /api/v1/tasks` 请求体关键字段（`TaskCreateRequest`）：

| Field | Type | Default | zh 说明 / en description |
|---|---|---|---|
| `model` | str | `qwen3.5-9b` | zh 模型名。en model name. |
| `executor_key` | str | `speed` | zh 执行器插件 key。en executor plugin key. |
| `task_type` | str | `model` | zh model/agent/code/security/artifact。en task type. |
| `suite_id` | str or null | null | zh 关联套件。en suite association. |
| `params` | dict | `{}` | zh 执行器扩展参数（含 `adapter_path`）。en executor params (incl. `adapter_path`). |
| `max_samples` | int or null | null | zh 采样上限。en sample cap. |
| `timeout_seconds` | int | 600 | zh 超时。en timeout. |
| `level` | str | `L1` | zh 评测级别 L1–L4。en eval level L1–L4. |
| `adapter_path` | str or null | null | zh LoRA 适配器路径，注入 `/v1/chat/completions` 的 `adapters` 字段（fusion-mlx 要求字符串形式）。en LoRA adapter path, injected as the string `adapters` field (fusion-mlx validates string form). |

## 套件与自定义套件 / Suites

| Method & Path | zh 说明 / en description |
|---|---|
| `GET /api/v1/suites` | zh 列出套件（l1-quick、l1-full、l3-security、long-session 等）。en list suites. |
| `GET /api/v1/suites/{suite_id}` | zh 套件详情与任务定义。en suite detail. |
| `POST /api/v1/suites` | zh 注册自定义套件。en register a custom suite. |
| `POST/GET /api/v1/suites/{id}/cases` | zh 上传/查询套件用例（`DatasetStore`）。en upload/query suite cases. |

## 结果与分析 / Results and analysis

| Method & Path | zh 说明 / en description |
|---|---|
| `GET /api/v1/results/{task_id}` | zh 单任务结果（主指标、pass_rate、用例数）。en result for one task. |
| `GET /api/v1/results/{task_id}/cases` | zh 用例级明细，支持 passed/failed 过滤。en case-level detail with pass filters. |
| `POST /api/v1/results/compare` | zh 对比至少 2 个任务。en compare two or more tasks. |
| `POST /api/v1/results/{task_id}/export` | zh 导出，`format=json|markdown`。en export as json or markdown. |
| `GET /api/v1/results/trend` | zh 趋势序列（`model`, `executor_key`, `level`, `limit` 1–200）。en trend points. |

## 质量门禁与基线 / Gates and baselines

| Method & Path | zh 说明 / en description |
|---|---|
| `GET /api/v1/gates` | zh 列出门禁（`tier`, `level` 过滤）。en list gates. |
| `POST /api/v1/gates` | zh 创建自定义门禁规则（metric/operator/threshold）。en create a custom gate rule. |
| `POST /api/v1/gates/check` | zh 对任务结果执行门禁判定。en evaluate gates for a task result. |
| `POST /api/v1/gates/{gate_id}/approve` | zh 人工放行被拦截的门禁（approver 必填）。en approve a blocked gate. |
| `GET/POST /api/v1/baselines`、`POST /api/v1/baselines/seed`、`POST /api/v1/baselines/{name}/diff`、`DELETE /api/v1/baselines/{name}` | zh 基线 CRUD、播种与差异对比。en baseline CRUD, seeding and diff. |
| CLI `baseline seed` / `compare --baseline` | zh 基线管理在 CLI 侧；`compare` 支持遗忘检测（GSM8K Δ ≤ -5% 告警）。en baselines are managed via the CLI; `compare` flags catastrophic forgetting (GSM8K delta at or below -5%). |

## 裁判 / Judges

| Method & Path | zh 说明 / en description |
|---|---|
| `POST /api/v1/judges` / `GET /api/v1/judges` | zh LLM-as-Judge 配置 CRUD（RBAC 保护）。en judge config CRUD (RBAC-guarded). |
| `POST /api/v1/judges/sxs/run` | zh 双盲 SxS 评审：返回 winner、逐准则 1–5 分、均值、rationale 与槽位 `position_map`；`persist` 可选。en double-blind SxS run: winner, per-criterion 1–5 scores, averages, rationale, slot `position_map`; optional persist. |
| `GET /api/v1/judges/sxs/runs` | zh 最近 SxS 运行（存于 `~/.fusion-bench/sxs_runs.db`）。en recent SxS runs. |

zh — SxS 持久化行始终存真实 winner，不存洗牌后的槽位身份。en — persisted rows always store the TRUE winner, never the shuffled slot identity.

## 系统与运维 / System and ops

| Method & Path | zh 说明 / en description |
|---|---|
| `GET /api/v1/system/health` | zh 健康检查，功能就绪才返回 200（唯一免鉴权端点）。en health check; 200 only when functionally ready (the only unauthenticated endpoint). |
| `GET /api/v1/system/resources`、`GET /api/v1/system/gpu` | zh Apple Silicon GPU/内存信息（MetalMonitor）。en GPU/system info via MetalMonitor. |
| `GET /api/v1/models` | zh 经网关代理 fusion-mlx `/v1/models`，返回已下载模型 id 列表。en proxied model id list from fusion-mlx. |
| `GET /api/v1/system/audit-logs` | zh 审计日志（admin 租户，operator 403）。en audit logs (admin tenants; operator gets 403). |
| `GET /api/v1/system/backups`、`POST /api/v1/system/backup`、`POST /api/v1/system/restore` | zh 备份与恢复（admin，恢复有名称确认守卫）。en backup and restore (admin; restore behind a name-confirm guard). |
| `POST /api/v1/datasets`、`POST /api/v1/datasets/load`、`GET /api/v1/datasets` | zh 数据集注册/加载（sharegpt/alpaca/messages）/列表。en dataset register/load (sharegpt/alpaca/messages)/list. |
| `GET/POST /api/v1/schedules`、`PUT /api/v1/schedules/{id}/toggle`、`DELETE /api/v1/schedules/{id}` | zh cron 调度管理。en cron schedule management. |
| `GET/POST /api/v1/approvals`、`PUT /api/v1/approvals/{request_id}/approve` 或 `/reject` | zh 门禁审批流。en gate approval flow. |
| `GET /api/v1/tasks/{task_id}/events` | zh SSE 实时进度流（`api/sse.py`）。en SSE live progress stream. |

## SDK / Python SDK

```python
from fusion_bench.sdk import FusionBenchClient
client = FusionBenchClient(base_url="http://127.0.0.1:11467")
```

zh — `fusion_bench.sdk.FusionBenchClient` 封装上述端点；鉴权头由调用方注入。en — `fusion_bench.sdk.FusionBenchClient` wraps the endpoints above; auth headers are the caller's responsibility.

## 库级 Python API / Library-level Python API

zh — 不走 HTTP 时可直接用引擎层：`BenchmarkRunner`（speed/stability/max-context）、`LMEvalTaskRunner`（2082 个 lm-eval 任务）、`MLXModel`（lm-eval 兼容适配器）、`ParameterTuner`、`QuantBenchmark`、`ReportGenerator`、`BenchSiteDB`、`BenchmarkCache`。方法签名见 [docs/api.md](../docs/api.md)。en — without HTTP, use the engine layer directly: `BenchmarkRunner`, `LMEvalTaskRunner`, `MLXModel`, `ParameterTuner`, `QuantBenchmark`, `ReportGenerator`, `BenchSiteDB`, `BenchmarkCache`. Signatures in [docs/api.md](../docs/api.md).

## CI 集成 / CI integration

zh — 仓库根 `action.yml` 是 GitHub 复合动作，可在工作流中对 PR 跑基准并回传结果；输入含 `base-url`（默认 `http://127.0.0.1:11467`）。en — the root `action.yml` is a GitHub composite action that runs benchmarks in a workflow; inputs include `base-url` (default `http://127.0.0.1:11467`).
