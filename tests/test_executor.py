"""隔离执行器单元测试。"""

import sys
sys.path.insert(0, "src")

import pytest
from depot.config import DepotConfig
from depot.executor import IsolatedExecutor, ExecutionResult


@pytest.fixture
def config():
    return DepotConfig(data_dir="./test-depot-executor-data")


@pytest.fixture
def executor(config):
    return IsolatedExecutor(config)


class TestBasicExecution:
    """基本执行功能。"""

    def test_simple_print(self, executor):
        result = executor.execute('print("hello")')
        assert result.success
        assert "hello" in result.stdout
        assert result.exit_code == 0

    def test_return_zero_on_success(self, executor):
        result = executor.execute("x = 1 + 1")
        assert result.exit_code == 0

    def test_return_one_on_error(self, executor):
        result = executor.execute('raise ValueError("test error")')
        assert result.exit_code == 1
        assert not result.success

    def test_multiline_code(self, executor):
        code = """
import json
data = {"a": 1, "b": 2}
print(json.dumps(data))
"""
        result = executor.execute(code)
        assert result.success
        assert "1" in result.stdout

    def test_computation_result(self, executor):
        code = """
import math
x = math.factorial(5)
print(f"factorial(5)={x}")
"""
        result = executor.execute(code)
        assert result.success
        assert "120" in result.stdout


class TestTimeout:
    """超时处理。"""

    def test_timeout(self):
        config = DepotConfig(data_dir="./test-depot-to", execution_timeout=1)
        executor = IsolatedExecutor(config)
        result = executor.execute("import time; time.sleep(10)")
        assert result.timed_out
        assert not result.success

    def test_no_timeout_fast_code(self, executor):
        result = executor.execute("x = 42")
        assert not result.timed_out
        assert result.success


class TestErrorClassification:
    """错误分类。"""

    def test_import_error(self, executor):
        result = executor.execute("import nonexistent_package_xyz_123")
        assert result.error_type == "import_error"
        assert result.has_import_error
        assert "No module named" in result.stderr

    def test_syntax_error(self, executor):
        result = executor.execute("for while if :::: garbage")
        assert result.error_type == "syntax_error"
        assert result.has_syntax_error

    def test_runtime_error(self, executor):
        result = executor.execute("1 / 0")
        assert result.error_type == "runtime_error"
        assert not result.success

    def test_no_error_on_success(self, executor):
        result = executor.execute("x = 1")
        assert result.error_type == ""

    def test_stderr_captured(self, executor):
        import sys
        result = executor.execute("import sys; print('to stderr', file=sys.stderr)")
        assert "to stderr" in result.stderr


class TestExecutionResult:
    """ExecutionResult 数据类测试。"""

    def test_success_property(self):
        r = ExecutionResult(exit_code=0)
        assert r.success

    def test_not_success_on_nonzero(self):
        r = ExecutionResult(exit_code=1)
        assert not r.success

    def test_not_success_on_timeout(self):
        r = ExecutionResult(exit_code=0, timed_out=True)
        assert not r.success

    def test_execution_time_tracked(self, executor):
        result = executor.execute("x = 1")
        assert result.execution_time_ms > 0


import shutil
def teardown_module():
    shutil.rmtree("./test-depot-executor-data", ignore_errors=True)
    shutil.rmtree("./test-depot-to", ignore_errors=True)
