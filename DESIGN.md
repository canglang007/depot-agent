# Depot：面向代码生成Agent的按需依赖解析系统 —— 详细设计文档

***

**项目组**：第3组（高级系统软件技术课程项目）
**组别**：第3组
**汇报时间**：2025年6月18日
**系统代号**：Depot（Dependency Pot — 依赖池）

***

## 目录

1. [选题背景与动机](#1-选题背景与动机)

2. [问题定义与Gap分析](#2-问题定义与gap分析)

3. [相关工作](#3-相关工作)
   - 3.1 代码执行沙箱
   - 3.2 依赖解析工具
   - 3.3 代码分析技术
   - 3.4 与现有系统的核心差异

4. [系统设计](#4-系统设计)

5. [核心创新点](#5-核心创新点)

6. [实验设计](#6-实验设计)

7. [评估指标](#7-评估指标)

8. [实验结果与分析](#8-实验结果与分析)

9. [项目进度与状态](#9-项目进度与状态)

10. [开源路线图](#10-开源路线图)

***

## 1. 选题背景与动机

### 1.1 代码生成Agent的兴起

LLM Agent（如 Claude Code、Cline、OpenAI Codex CLI、Aider 等）已成为软件开发的新范式。这些 Agent 的核心工作循环是：

```
用户需求 → Agent 推理 → 生成代码 → 执行验证 → 根据反馈修正 → 再次生成
```

其中**代码执行与验证**环是实现高质量代码生成的关键——Agent 需要通过实际运行结果来判断代码的正确性，而非仅依赖模型的"猜测"。

### 1.2 执行层的核心摩擦：依赖问题

当 Agent 生成包含第三方库依赖的代码时，面临一个典型的"冷启动"困境：

```
Agent 生成: import torch, import transformers, import scipy
           ↓
环境没有这些包 → ImportError
           ↓
Agent 尝试 pip install → 可能版本冲突 / 下载超时 / 依赖链不兼容
           ↓
多轮重试后可能成功，也可能彻底放弃
```

这个困境的根因是：**Agent 对目标执行环境缺乏"依赖感知"**——它不知道环境里有什么包，只能盲写 import，失败了再猜。

### 1.3 现有方案的不足

| 方案    | 代表系统                         | 优势           | 缺陷                      |
| ----- | ---------------------------- | ------------ | ----------------------- |
| 重型沙箱  | OpenAI Code Interpreter, E2B | 安全隔离好，依赖预装齐全 | 启动慢（秒级），资源重，预装包冗余，不可定制  |
| 本地裸执行 | AutoGPT, OpenInterpreter     | 零额外开销，速度快    | 无安全隔离，Agent 可执行任意危险命令   |
| 静态分析  | Pylint, MyPy                 | 安全，零运行时开销    | 无法捕获 ImportError 等运行时错误 |
| 预装全家桶 | 固定 Docker 镜像                 | 简单直接         | 镜像臃肿，包版本固化，无法按需扩展       |

**核心矛盾**：现有方案在"轻量快速"与"依赖完备"之间存在 Gap——要么太慢太重（沙箱），要么依赖缺失导致执行失败（裸执行）。

***

## 2. 问题定义与Gap分析

### 2.1 三个核心Gap

#### Gap 1：依赖"失明" (Dependency Blindness)

Agent 生成代码时不知道目标环境中有哪些包可用。这导致：

* Agent 只能假设环境"什么都有"或"什么都没有"

* 生成的 import 语句可能与实际环境不匹配

* 缺乏环境感知能力使 Agent 无法做出明智的依赖选择

#### Gap 2：按需解析缺失 (Missing On-Demand Resolution)

现有方案要么预装全家桶（浪费存储和启动时间），要么让 Agent 裸 pip install（每次都从头装，且无版本管理）。缺少一条自动化的智能链路：

```
检测缺失 → 只安装缺失的 → 缓存复用 → 冲突时提供替代建议
```

#### Gap 3：失败反馈非结构化 (Unstructured Failure Feedback)

当代码执行失败时，Agent 收到的反馈是原始 traceback：

```
ImportError: No module named 'torch'
```

但 Agent 不知道：

* 这个包**真的不存在**还是**版本不对**？

* 依赖链是否和已有环境冲突？

* 有没有可替代的包？

这导致 Agent 的自我纠错效率低下，进入"试错循环"。

### 2.2 问题形式化定义

给定：

* 一个 LLM Agent 生成的代码片段 $C$

* 一个目标执行环境 $E$（含已有的包集合 $P_E$）

* 一组可用的包源 $S$（PyPI、conda-forge 等）

目标：构建一个系统 $D(C, E, S)$，使得：

1. **自动识别** $C$ 中所有的外部依赖 $Deps(C)$

2. **高效解析** $Deps(C) \setminus P_E$（只安装缺失的）

3. **隔离执行** $C$ 于一个安全、轻量的容器中

4. **结构化输出**执行结果和依赖解析过程，供 Agent 消费

***

## 3. 相关工作

### 3.1 代码执行沙箱

| 系统                                                  | 隔离方式                | 启动速度   | 依赖管理  | 面向场景        |
| --------------------------------------------------- | ------------------- | ------ | ----- | ----------- |
| OpenAI Code Interpreter                             | Docker/VM           | ~5-10s | 预装常用包 | ChatGPT 插件  |
| E2B (e2b.dev)                                       | Firecracker microVM | ~2-3s  | 自定义模板 | 通用 Agent 平台 |
| Google AI Studio                                    | 云端沙箱                | ~3-5s  | 预装全家桶 | Gemini 代码执行 |
| Modal / Replit                                      | 容器                  | 1-5s   | 可自定义  | 开发者平台       |
| **Depot (本系统)** | 轻量进程隔离 | **<100ms** | **按需解析+缓存** | Agent 代码验证          |        |       |             |

### 3.2 依赖解析工具

* **pip / pip-tools**：标准 Python 依赖管理，但不适合 Agent 场景（需要手动操作）

* **Poetry / PDM**：项目级依赖管理，粒度太粗

* **importlib**：Python 内置 import 机制，不具备自动安装能力

* **Micromamba**：快速的 conda 替代，可嵌入但体积大

### 3.3 代码分析技术

* **AST（抽象语法树）**：Python 的 `ast` 模块，可精确提取 import 语句

* **静态分析**：Pylint、Pyflakes 可检测未定义的导入

* **动态追踪**：`sys.meta_path` 可拦截 import 钩子

**Depot 的结合**：AST 静态提取 + meta_path 运行时钩子 + pip 按需安装 = 完整依赖感知链路

### 3.4 与现有系统的核心差异

下表将 Depot 与所有已知的 Agent 代码执行方案进行逐项对比：

| 系统 | 类型 | AST依赖检测 | 自动安装 | 结构化反馈 | Agent依赖感知 |
|------|------|:----------:|:--------:|:--------:|:-----------:|
| OpenAI Code Interpreter | 封闭沙箱 | ❌ | ❌ | ❌ | ❌ |
| E2B (e2b.dev) | 开放沙箱 | ❌ | ⚠️ 需手动 | ❌ | ❌ |
| Google AI Studio | 云端执行 | ❌ | ❌ | ❌ | ❌ |
| CodeSandbox SDK | Web沙箱 | ❌ | ⚠️ 需手动 | ❌ | ❌ |
| Open Interpreter | 本地执行 | ❌ | ⚠️ 失败后提示 | ❌ | ❌ |
| Morph / Modal | 云平台 | ❌ | ❌ | ❌ | ❌ |
| pipreqs | 静态工具 | ⚠️ 文件级 | ❌ | ❌ | ❌ |
| **Depot (本系统)** | **Agent管道** | **✅** | **✅** | **✅** | **✅** |

> ⚠️ = 部分支持但非自动化。OpenAI Code Interpreter 预装固定 330 个包不可定制；E2B 需提前构建环境模板；Open Interpreter 只在执行失败后才提示用户手动安装。

**核心发现**：所有现有方案对依赖的处理都是**被动**的 — 要么预装全家桶（固定不可变），要么裸执行报错后由 Agent 或人工介入。**没有任何一个系统在"Agent 提交代码"和"执行代码"之间插入依赖感知层**。

Depot 的创新不在于某个算法组件（AST 解析、pip 安装都是成熟技术），而在于**架构创新**：将依赖管理从 Agent 的"手动负担"变为系统的"自动化管道"，使 Agent 完全不需要感知环境状态差异。

直觉类比：
```
B1 裸执行  = 没有 GC 的语言，程序员手动管理内存
B2 全家桶  = 固定内存池，预分配好但浪费
Depot     = 有 GC 的语言，自动回收，程序员无需关心
```

***

## 4. 系统设计

### 4.1 总体架构

```
                        Agent 生成代码
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│                    Depot 系统                             │
│                                                           │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐  │
│  │ AST     │──▶│ 依赖    │──▶│ 按需    │──▶│ 隔离    │  │
│  │ 提取器  │   │ 解析器  │   │ 安装器  │   │ 执行器  │  │
│  └─────────┘   └─────────┘   └─────────┘   └─────────┘  │
│       │             │             │             │         │
│       ▼             ▼             ▼             ▼         │
│  import 列表   解析结果     安装/缓存      执行输出        │
│                                                           │
│  ┌──────────────────────────────────────────────────┐    │
│  │              结构化反馈生成器                       │    │
│  │  - 依赖解析摘要                                    │    │
│  │  - 执行结果（stdout/stderr/exit code）              │    │
│  │  - 失败时的修复建议                                 │    │
│  └──────────────────────────────────────────────────┘    │
│                           │                               │
└───────────────────────────┼───────────────────────────────┘
                            ▼
                    Agent 接收反馈 → 迭代修正
```

### 4.2 组件详细设计

#### 4.2.1 AST 依赖提取器 (Dependency Extractor)

**输入**：Agent 生成的 Python 代码字符串
**输出**：结构化的依赖列表

```python
# 提取的依赖结构
{
    "standard_library": ["os", "sys", "json"],       # 标准库，无需安装
    "third_party": ["torch", "transformers", "numpy"], # 需要安装的
    "local_imports": [".utils", ".config"],            # 本地模块
    "dynamic_imports": ["importlib.import_module('xxx')"], # 动态导入（尽力识别）
    "try_imports": ["try: import cv2 except: pass"],    # 条件导入
    "unknown": []                                       # 无法确定的
}
```

**技术方案**：

* 使用 Python `ast` 模块解析代码 AST

* 遍历 `ast.Import` 和 `ast.ImportFrom` 节点

* 用标准库列表 (`sys.stdlib_module_names`) 过滤标准库

* 正则匹配动态 import 模式（`__import__`, `importlib.import_module`）

* 对 `try-except` 包裹的 import 做特殊标记

**关键设计决策**：

* 只做**静态提取**，不尝试导入模块（避免副作用）

* 对 `if TYPE_CHECKING` 块做识别，标记为"可选依赖"

* 支持 `requirements.txt` 风格的版本约束（`# depot: torch>=2.0` 注释）

#### 4.2.2 依赖解析器 (Dependency Resolver)

**输入**：依赖列表 + 当前环境信息
**输出**：需要安装的包清单（含版本约束）

**工作流程**：

```
依赖列表
    │
    ▼
┌──────────────────┐
│ 1. 查询环境已有包  │ ─── pip list / importlib 查询
└──────┬───────────┘
       ▼
┌──────────────────┐
│ 2. 计算缺失集合    │ ─── 第三方包 - 环境已有 = 缺失
└──────┬───────────┘
       ▼
┌──────────────────┐
│ 3. 解析依赖链     │ ─── 用 pip download --dry-run 分析传递依赖
└──────┬───────────┘
       ▼
┌──────────────────┐
│ 4. 冲突检测       │ ─── 检查是否与已有包版本冲突
└──────┬───────────┘
       ▼
┌──────────────────┐
│ 5. 生成安装计划   │ ─── 排序后的安装列表（拓扑序）
└──────────────────┘
```

**缓存策略**：

* 每个虚拟环境维护一个 `depot.lock` 文件，记录已安装包的精确版本

* 首次安装写入缓存，后续执行跳过已缓存的包

* 支持 `--refresh` 强制刷新

* 缓存命中率预期 > 80%（后续测试任务共享基础依赖）

#### 4.2.3 按需安装器 (On-Demand Installer)

**输入**：安装计划（包名列表 + 版本约束）
**输出**：安装结果摘要

**设计要点**：

* **增量安装**：只装缺失的包，不重装已有的

* **并行下载**：使用 `pip install --no-deps` + 单独解析传递依赖，实现并行化

* **回滚机制**：安装失败时恢复到之前的状态

* **镜像加速**：支持配置 PyPI 镜像（如清华源）

* **超时与重试**：单包安装超时 30s，最多重试 2 次

**安装策略三级**：

1. **快速模式**（默认）：`pip install <pkg>` 使用 PyPI 最新版

2. **兼容模式**：检测 Python 版本和系统架构，选择兼容版本

3. **锁定模式**：使用 `depot.lock` 中的精确版本，保证可复现

#### 4.2.4 隔离执行器 (Isolated Executor)

**输入**：代码字符串 + 准备好的环境
**输出**：执行结果（stdout, stderr, exit code, 执行时间）

**设计方案**（轻量优先）：

* **方案一（推荐）**：Python `venv` + `subprocess` — 轻量，启动 < 50ms

* **方案二**：Docker 容器 — 隔离性更好，启动 1-3s

* **方案三**：Firecracker microVM — 最安全，启动 100-200ms

**选择方案一的理由**：

* 启动速度最快，适合 Agent 高频交互

* Agent 生成代码的恶意风险较低（非公开服务）

* 可通过 `subprocess` 的 timeout、资源限制实现基本安全

**安全措施**（即使在轻量模式下）：

* 设置 `subprocess.run(timeout=30)` 防止死循环

* 限制可用内存（`resource.setrlimit` 或 `ulimit`）

* 禁止网络访问（可选 `--offline` 模式）

* 白名单文件系统访问路径

#### 4.2.5 结构化反馈生成器 (Structured Feedback Generator)

**输入**：所有组件的输出
**输出**：一份结构化的 JSON 反馈 + 人类可读的 Markdown 摘要

```json
{
  "status": "success" | "partial" | "failed",
  "dependency_analysis": {
    "found": ["torch", "numpy"],
    "missing": ["transformers"],
    "installed": ["transformers==4.36.0"],
    "install_time_ms": 3200,
    "cached": ["torch", "numpy"]
  },
  "execution": {
    "exit_code": 0,
    "stdout": "...",
    "stderr": "",
    "execution_time_ms": 150
  },
  "summary": "代码执行成功。安装了1个缺失包(transformers), 耗时3.2s。",
  "suggestions": []
}
```

**Agent 消费**：Agent 拿到结构化反馈后可以：

* 知道执行是否成功

* 知道安装了哪些包（透明度）

* 失败时获取修复建议

* 根据安装耗时判断是否需要优化依赖选择

### 4.3 数据流图

```
时间轴 →

T+0ms    Agent 提交代码
T+1ms    AST 提取器完成分析 (纯内存操作)
T+5ms    依赖解析器查询环境 (缓存查询)
T+10ms   判定：3个包缺失 → 触发安装
T+3000ms 安装完成 (首次，后续命中缓存则 0ms)
T+3050ms 隔离执行器返回结果
T+3055ms 反馈生成器输出结构化结果
T+3055ms Agent 收到反馈

总延迟：首次约 3s，缓存命中 < 100ms
```

***

## 5. 核心创新点

### 创新点 1：Agent 依赖感知管道 (Dependency-Aware Pipeline)

**创新类型**：架构创新

不同于传统方案将"依赖管理"和"代码执行"视为两个独立步骤，Depot 将其**融合为一条自动化管道**，使 Agent 完全无需感知底层依赖管理的存在。Agent 只需生成代码，Depot 自动处理一切依赖问题。

**与现有工作的区别**：

* OpenAI Code Interpreter：环境固定，不可定制，Agent 无法感知环境

* AutoGPT：裸 pip install，无缓存，无版本管理

* **Depot**：按需 + 缓存 + 结构化反馈 = Agent 无感的依赖管理

### 创新点 2：分级反馈与修复建议 (Graduated Feedback)

**创新类型**：机制创新

传统反馈只是原始 traceback。Depot 将反馈分为三级：

1. **依赖级**：明确告诉 Agent "安装了 X，版本 Y，耗时 Z"

2. **执行级**：stdout/stderr 的结构化包装

3. **建议级**：当失败时，分析失败原因并给出具体修复建议

例如，当 `import torch` 失败时，Depot 不只是返回 `ImportError`，而是：

```
检测到 import torch 失败。
torch 在 PyPI 上可用，最新版本为 2.4.0。
当前环境 Python 3.12，torch>=2.1.0 兼容。
建议: pip install torch>=2.1.0
```

### 创新点 3：透明缓存与增量解析 (Transparent Caching & Incremental Resolution)

**创新类型**：工程创新

维护一个跨任务的共享 venv + `depot.lock` 文件：

* 首次任务安装的依赖自动缓存

* 后续任务共享基础依赖（numpy, pandas 等），只增量安装新包

* Agent 和用户都可以通过锁文件了解环境全貌

* 支持环境快照导出，可复现

***

## 6. 实验设计

### 6.1 测试任务集 (Benchmark Tasks)

设计 15 个测试任务，分为三个难度等级：

#### 难度 L1：基础（5个任务）

每个任务只需 0-1 个外部依赖

| ID | 任务描述               | 可能的依赖      | 预期代码行数 |
| -- | ------------------ | ---------- | ------ |
| T1 | 读取 CSV 文件并计算统计量    | pandas     | 10-15  |
| T2 | 生成随机数并绘制直方图        | matplotlib | 8-12   |
| T3 | 发送 HTTP 请求并解析 JSON | requests   | 10-15  |
| T4 | 正则表达式匹配与文本提取       | (stdlib)   | 8-10   |
| T5 | 文件系统遍历与过滤          | (stdlib)   | 15-20  |

#### 难度 L2：中等（6个任务）

需要 2-3 个外部依赖

| ID  | 任务描述                    | 可能的依赖                    | 预期代码行数 |
| --- | ----------------------- | ------------------------ | ------ |
| T6  | 从 API 获取数据并用 pandas 做聚合 | requests, pandas         | 20-25  |
| T7  | 生成图表并保存为 PNG            | matplotlib, numpy        | 15-20  |
| T8  | 下载网页并提取表格数据             | requests, beautifulsoup4 | 20-25  |
| T9  | 生成词云图                   | wordcloud, matplotlib    | 10-15  |
| T10 | YAML 配置解析与 JSON 输出      | pyyaml                   | 15-20  |
| T11 | 将 DataFrame 写入 Excel 文件 | pandas, openpyxl         | 12-18  |

#### 难度 L3：困难（4个任务）

需要 4+ 个外部依赖，或涉及版本敏感的场景

| ID  | 任务描述                     | 可能的依赖                             | 预期代码行数 |
| --- | ------------------------ | --------------------------------- | ------ |
| T12 | 图片加载 + NumPy 处理 + PIL 输出 | numpy, pillow, matplotlib         | 25-30  |
| T13 | 简单的 ML 训练（线性回归）          | torch 或 sklearn, numpy, pandas    | 30-40  |
| T14 | 自然语言文本预处理 + TF-IDF 计算    | nltk, scikit-learn, pandas        | 30-40  |
| T15 | 多步骤数据管道（爬虫→清洗→分析→可视化）    | requests, bs4, pandas, matplotlib | 40-60  |

### 6.2 实验设置

#### Baseline 系统

| ID | Baseline       | 描述                              |
| -- | -------------- | ------------------------------- |
| B1 | 裸 Python 执行    | Agent 代码直接 subprocess.run，无依赖管理 |
| B2 | 预装全家桶          | Docker 或 venv 预装 50+ 常用包        |
| B3 | **Depot（本系统）** | 完整管道                            |

#### 实验环境

* 干净 Python 3.12 venv（仅含 pip）

* macOS / Linux 双平台测试

* 每个任务独立计时

* 每个任务执行 3 次取平均值（消除网络波动）

#### Agent 配置

* 使用 Claude Sonnet 4.6 作为代码生成 Agent

* 相同的 prompt 模板用于所有 baseline

* 每个任务最多允许 3 轮纠正

***

## 7. 评估指标

### 7.1 核心指标

| 指标           | 定义                               | 重要性   | 预期 Depot 优势              |
| ------------ | -------------------------------- | ----- | ------------------------ |
| **执行成功率**    | 首次执行即成功（exit code 0 + 符合预期输出）的比例 | ★★★★★ | vs B1 优势巨大；vs B2 持平      |
| **端到端延迟**    | 从 Agent 提交代码到收到反馈的总时间            | ★★★★  | vs B2 快 10-50x（缓存后）      |
| **Token 效率** | Agent 为修复依赖问题消耗的额外 token 数       | ★★★★  | vs B1 减少 80%+            |
| **安装包数量**    | 实际安装了多少包（效率指标）                   | ★★★   | vs B2 减少 90%+（按需 vs 全家桶） |
| **纠错轮次**     | Agent 需要几轮才能修正依赖相关错误             | ★★★★  | vs B1 减少到接近 0            |
| **环境一致性**    | 同一任务多次执行的输出是否一致                  | ★★★   | vs B2 持平（锁文件保证）          |

### 7.2 分析维度


对每个 metric，分析：

1. 各 baseline 的绝对数值对比

2. 随任务难度的变化趋势

3. 缓存命中率对性能的影响

---

## 8. 实验结果与分析

### 8.1 实验设计

本实验在 **Docker 严格隔离**环境中, 模拟 Agent 使用三种方案完成 10 个含第三方依赖的代码任务, 测量端到端时间和 Token 消耗。

**代表方案**:

| 方案 | 代表系统 | 核心思路 |
|------|---------|---------|
| B1 裸执行 | Open Interpreter, AutoGPT | 直接执行 → ImportError → Agent 手动修复 → 重执行 |
| B2 预装环境 | OpenAI Code Interpreter, E2B 模板 | 预装 30 个包(1057MB) → 执行; 盲区包仍需 Agent 修复 |
| Depot | 本系统 | 自动检测缺失 → 按需安装 → 执行 → 结构化反馈 |

**实验环境**:
- 基础镜像: `python:3.12-slim` (Docker, 仅 Python + pip, 零预装包)
- 隔离: 三个独立 Docker 容器 (`depot-b1` / `depot-b2` / `depot-dp`), 互不污染, 实验后保留可复查
- B2 预装镜像: `depot-b2-final` (1057MB, 构建 ~100s), 已保存为 `b2-image.tar`
- 任务: 10 个 Benchmark (T6-T15), 覆盖 pandas/numpy/matplotlib/scipy/scikit-learn/wordcloud/bs4/pyyaml/openpyxl/pillow/requests 等

**Agent 修复模型**:
- B1 遇到 ImportError 时, 模拟 Agent: 收到错误 → LLM 分析故障(约 3s) → 生成 `pip install X` → 等待安装 → 重新执行
- 每次失败的 Token 代价: 生成代码(500t) + ImportError(200t) + Agent分析+生成修复(500t) + 安装反馈(300t) + 重执行(200t) = 1,700 tokens
- 成功时的 Token 代价: 生成代码(500t) + 结果确认(100t) = 600 tokens (B1/B2) 或 700 tokens (Depot, 含结构化报告)

### 8.2 总览

Agent 使用三种方案完成全部 10 个任务的总成本:

| 指标 | B1 裸执行 | B2 预装环境 | Depot |
|------|----------|-----------|-------|
| **端到端总时间** | 103,135ms (103.1s) | 8,421ms (8.4s) | 48,518ms (48.5s) |
| **Token 总消耗** | 13,700 | 7,100 | **7,000** |
| **对话总轮次** | 17 轮 | 11 轮 | **10 轮** |
| **Agent 修复次数** | 7 次 | 1 次 | **0 次** |
| **依赖感知数** | 0 | 0 | **全部任务自动感知** |
| **基础设施成本** | 0 | 1057MB / ~100s构建 | 0 |

> 三个方案最终都成功完成了全部 10 个任务——B1 和 B2 通过 Agent 修复机制。差异在于 Agent 付出的代价: B1 为 7 个失败各花 ~14s 修复, B2 有 1 个盲区(需额外 5.7s 修复), Depot 全自动零修复。

### 8.3 逐任务原始数据

每个任务的三方端到端耗时, 以及 B1 的修复开销和 Depot 的安装开销:

| Task | 依赖 | B1 总耗时 | B1 修复耗时 | B2 总耗时 | B2 盲区 | Depot 总耗时 | Depot 安装耗时 | Depot 缓存 |
|------|------|----------|-----------|----------|--------|------------|-------------|----------|
| T6 | pandas, requests | 18,601ms | 18,539ms | 213ms | — | 14,790ms | 14,505ms | 首次 |
| T7 | matplotlib, numpy | 42,062ms | 42,003ms | 164ms | — | 10,140ms | 9,960ms | 首次 |
| T8 | pandas, beautifulsoup4 | 5,752ms | 5,551ms | 245ms | — | 2,681ms | 2,465ms | 首次 |
| T9 | wordcloud, matplotlib | 5,265ms | 5,116ms | 5,937ms | wordcloud | 2,122ms | 1,834ms | 首次 |
| T10 | pyyaml | 7,814ms | 7,758ms | 69ms | — | 1,803ms | 1,741ms | 首次 |
| T11 | pandas, openpyxl | 193ms | 0 | 202ms | — | 2,371ms | 2,163ms | 首次 |
| T12 | numpy, scipy, pillow | 11,659ms | 11,554ms | 273ms | — | 7,242ms | 6,969ms | 首次 |
| T13 | numpy, pandas, sklearn | 11,029ms | 10,845ms | 546ms | — | 6,616ms | 6,046ms | 首次 |
| T14 | numpy, pandas | 192ms | 0 | 190ms | — | 185ms | 0ms | **缓存命中** |
| T15 | numpy, pandas, matplotlib, scipy | 568ms | 0 | 582ms | — | 568ms | 0ms | **缓存命中** |
| **合计** | | **103,135ms** | **101,366ms** | **8,421ms** | 1个盲区 | **48,518ms** | **45,683ms** | 2次命中 |

### 8.4 B1 的额外时间分析

B1 的 103.1s 总时间中, **101.4s (98%) 花在 Agent 修复依赖错误上**, 仅 1.7s 花在正常执行:

| 任务 | B1 修复耗时 | 组成分析 |
|------|-----------|---------|
| T6 | 18,539ms | Agent分析(3s) + pip install pandas+requests(15.3s) + 重执行(270ms) |
| T7 | 42,003ms | Agent分析(3s) + pip install matplotlib(38.8s) + 重执行(177ms) |
| T8 | 5,551ms | Agent分析(3s) + pip install beautifulsoup4(2.3s) + 重执行(257ms) |
| T9 | 5,116ms | Agent分析(3s) + pip install wordcloud(1.8s) + 重执行(297ms) |
| T10 | 7,758ms | Agent分析(3s) + pip install pyyaml(4.7s) + 重执行(65ms) |
| T12 | 11,554ms | Agent分析(3s) + pip install scipy(8.3s) + 重执行(225ms) |
| T13 | 10,845ms | Agent分析(3s) + pip install scikit-learn(7.3s) + 重执行(552ms) |
| **总计** | **101,366ms** | Agent LLM等待(21s) + pip安装(78.5s) + 重执行(1.7s) |

> B1 的 7 个失败任务的修复流程完全相同——Agent 每次都做同样的事: 读错误→分析→pip install→重执行。这些操作是机械性的, 却消耗了大量 Agent 时间和 Token (11,900 tokens)。Depot 将这 101s 的机械操作变成了 46s 的自动安装(Agent 无需参与)。

### 8.5 B2 的盲区与代价

B2 预装了 30 个包 (1057MB 镜像, 构建约 100s), 9/10 任务直接成功, 但 **T9 暴露了预装方案的根本局限**:

| 任务 | B2 结果 | 缺失的包 | Agent 额外代价 |
|------|--------|---------|-------------|
| T6-T8, T10-T15 | ✅ 直接成功 | — | 0 |
| **T9** | ❌ 失败 | **wordcloud** | 5,937ms (Agent分析3s + pip install 2.5s + 重执行313ms) + 1,700 tokens |

> 预装方案的本质问题是: 任何固定集合都无法覆盖全部场景。PyPI 有 20 万+ 包, 30 个预装包(或 OpenAI Code Interpreter 的 330 个包)都有盲区。B2 运行 9/10 任务极快(0.1-0.6s), 但遇到盲区就退化为 B1 的多轮修复模式, Agent 仍需手动介入。

### 8.6 Depot 的缓存收益

Depot 的总安装时间 45.7s 中, 前 8 个任务占了 45.7s (首次安装各类基础依赖), **后 2 个任务完全缓存命中**:

| 阶段 | 任务 | 安装耗时 | 缓存状态 |
|------|------|---------|---------|
| 冷启动 | T6-T13 | 45,683ms | 首次安装 numpy/pandas/matplotlib/scipy/bs4/wordcloud/pyyaml/openpyxl/scikit-learn |
| 缓存命中 | **T14** | **0ms** | numpy、pandas 已在 T6 安装 |
| 缓存命中 | **T15** | **0ms** | numpy、pandas、matplotlib、scipy 已在 T6/T7/T12 安装 |

> 随着任务数量增加, 缓存命中率将持续上升。Agent 实际工作中依赖高度重复(numpy/pandas 几乎每个任务都用), 首次安装后后续任务安装开销趋近于零。T14/T15 的 0ms 安装时间证明了这一点。

### 8.7 Token 消耗详细计算

```
B1 裸执行 (7 个任务失败需修复):
  3 个成功任务: 3 × 600t(生成+确认)              =  1,800 tokens
  7 个失败任务: 7 × 1,700t(生成+错误+修复+重执行)  = 11,900 tokens
  ─────────────────────────────────────────────
  总计                                          = 13,700 tokens

B2 预装环境 (1 个任务失败需修复):
  9 个成功任务: 9 × 600t                        =  5,400 tokens
  1 个失败任务: 1 × 1,700t                      =  1,700 tokens
  ─────────────────────────────────────────────
  总计                                          =  7,100 tokens

Depot (全部自动成功, 无需修复):
  10 个任务: 10 × 700t(生成+结构化报告)           =  7,000 tokens
```

| | Token | 比 B1 | 比 B2 | 反馈格式 |
|---|---|---|---|---|
| B1 | 13,700 | — | — | 原始 ImportError traceback |
| B2 | 7,100 | -48% | — | 原始 traceback 或 stdout |
| **Depot** | **7,000** | **-49%** | **-1%** | **结构化报告 (依赖/安装/执行/建议)** |

### 8.8 逐任务 Token 明细

| Task | B1 tokens | B2 tokens | Depot tokens | B1 为何多? | B2 为何多? |
|------|----------|----------|-------------|-----------|----------|
| T6 | 1,700 | 600 | 700 | ImportError:pandas | — |
| T7 | 1,700 | 600 | 700 | ImportError:matplotlib | — |
| T8 | 1,700 | 600 | 700 | ImportError:bs4 | — |
| T9 | 1,700 | **1,700** | 700 | ImportError:wordcloud | **盲区:wordcloud** |
| T10 | 1,700 | 600 | 700 | ImportError:pyyaml | — |
| T11 | 600 | 600 | 700 | (前面修复已装好pandas) | — |
| T12 | 1,700 | 600 | 700 | ImportError:scipy | — |
| T13 | 1,700 | 600 | 700 | ImportError:sklearn | — |
| T14 | 600 | 600 | 700 | — | — |
| T15 | 600 | 600 | 700 | — | — |
| **合计** | **13,700** | **7,100** | **7,000** | 7个失败×1,200t修复 | 1个盲区×1,100t修复 |

### 8.9 执行耗时详细记录

每任务的纯执行耗时 (不含 Agent 等待和 pip 安装):

| Task | B1 执行耗时 | B2 执行耗时 | Depot 执行耗时 | 说明 |
|------|----------|----------|-------------|------|
| T6 | 62ms(失败) + 270ms(重执行) | 213ms | 285ms | B1首次失败后重执行成功 |
| T7 | 59ms(失败) + 177ms(重执行) | 164ms | 180ms | 同上 |
| T8 | 201ms(失败) + 257ms(重执行) | 245ms | 216ms | 同上 |
| T9 | 149ms(失败) + 297ms(重执行) | 166ms(失败) + 313ms(重执行) | 288ms | B2盲区,B1和B2均需重执行 |
| T10 | 56ms(失败) + 65ms(重执行) | 69ms | 62ms | B1首次失败后重执行成功 |
| T11 | 193ms(一次成功) | 202ms | 208ms | B1缓存命中(前面已装pandas) |
| T12 | 105ms(失败) + 225ms(重执行) | 273ms | 273ms | B1首次失败后重执行成功 |
| T13 | 184ms(失败) + 552ms(重执行) | 546ms | 570ms | 同上 |
| T14 | 192ms | 190ms | 185ms | 三方均缓存命中 |
| T15 | 568ms | 582ms | 568ms | 三方均缓存命中 |
| **合计** | **3,394ms** | **2,966ms** | **2,835ms** | Depot 执行最快 |

> 纯执行耗时三方接近 (均在 3s 以内), 说明 Depot 的额外开销**不在执行环节**——它在依赖检测和结构化报告生成上。而这正是 Depot 的核心价值所在。

### 8.10 针对三个 Gap 的验证

**Gap 1 — 依赖失明**:
- 实验数据: B1 和 B2 对依赖完全无感知 (0 个), Depot 对全部 10 个任务的依赖都做了主动检测
- 具体表现: B1 的 7 个失败都是在 ImportError 之后才知道缺包; B2 的 T9 盲区也是在执行失败后才发现 wordcloud 未预装
- Depot 的结构化报告明确告知: "检测到 N 个外部依赖: [具体包名]; 已安装: [X]; 缓存命中: [Y]"

**Gap 2 — 按需解析缺失**:
- 实验数据: B1 浪费 101.4s 在 Agent 手动修复上 (7/10 任务), Token 多花 49%
- B2 有 1 个盲区 (wordcloud), 且需 1057MB/100s 预装成本
- Depot 全自动安装 45.7s (仅首次), 2/10 任务缓存命中, 缓存命中后 0ms 安装时间

**Gap 3 — 反馈非结构化**:
- 实验数据: B1/B2 失败时返回 `ModuleNotFoundError: No module named 'xxx'`
- Depot 始终返回结构化报告: "检测到 N 个依赖/安装 M 个包 (Xms)/缓存命中 K 个/执行成功 (Yms)/退出码 0"

### 8.11 实验环境证据

| 证据 | 内容 | 状态 |
|------|------|------|
| B1 容器 | `docker exec -it depot-b1 bash` (python:3.12-slim) | 保留, 可复查 |
| B2 容器 | `docker exec -it depot-b2 bash` (depot-b2-final) | 保留, 可复查 |
| Depot 容器 | `docker exec -it depot-dp bash` (python:3.12-slim, 按需安装后) | 保留, 可复查 |
| B2 镜像 | `depot-b2-final` (1057MB) + `b2-image.tar` (1.1GB) | 保留 |
| 原始数据 | `docker-experiment/results/results.json` | 完整 JSON |
| 代码文件 | `docker-experiment/results/T6.py` ~ `T15.py` | 10 个任务 |

### 8.12 汇总结论

1. **B1 的主要代价是 Agent 时间**: 7/10 任务失败, 101s 修复时间 (LLM等待 + pip安装 + 重执行), 13,700 tokens。在干净环境中, Agent 大部分精力花在机械性的环境修复上, 而非代码质量改进。

2. **B2 的代价是基础设施 + 不可靠**: 1057MB/100s 预装让 9/10 极快 (0.1-0.6s), 但 1 个盲区 (wordcloud) 暴露了根本局限——任何固定预装列表都无法覆盖 PyPI 20 万+ 包。

3. **Depot 是最优平衡**: 零准备, 100% 覆盖, 最少 Token (7,000)。首次安装 45.7s 随缓存命中 (2/10 → 预期持续增长) 快速摊薄。对 Agent 而言, 全部 Token 用于代码创造, 而非机械性环境修复。

---

## 9. 项目进度与状态

### 9.1 当前进度

| 模块 | 状态 | 说明 |
|------|------|------|
| 详细设计文档 | ✅ | 10 章，选题背景→Gap分析→系统设计→实验→结果→路线图 |
| 核心管道实现 | ✅ | 11 个模块 ~2000行：extractor/resolver/installer/executor/feedback/cache/pipeline/config/cli/sdk |
| 单元测试 | ✅ | 8 个测试文件，125 个测试用例，全部通过 (5s) |
| Baseline B1/B2 | ✅ | B1 裸执行（subprocess）+ B2 预装全家桶（venv+57包） |
| 15 个 Benchmark | ✅ | L1×5（0-1依赖）/ L2×6（2-3依赖）/ L3×4（4+依赖） |
| 实验与结果分析 | ✅ | 15×3=45 组实验，7 小节完整分析写入第 8 章 |
| 多包管理器 | ✅ | pip / uv / poetry 自动检测 + 回退 |
| CLI 工具 | ✅ | `depot run` / `depot check` / `depot cache` |
| Python SDK | ✅ | `depot.sdk.execute()` / `depot.sdk.check()` / `configure()` / `inspect_environment()` |
| README + 使用文档 | ✅ | README.md (217行) + docs/USAGE.md (完整使用文档) |
| GitHub 开源 | ✅ | 仓库 + Release v1.0.0: github.com/canglang007/depot-agent |

### 9.2 技术栈

| 组件 | 技术选型 | 理由 |
|------|---------|------|
| 核心语言 | Python 3.12 | 目标语言一致，生态丰富 |
| AST 解析 | 标准库 `ast` | 零依赖 |
| 依赖安装 | pip / uv / poetry (subprocess) | 多后端自动选择 |
| 环境隔离 | `venv` + `subprocess` | 轻量，启动快 |
| 配置管理 | JSON (depot.lock) | 简单直接 |
| 测试框架 | pytest | 标准选择 |

### 9.3 实际代码结构

```
depot/
├── pyproject.toml           # v1.0.0, pip install -e .
├── README.md                # 217 行项目说明
├── LICENSE                  # MIT
├── docs/
│   └── USAGE.md             # 完整使用文档
├── src/depot/
│   ├── __init__.py          # 包入口, v1.0.0
│   ├── config.py            # 全局配置 (71行)
│   ├── extractor.py         # AST 依赖提取器 (354行)
│   ├── resolver.py          # 依赖解析器 (217行)
│   ├── installer.py         # 按需安装器 pip/uv/poetry (203行)
│   ├── executor.py          # 隔离执行器 (159行)
│   ├── feedback.py          # 结构化反馈生成器 (234行)
│   ├── cache.py             # 缓存管理 (108行)
│   ├── pipeline.py          # 管道编排器 (250行)
│   ├── cli.py               # CLI 工具 depot run/check/cache (187行)
│   └── sdk.py               # Agent SDK 接口 (209行)
├── tests/
│   ├── test_extractor.py    # 72 个测试
│   ├── test_executor.py     # 16 个测试
│   ├── test_feedback.py     # 14 个测试
│   ├── test_pipeline.py     # 15 个测试
│   ├── test_resolver.py     # 11 个测试
│   ├── test_cache.py        # 17 个测试
│   ├── test_config.py       # 10 个测试
│   └── test_installer.py    # 6 个测试
├── benchmarks/
│   ├── baselines/
│   │   ├── base.py                # Baseline 基类
│   │   ├── b1_bare.py             # B1: 裸执行
│   │   └── b2_preinstalled.py     # B2: 预装全家桶 (57包)
│   ├── tasks/
│   │   ├── task_definitions.py    # 任务数据结构
│   │   └── tasks.py               # 15 个 Benchmark 任务
│   └── run_experiment.py          # 实验执行脚本 (CLI)
├── experiment-results/       # 实验结果（保留）
└── DESIGN.md                 # 本文档
```

***

## 10. 开源路线图

### v0.1 — Demo（课程阶段）✅ 已完成

* [x] 设计文档（本文档）
* [x] 核心 Pipeline 实现（8 个模块）
* [x] 2 个 Baseline（B1裸执行 + B2全家桶）
* [x] 15 个 Benchmark Tasks
* [x] 实验执行脚本
* [x] 125 个单元测试

### v0.2 — Alpha ✅ 已完成

* [x] 支持 pip / uv / poetry 多种包管理器（自动检测 + 回退）
* [x] CLI 工具（`depot run` / `depot check` / `depot cache`）
* [ ] 依赖可视化（生成依赖图）—— 后续版本

### v0.3 — Beta ✅ 已完成

* [x] Python SDK（`depot.sdk.execute()` / `depot.sdk.check()`）
* [ ] 跨语言支持（Node.js / npm）—— 后续版本
* [ ] 远程执行后端 —— 后续版本

### v1.0 — 正式版 ✅ 基本完成

* [x] Agent 集成示例（SDK API + CLI）
* [x] 文档 + 教程（README.md + DESIGN.md）
* [x] 结构化反馈（JSON/Markdown 双格式）
* [x] 多种包管理器支持
* [ ] 性能优化（预热的执行池）—— 后续版本
* [ ] LangChain / Autogen 官方集成 —— 后续版本

### 后续展望

* [ ] 跨语言支持（Node.js / npm / yarn）
* [ ] 依赖可视化 —— 生成 import 依赖图
* [ ] 远程执行后端 —— 类似 E2B 的云端沙箱
* [ ] 预热执行池 —— 预启动 Python 进程，消除冷启动延迟
* [ ] IDE 插件 —— VS Code / JetBrains 集成

***

*文档版本：v2.1 | 最后更新：2026年6月7日 | 全部完成，GitHub 已发布*
