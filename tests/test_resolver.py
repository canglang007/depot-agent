"""依赖解析器单元测试。"""

import sys
sys.path.insert(0, "src")

import pytest
from depot.config import DepotConfig
from depot.extractor import ExtractionResult, DependencyInfo
from depot.resolver import DependencyResolver, ResolveResult, InstallItem


@pytest.fixture
def config():
    return DepotConfig(data_dir="./test-depot-data")


@pytest.fixture
def resolver(config):
    return DependencyResolver(config)


class TestResolveBasic:
    """基本解析功能。"""

    def test_no_third_party(self, resolver):
        """纯标准库，无需安装。"""
        ext = ExtractionResult(dependencies=[
            DependencyInfo("os", "standard_library", "import"),
            DependencyInfo("json", "standard_library", "import"),
        ])
        result = resolver.resolve(ext)
        assert len(result.missing_packages) == 0
        assert result.all_clear

    def test_stdlib_already_available(self, resolver):
        """标准库在环境中必然存在。"""
        ext = ExtractionResult(dependencies=[
            DependencyInfo("os", "standard_library", "import"),
        ])
        result = resolver.resolve(ext)
        assert "os" not in [item.name for item in result.missing_packages]

    def test_already_installed(self, resolver):
        """已安装的包不应在缺失列表中。"""
        # pip 自身一定在环境中
        resolver._installed_cache = {"pip", "setuptools", "wheel"}
        ext = ExtractionResult(dependencies=[
            DependencyInfo("pip", "third_party", "import"),
        ])
        result = resolver.resolve(ext)
        assert len(result.missing_packages) == 0

    def test_missing_third_party(self, resolver):
        """完全不存在的第三方包应在缺失列表中。"""
        resolver._installed_cache = {"pip"}
        ext = ExtractionResult(dependencies=[
            DependencyInfo("this_package_does_not_exist_xyz", "third_party", "import"),
        ])
        result = resolver.resolve(ext)
        assert len(result.missing_packages) == 1
        assert result.missing_packages[0].name == "this_package_does_not_exist_xyz"

    def test_mixed_installed_and_missing(self, resolver):
        resolver._installed_cache = {"pip", "numpy"}
        ext = ExtractionResult(dependencies=[
            DependencyInfo("numpy", "third_party", "import"),
            DependencyInfo("no_such_pkg_123", "third_party", "import"),
        ])
        result = resolver.resolve(ext)
        assert len(result.missing_packages) == 1
        assert result.missing_packages[0].name == "no_such_pkg_123"


class TestResolveResult:
    """ResolveResult 数据类测试。"""

    def test_needs_install_true(self):
        r = ResolveResult(missing_packages=[InstallItem("numpy")])
        assert r.needs_install

    def test_needs_install_false(self):
        r = ResolveResult()
        assert not r.needs_install

    def test_all_clear_no_conflicts(self):
        r = ResolveResult()
        assert r.all_clear

    def test_all_clear_with_conflicts(self):
        r = ResolveResult(conflicts=["numpy 版本冲突"])
        assert not r.all_clear


class TestInstallPlan:
    """安装计划构建。"""

    def test_base_packages_priority(self, resolver):
        """基础库应该先安装。"""
        from depot.resolver import InstallItem
        items = [
            InstallItem("python-dotenv"),
            InstallItem("numpy"),
            InstallItem("torch"),
            InstallItem("requests"),
        ]
        plan = resolver._build_install_plan(items)
        # numpy 和 torch 是基础库，应该排在前面
        assert plan[0].name in ("numpy", "torch")
        assert plan[0].priority == 1
        assert plan[-1].priority == 2

    def test_same_priority_sorted_by_name(self, resolver):
        from depot.resolver import InstallItem
        items = [
            InstallItem("zzz"),
            InstallItem("aaa"),
        ]
        plan = resolver._build_install_plan(items)
        assert plan[0].name == "aaa"
        assert plan[1].name == "zzz"


import shutil
def teardown_module():
    shutil.rmtree("./test-depot-data", ignore_errors=True)
