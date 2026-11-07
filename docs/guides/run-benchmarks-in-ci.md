---
doc_id: fusion-bench/run-benchmarks-in-ci
product: fusion-bench
class: platform
entry: service
doc_type: guide
title: { zh: "指南：在 CI 中跑基准", en: "Guide: Running benchmarks in CI" }
audience: engineer
status: draft
version: 0.4.25
updated: 2026-11-07
owner: "@dahai"
source_of_truth:
  - .github/action.yml
  - fusion_bench/cicd/github_action.py
  - .github/workflows/ci.yml
---

# 在 CI 中跑基准 / Run benchmarks in CI

zh — fusion-bench 提供根目录复合动作 `action.yml`，在 GitHub Actions 工作流里对 PR 跑基准并回传结果。en — the repo-root composite action `action.yml` runs benchmarks inside a GitHub Actions workflow and reports results back.

## 用法 / Usage

```yaml
- uses: dahai80/fusion-bench@main
  with:
    base-url: http://127.0.0.1:11467
```

zh — 具体输入以 `action.yml` 为准（`base-url` 默认 `http://127.0.0.1:11467`）；动作实现位于 `fusion_bench/cicd/github_action.py`。en — see `action.yml` for the exact inputs (`base-url` defaults to `http://127.0.0.1:11467`); the implementation lives in `fusion_bench/cicd/github_action.py`.

## 消费方不用再写什么 / What the consumer no longer writes

zh — 不用写安装与缓存步骤、不用拼 curl 提交结果、不用处理结果格式转换。en — no install/cache steps, no hand-rolled result submission via curl, no result-format conversion.

## 约束 / Constraints

zh — CI 环境没有 Apple Silicon GPU 时只能跑代理到远端 fusion-mlx 的模式（`base-url` 指向可达的推理服务）；profiler full-trace 模式有真实开销，CI 中保持关闭；`--enable-full-profile` 不要出现在 CI 命令里。本仓库自身 CI（`.github/workflows/ci.yml`）只做 lint + 全量测试 + 测试数漂移守卫，不在 GitHub runner 上跑模型评测。en — without Apple Silicon hardware the CI runner must proxy to a reachable inference service via `base-url`; the profiler full-trace mode has real per-token overhead and stays off in CI (never pass `--enable-full-profile`). This repo's own CI (`.github/workflows/ci.yml`) runs lint, the full test suite and the test-count drift guard only — no model evaluation on GitHub runners.
