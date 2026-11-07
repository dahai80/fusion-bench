---
doc_id: fusion-bench/get-started
product: fusion-bench
class: platform
entry: service
doc_type: get-started
title: { zh: "Fusion-Bench 快速开始", en: "Fusion-Bench Get Started" }
audience: engineer
status: draft
version: 0.4.25
updated: 2026-11-07
owner: "@dahai"
source_of_truth:
  - README.md
  - start.sh
  - pyproject.toml
---

# 快速开始 / Get Started

## 前置条件 / Prerequisites

- zh — macOS + Apple Silicon（M1–M5），Python 3.12+。en — macOS with Apple Silicon (M1–M5), Python 3.12+.
- zh — fusion-mlx 已运行（默认经 fusion-gateway `http://localhost:11432/v1` 访问）。en — fusion-mlx running (reached by default via fusion-gateway at `http://localhost:11432/v1`).
- zh — 需要 JWT 时先启动 fusion-identity 并获取租户 token。en — when JWT is required, start fusion-identity first and obtain a tenant token.

## 安装 / Install

```bash
git clone https://github.com/dahai80/fusion-bench.git
cd fusion-bench
pip install -e ".[test]"
```

## 第一次评测（CLI，无需服务）/ First benchmark (CLI, no service)

```bash
# list available suites and tasks
fusion-bench list-suites
fusion-bench list-tasks

# speed benchmark for one model
fusion-bench speed --model qwen3.5-9b

# run one evaluation task
fusion-bench run mmlu --model qwen3.5-9b
```

zh — CLI 直连 fusion-mlx 做单次评测，不启动 REST 服务。网关是默认路径；直连 `:11434` 需显式 `--direct-mlx`（或 `FUSION_BENCH_DIRECT_MLX=1`），模式会记录在结果 meta 里。
en — the CLI runs one-off benchmarks against fusion-mlx without starting the REST service. The gateway is the default path; direct `:11434` access is explicit opt-in via `--direct-mlx` (or `FUSION_BENCH_DIRECT_MLX=1`), and the mode is recorded in result meta.

## 启动服务 / Start the service

```bash
./start.sh start      # serve API on 127.0.0.1:11467
./start.sh status
./start.sh stop
```

zh — `start.sh` 会：校验端口已在 `port-registry.yaml` 注册（未注册拒绝启动）、按需构建 `web/dist`、生成模块密钥文件 `.fusion-bench-shell-key`（不入库）、注册 union-web shell 菜单（需网关 admin key）。日志写入 `logs/stdout.log` 与 `logs/stderr.log`。
en — `start.sh` verifies the port is registered in `port-registry.yaml` (refuses to start otherwise), builds `web/dist` if missing, generates the module key file `.fusion-bench-shell-key` (untracked) and registers the union-web shell menu (needs the gateway admin key). Logs go to `logs/stdout.log` and `logs/stderr.log`.

## 通过 REST 提交任务 / Submit a task via REST

服务是 fail-closed 的：每个请求都要 `X-Tenant-Id` 和 `Authorization: Bearer`（fusion-identity 签发的 JWT）。

The service is fail-closed: every request needs `X-Tenant-Id` and `Authorization: Bearer` (a JWT issued by fusion-identity).

```bash
curl -X POST http://127.0.0.1:11467/api/v1/tasks \
  -H "X-Tenant-Id: $TID" -H "Authorization: Bearer $JWT" \
  -d '{"model": "qwen3.5-9b", "executor_key": "speed", "level": "L1"}'
```

zh — 返回 `task_id`；用 `GET /api/v1/tasks/{task_id}` 轮询进度，完成后 `GET /api/v1/results/{task_id}` 取结果。完整接口见 [api-reference.md](api-reference.md)。
en — the response carries a `task_id`; poll `GET /api/v1/tasks/{task_id}` for progress and read `GET /api/v1/results/{task_id}` when done. Full surface in [api-reference.md](api-reference.md).

## Python SDK / Python SDK

```python
from fusion_bench.sdk import FusionBenchClient

client = FusionBenchClient(base_url="http://127.0.0.1:11467")
```

zh — SDK 封装全部 `/api/v1/*` 端点，鉴权头由调用方传入。en — the SDK wraps all `/api/v1/*` endpoints; auth headers are supplied by the caller.

## Web 控制台 / Web console

zh — 两种方式：独立开发模式 `cd web && bun install && bun run dev`（vite，端口 11474，代理到 11467）；或嵌入 union-web shell —— 服务启动后经网关 `http://127.0.0.1:11432/shell/fusion-bench/` 访问，鉴权头由 shell 会话注入，UI 本身不含鉴权逻辑。
en — two ways: standalone dev `cd web && bun install && bun run dev` (vite on 11474, proxying to 11467), or embedded in the union-web shell — after the service starts, reach it through the gateway at `http://127.0.0.1:11432/shell/fusion-bench/`; the shell session injects the auth headers and the UI carries no auth logic itself.

## 提交到社区站 / Submit to the community site

zh — 评测结果可直写 bench.dpdns.org 的本地数据库（站点前端在独立仓库 bench-site）。en — results can be written directly into the local database behind bench.dpdns.org (the site frontend lives in the separate bench-site repository).

```python
from fusion_bench.reporter.bench_site_db import BenchSiteDB
db = BenchSiteDB()   # auto-detects bench-site/data/bench.db
```

## 常用 CLI 命令 / Common CLI commands

| Command | zh 说明 / en description |
|---|---|
| `fusion-bench speed --model M` | zh 速度基准。en speed benchmark. |
| `fusion-bench run TASK --model M` | zh 运行单个评测任务。en run a single eval task. |
| `fusion-bench suite NAME --model M` | zh 按套件运行并过质量门禁。en run a suite with quality gates. |
| `fusion-bench tune --model M` | zh 参数自动调优。en auto-tune parameters. |
| `fusion-bench quant --model M` | zh 量化等级对比。en compare quantization levels. |
| `fusion-bench security --model M` | zh 安全探针（注入/有害/PII）。en security probes (injection/harmful/PII). |
| `fusion-bench profile --model M` | zh 推理画像（默认 lightweight 模式）。en inference profiler (lightweight mode by default). |
| `fusion-bench serve --host 127.0.0.1 --port 11467` | zh 启动 REST 服务。en start the REST service. |

zh — 遇到问题先看 [troubleshooting.md](troubleshooting.md)。en — for problems start at [troubleshooting.md](troubleshooting.md).
