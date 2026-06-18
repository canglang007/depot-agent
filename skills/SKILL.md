---
name: depot-agent
description: Use Depot to execute Python code with automatic dependency resolution. When you write Python code that uses third-party libraries, invoke this skill to run it through Depot instead of raw subprocess, so missing packages are detected, installed, and cached automatically.
metadata:
  version: "1.0.0"
  author: canglang007
---

# Depot — Python 代码自动依赖管理

## What Depot Does

When Claude writes Python code that imports third-party libraries, Depot:
1. **AST extracts** all `import` statements from the code
2. **Checks** which packages are already installed in the environment
3. **Installs** only the missing packages (using pip/uv/poetry)
4. **Executes** the code in an isolated subprocess
5. **Returns** a structured report (JSON/Markdown) with dependency analysis, install details, execution output, and fix suggestions

## When to Use

Use Depot whenever you need to run Python code that uses third-party imports, especially when:
- The code imports packages like `numpy`, `pandas`, `torch`, `matplotlib`, `requests`, etc.
- You're not 100% sure the target environment has those packages installed
- You want to avoid the `ModuleNotFoundError → fix → retry` cycle
- You want structured feedback about what was installed and how long it took

## Installation

```bash
pip install git+https://github.com/canglang007/depot-agent.git
# or (once released on PyPI)
pip install depot-agent
```

## Usage

### CLI

```bash
# Execute a Python file with automatic dependency handling
depot run script.py

# Execute inline code
depot run -c "import numpy; print(numpy.array([1,2,3]))"

# Check dependencies without executing
depot check -c "from transformers import pipeline; import torch" --json

# Use uv for faster installs
depot run --pm uv script.py

# Use a PyPI mirror
depot run --mirror https://pypi.tuna.tsinghua.edu.cn/simple script.py
```

### Python SDK (from inside Claude Code)

```python
from depot.sdk import execute, check

# Execute code with auto-dependency handling
result = execute("""
import numpy as np
import pandas as pd
df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
print(df.describe())
""")

# Result is a dict:
# {
#   "status": "success" | "partial" | "failed",
#   "stdout": "...",
#   "stderr": "",
#   "summary": "检测到 2 个外部依赖。代码执行成功。",
#   "dependency_analysis": {"third_party": ["numpy", "pandas"], ...},
#   "install_info": {"installed": ["pandas"], "skipped": ["numpy"], ...},
#   "suggestions": []  # fix tips if failed
# }

# Check dependencies only (no install, no execution)
deps = check("from transformers import pipeline; import torch")
print(deps["needs_install"])  # ["transformers", "torch"]
```

### Full Pipeline API

For more control, use the pipeline directly:

```python
from depot import DepotConfig, DepotPipeline

config = DepotConfig(
    data_dir="./depot-data",      # cache & venv storage
    execution_timeout=30,         # execution timeout (seconds)
    preferred_pm="uv",            # package manager: pip / uv / poetry
    pypi_mirror="https://pypi.tuna.tsinghua.edu.cn/simple",  # optional mirror
)
pipeline = DepotPipeline(config)

# Execute code
report = pipeline.run(code)
print(report.summary)          # human-readable summary
print(report.status)           # RunStatus.SUCCESS / FAILED

# Export reports
json_str = pipeline.report_to_json(report)
md_str = pipeline.report_to_markdown(report)
```

## How to Integrate into the Code-Execute Loop

When Claude generates Python code that needs to be executed:

1. **Write the code** as you normally would (no special handling needed)
2. **Execute via Depot** instead of raw `subprocess`:

```python
# INSTEAD OF:
subprocess.run(["python3", "-c", code], ...)  # may get ImportError

# USE:
from depot.sdk import execute
result = execute(code)
```

3. **Check the result**:

```python
if result["status"] == "success":
    return result["stdout"]
elif result["suggestions"]:
    # Depot already gives specific fix suggestions
    print(f"Fix needed: {result['suggestions']}")
```

## Configuration

Key configuration options (all optional):

| Option | Default | Description |
|--------|---------|-------------|
| `data_dir` | `./depot-data` | Cache and lock file directory |
| `execution_timeout` | 30 | Execution timeout in seconds |
| `preferred_pm` | `""` (auto) | Package manager: pip / uv / poetry |
| `pypi_mirror` | None | PyPI mirror URL |
| `allow_network` | True | Whether network access is allowed |
| `cache_enabled` | True | Enable caching of installed packages |

## When NOT to Use

Skip Depot when:
- The code only uses standard library (`os`, `sys`, `json`, `pathlib`, etc.)
- You've already verified all dependencies are installed
- You're running in a tightly controlled environment where network installs are impossible
