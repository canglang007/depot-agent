"""
缓存管理。

管理 depot.lock 文件 —— 记录已解析和已安装的包版本，
实现跨任务共享依赖缓存。
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import DepotConfig


@dataclass
class CacheInfo:
    """缓存统计信息。"""

    packages_count: int = 0
    last_updated: float = 0.0
    lock_file_path: str = ""


class CacheManager:
    """管理 depot 的包缓存和锁文件。"""

    def __init__(self, config: DepotConfig):
        self.config = config

    def add_packages(self, packages: dict[str, str]) -> None:
        """添加包到缓存。

        Args:
            packages: 包名到版本的映射，如 {"numpy": "1.26.0"}
        """
        lock_data = self.read_lock()
        lock_data.setdefault("packages", {})

        for name, version in packages.items():
            lock_data["packages"][name.lower()] = {
                "version": version,
                "cached_at": time.time(),
            }

        lock_data["updated_at"] = time.time()
        self._write_lock(lock_data)

    def has_package(self, name: str) -> bool:
        """检查包是否在缓存中。"""
        lock_data = self.read_lock()
        return name.lower() in lock_data.get("packages", {})

    def get_package(self, name: str) -> dict | None:
        """获取缓存中指定包的信息。"""
        lock_data = self.read_lock()
        return lock_data.get("packages", {}).get(name.lower())

    def remove_package(self, name: str) -> None:
        """从缓存中移除一个包。"""
        lock_data = self.read_lock()
        if name.lower() in lock_data.get("packages", {}):
            del lock_data["packages"][name.lower()]
            self._write_lock(lock_data)

    def read_lock(self) -> dict:
        """读取 depot.lock 文件。"""
        lock_file = self.config.lock_file
        if not lock_file.exists():
            return {}
        try:
            return json.loads(lock_file.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_lock(self, data: dict) -> None:
        """写入 depot.lock 文件。"""
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        self.config.lock_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def get_info(self) -> CacheInfo:
        """获取缓存统计信息。"""
        lock_data = self.read_lock()
        return CacheInfo(
            packages_count=len(lock_data.get("packages", {})),
            last_updated=lock_data.get("updated_at", 0.0),
            lock_file_path=str(self.config.lock_file),
        )

    def clear(self) -> None:
        """清空所有缓存。"""
        lock_file = self.config.lock_file
        if lock_file.exists():
            lock_file.unlink()

    def is_stale(self) -> bool:
        """检查缓存是否过期（超过 TTL）。"""
        if not self.config.cache_enabled:
            return True
        lock_data = self.read_lock()
        updated = lock_data.get("updated_at", 0)
        return (time.time() - updated) > self.config.cache_ttl

    def list_all(self) -> dict[str, str]:
        """列出所有缓存包的 (名称 → 版本) 映射。"""
        lock_data = self.read_lock()
        packages = lock_data.get("packages", {})
        return {name: info.get("version", "unknown") for name, info in packages.items()}
