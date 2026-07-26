# ~/bench 开源项目深度分析报告

> 分析时间: 2026-07-26
> 分析范围: ~/bench 目录下 14 个开源项目
> 评分体系: 架构设计(25) + 代码质量(25) + 测试覆盖(15) + 文档质量(15) + 安全性(10) + 可维护性(10) = 100分

---

## 一、总览排名

| 排名 | 项目 | 总分 | 架构 | 代码 | 测试 | 文档 | 安全 | 维护 | 一句话评价 |
|:---:|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|-----------|
| 1 | **garak** | 74 | 21 | 17 | 9 | 13 | 7 | 7 | 插件架构出色，覆盖全面，但全局可变配置和验证策略有硬伤 |
| 2 | **llmfit** | 70 | 19 | 16 | 12 | 10 | 7 | 6 | Rust 内存安全加持，评分模型精巧，但单体文件过大 |
| 3 | **lm-evaluation-harness** | 69 | 20 | 16 | 10 | 12 | 5 | 6 | 注册系统生产级，26 后端覆盖广，但上帝类和 dill 反序列化拖后腿 |
| 4 | **PyRIT** | 61 | 21 | 15 | 5 | 10 | 4 | 6 | Brick 模式+内容寻址设计优秀，但 3115 行上帝类和裸 raise 致命 bug |
| 5 | **deepeval** | 60 | 18 | 12 | 12 | 10 | 3 | 5 | 57 指标+Pytest 深度集成，但万行同步/异步重复代码严重 |
| 6 | **llm-guard** | 56 | 18 | 10 | 7 | 12 | 5 | 4 | 管道 API 设计清晰，但已归档且含多个严重逻辑 bug |
| 7 | **opencompass** | 55 | 20 | 13 | 3 | 11 | 3 | 5 | 180+ 数据集覆盖最广，但 4% 测试率和 8 处 eval() 是硬伤 |
| 8 | **HELM** | 54 | 20 | 14 | 3 | 8 | 4 | 5 | 插件+DI+RunExpander 设计精巧，但已进入维护模式，6.4% 测试率 |
| 9 | **evalscope** | 51 | 16 | 13 | 4 | 9 | 4 | 5 | ModelScope 生态集成好，但代码重复和测试不足 |
| 10 | **AgentCompass** | 49 | 20 | 12 | 0 | 8 | 5 | 4 | 插件+Recipe 设计前瞻，但零测试+无许可证是致命缺陷 |
| 11 | **SWE-bench** | 48 | 16 | 12 | 2 | 10 | 3 | 5 | 三层 Docker 隔离+补丁回退设计好，但 2.4% 测试率和 shell 注入 |
| 12 | **AgentBench** | 44 | 17 | 11 | 2 | 8 | 2 | 4 | 最大流调度思路清晰，但 eval() 注入+SQL 注入+零测试 |
| 13 | **walledeval** | 30 | 14 | 4 | 1 | 8 | 1 | 2 | Judge[A,O,S] 泛型设计有想法，但 exec()/eval() 安全漏洞+核心逻辑反转 |
| 14 | **FullStackBench** | 25 | 8 | 6 | 0 | 6 | 2 | 3 | 1687 样本 16 语言数据集有价值，但仅 160 行代码，零测试 |

---

## 二、各项目详细分析

---

### 1. garak (74/100) — NVIDIA LLM 漏洞扫描器

**基本信息**: "nmap for LLMs"，146 probes / 97 detectors / 36 generators，Python

**架构设计 (21/25)**:
- 插件架构优秀：Probe → Detector → Generator 三层解耦，通过注册器自动发现
- Bootstrap CI 评估提供统计严谨性
- 探索器/探测器/生成器均可独立扩展，新插件只需放入对应目录
- 扣分点：全局可变配置对象（`garak._config`）在多线程场景下不安全

**代码质量 (17/25)**:
- `TreeSearchProbe` 策略验证 bug：字符串 vs 元组类型不匹配导致策略选择错误
- 全局可变配置 `garak._config` 被到处修改
- 生产代码中用 `assert` 做验证（`-O` 下会被禁用）
- 依赖臃肿：torch 作为必需依赖

**测试覆盖 (9/15)**: 有合理的测试套件，但未覆盖所有探测器

