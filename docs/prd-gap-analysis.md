# Fusion-Bench PRD Gap Analysis

**Date**: 2026-07-26 (Updated)
**Current Version**: v0.2.0
**PRD Version**: v1.0 (ar.md)

---

## 一、总体差距概览

| 维度 | PRD 要求 | 当前实现 | 差距等级 |
|------|---------|---------|---------|
| 四级评测体系 | L1+L2+L3+L4 | L1+L2+L3+L4 全部实现 | 🟢 已完成 |
| 执行器插件数 | 10+ | 11 (speed/lm_harness/quant/security/tune/opencompass/agent/code/artifact/evalscope/helm/garak) | 🟢 已完成 |
| 功能需求 (FR) | 30 项 | ~25 项已实现 | 🟡 小差距 |
| 非功能需求 (NFR) | 16 项 | ~12 项已满足 | 🟡 小差距 |
| REST API | 20+ 接口 | 45+ 端点 (任务/套件/结果/门禁/基线/调度/数据集/裁判/审批/备份/GPU/SSE/审计) | 🟢 已完成 |
| Web 控制台 | 集成于 fusion-studio | bench-site + 对比页 | 🟡 中等 |
| 质量门禁 | 三级门禁 + 审批流 | 三级门禁 + 审批流 + Webhook | 🟢 已完成 |
| 分布式执行 | multi-node 集群 | TaskDistributor ABC + LocalDistributor | 🟡 框架就绪 |
| 企业级管控 | RBAC/多租户/审计 | RBAC + 审计日志 + 熔断器 | 🟡 核心就绪 |

**版本定位**: 当前 v0.2.0 已达到 PRD v0.5 Beta (M3) 阶段，接近 v1.0 GA。

---

## 二、四级评测体系差距

### L1 模型层 — 已完成 (~90%)

| 子维度 | PRD 要求 | 当前状态 | 差距 |
|--------|---------|---------|------|
| 通用语言能力 | lm-eval-harness + OpenCompass | ✅ LMHarnessExecutor + OpenCompassExecutor | 基本完整 |
| 中文专项能力 | OpenCompass C-Eval/CMMLU | ✅ OpenCompassExecutor | 已集成 |
| 多维度综合评估 | HELM | ✅ HelmAdapter | 已集成 |
| 代码基础能力 | HumanEval/MBPP | ✅ CodeExecutor (L3) + lm-eval YAML | 已实现 |
| 安全对齐能力 | Garak + PyRIT | ✅ SecurityExecutor + GarakExecutor | Garak 深度集成完成 |
| 性能指标 | 速度/内存/Metal | ✅ SpeedExecutor + BenchmarkRunner + MetalMonitor | 完整 |
| EvalScope | 阿里评测 | ✅ EvalScopeExecutor | 已集成 |

### L2 Agent 层 — 已实现 (~70%)

| 子维度 | PRD 要求 | 当前状态 |
|--------|---------|---------|
| 多步任务完成率 | AgentBench | ✅ AgentExecutor (3 默认场景) |
| 工具调用能力 | AgentBench | ✅ AgentExecutor (tool-selection 场景) |
| 规划与反思能力 | AgentCompass | 🟡 基础实现 |
| 环境交互能力 | AgentBench | 🟡 基础实现 |
| 容错与鲁棒性 | 自定义评测集 | ✅ 支持自定义场景 |
| 效率指标 | 统计插件 | 🟡 基础统计 |

### L3 应用层 — 已实现 (~60%)

| 子维度 | PRD 要求 | 当前状态 |
|--------|---------|---------|
| 代码研发场景 | SWE-bench/FullStackBench | ✅ CodeExecutor (3 默认用例, 无 exec/eval) |
| 代码安全场景 | 安全评测集 + SWE-bench 安全子集 | 🟡 SecurityExecutor + GarakExecutor |
| 通用对话场景 | 自定义评测集 + HELM | ✅ DatasetStore + HelmAdapter |
| 安全红队场景 | Garak/PyRIT | ✅ GarakExecutor (JSONL 解析 + 结构化结果) |

### L4 产物层 — 已实现 (~60%)

| 子维度 | PRD 要求 | 当前状态 |
|--------|---------|---------|
| 正确性 | 自动化校验 + LLM裁判 + 人工复核 | ✅ ArtifactExecutor (auto_check: json_valid/contains/min_length/regex) + JudgeStore |
| 合规性 | 内容安全扫描 + 规则校验 | ✅ ArtifactExecutor criteria 机制 |
| 可用性 | 规则校验 + 业务指标关联 | 🟡 基础 criteria |
| 风格一致性 | 风格匹配度检测 | 🟡 基础 regex 匹配 |

---

