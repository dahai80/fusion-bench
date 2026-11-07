---
doc_id: fusion-bench/architecture
product: fusion-bench
class: platform
entry: service
doc_type: architecture
title: { zh: "Fusion-Bench 架构", en: "Fusion-Bench Architecture" }
audience: engineer
status: draft
version: 0.4.25
updated: 2026-11-07
owner: "@dahai"
source_of_truth:
  - README.md
  - fusion_bench/core/registry.py
  - fusion_bench/orchestrator/pipeline.py
  - fusion_bench/api/app.py
  - fusion_bench/auth/tenant.py
---

# 架构 / Architecture

## 分层 / Layers

```
CLI (fusion_bench/cli.py)          REST API (fusion_bench/api/app.py, uvicorn)
        \                             /
         Orchestrator: Pipeline / GateEngine / Scheduler / CircuitBreaker
                       |                        |
              Executor plugins (Registry[T])   Web console (web/dist, static)
                       |
              Engine layer: BenchmarkRunner / LMEvalTaskRunner / Tuner / Quant
                       |
              MLXModel adapter -- HTTP only --> fusion-gateway :11432 --> fusion-mlx :11434
                       |
              Storage: TraceStore / BenchmarkCache / SxSStore (SQLite)
```

zh — 所有模型推理只经 fusion-mlx HTTP API（`/v1/chat/completions`、`/v1/completions`、`/v1/models`），代码不 import MLX。默认走网关 `:11432`；直连 `:11434` 必须显式 opt-in 且模式记入结果 meta。en — all inference goes through the fusion-mlx HTTP API; the code never imports MLX. The gateway on `:11432` is the default; direct `:11434` access is explicit opt-in and the mode is recorded in result meta.

## 核心机制 / Core mechanisms

### Registry[T] 插件模型 / Registry[T] plugin model

zh — `fusion_bench/core/registry.py` 提供类型安全的 `Registry[T]`，用于执行器插件、套件与门禁注册。执行器继承 `core/plugin_base.py` 的 `ExecutorPlugin` ABC（输入 `TaskConfig`，输出 `EvalResult`/`CaseResult`），在 `register_all()` 中注册后即可被 CLI、套件调度与 REST 使用；`fusion-bench list-executors` 列出全部注册项。每个执行器实现 `is_available()` 做依赖检查——统一语义是"依赖检查或 `return True`"，不做 `/models` 探测（网关 401 时不会误注销）。en — `fusion_bench/core/registry.py` provides a type-safe `Registry[T]` for executor plugins, suites and gates. Executors subclass the `ExecutorPlugin` ABC (`TaskConfig` in, `EvalResult`/`CaseResult` out) and register in `register_all()`, after which the CLI, scheduler and REST surface all see them; `fusion-bench list-executors` lists registrations. Each executor implements `is_available()` as a dependency check or `return True` — never a `/models` probe, so an unauthorized gateway cannot deregister executors silently.

### 编排层 / Orchestrator

zh — `orchestrator/pipeline.py` 并发执行套件任务，带暂停/恢复（`asyncio.Event`）、GPU 过载预检与条件触发器；`gate_engine.py` 做三级门禁判定（experimental / business / production），失败触发 HMAC 签名 webhook，production 拦截需显式审批；`scheduler.py` 定义 l1-quick、l1-full、l3-security、full、arabic-multilingual、long-session 等套件；`root_cause.py` 按 8 类失败模式归因并给出建议；`circuit_breaker.py` 连续 N 次失败自动熔断、冷却恢复；`distributed.py` 抽象 TaskDistributor（LocalDistributor / HTTP RemoteDistributor）。en — `pipeline.py` runs suite tasks concurrently with pause/resume (`asyncio.Event`), GPU overload pre-checks and conditional triggers; `gate_engine.py` evaluates the three gate tiers with HMAC-signed failure webhooks and explicit approval for blocked production gates; `scheduler.py` defines suites such as l1-quick, l1-full, l3-security, full, arabic-multilingual and long-session; `root_cause.py` attributes failures across 8 pattern categories; `circuit_breaker.py` opens after N consecutive failures and recovers after cooldown; `distributed.py` abstracts task distribution (local / HTTP remote).