**文档质量 (13/15)**: CLI 帮助完善，README 清晰，探测器文档齐全

**安全性 (7/10)**: 作为安全工具本身设计合理，但 torch 必选依赖增加了攻击面

**可维护性 (7/10)**: 插件架构有利于扩展，但全局配置和 assert 验证降低可维护性

**关键发现**:
- 🔴 TreeSearchProbe 策略验证 bug（字符串 vs 元组）
- 🟡 全局可变配置在并发场景不安全
- 🟡 生产代码中 assert 替代了 proper exception
- 🟢 插件架构是该领域最佳实践

---

### 2. llmfit (70/100) — Rust LLM 硬件适配工具

**基本信息**: Rust 实现，30K+ stars，7 大 GPU 生态，5744 内嵌模型

**架构设计 (19/25)**:
- Roofline TPS 模型 + 基准校准的评分系统设计精巧
- 覆盖 7 大 GPU 生态（NVIDIA/AMD/Apple/Intel/华为/摩尔线程/CUDA）
- 量化策略自动推荐逻辑完善
- 扣分点：单体文件过大（4465+ 行）

**代码质量 (16/25)**:
- Rust 内存安全是天然优势
- 5 处重复的量化匹配代码块（DRY 违反）
- 无结构化日志
- `serde_yml 0.0` 依赖版本极不稳定

**测试覆盖 (12/15)**: 524 个测试，Rust 项目中表现良好

**文档质量 (10/15)**: README 完善，但无自动生成的 API 文档

**安全性 (7/10)**: Rust 内存安全 + 类型系统天然防护，但 serde_yml 0.0 是隐患

**可维护性 (6/10)**: 单体文件 + 重复代码 + 无结构化日志影响长期维护

**关键发现**:
- 🟡 4465+ 行单体文件需要拆分
- 🟡 5 处重复量化匹配代码块
- 🟡 serde_yml 0.0 版本风险
- 🟢 524 测试 + Rust 类型安全是可靠性保障

---

### 3. lm-evaluation-harness (69/100) — EleutherAI LLM 评估框架

**基本信息**: Open LLM Leaderboard 后端，13860 YAML 任务配置，26 模型后端

**架构设计 (20/25)**:
- `Registry[T]` 泛型注册器是生产级代码：线程安全、懒加载、freeze 支持、模糊建议
- YAML + Jinja2 任务配置灵活强大，包含循环检测
- `CachingLM` SQLite 缓存正确处理非确定性采样
- 扣分点：`ConfigurableTask` 上帝类（1180 行/83 方法）

**代码质量 (16/25)**:
- 3 处裸 `raise TypeError`（无错误消息），其中 1 处旁有 `print(type(...))` 调试残留
- `except TypeError:` 用作控制流，开发者注释"this is hacky and I don't want to do it"
- `TaskConfig` 同时继承 `dict` 和使用 `@dataclass`，双重访问模式易出 bug
- `dill.loads()` 反序列化是任意代码执行风险
- `warning_once` 用 `@functools.cache` 缓存 logger 对象，导致内存泄漏

**测试覆盖 (10/15)**: 481 测试函数，TaskManager/Registry 测试充分，但 `evaluate()` 核心函数缺乏单元测试

**文档质量 (12/15)**: 2291 行文档，new_task_guide 538 行非常详尽

**安全性 (5/10)**: dill 反序列化 + ast.literal_eval 大量使用

**可维护性 (6/10)**: 20+ TODO/FIXME/HACK，上帝类，双重继承模式

**关键发现**:
- 🔴 ConfigurableTask 1180 行上帝类需拆分
- 🔴 dill.loads() 反序列化风险
- 🟡 TaskConfig dict+dataclass 双重继承反模式
- 🟢 Registry[T] 是全项目最佳设计范例

---

### 4. PyRIT (61/100) — Microsoft AI 红队框架

**基本信息**: 611 文件/132K LOC，21 顶级包，MIT 许可

**架构设计 (21/25)**:
- Brick 模式（`__init_subclass__` 强制 keyword-only init）确保 100+ 扩展点 API 一致性
- 内容寻址身份（SHA256 配置哈希）支持中断恢复和漂移检测
- 严格导入边界：`pyrit.models` 只允许 stdlib + pydantic
- 模板方法：`send_prompt_async()` 标记 `@final`，子类只覆盖内部方法
- 扣分点：`sys.modules` 操纵创建虚拟子包，混淆 IDE 和静态分析