## 三、功能需求 (FR) 实现状态

### 评测任务类

| FR | 描述 | 状态 | 说明 |
|----|------|------|------|
| FR-001 | 五大类评测任务 | ✅ | L1 Model + L2 Agent + L3 Code + L3 Security + L4 Artifact |
| FR-002 | 四种触发方式 | 🟡 | 手动(CLI/API) + 定时(ScheduleStore/cron)，缺事件/流水线触发 |
| FR-003 | 优先级/队列/并发 | ✅ | TaskConfig.priority + Pipeline sorted + asyncio concurrent |
| FR-004 | 暂停/取消/重试/断点续测 | 🟡 | API cancel/retry 端点，缺暂停/断点续测 |
| FR-005 | 实时进度监控与日志 | ✅ | SSE /tasks/{id}/events + /tasks/{id}/logs |

### 基准与规则类

| FR | 描述 | 状态 | 说明 |
|----|------|------|------|
| FR-006 | 内置 10+ 评测基准 | ✅ | 11 执行器 + 内置默认场景/用例 |
| FR-007 | 自定义评测集上传 | ✅ | DatasetStore (CRUD API + CLI) |
| FR-008 | 评测参数/权重/阈值配置 | ✅ | GateEngine + JudgeConfig (LLM-as-judge) |
| FR-009 | 多版本基线管理与对比 | ✅ | BaselineStore (set/get/list/diff/delete) |
| FR-010 | 裁判模型配置 | ✅ | JudgeStore + JudgeConfig (prompt_template/criteria/score_range) |

### 执行引擎类

| FR | 描述 | 状态 | 说明 |
|----|------|------|------|
| FR-011 | 插件化执行器架构 | ✅ | Registry[T] + ExecutorPlugin ABC |
| FR-012 | 分布式并行评测 | 🟡 | TaskDistributor ABC + LocalDistributor，框架就绪 |
| FR-013 | 评测环境容器化隔离 | ✅ | Dockerfile + docker-compose.yml |
| FR-014 | 评测结果缓存 | ✅ | BenchmarkCache (SQLite) |
| FR-015 | 子任务失败自动重试 | ✅ | CircuitBreaker (熔断+半开恢复) + API retry |

### 结果分析类

| FR | 描述 | 状态 | 说明 |
|----|------|------|------|
| FR-016 | 多维度可视化 | ✅ | matplotlib + 雷达图 + 趋势图 + bench-site recharts |
| FR-017 | 多模型/多版本横向对比 | ✅ | CLI compare + bench-site /compare 页 + API compare |
| FR-018 | 失败根因分析与建议 | 🟡 | GateEngine 门禁结果，缺自动根因分析 |
| FR-019 | 多格式报告导出 | ✅ | JSON/Markdown/PDF/Excel/Chart (reportlab + openpyxl) |
| FR-020 | 质量趋势与回归对比 | ✅ | BaselineStore.diff() + trend_chart() + API trend |

### 溯源与门禁类

| FR | 描述 | 状态 | 说明 |
|----|------|------|------|
| FR-021 | 结果关联模型/Agent/应用版本 | ✅ | TraceRecord.agent_version + app_version 字段 |
| FR-022 | 产物回溯 | ✅ | agent_version/app_version 追踪 |
| FR-023 | 多级质量门禁 | ✅ | GateEngine 3-tier + 审批流 |
| FR-024 | 门禁不通过阻断发布 | ✅ | WebhookConfig (gate_blocked 通知) + action="block" |
| FR-025 | 人工审批节点 | ✅ | ApprovalStore (pending/approved/rejected/expired) |

### 企业管理类

| FR | 描述 | 状态 | 说明 |
|----|------|------|------|
| FR-026 | RBAC 权限控制 | ✅ | RBACStore + Role/Permission + require_permission() FastAPI 依赖 |
| FR-027 | 多租户隔离 | ❌ | 未实现 |
| FR-028 | 审计日志 | ✅ | AuditStore (action/actor/resource/detail/ip_address) |
| FR-029 | 全局质量仪表盘 | 🟡 | bench-site + API stats，非实时仪表盘 |
| FR-030 | 离线环境部署 | ✅ | build_offline.sh 离线安装包 |

---

## 四、非功能需求 (NFR) 实现状态

