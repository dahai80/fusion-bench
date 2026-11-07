---
doc_id: fusion-bench/config-reference
product: fusion-bench
class: platform
entry: service
doc_type: config-reference
title: { zh: "Fusion-Bench 配置参考", en: "Fusion-Bench Config Reference" }
audience: engineer
status: draft
version: 0.4.25
updated: 2026-11-07
owner: "@dahai"
source_of_truth:
  - start.sh
  - fusion_bench/cli.py
  - fusion_bench/api/app.py
  - Dockerfile
  - docker-compose.yml
---

# 配置参考 / Config Reference

zh — Fusion-Bench 没有自有配置文件；配置全部来自环境变量与 CLI 参数，端口注册在 workspace 的 `architecture/port-registry.yaml`（单一事实源）。en — Fusion-Bench has no config file of its own; configuration comes from environment variables and CLI flags, with ports registered in the workspace `architecture/port-registry.yaml` (single source of truth).

## 服务端口 / Ports

| Port | Name | zh 用途 / en purpose |
|---|---|---|
| 11467 | fusion-bench | zh serve REST API（默认绑定 127.0.0.1）。en serve REST API (binds 127.0.0.1 by default). |
| 11468 | fusion-bench-benchsite | zh bench-site 开发服务器（`fusion-bench bench-site dev`），dev-only。en bench-site dev server, dev-only. |
| 11474 | fusion-bench-web | zh web 控制台 vite 开发端口，dev-only；生产由 API 进程挂载 `web/dist` 经网关 `/shell/fusion-bench/` 提供服务，无独立端口。en web console vite dev port, dev-only; in production `web/dist` is mounted by the API process behind the gateway `/shell/fusion-bench/` path with no dedicated port. |
| 11432 | fusion-gateway | zh 依赖：默认 MLX 入口。en dependency: default MLX entry. |
| 11434 | fusion-mlx | zh 依赖：直连模式（显式 opt-in）。en dependency: direct mode (explicit opt-in). |
| 11470 | fusion-identity | zh 依赖：JWT 签发与租户注册表。en dependency: JWT issuer and tenant registry. |

zh — `start.sh start` 启动前自检端口注册；未注册即拒绝启动（`FUSION_SKIP_REGISTRY_CHECK=1` 可绕过并输出 warn，注册文件缺失仅 warn）。en — `start.sh start` self-checks the port registration and refuses to start when unregistered (`FUSION_SKIP_REGISTRY_CHECK=1` bypasses with a warn; a missing registry file only warns).

## 环境变量 / Environment Variables

### 服务本体 / Service itself

| Variable | Default | zh 说明 / en description |
|---|---|---|
| `FUSION_BENCH_HOST` | `127.0.0.1` | zh serve 绑定地址。en serve bind address. |
| `FUSION_BENCH_PORT` | `11467` | zh serve 端口。en serve port. |
| `FUSION_BENCH_LOG_LEVEL` | — | zh 日志级别。en log level. |
| `FUSION_BENCH_DISABLE_UI` | unset | zh 设为 `1` 时不挂载 `web/dist` 静态界面。en set `1` to skip mounting the `web/dist` UI. |
| `FUSION_BENCH_MODEL` | — | zh 默认模型（CLI 兜底）。en default model fallback. |
| `FUSION_BENCH_TLS_ENFORCE` | unset | zh 设为 `1` 启用 TLS 强制中间件。en set `1` to enable TLS-enforcement middleware. |

### 推理与上游依赖 / Inference and upstream deps

| Variable | Default | zh 说明 / en description |
|---|---|---|
| `FUSION_MLX_URL` | `http://localhost:11432/v1` | zh fusion-mlx API 地址（默认走网关）。en fusion-mlx API URL (gateway by default). |
| `FUSION_BENCH_DIRECT_MLX` | unset | zh 设为 `1` 直连 `:11434`（等价 CLI `--direct-mlx`，记录进结果 meta）。en set `1` for direct `:11434` access (same as CLI `--direct-mlx`; recorded in result meta). |
| `FUSION_CLIENT_KEY` / `FUSION_MLX_API_KEY` / `MLX_API_KEY` | — | zh 上游调用密钥解析链（`fusion_core.config.client_key()`），dev 缺失为空串 + 一次性 warn，prod 缺失抛 `RuntimeError`。en client-key alias chain via `fusion_core.config.client_key()`; missing in dev = empty string plus one warn, missing in prod = `RuntimeError`. |
| `FUSION_IDENTITY_URL` | — | zh fusion-identity 服务地址。en fusion-identity base URL. |
| `FUSION_IDENTITY_SERVICE_TOKEN` | — | zh 服务级 token（用量上报等）。en service-level token (usage reporting). |
| `FUSION_SPEECH_URL` | — | zh fusion-speech 地址（arabic 执行器 STT 往返，不可达自动跳过）。en fusion-speech URL (arabic executor STT roundtrip; auto-skipped when unreachable). |
| `FUSION_AGENT_STUDIO_URL` | `http://127.0.0.1:11442` | zh long-session SLO 基线数据源。en long-session SLO telemetry source. |
| `FUSION_AGENT_STUDIO_API_KEY` | — | zh 上述数据源密钥，可被任务 `params` 覆盖。en its API key; overridable per task via `params`. |