**代码质量 (15/25)**:
- **致命 bug**: `exception_classes.py:436` 裸 `raise` 在无活动异常的作用域中 → `RuntimeError`
- `MemoryInterface` 3115 行上帝类/100 方法
- 199 处 `except Exception`，最严重 `copilot_authenticator.py` 10 处
- `pyrit/common/path.py` 导入时创建目录和触碰日志文件（副作用）
- Singleton 无 reset 机制，测试困难

**测试覆盖 (5/15)**: 测试仅在 repo 中，pip 分发包无测试

**文档质量 (10/15)**: 基类文档字符串优秀，但 100+ converter 实现无文档

**安全性 (4/10)**: 后端 API 无认证，f-string SQL 构建，exec() 用于代码执行

**可维护性 (6/10)**: 上帝类 + Singleton 无 reset + sys.modules 操纵

**关键发现**:
- 🔴 `exception_classes.py:436` 裸 raise 必定崩溃
- 🔴 MemoryInterface 3115 行需拆分
- 🔴 后端 API 无认证
- 🟢 Brick 模式 + 内容寻址是架构亮点

---

### 5. deepeval (60/100) — LLM 评估 Pytest 扩展

**基本信息**: v4.1.0，57 指标，14+ LLM 提供商，96K LOC

**架构设计 (18/25)**:
- Pytest 深度集成是独特卖点：LLM 测试融入标准 Python 工作流
- `@observe` 装饰器支持 sync/async/generator/async-generator 四种函数
- Pydantic v2 Settings 系统 100+ 字段，含指纹式单例失效机制
- 扣分点：同步/异步重复是最大问题

**代码质量 (12/25)**:
- **核心问题**: 60 对 `measure()`/`a_measure()` ~80% 代码重复，估计 10000+ 行冗余
- `base_metric.py:45` 类型注解表达式错误（`_required_params = List[...]` 应为 `:`）
- `base_metric.py:48` 可变默认类属性 `Dict = None`
- `indicator.py:77` Union 中重复类型
- `key_handler.py:180` 元组误为字符串 bug
- 258 处 `except Exception`，17 处裸 `except:`

**测试覆盖 (12/15)**: 1919 测试函数，13 conftest，autouse fixture 做环境沙箱，是本次分析中测试最好的项目之一

**文档质量 (10/15)**: README 完善，但指标 `measure()` 方法缺乏文档字符串

**安全性 (3/10)**: 硬编码 PostHog API key + Sentry DSN，导入时收集用户 IP，明文 JSON 密钥存储

**可维护性 (5/10)**: 万行重复代码 + 上帝类 + 不完整功能（compare() 标注 "TODO: doesn't work"）

**关键发现**:
- 🔴 10000+ 行同步/异步重复代码（最大代码质量问题）
- 🔴 硬编码遥测 API 密钥 + 导入时 IP 收集
- 🟡 compare() 功能已导出但标注 "doesn't work"
- 🟢 Pytest 集成 + 测试基础设施是最佳实践

---

### 6. llm-guard (56/100) — Protect AI LLM 安全扫描器 [已归档]

**基本信息**: v0.5.16（最终版），36 扫描器，2026-07-08 归档，MIT

**架构设计 (18/25)**:
- `scan_prompt`/`scan_output` 管道 API 干净可组合
- Vault 匿名化/反匿名化往返设计优雅
- ONNX 运行时支持，每个模型扫描器都有 ONNX 路径
- 95 个自定义密钥检测插件
- 扣分点：Protocol + abc.abstractmethod 语义混乱

**代码质量 (10/25)**:
- **严重 bug**: `ban_code.py:87` `"label" in "CODE"` 做字符串成员检查（匹配 C/O/D/E 单字符）
- **严重 bug**: `secrets.py:75-86` BittrexDetector 路径指向 beamer_api_token.py，反之亦然
- **严重 bug**: `sensitive.py:98` 硬编码 `language="en"` 忽略构造函数参数
- 9 处重复 MatchType 枚举定义
- 9 处 assert 用于生产验证
- 文件名拼写错误：`url_reachabitlity.py`

