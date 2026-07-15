<div align="center">

# Fusion-Bench

**MLX 模型性能评测与自动调优工作台**

在 Apple Silicon 上本地运行、评测和自动调优 AI 模型——完全离线，数据不出设备。

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-122-success.svg)](tests/)

[English](README.md) · [快速开始](#快速开始) · [CLI 参考](#cli-参考) · [架构](#架构) · [文档](docs/)

</div>

---

## 为什么选择 Fusion-Bench？

| 特性 | Fusion-Bench | lm-eval-harness | opencompass |
|------|-------------|-----------------|-------------|
| **MLX 原生** | ✅ fusion-mlx API | ❌ torch/HF | ❌ torch/HF |
| **Apple Silicon 优化** | ✅ Metal 监控 | ❌ | ❌ |
| **量化对比** | ✅ 4/8/16-bit | ❌ | ❌ |
| **自动参数调优** | ✅ | ❌ | ❌ |
| **评测任务** | 2082 (兼容 lm-eval) | 2082 | 100+ |
| **本地离线** | ✅ 100% | ✅ | ✅ |
| **bench.dpdns.org 集成** | ✅ 直接写入数据库 | ❌ | ❌ |

**一句话：** Fusion-Bench 是在 Apple Silicon 上评测和调优 MLX 模型的最快方式——直接集成 [bench.dpdns.org](https://bench.dpdns.org)。

---

## 快速开始

### 前置条件

- macOS Apple Silicon (M1–M5)
- Python 3.12+
- [fusion-mlx](https://github.com/dahai80/fusion-mlx) 运行在 `localhost:11434`

### 安装

```bash
git clone https://github.com/dahai80/fusion-bench.git
cd fusion-bench
pip install -e ".[test]"
```

### 运行评测

```bash
# 列出可用任务
fusion-bench list-tasks

# 测试模型速度
fusion-bench speed --model qwen3.5-9b

# 运行评测任务（需要 lm-evaluation-harness）
fusion-bench run mmlu --model qwen3.5-9b

# 自动调优模型参数
fusion-bench tune --model qwen3.5-9b

# 多模型对比
fusion-bench compare --models qwen3.5-9b,deepseek-v4 --tasks mmlu,gsm8k

# 量化等级对比
fusion-bench quant --model qwen3.5-9b
```

### 提交结果到 bench.dpdns.org

```python
from fusion_bench.reporter.bench_site_db import BenchSiteDB
from fusion_bench.engine.benchmark import BenchmarkRunner

import asyncio

async def main():
    # 1. 运行评测
    runner = BenchmarkRunner()
    results = await runner.benchmark("qwen3.5-9b")
    
    # 2. 直接写入 bench-site 数据库
    db = BenchSiteDB()
    for r in results:
        db.insert_from_benchmark(r)
    
    # 3. 结果立即可见: https://bench.dpdns.org
    print(f"已提交! 统计: {db.stats()}")

asyncio.run(main())
```

---

## CLI 参考

| 命令 | 说明 |
|------|------|
| `fusion-bench list-tasks [--pattern]` | 列出可用评测任务 |
| `fusion-bench run <task> [--model] [--max-samples]` | 运行评测任务 |
| `fusion-bench tune [--model] [--max-combinations]` | 自动调优模型参数 |
| `fusion-bench compare --models <m1,m2> [--tasks]` | 多模型对比 |
| `fusion-bench speed [--model] [--runs]` | 测试模型速度 |
| `fusion-bench quant [--model] [--levels]` | 量化等级对比 |

### 选项

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--mlx-url` | `http://localhost:11434/v1` | fusion-mlx API 地址 |
| `--model` | `qwen3.5-9b` | 模型名称 |
| `--output` | `""` | 输出文件路径 (JSON) |

---

## 架构

```
┌───────────────────────────────────────────────────────────────┐
│                      Fusion-Bench CLI                          │
│  run · list-tasks · tune · compare · speed · quant             │
└───────────────────────────┬───────────────────────────────────┘
                            │
┌───────────────────────────▼───────────────────────────────────┐
│                   评测引擎层                                    │
│  ┌────────────────┐  ┌────────────────┐  ┌─────────────────┐  │
│  │ LMEvalTaskRunner│  │ BenchmarkRunner│  │ ParameterTuner  │  │
│  │ (2082 个任务)   │  │ (速度/显存)    │  │ (自动调优)      │  │
│  └───────┬────────┘  └───────┬────────┘  └────────┬────────┘  │
└──────────┼──────────────────┼─────────────────────┼────────────┘
           │                  │                     │
┌──────────▼──────────────────▼─────────────────────▼────────────┐
│                    MLXModel 适配器                               │
│  generate_until · loglikelihood · tok_encode/decode             │
│           ↓ HTTP API（不直接调用 MLX）                          │
└────────────────────────────────────────────────────────────────┘
           │
┌──────────▼────────────────────────────────────────────────────┐
│  fusion-mlx (/v1/chat/completions, /v1/completions, /v1/models)│
│           ↓                                                    │
│  Apple Silicon MLX 运行时 (Metal GPU)                          │
└────────────────────────────────────────────────────────────────┘
```

### 核心模块

| 模块 | 文件 | 说明 |
|------|------|------|
| 评测引擎 | `engine/benchmark.py` | 速度/显存/稳定性/最大上下文探测 |
| 任务运行器 | `engine/task_runner.py` | 加载 lm-eval 任务 (2082 个) |
| Metal 监控 | `engine/metal_monitor.py` | 通过 system_profiler 采集 GPU 数据 |
| MLX 适配器 | `adapters/mlx_model.py` | lm-eval 兼容模型接口 |
| 参数调优 | `optimizer/tuner.py` | 自动遍历 batch/tokens/temperature |
| 量化对比 | `optimizer/quant_bench.py` | 多量化等级速度/精度对比 |
| 报表生成 | `reporter/report.py` | JSON/Markdown/图表/配置模板 |
| BenchSite 数据库 | `reporter/bench_site_db.py` | 直接写入 bench.dpdns.org 数据库 |
| 缓存 | `cache.py` | SQLite 评测缓存 |
| CLI | `cli.py` | 命令行接口 |

---

## 与 bench.dpdns.org 集成

Fusion-Bench 将评测结果直接写入 [bench.dpdns.org](https://bench.dpdns.org) 的数据库。运行评测后，结果立即可在网站上查看。

```python
from fusion_bench.reporter.bench_site_db import BenchSiteDB

db = BenchSiteDB()
db.insert_from_metrics(metrics, model_name="qwen3.5-9b", quantization="mxfp4")
# → https://bench.dpdns.org/benchmarks/{id}
```

---

## 开发

```bash
# 安装开发依赖
pip install -e ".[test]"

# 运行测试
pytest tests/

# 带覆盖率运行
pytest tests/ --cov=fusion_bench
```

### 测试统计
- **122 个测试**, 0 失败
- **核心模块 96%+** 语句覆盖率
- **Python 3.12+** 兼容

---

## 对比

| 维度 | lm-eval-harness | opencompass | **Fusion-Bench** |
|------|----------------|-------------|-----------------|
| MLX 原生 | ❌ torch/HF | ❌ torch/HF | ✅ fusion-mlx API |
| Metal 监控 | ❌ | ❌ | ✅ system_profiler |
| 量化对比 | ❌ | ❌ | ✅ 4/8/16-bit |
| 自动调优 | ❌ | ❌ | ✅ |
| 评测任务 | 2082 | 100+ | 2082 (兼容) |
| 本地离线 | ✅ | ✅ | ✅ 100% |
| bench.dpdns.org | ❌ | ❌ | ✅ 直接写入数据库 |

---

## 许可证

MIT

## 致谢

- [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness) — 评测框架参考
- [fusion-mlx](https://github.com/dahai80/fusion-mlx) — Apple Silicon 模型服务
- [bench.dpdns.org](https://bench.dpdns.org) — 社区评测平台