| NFR | 描述 | 状态 | 说明 |
|-----|------|------|------|
| NFR-001 | 水平扩展 | 🟡 | TaskDistributor ABC 就绪，待 remote 实现 |
| NFR-002 | 调度 QPS≥100 | 🟡 | FastAPI async + ScheduleStore cron |
| NFR-003 | 结果查询<200ms | ✅ | SQLite 本地查询 + 分页 |
| NFR-004 | PB级数据集存储 | ❌ | SQLite 文件存储 |
| NFR-005 | 可用性≥99.5% | ❌ | 无高可用 |
| NFR-006 | 断点续测 | 🟡 | CircuitBreaker 半开恢复，缺完整断点 |
| NFR-007 | 数据多副本/备份 | ✅ | DataBackup (backup/restore/list) |
| NFR-008 | 异常任务熔断 | ✅ | CircuitBreaker (CLOSED/OPEN/HALF_OPEN) |
| NFR-009 | 私有化部署 | ✅ | Dockerfile + 离线包 |
| NFR-010 | 传输加密/数据加密 | ✅ | TLS (ssl_certfile/ssl_keyfile) |
| NFR-011 | 审计日志留存180天 | ✅ | AuditStore + SQLite 持久化 |
| NFR-012 | 完全离线运行 | ✅ | build_offline.sh |
| NFR-013 | macOS/Linux 部署 | ✅ | macOS 验证 + Docker |
| NFR-014 | K8s 容器化 | ✅ | Dockerfile + docker-compose |
| NFR-015 | 兼容主流评测工具 | ✅ | lm-eval + OpenCompass + HELM + EvalScope + Garak |
| NFR-016 | OpenAI 兼容接口 | ✅ | fusion-mlx /v1 API |

---

## 五、REST API 实现状态

| API 分组 | 端点数 | 已实现 | 状态 |
|---------|--------|--------|------|
| 评测任务管理 | 7 | 7 (CRUD + cancel/retry/logs/events) | ✅ |
| 基线管理 | 5 | 5 (CRUD + diff) | ✅ |
| 调度管理 | 5 | 5 (CRUD + toggle) | ✅ |
| 数据集管理 | 4 | 4 (CRUD) | ✅ |
| 裁判模型 | 3 | 3 (create/list/delete) | ✅ |
| 审批流 | 5 | 5 (create/list/approve/reject) | ✅ |
| 结果与分析 | 5 | 5 (get/compare/export/trend) | ✅ |
| 质量门禁 | 5 | 5 (check/list/create/approve) | ✅ |
| 套件管理 | 2 | 2 (list/get) | ✅ |
| 系统管理 | 7 | 7 (health/resources/audit-logs/gpu/backup/backups/restore) | ✅ |

**总计**: 48 个 API 端点已实现

---

## 六、开源工具集成状态

| 工具 | PRD 层级 | 当前状态 | 模块 |
|------|---------|---------|------|
| LM Evaluation Harness | L1 | ✅ | LMHarnessExecutor |
| OpenCompass | L1 | ✅ | OpenCompassExecutor |
| HELM | L1 | ✅ | HelmAdapter |
| EvalScope | L1 | ✅ | EvalScopeExecutor |
| Garak | L3 | ✅ | GarakExecutor (结构化 JSONL 解析) |
| AgentBench | L2 | ✅ | AgentExecutor (3 默认场景) |
| SWE-bench | L3 | ✅ | CodeExecutor (3 默认用例) |
| PyRIT | L3 | 🟡 | SecurityExecutor (内置探测) |
| FullStackBench | L3 | 🟡 | CodeExecutor 覆盖 |
| SandboxFusion | L3 | ❌ | 未集成 |
| LLM Guard | L4 | 🟡 | ArtifactExecutor criteria |
| AgentCompass | L2 | 🟡 | AgentExecutor 基础 |

---

## 七、已完成的 PRD Gap 修复项 (本次迭代)