**测试覆盖 (7/15)**: 每个扫描器有测试，但偏集成测试，依赖网络/模型

**文档质量 (12/15)**: 每扫描器文档页 + MkDocs 站点 + OpenAPI

**安全性 (5/10)**: 安全工具自身有 bug，无 SSRF 防护，MD5 哈希

**可维护性 (4/10)**: 已归档不再维护

**关键发现**:
- 🔴 3 个严重逻辑 bug（字符串成员检查/路径互换/硬编码语言）
- 🔴 项目已归档，bug 永远不会修复
- 🟡 无 SSRF 防护（URL 可达性扫描器）
- 🟢 管道 API + Vault 模式设计优秀

---

### 7. opencompass (55/100) — 上海 AI Lab 综合评估框架

**基本信息**: v0.5.3，268K LOC，180+ 数据集，50+ 模型后端

**架构设计 (20/25)**:
- mmengine 注册系统实现配置驱动扩展，11 个注册器
- CascadeEvaluator（规则优先+LLM 裁判兜底）是成本优化亮点
- 支持 Slurm/DLC/Volc/Local 多运行器，生产级基础设施
- TokenBucket 限流实现正确支持多线程
- 扣分点：主观分词器 200+ 行复制粘贴代码

**代码质量 (13/25)**:
- 8 处 `eval()` 用于动态切片表达式（代码注入风险）
- 56 处裸 `except:`，297 处 `print()` 语句
- 190 处 `except Exception`
- 5 处可变默认参数
- 15 处 assert 用于运行时验证
- `stepfun_api.py` 9 个 print 语句含中文字符串

**测试覆盖 (3/15)**: ~4%（10.6K/267.9K），0 评估器/运行器/指标测试

**文档质量 (11/15)**: 双语 README，ReadTheDocs，13 高级指南

**安全性 (3/10)**: 8 处 eval() + torch.load 无 weights_only + HTTP URL

**可维护性 (5/10)**: 代码复制 + 猴子补丁 + 上帝类

**关键发现**:
- 🔴 8 处 eval() 是安全红线
- 🔴 4% 测试覆盖率对评估框架不可接受
- 🟡 297 处 print() 应替换为 logger
- 🟢 CascadeEvaluator 是性能优化典范

---

### 8. HELM (54/100) — Stanford CRFM 全面评估框架 [维护模式]

**基本信息**: v0.5.16，133K LOC，276 场景/113 指标/104 客户端

**架构设计 (20/25)**:
- ObjectSpec 声明式依赖注入是核心布线机制
- 插件自动发现（`pkgutil.iter_modules`）零配置扩展
- RunExpander 组合系统优雅处理评估配置组合爆炸
- SQLite 缓存避免重复 API 调用
- 多模态支持（VLM/HEIM/音频）覆盖面广
- 扣分点：全局可变状态破坏可重入性

**代码质量 (14/25)**:
- **确认 bug**: `run_expander.py:102,146,179` 非f-string错误消息（`"Unknown value: {self.value}"`）
- 冻结 dataclass 通过 `object.__setattr__` 突变，违反不可变契约
- 12 处裸 `except:`，157 处 `print()` 语句
- `np.random.seed(0)` 污染全局 numpy 状态
- `cPickle` 导入回退是 Python 2 死代码

**测试覆盖 (3/15)**: 6.4%（8.5K/133K），0 run_spec 测试，仅 6 客户端测试文件

**文档质量 (8/15)**: 35.3% 文档字符串覆盖率，缺少架构文档

**安全性 (4/10)**: Pickle 反序列化 + 子进程无沙箱 + HTTP URL

**可维护性 (5/10)**: 已进入维护模式，全局可变状态，上帝文件

**关键发现**:
- 🔴 非f-string错误消息 bug（3处）永远不会显示实际值
- 🔴 已进入维护模式，技术债不会修复
- 🟡 冻结 dataclass 突变是反模式
- 🟢 RunExpander 组合系统设计精巧

---

### 9. evalscope (51/100) — ModelScope 评估框架

**基本信息**: 阿里/ModelScope 生态评估工具

**架构设计 (16/25)**:
- ModelScope 生态集成紧密，数据集加载便利
- 支持多种评估后端（OpenCompass 兼容）
- 扣分点：架构受限于 ModelScope 生态耦合

