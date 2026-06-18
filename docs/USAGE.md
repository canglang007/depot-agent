# Depot 使用文档

## 目录

1. [快速开始](#1-快速开始)
2. [CLI 命令行工具](#2-cli-命令行工具)
3. [Python SDK (Agent 集成)](#3-python-sdk-agent-集成)
4. [管道 API (高级用法)](#4-管道-api-高级用法)
5. [配置详解](#5-配置详解)
6. [包管理器](#6-包管理器)
7. [缓存管理](#7-缓存管理)
8. [实验与评估](#8-实验与评估)
9. [常见问题](#9-常见问题)

---

## 1. 快速开始

### 安装

```bash
# 从 PyPI 安装（推荐）
pip install depot-agent

# 或从 GitHub 安装最新版
pip install git+https://github.com/canglang007/depot-agent.git
```

### 安装 Claude Code Skill（可选）

```bash
bash <(curl -sL https://raw.githubusercontent.com/canglang007/depot-agent/main/scripts/install-skill.sh)
```

安装后在 Claude Code 中输入 `/depot-agent` 即可调用 Skill。

### 一行代码

```python
from depot.sdk import execute

result = execute("import numpy; print(numpy.array([1,2,3]).sum())")
print(result["status"])   # "success"
```

### 命令行

```bash
depot run -c "import numpy; print(numpy.array([1,2,3]).sum())"
```

---

## 2. CLI 命令行工具

### `depot run` — 执行代码

```bash
# 执行文件
depot run script.py

# 执行内联代码
depot run -c "import numpy; print(numpy.__version__)"

# 从 stdin 读取
echo "print('hello')" | depot run

# 离线执行
depot run --offline script.py

# 指定超时（秒）
depot run --timeout 60 script.py

# 使用 uv 加速安装
depot run --pm uv script.py

# 指定 PyPI 镜像
depot run --mirror https://pypi.tuna.tsinghua.edu.cn/simple script.py

# JSON 输出（供 Agent 程序化消费）
depot run --json -c "import numpy; print('hello')"

# 只检查不安装
depot run --no-install script.py
```

### `depot check` — 检查依赖（不执行）

```bash
depot check script.py
depot check -c "import numpy; from torch import nn"
depot check --json -c "import numpy; from torch import nn"
```

JSON 输出示例：
```json
{
  "total_deps": 2,
  "third_party": ["numpy", "torch"],
  "stdlib": [],
  "needs_install": ["numpy", "torch"]
}
```

### `depot cache` — 缓存管理

```bash
depot cache list       # 列出缓存的包
depot cache info       # 缓存统计
depot cache clear      # 清除缓存
```

---

## 3. Python SDK (Agent 集成)

### 基本用法

```python
from depot.sdk import execute, check, configure, inspect_environment

# 可选：全局配置
configure(
    data_dir="./depot-data",
    timeout=60,
    preferred_pm="uv",
    mirror="https://pypi.tuna.tsinghua.edu.cn/simple",
)

# 执行代码 — 自动处理依赖
result = execute("import numpy; print(numpy.array([1,2,3]))")

# 检查依赖 — 不执行
deps = check("from transformers import pipeline; import torch")

# 环境检查
env = inspect_environment()
```

### execute() 返回值

```python
{
    "status": "success",          # "success" | "partial" | "failed"
    "exit_code": 0,
    "stdout": "...",
    "stderr": "",
    "summary": "检测到 1 个外部依赖。代码执行成功 (耗时 12ms)",
    "suggestions": [],
    "dependency_analysis": {
        "total": 1,
        "third_party": ["numpy"],
        "stdlib": [],
    },
    "install_info": {
        "installed": ["numpy"],      # 本次新安装的包
        "skipped": [],               # 缓存命中的包
        "failed": [],                # 安装失败的包
        "install_time_ms": 3200,
    },
    "execution_time_ms": 12,
    "total_time_ms": 3212,
}
```

### Agent 集成示例

```python
from depot.sdk import execute, check

class MyAgent:
    def run_code(self, code: str) -> str:
        # 可选预检
        deps = check(code)
        if deps["needs_install"]:
            self.log(f"需要安装: {deps['needs_install']}")

        # 执行
        result = execute(code)

        if result["status"] == "success":
            return result["stdout"]
        elif result["suggestions"]:
            # 把修复建议喂回 Agent
            return self.fix_and_retry(code, result["suggestions"])
```

### execute() 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `code` | str | 必填 | Python 代码 |
| `auto_install` | bool | True | 是否自动安装缺失包 |
| `known_modules` | set | None | 已知本地模块名 |
| `timeout` | int | None | 覆盖全局超时(秒) |
| `offline` | bool | False | 离线模式 |

---

## 4. 管道 API (高级用法)

```python
from depot import DepotConfig, DepotPipeline

config = DepotConfig(
    data_dir="./my-depot",
    execution_timeout=60,
    preferred_pm="uv",
)
pipeline = DepotPipeline(config)

# 执行
report = pipeline.run(code)

# 查看详情
print(report.status)              # RunStatus.SUCCESS
print(report.summary)             # 人类可读摘要
print(report.dependency_summary)  # 依赖详情
print(report.install_summary)     # 安装详情
print(report.execution_summary)   # 执行详情
print(report.suggestions)         # 修复建议
print(report.timeline)            # 时间线

# 导出
json_str = pipeline.report_to_json(report)
md_str = pipeline.report_to_markdown(report)
```

---

## 5. 配置详解

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `data_dir` | Path | `./depot-data` | 数据/缓存/锁文件目录 |
| `execution_timeout` | int | 30 | 执行超时(秒) |
| `install_timeout` | int | 60 | 单包安装超时(秒) |
| `install_retries` | int | 2 | 安装失败重试次数 |
| `preferred_pm` | str | `""` | 包管理器: pip/uv/poetry，"":自动检测 |
| `pypi_mirror` | str | None | PyPI 镜像 URL |
| `allow_network` | bool | True | 是否允许网络 |
| `cache_enabled` | bool | True | 是否启用缓存 |
| `cache_ttl` | int | 3600 | 缓存有效期(秒) |
| `parallel_install` | bool | True | 是否并行安装 |
| `max_parallel` | int | 4 | 最大并行数 |

---

## 6. 包管理器

| 管理器 | 特点 | CLI 用法 |
|--------|------|---------|
| pip | Python 标准，零额外依赖 | `--pm pip` |
| uv | Rust 实现，10-100x 快速 | `--pm uv` |
| poetry | 项目管理 + 依赖解析 | `--pm poetry` |

Depot 自动检测可用管理器，优先级 uv > pip > poetry。首选失败自动回退。

---

## 7. 缓存管理

Depot 通过 `depot.lock` 文件记录已安装包的版本，跨任务复用。

```bash
depot cache list       # 列出缓存包
depot cache info       # 缓存统计
depot cache clear      # 清除所有缓存
```

首次安装有延迟（~1-3s），缓存命中后零开销。

---

## 8. 实验与评估

```bash
# 运行完整实验（15 任务 × 3 Baseline = 45 组）
python benchmarks/run_experiment.py --timeout 60

# 指定任务
python benchmarks/run_experiment.py --tasks T1 T6 T9 T13

# 指定难度
python benchmarks/run_experiment.py --difficulty 1 2
```

输出 `experiment-results/results.json`（原始数据）和 `report.md`（对比报告）。

---

## 9. 常见问题

**Q: 执行慢？**
```bash
depot run --pm uv script.py                     # 用 uv 加速
depot run --mirror https://pypi.tuna.tsinghua.edu.cn/simple script.py  # 国内镜像
```

**Q: Agent 如何使用？**
```python
from depot.sdk import execute
result = execute(agent_generated_code)
if result["suggestions"]:
    agent.fix(result["suggestions"])  # 把修复建议喂回 Agent
```

**Q: 安全性？**
- 30s 超时 + 512MB 内存限制 + 可选离线模式 + 临时文件自动清理
- 生产环境建议 Docker / Firecracker microVM 增强隔离
