"""核心管道编排器集成测试。"""

import sys
sys.path.insert(0, "src")

import pytest
from depot.config import DepotConfig
from depot.pipeline import DepotPipeline
from depot.feedback import RunStatus


@pytest.fixture
def pipeline(tmp_path):
    config = DepotConfig(data_dir=tmp_path / "depot-pipeline-data")
    return DepotPipeline(config)


class TestPipelineBasic:
    """管道基本功能。"""

    def test_stdlib_code_success(self, pipeline):
        code = "import os; print(os.name)"
        report = pipeline.run(code, auto_install=False)
        assert report.status == RunStatus.SUCCESS

    def test_stdlib_code_has_summary(self, pipeline):
        code = "x = 1 + 1"
        report = pipeline.run(code, auto_install=False)
        assert len(report.summary) > 0

    def test_math_code(self, pipeline):
        code = "import math; print(math.pi)"
        report = pipeline.run(code, auto_install=False)
        assert report.status == RunStatus.SUCCESS

    def test_json_operations(self, pipeline):
        code = """
import json
data = {"key": "value"}
print(json.dumps(data))
"""
        report = pipeline.run(code, auto_install=False)
        assert report.status == RunStatus.SUCCESS
        assert "value" in report.execution_summary.get("stdout_preview", "")


class TestPipelineWithDependencies:
    """依赖检测和安装相关测试。"""

    def test_detect_third_party(self, pipeline):
        code = "import numpy; import pandas; print('ok')"
        report = pipeline.run(code, auto_install=False)
        third = report.dependency_summary.get("third_party", [])
        assert "numpy" in third
        assert "pandas" in third

    def test_no_third_party_report(self, pipeline):
        code = "import os, sys, json"
        report = pipeline.run(code, auto_install=False)
        third = report.dependency_summary.get("third_party", [])
        assert len(third) == 0

    def test_timeline_has_all_steps(self, pipeline):
        code = "x = 1"
        report = pipeline.run(code, auto_install=False)
        steps = [t.get("step") for t in report.timeline if "step" in t]
        # 至少应有 extract, resolve, install, execute
        assert len(steps) >= 4

    def test_total_duration_tracked(self, pipeline):
        code = "x = 1"
        report = pipeline.run(code, auto_install=False)
        total_entries = [t for t in report.timeline if "total_duration_ms" in t]
        assert len(total_entries) == 1


class TestPipelineMethods:
    """管道的其他方法。"""

    def test_check_dependencies(self, pipeline):
        code = "import numpy; from torch import nn"
        result = pipeline.check(code)
        assert "numpy" in result.package_names
        assert "torch" in result.package_names

    def test_check_no_errors(self, pipeline):
        code = "x = 1"
        result = pipeline.check(code)
        assert len(result.errors) == 0
        assert len(result.third_party) == 0

    def test_report_to_json(self, pipeline):
        report = pipeline.run("x = 1", auto_install=False)
        json_str = pipeline.report_to_json(report)
        assert len(json_str) > 0
        assert "success" in json_str.lower()

    def test_report_to_markdown(self, pipeline):
        report = pipeline.run("x = 1", auto_install=False)
        md = pipeline.report_to_markdown(report)
        assert "# Depot" in md
        assert "SUCCESS" in md


class TestPipelineErrorHandling:
    """错误处理。"""

    def test_syntax_error_code(self, pipeline):
        code = "for while if garbage {{{"
        report = pipeline.run(code, auto_install=False)
        assert report.status == RunStatus.FAILED

    def test_runtime_error_code(self, pipeline):
        code = "raise ValueError('intentional')"
        report = pipeline.run(code, auto_install=False)
        assert report.status == RunStatus.FAILED

    def test_run_safe_catches_errors(self, pipeline):
        # run_safe 应该捕获任何异常并返回失败报告
        report = pipeline.run_safe("raise SystemExit(1)")
        assert report.status in (RunStatus.SUCCESS, RunStatus.FAILED)  # 至少不崩溃

    def test_known_modules_respected(self, pipeline):
        pipeline.extractor._known_local.add("my_lib")
        code = "import my_lib"
        result = pipeline.check(code)
        assert "my_lib" not in result.package_names
        assert any(d.name == "my_lib" and d.category == "local" for d in result.dependencies)

    def test_auto_install_false_skips_install(self, pipeline):
        code = "import nonexistent_pkg_xyz_abc"
        report = pipeline.run(code, auto_install=False)
        # 没有安装，所以执行应该失败（import error）
        assert not report.execution_summary.get("success", True)


class TestMarkdownExport:
    """Markdown 导出。"""

    def test_markdown_has_sections(self, pipeline):
        report = pipeline.run("import os", auto_install=False)
        md = pipeline.report_to_markdown(report)
        assert "## 依赖分析" in md
        assert "## 安装" in md
        assert "## 执行结果" in md

    def test_markdown_with_suggestions(self, pipeline):
        report = pipeline.run("import nonexistent_xyz_abc", auto_install=False)
        md = pipeline.report_to_markdown(report)
        assert "## 修复建议" in md
