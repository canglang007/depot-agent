"""
Benchmark 任务定义。

15 个测试任务，分 L1/L2/L3 三个难度。
每个任务包含：
- id: 唯一标识
- prompt: 模拟 Agent 收到的用户请求
- expected_code: 期望生成的代码（用于验证我们不去 hook Agent，直接注入）
- validator: 验证函数，检查 stdout 是否满足要求
- expected_deps: 预期依赖列表（用于验证提取器准确性）
- difficulty: 难度等级
"""

import json
import re
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class BenchmarkTask:
    """单个 Benchmark 任务。"""

    id: str
    prompt: str
    code: str
    difficulty: int  # 1, 2, 3
    expected_deps: list[str] = field(default_factory=list)
    category: str = "general"  # data, web, ml, text, etc.

    def validate(self, stdout: str, stderr: str = "") -> tuple[bool, str]:
        """验证执行输出是否符合预期。

        Returns:
            (passed, reason) 元组
        """
        if stderr and ("Error" in stderr or "Traceback" in stderr):
            return False, f"执行有错误: {stderr[:200]}"
        return True, ""


class TaskRegistry:
    """任务注册中心。"""

    def __init__(self):
        self._tasks: dict[str, BenchmarkTask] = {}

    def register(self, task: BenchmarkTask) -> None:
        self._tasks[task.id] = task

    def get(self, task_id: str) -> BenchmarkTask:
        return self._tasks[task_id]

    def list_by_difficulty(self, difficulty: int) -> list[BenchmarkTask]:
        return [t for t in self._tasks.values() if t.difficulty == difficulty]

    def all(self) -> list[BenchmarkTask]:
        return list(self._tasks.values())

    @property
    def count(self) -> int:
        return len(self._tasks)
