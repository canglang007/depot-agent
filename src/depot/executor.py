"""
隔离执行器。

在轻量隔离环境中执行 Agent 生成的 Python 代码。
使用 venv + subprocess 方案，启动快、资源开销小。
"""

import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import DepotConfig


@dataclass
class ExecutionResult:
    """代码执行的完整结果。"""

    # 基本结果
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""

    # 执行元信息
    execution_time_ms: int = 0
    timed_out: bool = False
    memory_exceeded: bool = False

    # 错误信息
    error_type: str = ""  # "import_error", "syntax_error", "runtime_error", ""
    error_summary: str = ""

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    @property
    def has_import_error(self) -> bool:
        return "ImportError" in self.stderr or "ModuleNotFoundError" in self.stderr

    @property
    def has_syntax_error(self) -> bool:
        return "SyntaxError" in self.stderr


class IsolatedExecutor:
    """在轻量隔离环境中执行代码。"""

    def __init__(self, config: DepotConfig):
        self.config = config
        self._work_dir: Path = self.config.data_dir / "executions"
        self._work_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, code: str, env: dict[str, str] | None = None) -> ExecutionResult:
        """在隔离的 subprocess 中执行 Python 代码。

        Args:
            code: 要执行的 Python 代码
            env: 额外的环境变量

        Returns:
            ExecutionResult: 执行结果
        """
        result = ExecutionResult()
        start = time.time()

        # 写入临时文件（避免 shell 注入和引号问题）
        tmp_file = self._write_temp(code)

        # 构建命令
        cmd = [sys.executable, str(tmp_file)]

        # 准备环境变量
        exec_env = os.environ.copy()
        if not self.config.allow_network:
            exec_env["DEPOT_OFFLINE"] = "1"
        exec_env["PYTHONUNBUFFERED"] = "1"
        if env:
            exec_env.update(env)

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.execution_timeout,
                env=exec_env,
                cwd=str(self._work_dir),
            )

            result.exit_code = proc.returncode
            result.stdout = proc.stdout[:50000]  # 截断长输出
            result.stderr = proc.stderr[:50000]
            result.execution_time_ms = int((time.time() - start) * 1000)

        except subprocess.TimeoutExpired:
            result.timed_out = True
            result.exit_code = -1
            result.stderr = f"代码执行超时 (>{self.config.execution_timeout}s)"
            result.execution_time_ms = self.config.execution_timeout * 1000

        finally:
            # 清理临时文件
            try:
                tmp_file.unlink(missing_ok=True)
            except OSError:
                pass

        # 分析错误类型
        self._classify_error(result)
        return result

    def _write_temp(self, code: str) -> Path:
        """将代码写入临时文件。"""
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            prefix="depot_",
            dir=self._work_dir,
            delete=False,
        )
        tmp.write(code)
        tmp.flush()
        return Path(tmp.name)

    def _classify_error(self, result: ExecutionResult) -> None:
        """分析 stderr 以分类错误类型。"""
        stderr = result.stderr
        if "ModuleNotFoundError" in stderr or "ImportError" in stderr:
            result.error_type = "import_error"
            # 提取包名
            for line in stderr.split("\n"):
                if "No module named" in line:
                    result.error_summary = line.strip()
                    break
        elif "SyntaxError" in stderr:
            result.error_type = "syntax_error"
            for line in stderr.split("\n"):
                if "SyntaxError" in line:
                    result.error_summary = line.strip()
                    break
        elif result.exit_code != 0:
            result.error_type = "runtime_error"
            # 取最后一行有意义的内容
            lines = [l for l in stderr.split("\n") if l.strip()]
            if lines:
                result.error_summary = lines[-1].strip()


# ── 便捷函数 ──────────────────────────────────────────────

def execute_code(code: str, config: DepotConfig) -> ExecutionResult:
    """便捷函数：隔离执行一段代码。"""
    executor = IsolatedExecutor(config)
    return executor.execute(code)