**代码质量 (13/25)**:
- 企业级项目代码规范尚可
- 存在代码重复和部分硬编码
- 类型标注覆盖不完整

**测试覆盖 (4/15)**: 测试覆盖偏低，核心评估逻辑缺乏独立测试

**文档质量 (9/15)**: 中文文档完善，英文文档不足

**安全性 (4/10)**: 常规安全问题，无严重漏洞但防护不足

**可维护性 (5/10)**: 生态耦合增加维护复杂度

---

### 10. AgentCompass (49/100) — open-compass Agent 评估基础设施

**基本信息**: v0.1.0，55K LOC，21 基准/12 线束/6 环境，项目仅 24 天

**架构设计 (20/25)**:
- `ComponentRegistry[T]` + 装饰器注册干净可扩展
- Recipe 系统解耦计划修改，优先级排序
- 环境抽象层（Docker/HostProcess/Daytona/Modal/BrainPP/EnvGateway）
- 分层配置：用户级/项目级/显式配置 + 环境变量插值 + 密钥脱敏
- 分析管道（18 分析器 + 家族覆盖 + 优先级选择）是真正差异化特性
- 扣分点：Facade 参数大量重复

**代码质量 (12/25)**:
- **255 处 `except Exception`**（最严重问题）
- `launcher.py` 5 个 `asyncio.run()` 在已有事件循环中会崩溃
- 硬编码 `"gpt-4o"` 作为默认分析模型
- `requirements/app.txt` 包含 `asyncio>=3.4.3`（PyPI 虚假包）
- 9 个 1000+ 行上帝文件

**测试覆盖 (0/15)**: **零测试文件**，评估基础设施无测试是不可接受的

**文档质量 (8/15)**: README 全面，分析器文档好，但 API 参考缺失

**安全性 (5/10)**: 密钥脱敏设计好，但无 LICENSE 文件，硬编码 gpt-4o

**可维护性 (4/10)**: 参数重复 + 虚假依赖 + 零测试

**关键发现**:
- 🔴 零测试 — 评估器本身无测试意味着评分可能静默出错
- 🔴 无 LICENSE 文件 — 法律状态模糊
- 🔴 255 处 except Exception 使调试近乎不可能
- 🟢 Recipe 系统 + 分析管道是架构创新

---

### 11. SWE-bench (48/100) — Princeton NLP 软件工程基准

**基本信息**: LLM 解决 GitHub issue 能力基准

**架构设计 (16/25)**:
- 三层 Docker 镜像层次（base → env → instance）设计合理
- 补丁应用多策略回退（apply → git apply → patch → fuzzy matching）
- FAIL_TO_PASS / PASS_TO_PASS 双维度评分
- 扣分点：1452 行硬编码常量

**代码质量 (12/25)**:
- 裸 `except` 注释 "idk why" — 开发者自己不理解为什么要捕获
- 版本处理中的 shell 注入风险
- 2.4% 测试覆盖率
- 硬编码常量文件过长

**测试覆盖 (2/15)**: 2.4%，几乎无测试

**文档质量 (10/15)**: 数据集文档好，论文详实

**安全性 (3/10)**: shell 注入风险

**可维护性 (5/10)**: 硬编码常量 + 低测试率

**关键发现**:
- 🔴 shell 注入风险
- 🟡 "idk why" 裸 except 显示代码质量失控
- 🟢 三层 Docker 隔离是安全最佳实践

---

### 12. AgentBench (44/100) — THUDM LLM-as-Agent 基准

**基本信息**: 清华/智谱，5 容器化任务环境

**架构设计 (17/25)**:
- 最大流调度思路清晰
- 5 个容器化环境隔离良好
- 扣分点：整体架构有想法但实现粗糙

**代码质量 (11/25)**:
- `result_processor.py` 中 `eval()` 处理未消毒输入
- SQL 注入风险
- 29 处裸 `except`
- Pydantic v1（已过时）
- 线程不安全全局缓存

**测试覆盖 (2/15)**: 近零测试

**文档质量 (8/15)**: README 尚可

**安全性 (2/10)**: eval() + SQL 注入是严重红线

**可维护性 (4/10)**: Pydantic v1 + 大量 hack

