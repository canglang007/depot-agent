# Depot

> 面向代码生成 Agent 的按需依赖解析系统

[![PyPI](https://img.shields.io/pypi/v/depot-agent?color=blue)](https://pypi.org/project/depot-agent/)
[![Python](https://img.shields.io/pypi/pyversions/depot-agent?color=brightgreen)](https://python.org)
[![License](https://img.shields.io/github/license/canglang007/depot-agent)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-125%20passed-brightgreen)]()
[![Downloads](https://img.shields.io/pypi/dm/depot-agent?color=orange)](https://pypi.org/project/depot-agent/)

**Depot** 是一个为 LLM Agent 构建的轻量级代码执行运行时。它自动检测 Agent 生成代码中的外部依赖，按需安装缺失的包，在隔离环境中执行代码，并生成结构化的执行报告反馈给 Agent。

---

## 为什么需要 Depot？

LLM Agent 生成代码后需要执行验证，但核心困境是：**Agent 不知道自己运行环境里有什么包**。

```
Agent 盲写 import torch -> 环境没有 -> ImportError -> 多轮试错
```

| 方案 | 代表系统 | 问题 |
|------|---------|------|
| 裸执行 | Open Interpreter, AutoGPT | ImportError 后 Agent 手动修，多轮 Token 浪费 |
| 预装环境 | OpenAI Code Interpreter, E2B | 固定包集合，臃肿(1GB+)，新包仍然失败 |
| **Depot** | **本系统** | **按需安装，零预装，零盲区，结构化反馈** |

实验结果：
- **B1**: 6/15 首次成功 — Agent 浪费 44% Token 在修复依赖上
- **B2**: 9/15 首次成功（1057MB 预装仍有 6 个盲区）— 臃肿且不可靠
- **Depot**: 14/15 首次成功 — Token 节省 44%，零预装，零盲区

---

## 安装

### 从 PyPI 安装（推荐）

```bash
pip install depot-agent
```

### 从 GitHub 安装

```bash
pip install git+https://github.com/canglang007/depot-agent.git
```

### 安装 Claude Code Skill（可选）

如果你使用 Claude Code，一键安装 Skill：

```bash
bash <(curl -sL https://raw.githubusercontent.com/canglang007/depot-agent/main/scripts/install-skill.sh)
```

安装后在 Claude Code 中输入 `/depot-agent` 即可调用 Skill。

---

## 快速使用

### CLI 命令行

```bash
# 执行代码（自动安装缺失的包）
depot run -c "import numpy; print(numpy.array([1,2,3]).sum())"

# 执行文件
depot run script.py

# 检查依赖（不执行）
depot check -c "from transformers import pipeline; import torch" --json

# 使用 uv 加速安装
depot run --pm uv script.py

# JSON 输出（供 Agent 程序化消费）
depot run --json -c "import pandas; print('ok')"

# 缓存管理
depot cache list
depot cache info
depot cache clear
```

### Python SDK（Agent 集成）

```python
from depot.sdk import execute, check, configure

# 可选：全局配置
configure(
    data_dir="./depot-data",
    timeout=30,
    preferred_pm="uv",
    mirror="https://pypi.tuna.tsinghua.edu.cn/simple",
)

# 执行代码 —— 一行搞定，自动处理依赖
result = execute(