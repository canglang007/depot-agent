"""
B1 Baseline: 裸 Python 执行。

Agent 代码直接 subprocess.run 执行，无任何依赖管理。
这是最简捷但最脆弱的方案 —— 如果代码 import 了未安装的包，
Agent 需要自己识别错误并手动 pip install。
"""

import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .base import Baseline, BaselineResult


class BareExecutionBaseline(Baseline):
    """B1: 裸执行 —— 无依赖管理，直接 subprocess。"""

    def __init__(self, timeout: int = 30):
        super().__init__(
            name="B1-裸执行",
            timeout=timeout,
        )

    def run(self, code: str) -> BaselineResult:
        """直接在 subprocess 中执行 Python 代码。"""
        result = BaselineResult()
        t0 = time.time()

        result.timeline = []

        # 写入临时文件
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", prefix="bare_", delete=False
        )
        tmp.write(code)
        tmp.flush()
        tmp_path = Path(tmp.name)

        # 执行
        t_exec = time.time()
        try:
            proc = subprocess.run(
                [sys.executable, str(tmp_path)],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            result.exit_code = proc.returncode
            result.stdout = proc.stdout[:50000]
            result.stderr = proc.stderr[:50000]
            result.execution_time_ms = int((time.time() - t_exec) * 1000)
        except subprocess.TimeoutExpired:
            result.timed_out = True
            result.exit_code = -1
            result.stderr = f"执行超时 (>{self.timeout}s)"
            result.execution_time_ms = self.timeout * 1000
        finally:
            tmp_path.unlink(missing_ok=True)

        # 错误分类
        self._classify_error(result)

        # 状态判定
        result.total_time_ms = int((time.time() - t0) * 1000)
        result.status = "success" if result.exit_code == 0 and not result.timed_out else "failed"
        result.summary = (
            f"裸执行{'成功' if result.status == 'success' else '失败'}"
            f" (耗时 {result.execution_time_ms}ms)"
        )
        if result.error_summary:
            result.summary += f": {result.error_summary}"

        return result

    def _classify_error(self, result: BaselineResult) -> None:
        """分析 stderr 分类错误。"""
        if "ModuleNotFoundError" in result.stderr or "ImportError" in result.stderr:
            result.error_type = "import_error"
            for line in result.stderr.split("\n"):
                if "No module named" in line:
                    result.error_summary = line.strip()
                    pkg = line.split("No module named")[-1].strip().strip("'\"")
                    result.suggestions.append(f"需要安装包: pip install {pkg}")
                    break
        elif "SyntaxError" in result.stderr:
            result.error_type = "syntax_error"
        elif result.exit_code != 0:
            result.error_type = "runtime_error"
            lines = [l for l in result.stderr.split("\n") if l.strip()]
            if lines:
                result.error_summary = lines[-1].strip()
