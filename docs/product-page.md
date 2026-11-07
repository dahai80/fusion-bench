---
doc_id: fusion-bench/product-page
product: fusion-bench
class: platform
entry: service
doc_type: product-page
title: { zh: "Fusion-Bench 产品页 — MLX 模型评测与调优平台", en: "Fusion-Bench Product Page — MLX Benchmarking and Tuning Platform" }
audience: engineer
status: draft
version: 0.4.25
updated: 2026-11-07
owner: @dahai
source_of_truth:
  - README.md
  - pyproject.toml
  - start.sh
  - fusion_bench/cli.py
---

# Fusion-Bench 产品页 / Product Page

zh: Fusion-Bench 是面向 fusion 生态的模型评测平台（平台类产品，以 HTTP 服务形态提供）。它在 Apple Silicon 上对本地的 MLX 模型做速度、精度、安全、量化、调优五类基准测试，输出可复现的指标，并提供质量门禁、基线对比、轨迹存储与报告导出。版本 0.4.25。

en: Fusion-Bench is the model evaluation platform of the fusion ecosystem (platform-class product, consumed as an HTTP service). It benchmarks local MLX models on Apple Silicon across five benchmark types — speed, accuracy, security, quantization, tuning — with reproducible metrics, plus quality gates, baselines, trace storage and report export. Version 0.4.25.

## 平台定位 / Platform Position

- serves: zh — 为所有需要"模型好不好、快不快、安不安全"结论的 fusion 组件提供统一评测服务（REST API `:11467`）。en — provides the unified evaluation service (REST API on `:11467`) for any fusion component that needs a "how fast / how accurate / how safe" verdict on a model.
- builds_on: zh — fusion-mlx（模型推理，默认经 fusion-gateway `:11432`）、fusion-identity（JWT 签发与租户注册表，fail-closed 校验）、fusion-core（配置 / 客户端密钥 / 进程标题等公共底座）。en — builds on fusion-mlx (inference, by default via fusion-gateway on `:11432`), fusion-identity (JWT issuer + tenant registry, fail-closed verification) and fusion-core (shared config / client-key / process-title base).
- hosts: zh — `serve` REST 服务（127.0.0.1:11467）、web 控制台静态资源（`web/dist`，由 API 进程直接挂载，经网关 `/shell/fusion-bench/` 代理访问）、SQLite 轨迹/缓存/评审库（`~/.fusion-bench/`）。en — hosts the `serve` REST API (127.0.0.1:11467), the web console static bundle (`web/dist`, mounted by the API process, reached through the gateway `/shell/fusion-bench/` proxy) and the SQLite trace/cache/judge stores under `~/.fusion-bench/`.
- integration_surface: zh — REST `/api/v1/*`（任务、套件、结果、门禁、基线、裁判、系统）、Python SDK（`fusion_bench.sdk`，httpx 客户端）、CLI `fusion-bench`、GitHub Action 复合动作（`action.yml`）、union-web shell 模块清单（`web/manifest.json` 自注册）。en — REST `/api/v1/*` (tasks, suites, results, gates, baselines, judges, system), the Python SDK (`fusion_bench.sdk`, httpx client), the `fusion-bench` CLI, a GitHub Action composite action (`action.yml`) and the union-web shell module manifest (`web/manifest.json`, self-registered).
- extension_points: zh — `Registry[T]` 执行器插件（继承 `ExecutorPlugin` 并注册）、自定义套件（`POST /api/v1/suites`）、自定义质量门禁（`POST /api/v1/gates`）、基线播种与差异对比、报告导出器（JSON/MD/HTML/PDF/Excel）。en — `Registry[T]` executor plugins (subclass `ExecutorPlugin` and register), custom suites (`POST /api/v1/suites`), custom quality gates (`POST /api/v1/gates`), baseline seeding with delta comparison, and report exporters (JSON/MD/HTML/PDF/Excel).

## 能力清单 / Capabilities

每个能力都回答"消费方不用再自己写什么"，并给出边界约束。/ Each capability states what the consumer no longer has to write, plus its constraint.

