# Depot

> 面向代码生成 Agent 的按需依赖解析系统

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-125%20passed-brightgreen)]()
[![Version](https://img.shields.io/badge/version-1.0.0-orange)]()

**Depot** 是一个为 LLM Agent 构建的轻量级代码执行运行时。它自动检测 Agent 生成代码中的外部依赖，按需安装缺失的包，在隔离环境中执行代码，并生成结构化的执行报告反馈给 Agent。

---

## 为什么需要 Depot？

LLM Agent 生成代码后需要执行验证，但核心困境是：**Agent 不知道自己运行环境里有什么包**。

```
Agent 盲写 import torch → 环境没有 → ImportError → 多轮试错
```

现有方案：
- **OpenAI Code Interpreter**：预装 330 个固定包，不可定制
- **E2B / CodeSandbox**：需提前构建环境模板
- **裸执行**：ImportError 后 Agent 手动修

**Depot 的方案**：在 Agent 提交代码和执行代码之间插入一个依赖感知管道，使 Agent 完全不需要关心环境状态。

```
Agent 生成代码 → Depot: AST分析→检测缺失→按需安装→隔离执行→结构化报告 → Agent 收到结果
```

## 快速开始

### 安装

```bash
pip install depot-agent
# 或
pip install depot
```

### 命令行

```bash
# 执行代码文件
depot run script.py

# 执行内联代码
depot run -c "import numpy; print(numpy.array([1,2,3]))"

# 检查依赖（不执行）
depot check script.py

# 使用 uv 加速安装
depot run --pm uv script.py

# 离线模式
depot run --offline script.py

# JSON 输出（供 Agent 消费）
depot run --json -c "import requests; print(requests.get('...'))"

# 缓存管理
depot cache list
depot cache info
depot cache clear
```

### SDK (Agent 集成)

```python
from depot.sdk import execute, check, configure

# 配置
configure(data_dir="./depot-data", timeout=30, preferred_pm="uv")

# 执行代码 —— 一行搞定
result = execute("""
import numpy as np
import pandas as pd

data = pd.DataFrame({"a": [1,2,3], "b": [4,5,6]})
print(data.describe())
""")

print(result["status"])          # "success"
print(result["summary"])         # "检测到2个外部依赖。代码执行成功。"
print(result["dependency_analysis"])
# {"third_party": ["numpy", "pandas"], "stdlib": []}
print(result["install_info"])
# {"installed": ["pandas"], "skipped": ["numpy"], "install_time_ms": 3200}

# 检查依赖（不执行）
deps = check("from transformers import pipeline; import torch")
print(deps["needs_install"])  # ["transformers", "torch"]
```

### 完整管道 API

```python
from depot import DepotConfig, DepotPipeline

config = DepotConfig(
    data_dir="./my-depot",
    execution_timeout=60,
    preferred_pm="uv",
    pypi_mirror="https://pypi.tuna.tsinghua.edu.cn/simple",
)
pipeline = DepotPipeline(config)

report = pipeline.run(code)
print(report.status)     # RunStatus.SUCCESS
print(report.summary)    # 人类可读摘要

# 结构化报告包含:
#   - dependency_analysis: 检测到的所有导入（分类）
#   - install_info: 安装详情（装了哪些/跳过哪些/失败）
#   - execution: 执行结果（exit_code/stdout/stderr/耗时）
#   - suggestions: 修复建议
#   - timeline: 完整时间线
```

## 系统架构

```
Agent 代码
     │
     ▼
┌─────────────────────────────────────────────┐
│              Depot 系统                       │
│                                               │
│  AST提取器   →   依赖解析器   →   按需安装器    │
│  (代码分析)      (环境查询)       (增量安装)     │
│                                               │
│           隔离执行器   →   结构化反馈           │
│           (安全执行)       (Agent报告)          │
└─────────────────────────────────────────────┘
     │
     ▼
Agent 收到结构化报告
```

## 三种 Baseline 对比

| 方案 | 原理 | 依赖处理 | 环境准备 | 故障模式 |
|------|------|---------|---------|---------|
| **B1 裸执行** | 系统 Python 直接 subprocess | 零，缺包就报错 | 0 | ImportError, Agent 自己修 |
| **B2 全家桶** | venv + 预装 57 个包 | 预装，新包仍缺 | ~90s / ~2GB | 不在全家桶范围的包仍失败 |
| **Depot** | AST 分析 + 按需安装 + 缓存 | 自动检测+补齐 | 0（按需） | 首次安装有延迟，缓存后零开销 |

## 与现有系统的差异

| 系统 | AST依赖检测 | 自动安装 | 结构化反馈 | Agent感知 |
|------|:----------:|:--------:|:--------:|:---------:|
| OpenAI Code Interpreter | ❌ | ❌ | ❌ | ❌ |
| E2B | ❌ | ⚠️ 需手动 | ❌ | ❌ |
| Google AI Studio | ❌ | ❌ | ❌ | ❌ |
| CodeSandbox SDK | ❌ | ⚠️ 需手动 | ❌ | ❌ |
| Open Interpreter | ❌ | ⚠️ 失败后 | ❌ | ❌ |
| **Depot** | **✅** | **✅** | **✅** | **✅** |

## 配置选项

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `data_dir` | `./depot-data` | 数据目录 |
| `execution_timeout` | 30 | 执行超时(秒) |
| `install_timeout` | 60 | 安装超时(秒) |
| `preferred_pm` | `""` (自动) | 包管理器: pip/uv/poetry |
| `pypi_mirror` | `None` | PyPI 镜像 URL |
| `allow_network` | `True` | 是否允许网络 |
| `cache_enabled` | `True` | 是否启用缓存 |
| `parallel_install` | `True` | 是否并行安装 |

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# 运行 benchmark 实验
python benchmarks/run_experiment.py
```

## 项目结构

```
depot/
├── pyproject.toml
├── README.md
├── src/depot/
│   ├── __init__.py       # 包入口
│   ├── sdk.py            # Agent 集成 SDK
│   ├── cli.py            # 命令行工具
│   ├── config.py         # 全局配置
│   ├── extractor.py      # AST 依赖提取器
│   ├── resolver.py       # 依赖解析器
│   ├── installer.py      # 按需安装器 (pip/uv/poetry)
│   ├── executor.py       # 隔离执行器
│   ├── feedback.py       # 结构化反馈生成器
│   ├── cache.py          # 缓存管理
│   └── pipeline.py       # 管道编排器
├── tests/                # 125 个单元测试
├── benchmarks/           # 15 个 benchmark 任务
│   ├── tasks/
│   ├── baselines/
│   └── run_experiment.py
└── DESIGN.md             # 详细设计文档
```

## 许可证

MIT License