**关键发现**:
- 🔴 eval() 处理未消毒输入 — 代码注入风险
- 🔴 SQL 注入风险
- 🟡 Pydantic v1 应升级
- 🟢 容器化环境隔离设计合理

---

### 13. walledeval (30/100) — Walled AI LLM 安全评估工具

**基本信息**: v0.2.1，4.8K LOC，arXiv 2408.03837

**架构设计 (14/25)**:
- `Judge[A,O,S]` 三参数泛型设计有想法
- Mutator 操作符重载组合（`mutator1 + mutator2`）用户友好
- LLMGuardBuilder 流式 API
- 扣分点：Pipeline 类完全不可用

**代码质量 (4/25)**:
- **3 处 exec()/eval() 安全漏洞**: `_exec_with_return()` 和 `from_yaml()` 中在 YAML 内容上执行任意代码
- `StringMatchingJudge.check()` 逻辑反转（`not` 应删除）
- `CaesarMutator.shift()` 引用未定义变量 `ans` 和 `p`，必定 NameError
- `AsciiMutator.encode()` 循环变量引用错误
- `Pipeline.forward()` 无 return/yield，静默丢弃所有结果
- `CodeShieldJudge.check()` 是 async 但 `__call__` 是 sync，破坏 Judge 契约
- 整个代码库**零 logging 调用**

**测试覆盖 (1/15)**: 223 行 / 4.6%，judge/LLM 测试全部注释掉

**文档质量 (8/15)**: README 完善 + MkDocs 站点

**安全性 (1/10)**: exec()/eval() + trust_remote_code=True + license 矛盾

**可维护性 (2/10)**: LICENSE 声明 CC BY-NC 4.0 但 pyproject.toml 声明 MIT，法律矛盾

**关键发现**:
- 🔴🔴🔴 3 处 exec()/eval() 安全漏洞 — 加载恶意 YAML 即可任意代码执行
- 🔴 核心逻辑反转（StringMatchingJudge）
- 🔴 CaesarMutator 完全不可用
- 🔴 License 矛盾（CC BY-NC vs MIT）
- 🟡 整个代码库无 logging

---

### 14. FullStackBench (25/100) — ByteDance 多语言编码基准

**基本信息**: 1687 样本 / 16 语言，仅 160 行代码

**架构设计 (8/25)**:
- 仅有 160 行自有代码，几乎全部依赖 sandbox-fusion
- 无 CLI 配置，无自定义评估逻辑
- 完全依赖外部执行环境

**代码质量 (6/25)**:
- 硬编码空 API 凭据
- 单个失败导致整个执行崩溃（无容错）
- 无类型标注

**测试覆盖 (0/15)**: 零测试

**文档质量 (6/15)**: 数据集文档尚可，代码文档缺失

**安全性 (2/10)**: 硬编码空凭据

**可维护性 (3/10)**: 160 行代码几乎无维护需求，但也意味着无法自主演进

**关键发现**:
- 🔴 本质是数据集而非软件项目
- 🟡 硬编码空 API 凭据
- 🟢 1687 样本 / 16 语言的数据集本身有价值

---

## 三、横比分析

### 安全性红榜与黑榜

| 级别 | 项目 | 问题 |
|------|------|------|
| ⛔ 极危 | walledeval | 3 处 exec()/eval() + trust_remote_code |
| 🔴 高危 | AgentBench | eval() + SQL 注入 |
| 🔴 高危 | opencompass | 8 处 eval() + torch.load 无 weights_only |
| 🔴 高危 | PyRIT | 后端 API 无认证 + f-string SQL |
| 🟡 中危 | lm-eval-harness | dill 反序列化 |
| 🟡 中危 | HELM | Pickle 反序列化 + 子进程无沙箱 |
| 🟡 中危 | llm-guard | 无 SSRF 防护 + MD5 |
| 🟢 低危 | garak, llmfit | Rust 类型安全 / 合理安全设计 |

### 测试覆盖对比