| Capability | Consumer no longer writes | Constraint / Limit |
|---|---|---|
| zh — 五类基准执行（speed / accuracy / security / quant / tune）。en — Five benchmark executors (speed / accuracy / security / quant / tune). | zh — 不用再写流式 TTFT 统计、Metal 显存监控、lm-eval 适配层、安全探针集。en — no streaming TTFT accounting, Metal memory monitor, lm-eval adapter layer or security probe sets. | zh — 评测对象必须是 fusion-mlx HTTP API 可达的模型；lm-eval 任务需要本地存在 lm-evaluation-harness 目录（缺失时 `TasksDirMissingError` 直接报错，不静默返回空）。en — the target must be reachable through the fusion-mlx HTTP API; lm-eval tasks need a local lm-evaluation-harness directory (missing dir raises `TasksDirMissingError`, it never returns empty results silently). |
| zh — 质量门禁（三级：experimental / business / production）。en — Three-tier quality gates (experimental / business / production). | zh — 不用再写阈值判定、失败 webhook、人工审批流。en — no threshold evaluation, failure webhooks or manual approval flow. | zh — production 级门禁被拦截时必须显式审批（`POST /api/v1/gates/{id}/approve`）才能放行；webhook 需要 HMAC 密钥配置。en — a blocked production gate must be explicitly approved (`POST /api/v1/gates/{id}/approve`) before release; webhooks need an HMAC secret configured. |
| zh — 租户隔离与鉴权。en — Tenant isolation and auth. | zh — 不用再实现 JWT 校验、租户头检查、跨租户数据隔离、角色权限矩阵。en — no JWT verification, tenant header checks, cross-tenant data isolation or role permission matrix. | zh — fail-closed：缺 `X-Tenant-Id`、token 无效或 `jwt.tid` 与头不一致一律 401，没有默认租户降级；JWT 必须由 fusion-identity 签发（默认 `:11470`）。en — fail-closed: missing `X-Tenant-Id`, an invalid token or a `jwt.tid`/header mismatch all return 401 with no default-tenant fallback; JWTs must come from fusion-identity (default `:11470`). |
| zh — 轨迹存储与结果缓存。en — Trace store and result cache. | zh — 不用再写 SQLite 表结构、按租户 scoped 的查询、缓存命中逻辑。en — no SQLite schemas, tenant-scoped queries or cache-hit logic. | zh — 轨迹库与缓存都在本机 `~/.fusion-bench/`，没有内建跨节点同步；缓存 key 含模型/配置/任务，`cache clear` 按需清理。en — both stores live in local `~/.fusion-bench/` with no built-in cross-node sync; cache keys include model/config/task and `cache clear` removes entries on demand. |
| zh — 推理画像（profiler）。en — Inference profiler. | zh — 不用再区分引擎侧与 agent 侧延迟口径，也不用写 per-token ITL 采样。en — no need to split engine-side vs agent-side latency accounting or sample per-token ITL. | zh — 输出固定为 `fusion-bench.profiler/v1` 模式，`backend` 键必填，引擎侧与 agent 侧延迟键永不合并；full-trace 模式有真实每 token 开销，CI 中保持关闭。en — output is fixed to the `fusion-bench.profiler/v1` schema with a mandatory `backend` key; engine-side and agent-side latency keys are never merged; full-trace mode has real per-token overhead and stays off in CI. |
| zh — LLM-as-Judge 与 SxS 双盲评审。en — LLM-as-Judge and double-blind SxS review. | zh — 不用再写评审提示词、位置偏差消除（seeded A/B 洗牌）、胜/负/平聚合与持久化。en — no judge prompts, position-bias removal (seeded A/B shuffle), win/loss/tie aggregation or persistence. | zh — SxS REST 面仅 `POST /api/v1/judges/sxs/run` 与 `GET /api/v1/judges/sxs/runs`，运行记录存 `~/.fusion-bench/sxs_runs.db`；评审模型本身也要占用推理资源。en — the SxS REST surface is only `POST /api/v1/judges/sxs/run` and `GET /api/v1/judges/sxs/runs`, persisted in `~/.fusion-bench/sxs_runs.db`; the judge model itself consumes inference capacity. |
| zh — 报告与社区站提交。en — Reporting and community-site submission. | zh — 不用再写 JSON/MD/HTML/PDF/Excel 导出、雷达图/趋势图、以及向 bench.dpdns.org 数据库写入记录的代码。en — no JSON/MD/HTML/PDF/Excel exporters, radar/trend charts, or code to write records into the bench.dpdns.org database. | zh — 站点提交走 `BenchSiteDB` 直写本地 bench-site SQLite；站点本身是独立仓库（GitHub `bench-site`），本仓库不维护其前端代码。en — site submission goes through `BenchSiteDB` direct writes into the local bench-site SQLite; the site itself is a separate repository (GitHub `bench-site`) whose frontend is not maintained here. |

## 边界 / Non-Goals

zh — Fusion-Bench 不做模型训练（fusion-trainer）、不托管模型文件（fusion-model-hub）、不替代 lm-evaluation-harness 的任务定义、不做云端服务（100% 本地离线，HTTP 仅访问 127.0.0.1）。Ascend NPU 后端不在画像范围内。

en — Fusion-Bench does not train models (fusion-trainer), does not host model files (fusion-model-hub), does not replace lm-evaluation-harness task definitions, and ships no cloud service (100% local-offline; HTTP only to 127.0.0.1). Ascend NPU backends are out of scope for the profiler.

## 快速入口 / Entry Points

- zh — 首次接入：[get-started.md](get-started.md)。en — first integration: [get-started.md](get-started.md).
- zh — REST 接口：[api-reference.md](api-reference.md)。en — REST surface: [api-reference.md](api-reference.md).
- zh — 环境变量与端口：[config-reference.md](config-reference.md)。en — env vars and ports: [config-reference.md](config-reference.md).
- zh — 故障排查：[troubleshooting.md](troubleshooting.md)。en — troubleshooting: [troubleshooting.md](troubleshooting.md).
