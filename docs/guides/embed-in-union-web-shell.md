---
doc_id: fusion-bench/embed-in-union-web-shell
product: fusion-bench
class: platform
entry: service
doc_type: guide
title: { zh: "指南：嵌入 union-web shell", en: "Guide: Embedding in the union-web shell" }
audience: engineer
status: draft
version: 0.4.25
updated: 2026-11-07
owner: "@dahai"
source_of_truth:
  - start.sh
  - fusion_bench/shell_registry.py
  - web/manifest.json
  - fusion_bench/auth/shell_module.py
---

# 嵌入 union-web shell / Embed in the union-web shell

zh — 本指南把 fusion-bench 的 web 控制台接入 union-web shell（fusion-gateway `:11432` 统一菜单）。en — this guide wires the fusion-bench web console into the union-web shell (unified menu behind fusion-gateway on `:11432`).

## 步骤 / Steps

1. zh — 确认清单 `web/manifest.json`：`category: governance`、标题"模型评测"/"Bench"、`upstream: http://127.0.0.1:11467`、`api_key_env: FUSION_BENCH_SHELL_API_KEY`。en — check `web/manifest.json`: `category: governance`, title "模型评测"/"Bench", `upstream: http://127.0.0.1:11467`, `api_key_env: FUSION_BENCH_SHELL_API_KEY`.
2. zh — 启动服务 `./start.sh start`。脚本会：生成并持久化模块密钥 `.fusion-bench-shell-key`（600 权限）、按需构建 `web/dist`、以 `FUSION_SHELL_GATEWAY_URL`（默认 `http://127.0.0.1:11432`）+ 网关 admin key 注册清单并每 15 秒心跳。en — run `./start.sh start`. The script generates and persists the module key `.fusion-bench-shell-key` (mode 600), builds `web/dist` when missing, and registers the manifest with `FUSION_SHELL_GATEWAY_URL` (default `http://127.0.0.1:11432`) plus the gateway admin key, heartbeating every 15 seconds.
3. zh — admin key 解析顺序：`FUSION_ADMIN_KEY` 环境变量 > `FUSION_GATEWAY_CONFIG` 指向文件里的 `admin_key:`（默认 `~/fusion/fusion-gateway/config.yaml`）。两者都没有时注册保持关闭（静默）。en — admin-key resolution: the `FUSION_ADMIN_KEY` env var wins, else the `admin_key:` line from `FUSION_GATEWAY_CONFIG` (default `~/fusion/fusion-gateway/config.yaml`). With neither, registration stays silently off.
4. zh — 打开 `http://127.0.0.1:11432/shell/fusion-bench/`。网关把请求代理到 11467，注入模块 Bearer；服务端 `auth/shell_module.py` 合成 `shell` 租户放行。en — open `http://127.0.0.1:11432/shell/fusion-bench/`. The gateway proxies to 11467 and injects the module bearer; `auth/shell_module.py` admits it under the synthetic `shell` tenant.

## 消费方不用再写什么 / What the consumer no longer writes

zh — 不用写网关静态路由（动态注册携带 upstream）、不用管理模块密钥分发、不用实现菜单心跳与灰点逻辑、不用在 UI 里做鉴权。en — no static gateway routes (dynamic registration carries the upstream), no module-key distribution, no menu heartbeat/gray-dot logic, and no auth in the UI.

## 约束 / Constraints

zh — 网关心跳 30 秒过期，进程重启必须经 `start.sh`（或等价 env 注入）否则菜单项消失；模块密钥文件不入库，换机器要重新生成并重新注册；网关宕机只影响菜单与代理，bench API `:11467` 照常可用。en — the gateway heartbeat expires after 30 seconds, so process restarts must go through `start.sh` (or equivalent env injection) or the menu entry disappears; the module key file is untracked and regenerates per machine; a down gateway affects only the menu and proxy — the bench API on `:11467` stays available.

zh — 相关故障见 [troubleshooting.md](../troubleshooting.md) 的 401 与嵌入界面小节。en — related failures are covered in the 401 and embedded-UI sections of [troubleshooting.md](../troubleshooting.md).
