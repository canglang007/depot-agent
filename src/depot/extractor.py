"""
AST 依赖提取器。

使用 Python ast 模块从 Agent 生成的代码中提取外部依赖信息。
只做静态分析 —— 不导入任何模块，不执行任何代码。
"""

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── 标准库列表 ─────────────────────────────────────────────
# sys.stdlib_module_names 在 3.10+ 可用
_STDLIB: set[str] = set(sys.stdlib_module_names)


# ── 动态 import 的正则模式 ──────────────────────────────────
_IMPORTLIB_PATTERN = re.compile(
    r"importlib\s*\.\s*import_module\s*\(\s*['\"]([^'\"]+)['\"]"
)
_IMPORT_BUILTIN_PATTERN = re.compile(
    r"__import__\s*\(\s*['\"]([^'\"]+)['\"]"
)


@dataclass
class DependencyInfo:
    """单个依赖的详细信息。"""

    name: str
    category: str  # standard_library, third_party, local, dynamic, conditional
    import_type: str  # "import", "from", "dynamic", "conditional"
    alias: Optional[str] = None  # import numpy as np 中的 "np"
    line_no: int = 0
    original: str = ""  # 原始 import 语句

    def is_installable(self) -> bool:
        """是否需要安装（只有第三方依赖需要）。"""
        return self.category in ("third_party", "conditional")


@dataclass
class ExtractionResult:
    """AST 提取的完整结果。"""

    dependencies: list[DependencyInfo] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # 按类别分组的便捷访问
    @property
    def standard_library(self) -> list[DependencyInfo]:
        return [d for d in self.dependencies if d.category == "standard_library"]

    @property
    def third_party(self) -> list[DependencyInfo]:
        return [d for d in self.dependencies if d.category == "third_party"]

    @property
    def local_imports(self) -> list[DependencyInfo]:
        return [d for d in self.dependencies if d.category == "local"]

    @property
    def dynamic_imports(self) -> list[DependencyInfo]:
        return [d for d in self.dependencies if d.category == "dynamic"]

    @property
    def conditional_imports(self) -> list[DependencyInfo]:
        return [d for d in self.dependencies if d.category == "conditional"]

    @property
    def installable(self) -> list[DependencyInfo]:
        """所有需要安装的依赖。"""
        return [d for d in self.dependencies if d.is_installable()]

    @property
    def package_names(self) -> list[str]:
        """安装用的包名列表（去重）。"""
        return list({d.name for d in self.installable})


