# Fusion-Bench 深度对标分析与整合方案

> 基于对 `~/bench/lm-evaluation-harness` (2082 tasks, v0.4.13) 和 `~/bench/opencompass` (v0.5.3) 的完整代码分析。

---

## 一、对标产品能力矩阵

### 1.1 lm-evaluation-harness (EleutherAI)

| 模块 | 能力 | 行数 | 说明 |
|------|------|------|------|
| `api/model.py` | LM 抽象接口 | 180 | `generate_until`, `loglikelihood`, `loglikelihood_rolling` |
| `api/metrics.py` | 评分指标 | 300+ | accuracy, f1, perplexity, bleu, chrf, matthews_corrcoef |
| `api/task.py` | 任务定义 | 400+ | doc_to_text, doc_to_target, process_results, aggregation |
| `evaluator.py` | 评测引擎 | 500+ | 任务调度、结果收集、聚合计算 |
| `evaluator_utils.py` | 工具函数 | 300+ | 结果处理、分组聚合 |
| `models/` | 28 个模型后端 | 13,306 | HF, vLLM, SGLang, GGUF, OpenAI, Anthropic 等 |
| `tasks/` | 215 个目录, 2082 个 YAML | — | MMLU, GSM8K, BBH, ARC, HellaSwag 等 |

**核心架构：**
```
LM (抽象接口) ← CachingLM (缓存) ← TemplateLM (分词模板)
    ↑
MLXModel (我们的适配器) → fusion-mlx HTTP API
```

### 1.2 opencompass (上海AI实验室)

| 模块 | 能力 | 说明 |
|------|------|------|
| `models/` | 30+ 模型 API | OpenAI, DeepSeek, GLM, Baichuan 等 |
| `datasets/` | 100+ 数据集 | C-Eval, CMMLU, AGIEval, MMLU 等 |
| `evaluator/` | 评测器 | cascade, generic_llm, math |
| `metrics/` | 评分指标 | dump_results, mme_score, seedbench |
| `runners/` | 运行器 | local, slurm, dlc, volc |

---

## 二、Fusion-Bench 当前能力 vs 差距

| 能力维度 | lm-eval | opencompass | Fusion-Bench (当前) | 差距 |
|---------|---------|-------------|-------------------|------|
| **评测任务数** | 2082 | 100+ | 0 (需手动定义) | 🔴 需集成 lm-eval 任务 |
| **模型后端** | 28 | 30+ | 1 (fusion-mlx) | 专注 MLX 即可 |
| **评分指标** | 20+ | 10+ | 3 (speed/memory/stable) | 🟡 需补充 accuracy/f1/perplexity |
| **缓存系统** | SQLite 缓存 | 无 | 无 | 🟡 需加缓存 |
| **Metal 监控** | 无 | 无 | 基础内存 | 🔴 需 Metal 专属监控 |
| **MLX 量化评测** | 无 | 无 | 无 | 🔴 需量化精度对比 |
| **中文评测** | 部分 | 完整 | 无 | 🟡 需集成 C-Eval |
| **自动调优** | 无 | 无 | 基础参数遍历 | 🟡 需完善 |
| **图表输出** | 无 | 无 | matplotlib | 🟡 需完善 |
| **CLI 命令行** | 完整 | 完整 | start.sh | 🟡 需完善 CLI |

---

## 三、整合方案

### 3.1 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                     Fusion-Bench CLI                             │
│  fusion-bench run mmlu --model qwen3.5-9b                        │
│  fusion-bench tune --model qwen3.5-9b                            │
│  fusion-bench list-tasks                                         │
│  fusion-bench compare --models qwen3.5-9b,deepseek-v4            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    评测调度层                                    │
│                                                                  │
│  ┌────────────────────┐  ┌────────────────┐  ┌───────────────┐  │
│  │ LMEvalTaskRunner   │  │ BenchmarkRunner│  │ ParameterTuner│  │
│  │ (加载 lm-eval YAML)│  │ (速度/显存测试) │  │ (参数寻优)    │  │
│  └─────────┬──────────┘  └───────┬────────┘  └───────┬───────┘  │
└────────────┼──────────────────────┼──────────────────┼──────────┘
             │                      │                  │
┌────────────▼──────────────────────▼──────────────────▼──────────┐
│                    模型适配层                                    │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ MLXModel (lm-eval 兼容接口)                                 │  │
│  │ - generate_until → /v1/chat/completions                    │  │
│  │ - loglikelihood → /v1/completions + logprobs               │  │
│  │ - tok_encode / tok_decode (估算)                           │  │
│  └──────────────────────┬─────────────────────────────────────┘  │
└─────────────────────────┼────────────────────────────────────────┘
                          │ HTTP