| # | 任务 | 模块 | 状态 |
|---|------|------|------|
| 1 | P1-1: L2 Agent 评测执行器 | executors/agent_executor.py | ✅ |
| 2 | P1-2: 分布式执行接口 | orchestrator/distributed.py | ✅ |
| 3 | P1-3: 多版本基线管理 | storage/baseline_store.py | ✅ |
| 4 | P1-4: 报告导出增强 PDF/Excel | reporter/report_enhanced.py | ✅ |
| 5 | P1-5: 定时/事件触发 | orchestrator/scheduler_engine.py | ✅ |
| 6 | P1-6: 优先级队列 | core/plugin_base.py (priority) + pipeline.py (sorted) | ✅ |
| 7 | P1-7: 实时进度监控 SSE | api/sse.py + /tasks/{id}/events | ✅ |
| 8 | P1-8: HELM 接口适配 | executors/helm_adapter.py | ✅ |
| 9 | P1-9: EvalScope 集成 | executors/evalscope_executor.py | ✅ |
| 10 | P2-10: L3 代码评测执行器 | executors/code_executor.py | ✅ |
| 11 | P2-11: L4 产物层评测 | executors/artifact_executor.py | ✅ |
| 12 | P2-12: RBAC 权限框架 | auth/rbac.py | ✅ |
| 13 | P2-13: 审计日志 | storage/audit_store.py | ✅ |
| 14 | P2-14: 容器化配置 | Dockerfile + docker-compose.yml | ✅ |
| 15 | P2-15: 自定义评测集上传 | storage/dataset_store.py | ✅ |
| 16 | P2-16: 裁判模型配置 | core/judge_config.py | ✅ |
| 17 | P2-17: 数据多副本/备份 | storage/backup.py | ✅ |
| 18 | P2-18: 异常任务熔断 | orchestrator/circuit_breaker.py | ✅ |
| 19 | P3-19: 审批流程编排 | orchestrator/approval_workflow.py | ✅ |
| 20 | P3-20: 离线安装包 | build_offline.sh | ✅ |
| 21 | P3-24: 传输加密 TLS | cli.py --ssl-certfile/--ssl-keyfile | ✅ |
| 22 | 增强A: Garak 深度集成 | executors/garak_executor.py | ✅ |
| 23 | 增强B: 门禁阻断 Webhook | api/webhook.py | ✅ |
| 24 | 增强C: 可视化增强 | reporter/report_enhanced.py (radar+trend) | ✅ |
| 25 | 增强D: 多模型交互对比 | bench-site/src/app/compare/page.tsx | ✅ |
| 26 | 增强E: 产物回溯 | core/models.py (agent_version/app_version) | ✅ |
| 27 | 增强F: 实时 GPU 监控 | api/gpu_monitor.py + /system/gpu | ✅ |
| 28 | API 集成 | api/app.py (48 端点) | ✅ |
| 29 | CLI 新命令 | cli.py (baseline/schedule/dataset/backup) | ✅ |
| 30 | pyproject.toml 可选依赖 | pdf/excel/security | ✅ |

---

## 八、剩余差距

| 差距 | 优先级 | 说明 |
|------|--------|------|
| 多租户隔离 | P2 | 需设计 tenant_id 隔离方案 |
| PB 级存储 | P3 | 需迁移到对象存储/列式数据库 |
| 高可用 (99.5%) | P3 | 需主备切换 + 负载均衡 |
| 事件/流水线触发 | P2 | 需消息队列集成 |
| 断点续测 (完整) | P2 | 需任务状态快照 + 恢复机制 |
| 失败根因自动分析 | P2 | 需 LLM 辅助分析模块 |
| 实时仪表盘 | P3 | 需 WebSocket + 前端仪表盘 |
| SandboxFusion 集成 | P3 | 需沙箱执行环境 |
| RemoteDistributor | P2 | TaskDistributor ABC 已就绪，待 remote 实现 |

---

## 九、Previous Review 已修复项

| # | 问题 | 文件 | 状态 |
|---|------|------|------|
| 1 | asyncio import 顺序错误 | engine/metrics.py | ✅ 已修复 |
| 2 | token 统计 `=` 应为 `+=` | engine/benchmark.py | ✅ 已修复 |
| 3 | async client 竞态条件 | adapters/mlx_model.py + engine/benchmark.py | ✅ 已修复 |
| 4 | BenchmarkRunner 未关闭 | executors/tune_executor.py | ✅ 已修复 |
| 5 | runner.close() 异常跳过 | optimizer/quant_bench.py | ✅ 已修复 |
| 6 | ALTER TABLE 参数未校验 | reporter/bench_site_db.py | ✅ 已修复 |
| 7 | eval_result.num_cases 不存在 | reporter/bench_site_db.py + bench_site.py | ✅ 已修复 |
| 8 | BenchmarkRunner/ParameterTuner 未关闭 | cli.py | ✅ 已修复 |
| 9 | cursor.rowcount 读取时机错误 | cache.py | ✅ 已修复 |
| 10 | bare except pass | engine/task_runner.py | ✅ 已修复 |
| 11 | bench-site SQL LIKE 未转义 | aggregate/route.ts | ✅ 已修复 |
| 12 | parseInt 无 radix/NaN 检查 | [id]/route.ts + route.ts | ✅ 已修复 |
| 13 | JSON.parse 无 try/catch | 3 个 route 文件 | ✅ 已修复 |
| 14 | 排序字段映射缺失 | route.ts | ✅ 已修复 |
| 15 | ttft_ms Best/Worst 标签反转 | performance/page.tsx | ✅ 已修复 |
| 16 | hash 参数无验证 | my/[hash]/page.tsx | ✅ 已修复 |
| 17 | CLI 入口点缺失 | pyproject.toml | ✅ 已修复 |
| 18 | 9 个测试质量问题 | tests/*.py | ✅ 已修复 |
