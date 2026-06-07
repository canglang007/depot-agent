"""
Baseline 基类。
"""

import time
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


@dataclass
class BaselineResult:
    """Baseline 执行结果（与 Depot ExecutionReport 对齐）。"""

    status: str = ""          # "success", "partial", "failed"
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    execution_time_ms: int = 0
    install_time_ms: int = 0
    total_time_ms: int = 0
    timed_out: bool = False
    error_type: str = ""
    error_summary: str = ""
    dependency_analysis: dict = field(default_factory=dict)
    summary: str = ""
    suggestions: list[str] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)


class Baseline(ABC):
    """所有 Baseline 的基类。

    子类必须实现 run() 方法，返回 BaselineResult。
    """

    def __init__(self, name: str, timeout: int = 30):
        self.name = name
        self.timeout = timeout

    @abstractmethod
    def run(self, code: str) -> BaselineResult:
        """执行代码并返回结果。"""
        ...

    def setup(self) -> None:
        """一次性初始化（B2 用于预装包）。"""
        pass

    def teardown(self) -> None:
        """清理资源。"""
        pass
