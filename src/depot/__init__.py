"""
Depot — 面向代码生成Agent的按需依赖解析系统。

核心功能：
- AST 依赖提取：从 Agent 生成的代码中提取 import 语句并分类
- 依赖解析：查询环境已有包，识别缺失依赖
- 按需安装：增量安装缺失的包，自动缓存
- 隔离执行：在轻量隔离环境中执行代码
- 结构化反馈：生成 Agent 友好的执行报告

快速使用:
    # 命令行
    $ depot run script.py
    $ depot run -c "import numpy; print(numpy.__version__)"

    # SDK (Agent 集成)
    >>> from depot.sdk import execute, check
    >>> result = execute("import numpy; print(numpy.array([1,2,3]))")
    >>> print(result["status"])  # "success"

    # 完整管道
    >>> from depot import DepotPipeline, DepotConfig
    >>> pipeline = DepotPipeline(DepotConfig())
    >>> report = pipeline.run("import numpy; print('hello')")
    >>> print(report.summary)
"""

from .config import DepotConfig
from .pipeline import DepotPipeline
from .feedback import ExecutionReport

__version__ = "1.0.0"
__all__ = ["DepotConfig", "DepotPipeline", "ExecutionReport"]