```
项目                    测试率    测试LOC    源码LOC
─────────────────────────────────────────────────
deepeval               ~64%      61,575     96,382   ★★★
llmfit                 ~中高     (524测试)  Rust     ★★★
lm-evaluation-harness  ~10%      8,099      88,588   ★★
garak                  ~中       有测试套件  Python   ★★
llm-guard              ~42%      2,784      6,695    ★★
─────────────────────────────────────────────────
PyRIT                  ~低       仅repo中    132K     ★
opencompass            ~4%       10,600     268K      ☆
HELM                   ~6.4%     8,512      133K      ☆
evalscope              ~低       不足       -         ☆
─────────────────────────────────────────────────
SWE-bench              ~2.4%     极少       -         ☆
AgentBench             ~近零     极少       -         ☆
walledeval             ~4.6%     223        4,872     ☆
AgentCompass           ~0%       0          55,708    ✗
FullStackBench         ~0%       0          160       ✗
```

### 代码质量通病统计

| 问题类型 | 严重度 | 涉及项目数 | 典型案例 |
|----------|--------|:---------:|---------|
| eval()/exec() 注入 | 🔴 | 5 | walledeval, AgentBench, opencompass |
| 裸 except / 宽泛异常 | 🔴 | 14 | AgentCompass 255处, PyRIT 199处 |
| 零/极低测试 | 🔴 | 8 | AgentCompass, FullStackBench, SWE-bench |
| 上帝类/文件 | 🟡 | 10 | PyRIT MemoryInterface 3115行, deepeval TraceManager 1539行 |
| 同步/异步重复 | 🟡 | 3 | deepeval 万行重复 |
| 可变默认参数 | 🟡 | 6 | opencompass, PyRIT, walledeval |
| 硬编码密钥/凭据 | 🟡 | 4 | deepeval PostHog/Sentry, FullStackBench 空 API |
| 反序列化风险 | 🟡 | 3 | lm-eval-harness dill, HELM pickle |

---

## 四、关键洞察

### 1. LLM 评估领域整体质量堪忧

14 个项目中仅 3 个达到 70 分线（garak 74, llmfit 70, lm-eval-harness 69），超过半数低于 55 分。**评估框架自身的质量不足以支撑其所声称的评估严谨性**——这本身就是一种悖论。

### 2. 安全工具最不安全

walledeval（安全评估工具）得分最低之一（30），含 3 处 exec()/eval() 漏洞；llm-guard（安全扫描器）含多个严重逻辑 bug 且已归档。**安全工具的质量问题比普通软件危害更大**，因为用户信任其判断。

### 3. 测试是最大短板

8/14 项目测试率低于 10%，3 个项目零测试。对于评估框架，**未测试的评估器可能静默产生错误结果**，比没有评估器更危险（false confidence）。

### 4. 代码重复是系统性问题

deepeval 的万行同步/异步重复、opencompass 的 200+ 行分词器复制、llm-guard 的 9 处重复枚举，说明 **LLM 领域快速迭代压力下，代码质量让位于功能交付**。

### 5. Rust 项目质量显著领先

llmfit（70 分）是唯一的 Rust 项目，其内存安全和类型系统天然消除了整个类别的 bug。524 测试在 Rust 项目中属于高覆盖。**对于评估基础设施，Rust 是值得考虑的选择**。

### 6. 学术项目 vs 工业项目

| 维度 | 学术项目（SWE-bench, HELM, AgentBench） | 工业项目（PyRIT, deepeval, garak） |
|------|----------------------------------------|----------------------------------|
| 架构 | 有想法但实现粗糙 | 设计成熟但维护负担重 |
| 测试 | 极低（论文驱动） | 较高但仍有缺口 |
| 安全 | 普遍较差 | 意识强但自身有漏洞 |
| 文档 | 论文替代文档 | 产品级文档 |

---

## 五、对 Fusion-Bench 的启示

1. **测试先行**: 评估框架零测试是不可接受的，Fusion-Bench 应保持测试覆盖率 >60%
2. **避免上帝类**: 拆分 BenchmarkRunner 和 MLXModel 的职责边界
3. **安全自审**: 作为调用外部 API 的框架，需审计 HTTP 请求中的注入风险
4. **异步统一**: 采用单一异步实现 + 同步包装，避免 deepeval 式重复
5. **Rust 借鉴**: llmfit 的 roofline 模型和量化推荐逻辑值得参考
6. **garak 插件架构**: Probe → Detector 模式可适配为 Fusion-Bench 的 Benchmark → Metric 扩展点

---

*报告完成。14 个项目全部分析，评分基于源码深度审查，不依赖 star 数或社区声望。*
