"""
Depot SDK —— 为 Agent 集成提供的高级 API。

Agent 可以通过 import depot.sdk 直接使用这些函数，
无需了解底层管道细节。

用法:
    from depot.sdk import execute, check

    # 检查依赖
    deps = check(code)
    if deps["needs_install"]:
        print(f"需要安装: {deps['needs_install']}")

    # 执行代码（自动处理依赖）
    result = execute("import numpy; print(numpy.array([1,2,3]))")
    print(result["status"])    # "success"
    print(result["summary"])   # "检测到1个外部依赖。代码执行成功。"
"""

from pathlib import Path
from typing import Optional

from .config import DepotConfig
from .pipeline import DepotPipeline


# 全局默认实例（懒加载）
_default_pipeline: Optional[DepotPipeline] = None
_default_config: Optional[DepotConfig] = None


def _get_pipeline() -> DepotPipeline:
    global _default_pipeline, _default_config
    if _default_pipeline is None:
        _default_config = DepotConfig(data_dir=Path("./depot-data"))
        _default_pipeline = DepotPipeline(_default_config)
    return _default_pipeline


def configure(
    data_dir: str = "./depot-data",
    timeout: int = 30,
    offline: bool = False,
    preferred_pm: str = "",
    mirror: Optional[str] = None,
) -> None:
    """配置 Depot SDK 的全局设置。

    Args:
        data_dir: 数据目录（缓存、venv）
        timeout: 执行超时（秒）
        offline: 离线模式
        preferred_pm: 首选包管理器 ("pip", "uv", "poetry")
        mirror: PyPI 镜像 URL
    """
    global _default_pipeline, _default_config
    _default_config = DepotConfig(
        data_dir=Path(data_dir),
        execution_timeout=timeout,
        allow_network=not offline,
        preferred_pm=preferred_pm,
        pypi_mirror=mirror,
    )
    _default_pipeline = DepotPipeline(_default_config)


def execute(
    code: str,
    *,
    auto_install: bool = True,
    known_modules: Optional[set[str]] = None,
    timeout: Optional[int] = None,
    offline: bool = False,
) -> dict:
    """执行 Python 代码，自动处理依赖。

    这是 Agent 使用 Depot 的核心 API。

    Args:
        code: Python 代码字符串
        auto_install: 是否自动安装缺失的包
        known_modules: 已知的本地模块名
        timeout: 执行超时（秒），覆盖全局配置
        offline: 离线模式，覆盖全局配置

    Returns:
        dict: 包含以下键:
            - status: "success" | "partial" | "failed"
            - exit_code: 进程退出码
            - stdout: 标准输出
            - stderr: 标准错误
            - summary: 人类可读摘要
            - suggestions: 修复建议列表
            - dependency_analysis: 依赖分析详情
            - install_info: 安装详情
            - execution_time_ms: 执行耗时
            - total_time_ms: 总耗时

    Example:
        >>> result = execute("import requests; print(requests.get('https://httpbin.org/status/200'))")
        >>> print(result["status"])
        "success"
    """
    pipeline = _get_pipeline()

    # 临时覆盖配置
    if timeout is not None or offline:
        original_config = pipeline.config
        config = DepotConfig(
            data_dir=original_config.data_dir,
            execution_timeout=timeout or original_config.execution_timeout,
            allow_network=not offline,
            preferred_pm=original_config.preferred_pm,
            pypi_mirror=original_config.pypi_mirror,
        )
        pipeline = DepotPipeline(config)

    report = pipeline.run_safe(
        code,
        known_modules=known_modules,
        auto_install=auto_install,
    )

    return {
        "status": report.status.value,
        "exit_code": report.execution_summary.get("exit_code", -1),
        "stdout": report.execution_summary.get("stdout_preview", ""),
        "stderr": report.execution_summary.get("stderr_preview", ""),
        "summary": report.summary,
        "suggestions": report.suggestions,
        "dependency_analysis": {
            "total": len(report.dependency_summary.get("third_party", [])),
            "third_party": report.dependency_summary.get("third_party", []),
            "stdlib": report.dependency_summary.get("standard_library", []),
        },
        "install_info": {
            "installed": report.install_summary.get("installed", []),
            "skipped": report.install_summary.get("skipped", []),
            "failed": report.install_summary.get("failed", []),
            "install_time_ms": report.install_summary.get("total_time_ms", 0),
        },
        "execution_time_ms": report.execution_summary.get("execution_time_ms", 0),
        "total_time_ms": next(
            (t.get("total_duration_ms", 0) for t in report.timeline if "total_duration_ms" in t), 0
        ),
    }


def check(code: str, *, known_modules: Optional[set[str]] = None) -> dict:
    """分析代码依赖，不执行也不安装。

    Agent 可以在生成代码前先用此函数了解依赖情况。

    Args:
        code: Python 代码字符串
        known_modules: 已知的本地模块名

    Returns:
        dict: 包含:
            - total_deps: 总导入数
            - third_party: 第三方依赖列表
            - stdlib: 标准库列表
            - needs_install: 需要安装的包名列表
            - conditional: 条件导入列表
            - dynamic: 动态导入列表

    Example:
        >>> deps = check("import numpy; from torch import nn; import os")
        >>> print(deps["needs_install"])
        ["numpy", "torch"]
    """
    pipeline = _get_pipeline()
    result = pipeline.check(code)

    return {
        "total_deps": len(result.dependencies),
        "third_party": [d.name for d in result.third_party],
        "stdlib": [d.name for d in result.standard_library],
        "local": [d.name for d in result.local_imports],
        "conditional": [d.name for d in result.conditional_imports],
        "dynamic": [d.name for d in result.dynamic_imports],
        "needs_install": result.package_names,
    }


def inspect_environment() -> dict:
    """检查当前 Depot 环境状态。

    Returns:
        dict: 包含:
            - cached_packages: 缓存包列表
            - cache_count: 缓存包数
            - config: 当前配置摘要
    """
    pipeline = _get_pipeline()
    cache = pipeline.cache
    info = cache.get_info()

    return {
        "cached_packages": cache.list_all(),
        "cache_count": info.packages_count,
        "last_updated": info.last_updated,
        "config": {
            "data_dir": str(pipeline.config.data_dir),
            "timeout": pipeline.config.execution_timeout,
            "offline": not pipeline.config.allow_network,
        },
    }
