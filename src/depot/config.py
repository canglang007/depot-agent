"""
Depot 配置管理。

控制所有组件的行为：缓存策略、安装源、安全限制等。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class DepotConfig:
    """Depot 系统全局配置。"""

    # ---- 路径配置 ----
    # Depot 数据目录，存放 venv、缓存、锁文件等
    data_dir: Path = Path("./depot-data")

    # ---- 依赖解析 ----
    # PyPI 镜像 URL（留空使用默认）
    pypi_mirror: Optional[str] = None
    # pip 额外参数
    pip_extra_args: list[str] = field(default_factory=list)

    # ---- 安装策略 ----
    # 首选包管理器: "pip", "uv", "poetry", 或 "" 自动检测
    preferred_pm: str = ""
    # 安装超时（秒）
    install_timeout: int = 60
    # 单包安装重试次数
    install_retries: int = 2
    # 是否并行安装
    parallel_install: bool = True
    # 最大并行数
    max_parallel: int = 4

    # ---- 执行隔离 ----
    # 代码执行超时（秒）
    execution_timeout: int = 30
    # 是否允许网络访问
    allow_network: bool = True
    # 是否允许文件系统写入（超出临时目录）
    allow_filesystem_write: bool = False
    # 内存限制 (MB)，0 表示不限制
    memory_limit_mb: int = 512

    # ---- 缓存 ----
    # 是否启用缓存
    cache_enabled: bool = True
    # 缓存 TTL（秒），超时后重新解析
    cache_ttl: int = 3600

    def __post_init__(self):
        self.data_dir = Path(self.data_dir)
        self.venv_dir = self.data_dir / "venv"
        self.cache_dir = self.data_dir / "cache"
        self.lock_file = self.data_dir / "depot.lock"

    @property
    def pip_index_args(self) -> list[str]:
        """返回 pip 索引相关参数。"""
        if self.pypi_mirror:
            return ["-i", self.pypi_mirror]
        return []

    def ensure_dirs(self) -> None:
        """创建必要的目录。"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.venv_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