### union-web shell 集成 / union-web shell integration

| Variable | Default | zh 说明 / en description |
|---|---|---|
| `FUSION_SHELL_GATEWAY_URL` | `http://127.0.0.1:11432` | zh shell 注册与心跳目标；设置后启用自注册（默认关闭）。en gateway URL for shell registration + heartbeat; setting it enables self-registration (off by default). |
| `FUSION_ADMIN_KEY` | — | zh 网关 admin key；未设置时 `start.sh` 从 `FUSION_GATEWAY_CONFIG`（默认 `~/fusion/fusion-gateway/config.yaml`）读取 `admin_key:`。en gateway admin key; when unset, `start.sh` reads `admin_key:` from `FUSION_GATEWAY_CONFIG` (default `~/fusion/fusion-gateway/config.yaml`). |
| `FUSION_BENCH_SHELL_API_KEY` | 生成的随机值 | zh 模块代理密钥；未设置时 `start.sh` 生成 `fm-bench-` 前缀随机值并持久化到 `.fusion-bench-shell-key`（600 权限，不入库）。en module proxy key; when unset, `start.sh` generates a `fm-bench-` random value persisted to `.fusion-bench-shell-key` (mode 600, untracked). |
| `FUSION_SHELL_MANIFEST` | `web/manifest.json` | zh shell 清单路径覆盖（`fusion_bench/shell_registry.py`）。en manifest path override (`fusion_bench/shell_registry.py`). |
| `FUSION_GATEWAY_CONFIG` | `~/fusion/fusion-gateway/config.yaml` | zh admin key 读取路径。en admin-key config path. |
| `FUSION_REGISTRY` | `~/fusion/architecture/port-registry.yaml` | zh 端口注册表路径。en port registry path. |
| `FUSION_SKIP_REGISTRY_CHECK` | unset | zh 设为 `1` 绕过端口注册自检（输出 warn）。en set `1` to bypass the registry self-check (warns). |

### 开发态 / Dev-only

| Variable | Default | zh 说明 / en description |
|---|---|---|
| `FUSION_DEV_BACKEND` | `http://127.0.0.1:11467` | zh vite 代理后端目标。en vite proxy backend target. |
| `FUSION_BENCH_WEB_PORT` | `11474` | zh vite 开发端口。en vite dev port. |
| `VITE_BENCH_TENANT` / `VITE_BENCH_TOKEN` | — | zh 独立开发模式注入鉴权头（仅开发便利，UI 不含鉴权逻辑）。en standalone-dev auth headers (dev convenience only; the UI ships no auth logic). |

zh — 密钥类值（admin key、module key、client key、JWT）永远不写入仓库；`.fusion-bench-shell-key` 与 `.env` 在 `.gitignore` 中。en — secret values (admin key, module key, client key, JWT) never enter the repository; `.fusion-bench-shell-key` and `.env` are gitignored.

## CLI 全局参数 / CLI global flags

| Flag | Default | zh 说明 / en description |
|---|---|---|
| `--mlx-url` | `http://localhost:11432/v1` | zh fusion-mlx API 地址。en fusion-mlx API URL. |
| `--model` | `qwen3.5-9b` | zh 目标模型。en target model. |
| `--output` | `""` | zh JSON 输出文件路径。en JSON output path. |
| `serve --host / --port` | `127.0.0.1` / `11467` | zh REST 服务绑定。en REST bind address/port. |

## 持久化位置 / Data locations

| Path | zh 内容 / en content |
|---|---|
| `~/.fusion-bench/cache.db` | zh 结果缓存（`fusion-bench cache stats/clear` 管理）。en result cache (managed via `fusion-bench cache`). |
| `~/.fusion-bench/sxs_runs.db` | zh SxS 评审记录。en SxS judge runs. |
| `~/.fusion-bench/` | zh 数据根目录（Docker 中预建并归属非 root 用户）。en data root (pre-created and chowned in Docker). |
| `bench-site/data/bench.db` | zh 社区站数据库（`BenchSiteDB` 自动探测；部署时 rsync 排除，不被覆盖）。en community-site database (auto-detected by `BenchSiteDB`; excluded from deploys). |
| `logs/stdout.log`, `logs/stderr.log` | zh `start.sh` 服务日志。en `start.sh` service logs. |
| `benchmarks/results/`, `benchmarks/testsets/` | zh 已提交的基线结果与可复现测试集。en committed baseline results and reproducible testsets. |

## Docker

zh — `Dockerfile`（python:3.12-slim、非 root、HEALTHCHECK 打 `/api/v1/system/health`、`EXPOSE 11467`）与 `docker-compose.yml`（命名卷挂 `~/.fusion-bench` 与 `~/bench`）。构建可用 `PIP_INDEX_URL` 换镜像源。en — `Dockerfile` (python:3.12-slim, non-root, HEALTHCHECK on `/api/v1/system/health`, `EXPOSE 11467`) and `docker-compose.yml` (named volumes for `~/.fusion-bench` and `~/bench`); pass `PIP_INDEX_URL` to use a mirror at build time.
