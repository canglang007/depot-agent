"""缓存管理单元测试。"""

import sys
sys.path.insert(0, "src")

import json
import pytest
from pathlib import Path
from depot.config import DepotConfig
from depot.cache import CacheManager, CacheInfo


@pytest.fixture
def cache(tmp_path):
    config = DepotConfig(data_dir=tmp_path / "depot-data")
    config.ensure_dirs()
    return CacheManager(config)


class TestBasicCache:
    """基本缓存操作。"""

    def test_add_and_read(self, cache):
        cache.add_packages({"numpy": "1.26.0"})
        assert cache.has_package("numpy")
        assert cache.has_package("NUMPY")  # 大小写不敏感

    def test_get_package_info(self, cache):
        cache.add_packages({"pandas": "2.1.0"})
        info = cache.get_package("pandas")
        assert info is not None
        assert info["version"] == "2.1.0"

    def test_get_missing_package(self, cache):
        assert cache.get_package("nonexistent") is None

    def test_has_nonexistent(self, cache):
        assert not cache.has_package("nonexistent_pkg")

    def test_remove_package(self, cache):
        cache.add_packages({"pytest": "7.0"})
        assert cache.has_package("pytest")
        cache.remove_package("pytest")
        assert not cache.has_package("pytest")

    def test_remove_nonexistent_no_error(self, cache):
        cache.remove_package("never_added")

    def test_add_multiple_packages(self, cache):
        cache.add_packages({"a": "1.0", "b": "2.0", "c": "3.0"})
        assert cache.has_package("a")
        assert cache.has_package("b")
        assert cache.has_package("c")


class TestLockFile:
    """锁文件读写。"""

    def test_read_empty_lock(self, cache):
        data = cache.read_lock()
        assert data == {}

    def test_write_and_read_lock(self, cache):
        cache.add_packages({"flask": "3.0.0"})
        data = cache.read_lock()
        assert "packages" in data
        assert "flask" in data["packages"]

    def test_lock_is_valid_json(self, cache):
        cache.add_packages({"requests": "2.31.0"})
        assert cache.config.lock_file.exists()
        content = cache.config.lock_file.read_text()
        data = json.loads(content)
        assert "packages" in data

    def test_updated_at_timestamp(self, cache):
        cache.add_packages({"pytz": "2024.1"})
        data = cache.read_lock()
        assert "updated_at" in data
        assert data["updated_at"] > 0


class TestCacheInfo:
    """缓存统计。"""

    def test_info_empty(self, cache):
        info = cache.get_info()
        assert info.packages_count == 0
        assert info.last_updated == 0.0

    def test_info_with_data(self, cache):
        cache.add_packages({"a": "1.0", "b": "2.0"})
        info = cache.get_info()
        assert info.packages_count == 2
        assert info.last_updated > 0

    def test_clear(self, cache):
        cache.add_packages({"a": "1.0"})
        cache.clear()
        assert not cache.has_package("a")
        assert cache.get_info().packages_count == 0

    def test_list_all(self, cache):
        cache.add_packages({"x": "1.0", "y": "2.0"})
        all_pkgs = cache.list_all()
        assert all_pkgs == {"x": "1.0", "y": "2.0"}


class TestStaleness:
    """过期检查。"""

    def test_not_stale_within_ttl(self, cache):
        cache.add_packages({"a": "1.0"})
        assert not cache.is_stale()

    def test_disabled_cache_is_stale(self, cache):
        cache.config.cache_enabled = False
        cache.add_packages({"a": "1.0"})
        assert cache.is_stale()
