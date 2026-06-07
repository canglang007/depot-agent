"""结构化反馈生成器单元测试。"""

import sys
sys.path.insert(0, "src")

import pytest
from depot.feedback import (
    FeedbackGenerator,
    ExecutionReport,
    RunStatus,
    generate_report,
)
from depot.extractor import ExtractionResult, DependencyInfo
from depot.resolver import ResolveResult, InstallItem
from depot.installer import InstallReport
from depot.executor import ExecutionResult


@pytest.fixture
def generator():
    return FeedbackGenerator()


class TestReportGeneration:
    """报告生成。"""

    def test_generate_basic(self, generator):
        """基本的成功报告生成。"""
        extraction = ExtractionResult(dependencies=[
            DependencyInfo("os", "standard_library", "import"),
        ])
        execution = ExecutionResult(exit_code=0, stdout="hello")
        report = generator.generate(extraction=extraction, execution=execution)
        assert report.status == RunStatus.SUCCESS
        assert len(report.summary) > 0

    def test_generate_with_deps(self, generator):
        extraction = ExtractionResult(dependencies=[
            DependencyInfo("numpy", "third_party", "import"),
            DependencyInfo("pandas", "third_party", "import"),
        ])
        execution = ExecutionResult(exit_code=0, stdout="ok")
        report = generator.generate(extraction=extraction, execution=execution)
        assert len(report.dependency_summary["third_party"]) == 2

    def test_generate_with_install(self, generator):
        install = InstallReport(
            installed=["numpy"],
            skipped=["pandas"],
            total_time_ms=1500,
        )
        execution = ExecutionResult(exit_code=0, stdout="ok")
        report = generator.generate(install=install, execution=execution)
        assert len(report.install_summary["installed"]) == 1
        assert len(report.install_summary["skipped"]) == 1

    def test_generate_failed_execution(self, generator):
        execution = ExecutionResult(
            exit_code=1,
            stderr="ImportError: No module named 'requests'",
        )
        report = generator.generate(execution=execution)
        assert report.status == RunStatus.FAILED

    def test_generate_partial(self, generator):
        """有安装失败但执行成功。"""
        install = InstallReport(failed=[{"name": "numpy", "error": "timeout"}])
        execution = ExecutionResult(exit_code=0, stdout="ok")
        report = generator.generate(install=install, execution=execution)
        assert report.status == RunStatus.PARTIAL


class TestSuggestions:
    """修复建议生成。"""

    def test_import_error_suggestion(self, generator):
        execution = ExecutionResult(
            exit_code=1,
            stderr="ModuleNotFoundError: No module named 'torch'",
        )
        report = generator.generate(execution=execution)
        assert any("torch" in s for s in report.suggestions)

    def test_syntax_error_suggestion(self, generator):
        execution = ExecutionResult(
            exit_code=1,
            stderr="SyntaxError: invalid syntax",
        )
        report = generator.generate(execution=execution)
        assert any("语法错误" in s for s in report.suggestions)

    def test_timeout_suggestion(self, generator):
        execution = ExecutionResult(timed_out=True, exit_code=-1)
        report = generator.generate(execution=execution)
        assert any("超时" in s for s in report.suggestions)

    def test_install_failure_suggestion(self, generator):
        install = InstallReport(failed=[{"name": "pkg", "error": "connection timeout"}])
        execution = ExecutionResult(exit_code=1, stderr="ImportError")
        report = generator.generate(install=install, execution=execution)
        assert any("pkg" in s for s in report.suggestions)

    def test_no_suggestions_on_success(self, generator):
        execution = ExecutionResult(exit_code=0, stdout="ok")
        report = generator.generate(execution=execution)
        assert report.suggestions == []


class TestSummaryGeneration:
    """摘要文本生成。"""

    def test_summary_non_empty(self, generator):
        extraction = ExtractionResult(dependencies=[
            DependencyInfo("numpy", "third_party", "import"),
        ])
        execution = ExecutionResult(exit_code=0, stdout="ok")
        report = generator.generate(extraction=extraction, execution=execution)
        assert len(report.summary) > 0
        assert "numpy" in report.summary or "1" in report.summary


class TestRunStatusEnum:
    """状态枚举。"""

    def test_status_values(self):
        assert RunStatus.SUCCESS.value == "success"
        assert RunStatus.PARTIAL.value == "partial"
        assert RunStatus.FAILED.value == "failed"


class TestTimeline:
    """时间线记录。"""

    def test_timeline_preserved(self, generator):
        timeline = [
            {"step": "extract", "duration_ms": 1},
            {"step": "execute", "duration_ms": 10},
        ]
        execution = ExecutionResult(exit_code=0, stdout="ok")
        report = generator.generate(execution=execution, timeline=timeline)
        assert len(report.timeline) == 2


class TestConvenienceFunction:
    def test_generate_report_convenience(self):
        execution = ExecutionResult(exit_code=0, stdout="ok")
        report = generate_report(execution=execution)
        assert report.status == RunStatus.SUCCESS
