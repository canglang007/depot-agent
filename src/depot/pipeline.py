"""
Depot 核心管道编排器。

将所有组件串联为统一的执行管道：
AST提取 → 依赖解析 → 按需安装 → 隔离执行 → 结构化反馈
"""

import time
from pathlib import Path
from typing import Optional

from .cache import CacheManager
from .config import DepotConfig
from .executor import ExecutionResult, IsolatedExecutor
from .extractor import DependencyExtractor, ExtractionResult
from .feedback import ExecutionReport, FeedbackGenerator
from .installer import InstallReport, Installer
from .resolver import DependencyResolver, ResolveResult


class DepotPipeline:
    """Depot 系统的主管道。

    用法:
        config = DepotConfig()
        pipeline = DepotPipeline(config)

        report = pipeline.run('''
            import numpy as np
            print(np.array([1, 2, 3]).sum())
        ''')

        print(report.summary)
        print(report.status)
    """

    def __init__(self, config: DepotConfig | None = None):
        self.config = config or DepotConfig()
        self.config.ensure_dirs()

        # 组件
        self.extractor = DependencyExtractor()
        self.resolver = DependencyResolver(self.config)
        self.installer = Installer(self.config)
        self.executor = IsolatedExecutor(self.config)
        self.feedback = FeedbackGenerator()
        self.cache = CacheManager(self.config)

    def run(
        self,
        code: str,
        *,
        known_modules: Optional[set[str]] = None,
        auto_install: bool = True,
    ) -> ExecutionReport:
        """运行完整的 Depot 管道。

        Args:
            code: Agent 生成的 Python 代码
            known_modules: 已知的本地模块名（不会被归为第三方依赖）
            auto_install: 是否自动安装缺失的包

        Returns:
            ExecutionReport: 完整的结构化报告
        """
        if known_modules:
            self.extractor._known_local.update(known_modules)

        timeline = []
        t0 = time.time()

        # ── Step 1: AST 依赖提取 ─────────────────────────
        t1 = time.time()
        extraction = self.extractor.extract(code)
        timeline.append({
            "step": "extract",
            "duration_ms": int((time.time() - t1) * 1000),
            "deps_found": len(extraction.installable),
        })

        # ── Step 2: 依赖解析 ─────────────────────────────
        t2 = time.time()
        resolve = self.resolver.resolve(extraction)
        timeline.append({
            "step": "resolve",
            "duration_ms": int((time.time() - t2) * 1000),
            "missing": len(resolve.missing_packages),
            "cached": len(resolve.cached_packages),
            "available": len(resolve.available_packages),
        })

        # ── Step 3: 按需安装 ─────────────────────────────
        install = None
        if auto_install and resolve.needs_install:
            t3 = time.time()
            install = self.installer.install(resolve)
            timeline.append({
                "step": "install",
                "duration_ms": int((time.time() - t3) * 1000),
                "installed": install.installed,
                "failed": install.failed,
            })

            # 更新缓存：记录新安装的包
            if install.installed:
                self._update_cache_after_install(install.installed)
        elif not resolve.needs_install:
            timeline.append({
                "step": "install",
                "duration_ms": 0,
                "note": "所有依赖已满足，跳过安装",
            })

        # ── Step 4: 隔离执行 ─────────────────────────────
        t4 = time.time()
        execution = self.executor.execute(code)
        timeline.append({
            "step": "execute",
            "duration_ms": execution.execution_time_ms,
            "exit_code": execution.exit_code,
            "success": execution.success,
        })

        # ── Step 5: 生成报告 ─────────────────────────────
        t5 = time.time()
        report = self.feedback.generate(
            extraction=extraction,
            resolve=resolve,
            install=install,
            execution=execution,
            timeline=timeline,
        )

        report.timeline.append({
            "total_duration_ms": int((time.time() - t0) * 1000),
        })

        return report

    def run_safe(
        self,
        code: str,
        **kwargs,
    ) -> ExecutionReport:
        """安全的管道运行（捕获所有异常，返回错误报告而非抛出）。"""
        try:
            return self.run(code, **kwargs)
        except Exception as e:
            import traceback
            return ExecutionReport(
                status="failed",
                summary=f"管道内部错误: {e}",
                execution_summary={
                    "exit_code": -1,
                    "success": False,
                    "stderr_preview": traceback.format_exc()[:1000],
                },
                suggestions=[f"Depot 内部错误: {e}"],
            )

    def check(self, code: str) -> ExtractionResult:
        """只做依赖检查和预演，不执行也不安装。

        用于 Agent 在生成代码前快速检查依赖情况。

        Args:
            code: Python 代码

        Returns:
            ExtractionResult: 依赖信息
        """
        return self.extractor.extract(code)

    def _update_cache_after_install(self, installed: list[str]) -> None:
        """安装完成后更新缓存记录。"""
        import importlib.metadata as meta

        updates = {}
        for pkg_name in installed:
            try:
                version = meta.version(pkg_name)
                updates[pkg_name] = version
            except meta.PackageNotFoundError:
                updates[pkg_name] = "unknown"

        self.cache.add_packages(updates)

    # ── 报告导出 ────────────────────────────────────────

    def report_to_json(self, report: ExecutionReport) -> str:
        """将报告导出为 JSON 字符串。"""
        import json
        from dataclasses import asdict
        return json.dumps(asdict(report), indent=2, ensure_ascii=False, default=str)

    def report_to_markdown(self, report: ExecutionReport) -> str:
        """将报告导出为 Markdown。"""
        lines = [
            "# Depot 执行报告",
            "",
            f"**状态**: {report.status.value.upper()}",
            f"**时间**: {report.timestamp}",
            f"**摘要**: {report.summary}",
            "",
            "## 依赖分析",
        ]

        ds = report.dependency_summary
        if ds:
            lines.append(f"- 总导入: {ds.get('total_imports', 0)}")
            third = ds.get("third_party", [])
            if third:
                lines.append(f"- 第三方依赖: {', '.join(third)}")
            else:
                lines.append("- 无第三方依赖")
            stdlib = ds.get("standard_library", [])
            if stdlib:
                lines.append(f"- 标准库: {', '.join(stdlib)}")

        lines.extend(["", "## 安装"])
        inst = report.install_summary
        if inst:
            if inst["installed"]:
                lines.append(f"- 新安装: {', '.join(inst['installed'])}")
            if inst["skipped"]:
                lines.append(f"- 跳过(缓存): {', '.join(inst['skipped'])}")
            if inst["failed"]:
                lines.append(f"- 失败: {inst['failed']}")
            lines.append(f"- 耗时: {inst['total_time_ms']}ms")
        else:
            lines.append("- 无需安装")

        lines.extend(["", "## 执行结果"])
        exc = report.execution_summary
        if exc:
            lines.append(f"- 退出码: {exc.get('exit_code', 'N/A')}")
            lines.append(f"- 执行耗时: {exc.get('execution_time_ms', 'N/A')}ms")
            if exc.get("timed_out"):
                lines.append("- ⚠️ 执行超时")
            if exc.get("stdout_preview"):
                lines.extend(["", "```", exc["stdout_preview"][:1000], "```"])
            if exc.get("stderr_preview"):
                lines.extend(["", "**stderr**:", "", "```", exc["stderr_preview"][:1000], "```"])

        if report.suggestions:
            lines.extend(["", "## 修复建议"])
            for s in report.suggestions:
                lines.append(f"- {s}")

        return "\n".join(lines)
