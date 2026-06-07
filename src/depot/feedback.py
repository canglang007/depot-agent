"""
结构化反馈生成器。

将管道中各组件的输出汇总成 Agent 友好的结构化报告。
输出 JSON（供 Agent 程序化消费）和 Markdown（供人类阅读）。
"""

from dataclasses import dataclass, field
from enum import Enum

from .executor import ExecutionResult
from .extractor import ExtractionResult
from .installer import InstallReport
from .resolver import ResolveResult


class RunStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class ExecutionReport:
    """Depot 执行的结构化报告。"""

    status: RunStatus = RunStatus.SUCCESS
    timestamp: str = ""

    # 依赖分析概要
    dependency_summary: dict = field(default_factory=dict)

    # 安装概要
    install_summary: dict = field(default_factory=dict)

    # 执行概要
    execution_summary: dict = field(default_factory=dict)

    # 人类可读的摘要
    summary: str = ""

    # 修复建议
    suggestions: list[str] = field(default_factory=list)

    # 完整时间线
    timeline: list[dict] = field(default_factory=list)


class FeedbackGenerator:
    """汇总管道输出，生成结构化报告。"""

    def __init__(self):
        pass

    def generate(
        self,
        extraction: ExtractionResult | None = None,
        resolve: ResolveResult | None = None,
        install: InstallReport | None = None,
        execution: ExecutionResult | None = None,
        timeline: list[dict] | None = None,
    ) -> ExecutionReport:
        """生成完整的执行报告。

        Args:
            extraction: AST 提取结果
            resolve: 依赖解析结果
            install: 安装报告
            execution: 执行结果
            timeline: 时间线事件列表

        Returns:
            ExecutionReport: 完整的结构化报告
        """
        from datetime import datetime, timezone

        report = ExecutionReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            timeline=timeline or [],
        )

        # 1. 依赖摘要
        if extraction:
            report.dependency_summary = {
                "total_imports": len(extraction.dependencies),
                "standard_library": [d.name for d in extraction.standard_library],
                "third_party": [d.name for d in extraction.third_party],
                "local": [d.name for d in extraction.local_imports],
                "dynamic": [d.name for d in extraction.dynamic_imports],
                "conditional": [d.name for d in extraction.conditional_imports],
            }

        # 2. 安装摘要
        if install:
            report.install_summary = {
                "installed": install.installed,
                "skipped": install.skipped,
                "failed": install.failed,
                "total_time_ms": install.total_time_ms,
            }

        # 3. 执行摘要
        if execution:
            report.execution_summary = {
                "exit_code": execution.exit_code,
                "success": execution.success,
                "execution_time_ms": execution.execution_time_ms,
                "timed_out": execution.timed_out,
                "error_type": execution.error_type,
                "error_summary": execution.error_summary,
                "stdout_preview": execution.stdout[:500],
                "stderr_preview": execution.stderr[:500],
            }

        # 4. 判定状态
        report.status = self._determine_status(
            extraction, resolve, install, execution
        )

        # 5. 生成人类可读摘要
        report.summary = self._generate_summary(report)

        # 6. 生成修复建议
        report.suggestions = self._generate_suggestions(
            extraction, resolve, install, execution
        )

        return report

    def _determine_status(
        self,
        extraction: ExtractionResult | None,
        resolve: ResolveResult | None,
        install: InstallReport | None,
        execution: ExecutionResult | None,
    ) -> RunStatus:
        """判定整体运行状态。"""
        if execution is None:
            return RunStatus.FAILED

        if execution.success:
            # 即使执行成功，如果有安装失败的情况也算 partial
            if install and install.fail_count > 0:
                return RunStatus.PARTIAL
            return RunStatus.SUCCESS

        if install and install.fail_count > 0:
            return RunStatus.FAILED

        return RunStatus.FAILED

    def _generate_summary(self, report: ExecutionReport) -> str:
        """生成人类可读的单行摘要。"""
        parts = []

        dep_count = len(report.dependency_summary.get("third_party", []))
        if dep_count > 0:
            parts.append(f"检测到 {dep_count} 个外部依赖")

        installed = report.install_summary.get("installed", [])
        if installed:
            parts.append(f"安装了 {', '.join(installed)}")

        skipped = report.install_summary.get("skipped", [])
        if skipped:
            parts.append(f"跳过 {len(skipped)} 个已缓存包")

        exec_info = report.execution_summary
        if exec_info:
            if exec_info.get("success"):
                parts.append(
                    f"代码执行成功 (耗时 {exec_info.get('execution_time_ms', '?')}ms)"
                )
            elif exec_info.get("timed_out"):
                parts.append("代码执行超时")
            else:
                parts.append(
                    f"代码执行失败: {exec_info.get('error_summary', '未知错误')}"
                )

        failed = report.install_summary.get("failed", [])
        if failed:
            parts.append(f"{len(failed)} 个包安装失败")

        return "。".join(parts) if parts else "无操作"

    def _generate_suggestions(
        self,
        extraction: ExtractionResult | None,
        resolve: ResolveResult | None,
        install: InstallReport | None,
        execution: ExecutionResult | None,
    ) -> list[str]:
        """根据错误类型生成修复建议。"""
        suggestions = []

        if execution is None:
            return suggestions

        if execution.has_import_error:
            # 提取缺失的包名
            for line in execution.stderr.split("\n"):
                if "No module named" in line:
                    pkg = line.split("No module named")[-1].strip().strip("'\"")
                    suggestions.append(f"需要安装包: pip install {pkg}")
                    break

        if execution.has_syntax_error:
            suggestions.append("代码存在语法错误，请检查拼写和缩进")

        if execution.timed_out:
            suggestions.append(
                "代码执行超时，建议检查是否有死循环或阻塞操作"
            )

        if install and install.fail_count > 0:
            for fail in install.failed:
                suggestions.append(f"包 '{fail['name']}' 安装失败: {fail['error']}")

        return suggestions


# ── 便捷函数 ──────────────────────────────────────────────

def generate_report(
    extraction: ExtractionResult | None = None,
    resolve: ResolveResult | None = None,
    install: InstallReport | None = None,
    execution: ExecutionResult | None = None,
    timeline: list[dict] | None = None,
) -> ExecutionReport:
    """便捷函数：生成结构化执行报告。"""
    generator = FeedbackGenerator()
    return generator.generate(extraction, resolve, install, execution, timeline)