class DependencyExtractor:
    """从 Python 代码中提取依赖信息。"""

    def __init__(self, known_local_modules: Optional[set[str]] = None):
        """
        Args:
            known_local_modules: 已知的本地模块名集合（如项目内模块），
                                 这些不会被归类为第三方依赖。
        """
        self._known_local = known_local_modules or set()

    def extract(self, code: str) -> ExtractionResult:
        """分析 Python 代码字符串，提取所有依赖信息。

        Args:
            code: Agent 生成的 Python 代码

        Returns:
            ExtractionResult: 分类后的依赖列表
        """
        result = ExtractionResult()

        # 1. AST 解析
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            result.errors.append(f"AST 解析失败: {e}")
            # 对语法错误的代码，退化为正则匹配
            self._fallback_regex(code, result)
            return result

        # 2. 第一遍：遍历 AST 提取所有 import 并分类
        for node in ast.walk(tree):
            self._handle_node(node, result)

        # 3. 第二遍：修正 try-except 中的条件导入
        # （必须在第一遍之后，因为 ast.walk 可能先访问 Try 再访问其内部 Import，
        #   此时 Import 还没被添加到依赖列表，导致无法重新分类）
        self._fix_conditional_imports(tree, result)

        # 4. 正则补扫动态 import（AST 无法捕获字符串内的 import）
        self._scan_dynamic(code, result)

        return result

    # ── 节点处理 ───────────────────────────────────────────

    def _handle_node(self, node: ast.AST, result: ExtractionResult) -> None:
        """分发不同类型的 import 节点。"""
        if isinstance(node, ast.Import):
            self._handle_import(node, result)
        elif isinstance(node, ast.ImportFrom):
            self._handle_import_from(node, result)

    # ── 条件导入修正（第二遍） ─────────────────────────────

    def _fix_conditional_imports(
        self, tree: ast.Module, result: ExtractionResult
    ) -> None:
        """修正 try-except 中 import 的分类（从 third_party 改为 conditional）。"""
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.Try):
                    continue
                for stmt in ast.walk(child):
                    if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                        self._mark_conditional_for_try(stmt, result)

    def _handle_import(self, node: ast.Import, result: ExtractionResult) -> None:
        """处理 `import X` 和 `import X as Y` 语句。"""
        for alias in node.names:
            deps = self._classify(
                name=alias.name,
                import_type="import",
                alias=alias.asname,
                line_no=node.lineno,
                original=ast.unparse(node),
            )
            result.dependencies.extend(deps)

    def _handle_import_from(self, node: ast.ImportFrom, result: ExtractionResult) -> None:
        """处理 `from X import Y` 和 `from .X import Y` 语句。"""
        module = node.module or ""
        level = node.level  # 相对导入的层级

        if level > 0 or module.startswith("."):
            # 相对导入 → 本地模块
            for alias in node.names:
                result.dependencies.append(
                    DependencyInfo(
                        name=alias.name,
                        category="local",
                        import_type="from",
                        alias=alias.asname,
                        line_no=node.lineno,
                        original=ast.unparse(node),
                    )
                )
            return

        # 绝对导入 from X import Y —— 分类 module（顶层包），不是 alias.name
        deps = self._classify(
            name=module,
            import_type="from",
            alias=None,
            line_no=node.lineno,
            original=ast.unparse(node),
        )
        result.dependencies.extend(deps)

    # ── 分类逻辑 ────────────────────────────────────────────

    def _classify(
        self,
        name: str,
        import_type: str,
        alias: Optional[str],
        line_no: int,
        original: str,
    ) -> list[DependencyInfo]:
        """将 import 名称分类到依赖类别中。

        返回列表是因为一个 import 可能涉及多个顶层包
        （虽然罕见，但 import os, sys 这种是多个 alias）。
        """
        top_level = name.split(".")[0]

        category = self._determine_category(top_level, name)

        return [
            DependencyInfo(
                name=top_level,
                category=category,
                import_type=import_type,
                alias=alias,
                line_no=line_no,
                original=original,
            )
        ]

    def _determine_category(self, top_level: str, full_name: str) -> str:
        """确定依赖类别。"""
        # 1. 标准库
        if top_level in _STDLIB:
            return "standard_library"

        # 2. 已知本地模块
        if top_level in self._known_local:
            return "local"

        # 3. 本地路径（包含 . 的模块名）
        if "." in full_name and full_name.startswith("."):
            return "local"

        # 4. 默认归类为第三方依赖
        return "third_party"

    def _mark_conditional_for_try(
        self, node: ast.Import | ast.ImportFrom, result: ExtractionResult
    ) -> None:
        """将 try 块中特定 import 语句对应的依赖标记为条件导入。"""
        # 提取这个 import 节点涉及的所有顶层包名
        affected = self._get_import_top_levels(node)
        for dep in result.dependencies:
            if dep.name in affected and dep.category == "third_party":
                dep.category = "conditional"

    def _get_import_top_levels(
        self, node: ast.Import | ast.ImportFrom
    ) -> set[str]:
        """获取 import 节点涉及的顶层包名。"""
        names = set()
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
        return names

    # ── 动态导入扫描 ────────────────────────────────────────

    def _scan_dynamic(self, code: str, result: ExtractionResult) -> None:
        """正则匹配动态 import 模式。"""
        # importlib.import_module("xxx")
        for m in _IMPORTLIB_PATTERN.finditer(code):
            name = m.group(1)
            if not any(d.name == name for d in result.dependencies):
                result.dependencies.append(
                    DependencyInfo(
                        name=name,
                        category="dynamic",
                        import_type="dynamic",
                        line_no=0,
                        original=m.group(0),
                    )
                )

        # __import__("xxx")
        for m in _IMPORT_BUILTIN_PATTERN.finditer(code):
            name = m.group(1)
            if not any(d.name == name for d in result.dependencies):
                result.dependencies.append(
                    DependencyInfo(
                        name=name,
                        category="dynamic",
                        import_type="dynamic",
                        line_no=0,
                        original=m.group(0),
                    )
                )

    # ── 容错回退 ────────────────────────────────────────────

    def _fallback_regex(self, code: str, result: ExtractionResult) -> None:
        """当 AST 解析失败时，用正则做尽力提取。"""
        import_pattern = re.compile(
            r"^\s*(?:import\s+([\w\s,]+)|from\s+(\w+)\s+import\s+([\w\s,]+))",
            re.MULTILINE,
        )
        for m in import_pattern.finditer(code):
            if m.group(1):  # import X, Y
                for name in m.group(1).split(","):
                    name = name.strip().split()[0]  # 去除 as 别名
                    if name:
                        category = self._determine_category(name.split(".")[0], name)
                        result.dependencies.append(
                            DependencyInfo(
                                name=name.split(".")[0],
                                category=category,
                                import_type="import",
                                alias=None,
                                line_no=0,
                                original=m.group(0).strip(),
                            )
                        )
            elif m.group(2):  # from X import Y
                module = m.group(2)
                category = self._determine_category(module.split(".")[0], module)
                result.dependencies.append(
                    DependencyInfo(
                        name=module.split(".")[0],
                        category=category,
                        import_type="from",
                        alias=None,
                        line_no=0,
                        original=m.group(0).strip(),
                    )
                )


# ── 便捷函数 ──────────────────────────────────────────────

def extract_dependencies(
    code: str,
    known_local_modules: Optional[set[str]] = None,
) -> ExtractionResult:
    """快速提取代码中的依赖信息。

    Args:
        code: Python 代码字符串
        known_local_modules: 已知本地模块名集合

    Returns:
        ExtractionResult: 分类后的依赖信息
    """
    extractor = DependencyExtractor(known_local_modules)
    return extractor.extract(code)