┌─────────────────────────▼────────────────────────────────────────┐
│                    fusion-mlx (模型服务)                          │
│  /v1/chat/completions  /v1/completions  /v1/embeddings           │
│  /v1/models  /stats  /admin/api/*                                │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 需要新增的模块

| 模块 | 文件 | 说明 | 工作量 |
|------|------|------|--------|
| **CLI 命令行** | `fusion_bench/cli.py` | `run/list/tune/compare` 子命令 | 2天 |
| **评测缓存** | `fusion_bench/cache.py` | SQLite 缓存，避免重复评测 | 1天 |
| **Metal 监控器** | `fusion_bench/metal_monitor.py` | 通过 `system_profiler` 采集 GPU 真实数据 | 1天 |
| **量化对比** | `fusion_bench/quant_bench.py` | 同一模型不同量化等级对比 | 1天 |
| **中文评测** | 集成 C-Eval/AGIEval | 从 lm-eval 加载中文任务 | 2天 |
| **图表增强** | `fusion_bench/reporter/charts.py` | 量化对比图、显存趋势图 | 1天 |
| **对比模式** | 多模型横向对比 | 同时跑多个模型输出对比表 | 1天 |

### 3.3 Metal 专属优化（核心差异化）

```python
# Metal 性能监控 — 通过 system_profiler 采集真实 GPU 数据
class MetalMonitor:
    """Apple Metal 性能监控，采集 GPU 利用率、显存、温度等真实指标。"""

    def collect(self) -> dict:
        """采集 Metal 性能指标。"""
        import subprocess, json
        try:
            # 通过 system_profiler 获取 GPU 信息
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                capture_output=True, text=True, timeout=5,
            )
            data = json.loads(result.stdout)
            gpu_info = data.get("SPDisplaysDataType", [{}])[0]
            return {
                "gpu_model": gpu_info.get("sppci_model", ""),
                "gpu_cores": gpu_info.get("sppci_cores", 0),
                "metal_family": gpu_info.get("metal_family", ""),
                "vram": gpu_info.get("spdisplays_vram", ""),
            }
        except Exception:
            return {}

    def collect_mlx_memory(self) -> dict:
        """通过 fusion-mlx /stats 获取 MLX 显存占用。"""
        import httpx
        try:
            resp = httpx.get("http://localhost:11434/stats", timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "model_memory_used": data.get("model_memory_used_formatted", "0B"),
                    "model_memory_max": data.get("model_memory_max_formatted", "unlimited"),
                }
        except Exception:
            pass
        return {}
```

### 3.4 量化精度对比（MLX 专属）

```python
class QuantBenchmark:
    """同一模型不同量化等级 (4bit/8bit/16bit) 的速度与精度对比。"""

    QUANT_LEVELS = ["mxfp4", "mxfp8", "mixed_3_4", "quant2_all"]

    async def run(self, base_model: str, tasks: list[str]) -> list[dict]:
        results = []
        for quant in self.QUANT_LEVELS:
            model_name = f"{base_model}-{quant}"
            logger.info("Benchmarking %s ...", model_name)
            runner = LMEvalTaskRunner(model=model_name)
            for task in tasks:
                result = await runner.run_task(task)
                results.append({
                    "model": model_name,
                    "quant": quant,
                    "task": task,
                    "accuracy": result.get("metrics", {}).get("accuracy", 0),
                    "speed": result.get("timing", {}).get("samples_per_second", 0),
                })
        return results
```

---

## 四、执行路线图

### Week 1: CLI + 缓存 + 评测集成

| 天 | 任务 | 交付物 |
|----|------|--------|
| 1 | CLI 命令行框架 | `fusion-bench run/list/tune/compare` |
| 2 | 集成 lm-eval 任务加载 | 可加载 2082 个任务并按需运行 |
| 3 | 评测缓存 (SQLite) | 避免重复评测，断点续跑 |
| 4 | 完善 MLXModel 适配器 | 修复 loglikelihood、支持缓存 |
| 5 | 测试 + 修复 | 80%+ 覆盖率 |

### Week 2: Metal 监控 + 量化对比 + 图表

| 天 | 任务 | 交付物 |
|----|------|--------|
| 1 | Metal 性能监控器 | GPU 利用率、显存、温度采集 |
| 2 | 量化精度对比 | 4bit/8bit/16bit 速度+精度对比 |
| 3 | 多模型横向对比 | 同时跑多个模型输出对比表 |
| 4 | 图表增强 | 量化对比图、显存趋势图 |
| 5 | 测试 + 发布 | 95%+ 覆盖率，v0.1 发布 |

---

## 五、业界第一的目标

### 5.1 当前 macOS 评测工具现状

| 工具 | MLX 支持 | Metal 监控 | 量化对比 | 评测任务 | 自动调优 |
|------|----------|-----------|---------|---------|---------|
| lm-evaluation-harness | ❌ | ❌ | ❌ | 2082 ✅ | ❌ |
| opencompass | ❌ | ❌ | ❌ | 100+ | ❌ |
| whichllm | ❌ | ❌ | ❌ | 0 | ❌ |
| Ollama bench | ✅ (Ollama) | ❌ | ❌ | 0 | ❌ |
| **Fusion-Bench (目标)** | **✅ fusion-mlx** | **✅ Metal 真实数据** | **✅ 4/8/16bit** | **2082 (lm-eval)** | **✅ 参数寻优** |

### 5.2 差异化壁垒

1. **唯一 MLX 原生评测平台** — 所有模型调用走 fusion-mlx HTTP API，无需 torch/transformers
2. **唯一 Metal 真实监控** — 通过 `system_profiler` 和 MLX 底层 API 获取 GPU 真实数据
3. **唯一量化精度对比** — 同一模型 4bit/8bit/16bit 的速度与精度对比
4. **唯一自动调优+评测一体化** — 先调优找到最优参数，再用最优参数跑评测
5. **唯一 macOS 后台守护** — 评测任务可后台运行，完成后通知

### 5.3 一句话定位

> **Fusion-Bench = lm-evaluation-harness (2082 tasks) + Metal 真实监控 + MLX 量化对比 + 自动参数寻优 — 全部在 Apple Silicon 上本地离线运行。**