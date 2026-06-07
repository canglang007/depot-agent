"""
按需安装器。

支持多种包管理器后端（pip、uv、poetry），增量安装缺失的包，
自动缓存，并行下载，超时重试，镜像加速。
"""

import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from .config import DepotConfig
from .resolver import InstallItem, ResolveResult


class PackageManager(str, Enum):
    """支持的包管理器。"""
    PIP = "pip"
    UV = "uv"
    POETRY = "poetry"


@dataclass
class InstallReport:
    """安装操作的报告。"""

    installed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    total_time_ms: int = 0
    pm_used: str = "pip"  # 实际使用的包管理器

    @property
    def success_count(self) -> int:
        return len(self.installed)

    @property
    def fail_count(self) -> int:
        return len(self.failed)

    @property
    def ok(self) -> bool:
        return self.fail_count == 0


def _detect_pm(config: DepotConfig) -> PackageManager:
    """检测并返回可用的包管理器（按优先级：uv > pip > poetry）。"""
    if config.preferred_pm:
        pm = PackageManager(config.preferred_pm)
        if _pm_available(pm):
            return pm
    # 自动检测
    for pm in [PackageManager.UV, PackageManager.PIP, PackageManager.POETRY]:
        if _pm_available(pm):
            return pm
    return PackageManager.PIP  # pip 总是可用


def _pm_available(pm: PackageManager) -> bool:
    """检查包管理器是否可用。"""
    try:
        if pm == PackageManager.UV:
            subprocess.run(["uv", "--version"], capture_output=True, timeout=5)
            return True
        elif pm == PackageManager.POETRY:
            subprocess.run(["poetry", "--version"], capture_output=True, timeout=5)
            return True
        elif pm == PackageManager.PIP:
            return True  # pip 随 Python 发布
    except FileNotFoundError:
        return False
    return False


def _build_install_cmd(
    pm: PackageManager,
    pkg_spec: str,
    config: DepotConfig,
) -> list[str]:
    """构建安装命令。"""
    if pm == PackageManager.UV:
        cmd = ["uv", "pip", "install", "--quiet"]
        cmd.extend(config.pip_index_args)
        cmd.append(pkg_spec)
    elif pm == PackageManager.POETRY:
        cmd = ["poetry", "add", pkg_spec]
    else:  # pip
        cmd = [
            sys.executable, "-m", "pip", "install",
            "--quiet", "--no-input", "--disable-pip-version-check",
        ]
        cmd.extend(config.pip_index_args)
        cmd.extend(config.pip_extra_args)
        cmd.append(pkg_spec)
    return cmd


class Installer:
    """按需安装器 —— 支持多种包管理器后端。"""

    def __init__(self, config: DepotConfig):
        self.config = config
        self._pm: Optional[PackageManager] = None

    @property
    def pm(self) -> PackageManager:
        if self._pm is None:
            self._pm = _detect_pm(self.config)
        return self._pm

    def install(self, resolve_result: ResolveResult) -> InstallReport:
        report = InstallReport()
        report.pm_used = self.pm.value
        start = time.time()

        report.skipped = [item.name for item in resolve_result.cached_packages]
        to_install = resolve_result.missing_packages

        if not to_install:
            report.total_time_ms = int((time.time() - start) * 1000)
            return report

        if self.config.parallel_install and len(to_install) > 1:
            self._parallel_install(to_install, report)
        else:
            self._sequential_install(to_install, report)

        report.total_time_ms = int((time.time() - start) * 1000)
        return report

    def _sequential_install(self, items: list[InstallItem], report: InstallReport) -> None:
        for item in items:
            self._install_one(item, report)

    def _parallel_install(self, items: list[InstallItem], report: InstallReport) -> None:
        max_workers = min(self.config.max_parallel, len(items))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self._install_one_return, item): item for item in items}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    name, success, error = future.result()
                    if success:
                        report.installed.append(name)
                    else:
                        report.failed.append({"name": name, "error": error})
                except Exception as e:
                    report.failed.append({"name": item.name, "error": str(e)})

    def _install_one_return(self, item: InstallItem) -> tuple[str, bool, str]:
        report = InstallReport()
        self._install_one(item, report)
        if report.failed:
            return item.name, False, report.failed[0]["error"]
        return item.name, True, ""

    def _install_one(self, item: InstallItem, report: InstallReport) -> None:
        pkg_spec = item.name
        if item.version_spec:
            pkg_spec = f"{item.name}{item.version_spec}"

        # 尝试首选 PM
        cmd = _build_install_cmd(self.pm, pkg_spec, self.config)
        if self._try_install(cmd, item, report):
            return

        # 回退：uv 失败用 pip，pip 失败用 uv
        fallback_pms = []
        if self.pm == PackageManager.UV:
            fallback_pms = [PackageManager.PIP]
        elif self.pm == PackageManager.PIP:
            fallback_pms = [PackageManager.UV]

        for fb_pm in fallback_pms:
            if _pm_available(fb_pm):
                fb_cmd = _build_install_cmd(fb_pm, pkg_spec, self.config)
                if self._try_install(fb_cmd, item, report):
                    return

        report.failed.append({"name": item.name, "error": "所有包管理器均失败"})

    def _try_install(self, cmd: list[str], item: InstallItem, report: InstallReport) -> bool:
        for attempt in range(self.config.install_retries + 1):
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.config.install_timeout)
                if proc.returncode == 0:
                    report.installed.append(item.name)
                    return True
                if attempt == self.config.install_retries:
                    return False
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return False
        return False


def install_missing(config: DepotConfig, resolve_result: ResolveResult) -> InstallReport:
    installer = Installer(config)
    return installer.install(resolve_result)
