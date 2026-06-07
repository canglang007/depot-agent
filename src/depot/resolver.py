"""
依赖解析器。

查询目标环境状态，与提取的依赖列表对比，生成按需安装计划。
"""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .config import DepotConfig
from .extractor import ExtractionResult


@dataclass
class InstallItem:
    """单个安装项。"""

    name: str
    reason: str = ""  # 为什么需要安装这个包
    version_spec: Optional[str] = None  # 版本约束，如 ">=2.1.0"
    is_cached: bool = False  # 是否已缓存
    priority: int = 0  # 安装优先级（数字越小越先装）


@dataclass
class ResolveResult:
    """依赖解析的完整结果。"""

    # 环境中已有的包
    available_packages: set[str] = field(default_factory=set)
    # 缺失需要安装的包
    missing_packages: list[InstallItem] = field(default_factory=list)
    # 已缓存无需安装的包
    cached_packages: list[InstallItem] = field(default_factory=list)
    # 冲突的包（版本不兼容等）
    conflicts: list[str] = field(default_factory=list)
    # 解析过程中的警告
    warnings: list[str] = field(default_factory=list)
    # 安装计划（排序后的安装列表）
    install_plan: list[InstallItem] = field(default_factory=list)

    @property
    def needs_install(self) -> bool:
        """是否需要安装任何包。"""
        return len(self.missing_packages) > 0

    @property
    def all_clear(self) -> bool:
        """是否所有依赖都满足，可以直接执行。"""
        return not self.needs_install and len(self.conflicts) == 0


class DependencyResolver:
    """查询环境，生成安装计划。"""

    def __init__(self, config: DepotConfig):
        self.config = config
        self._installed_cache: Optional[set[str]] = None

    def resolve(self, extraction: ExtractionResult) -> ResolveResult:
        """解析依赖：找出缺失的包，生成安装计划。

        Args:
            extraction: AST 提取器的输出

        Returns:
            ResolveResult: 解析结果，含安装计划
        """
        result = ResolveResult()

        # 1. 获取环境已有包
        result.available_packages = self._get_installed_packages()
        stdlib = set(sys.stdlib_module_names)

        # 2. 需要检查的包（第三方 + 条件 + 动态）
        to_check = {d.name for d in extraction.installable}

        for pkg in sorted(to_check):
            # 跳过标准库
            if pkg in stdlib:
                continue

            # 跳过已安装的
            if pkg in result.available_packages:
                continue

            # 检查缓存
            cached = self._check_cache(pkg)

            if cached:
                result.cached_packages.append(InstallItem(name=pkg, is_cached=True))
            else:
                item = InstallItem(
                    name=pkg,
                    reason=f"代码中 import 了 {pkg}，但环境中未安装",
                )
                result.missing_packages.append(item)

        # 3. 检测版本冲突（简化版）
        self._detect_conflicts(to_check, result)

        # 4. 生成安装计划
        result.install_plan = self._build_install_plan(result.missing_packages)

        return result

    # ── 环境查询 ────────────────────────────────────────────

    def _get_installed_packages(self) -> set[str]:
        """获取当前 Python 环境中已安装的包名集合。"""
        if self._installed_cache is not None:
            return self._installed_cache

        packages = set()

        try:
            # 方法 1：pip list（最可靠）
            pip_path = self._get_pip_path()
            proc = subprocess.run(
                [pip_path, "list", "--format=json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode == 0:
                data = json.loads(proc.stdout)
                packages = {pkg["name"].lower() for pkg in data}
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            pass

        # 方法 2：importlib fallback
        if not packages:
            import importlib.metadata as meta
            packages = {dist.metadata["Name"].lower() for dist in meta.distributions()}

        self._installed_cache = packages
        return packages

    def _get_pip_path(self) -> str:
        """获取 pip 可执行文件路径。"""
        return sys.executable + " -m pip"

    # ── 缓存查询 ────────────────────────────────────────────

    def _check_cache(self, package_name: str) -> bool:
        """检查包是否在 depot 缓存中。"""
        if not self.config.cache_enabled:
            return False

        lock_data = self._read_lock()
        return package_name.lower() in lock_data.get("packages", {})

    def _read_lock(self) -> dict:
        """读取 depot.lock 文件。"""
        lock_file = self.config.lock_file
        if not lock_file.exists():
            return {}
        try:
            return json.loads(lock_file.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    # ── 冲突检测 ────────────────────────────────────────────

    def _detect_conflicts(self, required: set[str], result: ResolveResult) -> None:
        """检测版本冲突（基础版：检查 PyPI 是否有这个包）。"""
        for pkg in list(required)[:20]:  # 限制检查数量
            exists = self._pypi_exists(pkg)
            if not exists:
                result.warnings.append(
                    f"包 '{pkg}' 在 PyPI 上未找到，可能是拼写错误或内部包"
                )

    def _pypi_exists(self, package_name: str) -> bool:
        """检查包在 PyPI 上是否存在（用 pip index）。"""
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "index",
                    "versions",
                    package_name,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return proc.returncode == 0 and "ERROR" not in proc.stdout
        except subprocess.TimeoutExpired:
            return True  # 超时假定存在，不阻塞流程

    # ── 安装计划构建 ────────────────────────────────────────

    def _build_install_plan(self, missing: list[InstallItem]) -> list[InstallItem]:
        """构建有序的安装计划。

        策略：按依赖优先级排序。当前简化实现：基础库优先。
        """
        # 已知的基础库（可能被其他包依赖）
        base_packages = {
            "numpy", "scipy", "torch", "tensorflow", "pandas",
            "matplotlib", "pillow", "setuptools", "wheel", "cython",
        }

        for item in missing:
            if item.name.lower() in base_packages:
                item.priority = 1
            else:
                item.priority = 2

        return sorted(missing, key=lambda x: (x.priority, x.name))
