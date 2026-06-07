"""DepotConfig 配置管理测试。"""

import sys
sys.path.insert(0, "src")

import pytest
from pathlib import Path
from depot.config import DepotConfig


class TestDefaultConfig:
    """默认配置。"""

    def test_default_data_dir(self):
        c = DepotConfig()
        assert c.data_dir == Path("./depot-data")

    def test_default_timeout(self):
        c = DepotConfig()
        assert c.execution_timeout == 30
        assert c.install_timeout == 60

    def test_default_cache_enabled(self):
        c = DepotConfig()
        assert c.cache_enabled

    def test_default_retries(self):
        c = DepotConfig()
        assert c.install_retries == 2

    def test_derived_paths(self):
        c = DepotConfig(data_dir="./my-data")
        assert c.venv_dir == Path("./my-data/venv")
        assert c.cache_dir == Path("./my-data/cache")
        assert c.lock_file == Path("./my-data/depot.lock")


class TestCustomConfig:
    """自定义配置。"""

    def test_custom_timeout(self):
        c = DepotConfig(execution_timeout=60, install_timeout=120)
        assert c.execution_timeout == 60
        assert c.install_timeout == 120

    def test_disable_network(self):
        c = DepotConfig(allow_network=False)
        assert not c.allow_network

    def test_mirror_url(self):
        c = DepotConfig(pypi_mirror="https://pypi.tuna.tsinghua.edu.cn/simple")
        assert c.pip_index_args == ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]

    def test_no_mirror_empty_args(self):
        c = DepotConfig()
        assert c.pip_index_args == []

    def test_memory_limit(self):
        c = DepotConfig(memory_limit_mb=1024)
        assert c.memory_limit_mb == 1024

    def test_ensure_dirs_creates_all(self, tmp_path):
        c = DepotConfig(data_dir=tmp_path / "depot-data")
        c.ensure_dirs()
        assert c.data_dir.exists()
        assert c.venv_dir.exists()
        assert c.cache_dir.exists()
