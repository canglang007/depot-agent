"""按需安装器单元测试。"""

import sys
sys.path.insert(0, "src")

import pytest
from depot.config import DepotConfig
from depot.installer import Installer, InstallReport
from depot.resolver import ResolveResult, InstallItem


@pytest.fixture
def config(tmp_path):
    return DepotConfig(data_dir=tmp_path / "depot-data")


@pytest.fixture
def installer(config):
    return Installer(config)


class TestInstallReport:
    """安装报告数据类。"""

    def test_empty_install(self):
        report = InstallReport()
        assert report.ok
        assert report.success_count == 0
        assert report.fail_count == 0

    def test_ok_with_installs(self):
        report = InstallReport(installed=["numpy"])
        assert report.ok

    def test_not_ok_with_failures(self):
        report = InstallReport(failed=[{"name": "x", "error": "timeout"}])
        assert not report.ok

    def test_mixed_installed_skipped(self):
        report = InstallReport(
            installed=["numpy"],
            skipped=["pandas"],
            failed=[{"name": "broken", "error": "unknown"}],
        )
        assert report.success_count == 1
        assert report.fail_count == 1
        assert len(report.skipped) == 1


class TestNoOpInstall:
    """空安装（无需安装任何包）。"""

    def test_empty_resolve_no_install(self, installer):
        resolve = ResolveResult()  # 无缺失
        report = installer.install(resolve)
        assert report.ok
        assert report.success_count == 0
        assert report.fail_count == 0
        assert report.total_time_ms >= 0


class TestInstallPlanExecution:
    """安装计划执行（用小包测试）。"""

    def test_install_single_cached_package(self, installer):
        """已缓存的不需要重新安装。"""
        item = InstallItem("numpy", is_cached=True)
        resolve = ResolveResult(
            cached_packages=[item],
        )
        report = installer.install(resolve)
        assert "numpy" in report.skipped
        assert report.fail_count == 0

    @pytest.mark.slow
    def test_install_real_package(self, installer):
        """真实安装一个小包（需要网络）。"""
        item = InstallItem("six")  # six 是微小的纯 Python 包
        resolve = ResolveResult(missing_packages=[item])
        report = installer.install(resolve)
        # 可能成功或失败（取决于网络），但不应该 crash
        assert report.total_time_ms >= 0

    def test_sequential_install_empty(self, installer):
        items = []
        report = InstallReport()
        installer._sequential_install(items, report)
        assert report.ok