### 鉴权与租户 / Auth and tenancy

zh — `auth/tenant.py` 挂载 `fusion_core.tenant.install_tenant_middleware`，`verify_jwt` 回调 fail-closed 调 fusion-identity `POST /api/v1/auth/verify`；`auth/rbac.py` 维护 admin/operator/viewer 权限矩阵并从 `TenantContext.role` 读取 identity 角色；`auth/shell_module.py` 为网关 shell 代理注入的模块密钥合成 `shell` 租户（`start.sh` 生成的 `FUSION_BENCH_SHELL_API_KEY`，不匹配仍 401）。TraceStore 所有查询按 tenant_id 过滤，跨租户不可见；用量 best-effort 上报 identity。en — `auth/tenant.py` mounts `fusion_core.tenant.install_tenant_middleware` with a fail-closed `verify_jwt` callback calling fusion-identity `POST /api/v1/auth/verify`; `auth/rbac.py` keeps the admin/operator/viewer matrix fed from `TenantContext.role`; `auth/shell_module.py` admits gateway-proxy requests carrying the module key under a synthetic `shell` tenant (key mismatch still 401). All TraceStore queries are scoped by tenant_id, and usage is reported best-effort to identity.

### 度量完整性 / Metric integrity

zh — v0.4.10 (#28) 起所有数字都是实测：TTFT 来自流式首 token 时间戳（`stream: true` + `include_usage`），输出 p50/p95；删除了硬编码的 `elapsed * 0.3` prefill 假设，prefill 速度由 prompt tokens / TTFT 得出（如实含开销的下界）。lm-eval 目录缺失抛 `TasksDirMissingError`，CLI 非零退出。测试数徽章由 `scripts/check_test_count.py` 用 `pytest --collect-only` 重算，CI 禁止漂移。en — since v0.4.10 (#28) every number is measured: TTFT is the timestamped first streamed content token (`stream: true` + `include_usage`) with p50/p95; the fabricated `elapsed * 0.3` prefill assumption was removed and prefill speed derives from prompt tokens / TTFT (an honest overhead-inclusive lower bound). A missing lm-eval directory raises `TasksDirMissingError` and the CLI exits non-zero. The test-count badge is recomputed by `scripts/check_test_count.py` and CI forbids drift.

### Profiler 口径 / Profiler accounting

zh — `engine/profiler.py`（#40）输出唯一模式 `fusion-bench.profiler/v1`，`backend` 键必填；延迟键分引擎侧（`engine_ttft_ms`、`engine_itl_p50_p99`，在 fusion-mlx HTTP 流边界测）与 agent 侧（`agent_e2e_ms`，客户端整墙钟），两组永不合并；内存峰值读 fusion-mlx `/stats`。lightweight 模式默认开；full-trace（每 token ITL）有真实开销，CI 中关闭。en — `engine/profiler.py` (#40) emits the single `fusion-bench.profiler/v1` schema with a mandatory `backend` key; latency keys split engine-side (`engine_ttft_ms`, `engine_itl_p50_p99`, measured at the fusion-mlx HTTP stream boundary) from agent-side (`agent_e2e_ms`, full client wall clock) and are never merged; peak memory reads fusion-mlx `/stats`. Lightweight mode is always on; full-trace per-token ITL has real overhead and stays off in CI.

### 数据与持久化 / Data and persistence

zh — TraceStore（轨迹，带 tenant_id 列，自动迁移）、BenchmarkCache（`~/.fusion-bench/cache.db`）、SxSStore / JudgeStore（`~/.fusion-bench/sxs_runs.db`）都是 SQLite。报告导出 JSON/Markdown/HTML/PDF/Excel，含 5 维雷达图与按模型时间序列趋势图。`reporter/bench_site_db.py` 直写社区站 SQLite（站点前端在独立仓库 bench-site）。en — TraceStore (tenant-scoped, auto-migrated), BenchmarkCache, SxSStore/JudgeStore are all SQLite. Reports export JSON/Markdown/HTML/PDF/Excel with a 5-dimension radar and per-model trend charts. `reporter/bench_site_db.py` writes directly into the community-site SQLite (the site frontend lives in the separate bench-site repo).

## web 控制台 / Web console

zh — `web/`（React 18 + Vite + Tailwind + `@fusion/web-ui`、vendored `@fusion/web-sdk`，零 registry 依赖）产出相对路径 + hash 路由的 `web/dist`，由 FastAPI 应用挂载在 `/`（API 路由先注册，挂载不遮蔽）。嵌入模式下经网关 `/shell/fusion-bench/` 代理，`apiBase()` 从 `window.location.pathname` 推导 fetch 基址，避免子路径 401；UI 不含鉴权逻辑。`web/manifest.json` 由 `shell_registry.py` 在 lifespan 中 POST 给网关并每 15s 心跳，网关宕机只降级不影响 bench 服务。en — `web/` (React 18 + Vite + Tailwind + `@fusion/web-ui`, vendored `@fusion/web-sdk`, zero registry deps) builds a relative-base hash-router bundle mounted by the FastAPI app after API routes. Embedded mode serves it through the gateway `/shell/fusion-bench/` proxy with `apiBase()` derived from `window.location.pathname`; the UI carries no auth logic. `web/manifest.json` is POSTed by `shell_registry.py` on lifespan start with a 15s heartbeat; a down gateway degrades registration only and never takes bench down.

## 执行器清单 / Executors

zh — 已注册：speed（速度/显存）、lm_harness（lm-eval 任务）、tune（参数调优）、quant（量化对比）、security（注入/有害/PII 探针）、agent（多轮工具沙箱 + 轨迹评分）、code（代码生成 pass rate）、artifact、evalscope、bnup（北师大版 K-12 数学四维评测）、laya（laya-mlx 决策端点 6 维基准，404 自动跳过）、arabic（阿语 5 维：翻译 BLEU/chrF、RTL 完整性、理解、STT 往返）、session_slo（agent-studio 长会话 SLO 基线）、dsl_eval / dsl_format（DSL 校验与求值，AST 安全求值器，无 eval/exec）。en — registered: speed, lm_harness, tune, quant, security (injection/harmful/PII), agent (multi-turn tool sandbox + trajectory scoring), code, artifact, evalscope, bnup (4-dimension K-12 math), laya (6-dimension laya-mlx decision benchmark, auto-skip on 404), arabic (5 dimensions: BLEU/chrF translation, RTL integrity, understanding, STT roundtrip), session_slo (agent-studio long-session SLO baselines), dsl_eval / dsl_format (AST-safe evaluator, no eval/exec).

## 依赖关系 / Dependencies

zh — 运行时依赖 fusion-core（>=0.9.0，workspace editable 安装）、fastapi/uvicorn、httpx、pydantic、datasets、jsonschema、sacrebleu、matplotlib、setproctitle；可选 extras：test / pdf / excel / security（garak）/ doc（pdoc）。上游：fusion-mlx（必须）、fusion-gateway（默认路由）、fusion-identity（鉴权必须）、fusion-speech（可选，arabic STT）、fusion-agent-studio（可选，session_slo）。en — runtime deps: fusion-core (>=0.9.0, workspace editable), fastapi/uvicorn, httpx, pydantic, datasets, jsonschema, sacrebleu, matplotlib, setproctitle; optional extras test/pdf/excel/security(garak)/doc(pdoc). Upstream: fusion-mlx (required), fusion-gateway (default routing), fusion-identity (required for auth), fusion-speech (optional, arabic STT), fusion-agent-studio (optional, session_slo).
