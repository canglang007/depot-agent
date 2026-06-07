"""
B2 Baseline: 预装全家桶。

在 Docker 风格的 Python venv 中预装 50+ 常用数据科学/ML 包。
代码在执行时无需安装任何依赖（理想情况），但环境臃肿、启动慢。

缺点：
- 首次创建 venv 和安装全家桶耗时长（10-20 分钟）
- 包版本固定，遇到新包仍会失败
- 镜像体积大（2-5GB）
"""

import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .base import Baseline, BaselineResult

# ── B2 预装全家桶包清单 ──────────────────────────────────────
# 覆盖数据科学、ML、Web、工具等常见场景
B2_PACKAGES = [
    # 数据科学核心
    "numpy", "pandas", "scipy", "matplotlib", "seaborn",
    "scikit-learn", "statsmodels",
    # 机器学习 / 深度学习
    "torch", "torchvision", "transformers", "datasets",
    # 图像处理
    "pillow", "opencv-python", "imageio",
    # Web / API
    "requests", "httpx", "aiohttp", "flask", "fastapi", "uvicorn",
    # 文本 / NLP
    "nltk", "spacy", "textblob", "wordcloud",
    # 工具
    "pyyaml", "toml", "python-dotenv", "click", "tqdm",
    "rich", "pydantic", "pydantic-settings",
    # 序列化
    "orjson", "ujson", "msgpack",
    # 数据库
    "sqlalchemy", "sqlite-utils",
    # 科学计算
    "sympy", "networkx",
    # 测试
    "pytest", "hypothesis",
    # 可视化
    "plotly", "bokeh",
    # 加密 / 安全
    "cryptography", "pyjwt",
    # 日期时间
    "python-dateutil", "arrow",
    # 系统
    "psutil", "watchdog",
    # Jupyter
    "jupyter", "ipython",
    # 其他常用
    "lxml", "beautifulsoup4", "html5lib",
    "openpyxl", "xlrd", "tabulate",
]


class PreInstalledBaseline(Baseline):
    """B2: 预装全家桶 —— venv 中预装 50+ 常用包。"""

    def __init__(self, timeout: int = 30, data_dir: str = "./b2-data"):
        super().__init__(
            name="B2-预装全家桶",
            timeout=timeout,
        )
        self.data_dir = Path(data_dir)
        self.venv_dir = self.data_dir / "venv"
        self.python_bin = self.venv_dir / "bin" / "python3"
        self._ready = False

    # ── 环境准备 ────────────────────────────────────────

    def setup(self) -> None:
        """创建 venv 并预装所有包（仅首次运行）。"""
        if self._ready:
            return

        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 创建 venv（如果不存在）
        if not self.python_bin.exists():
            print(f"[B2] 创建 venv: {self.venv_dir}")
            subprocess.run(
                [sys.executable, "-m", "venv", str(self.venv_dir)],
                check=True,
                capture_output=True,
            )

        # 安装全家桶（检查是否已完成）
        marker = self.data_dir / ".installed"
        if not marker.exists():
            print(f"[B2] 安装全家桶 ({len(B2_PACKAGES)} 个包)...")
            t0 = time.time()

            # 批量安装（一次 pip install 比逐个快）
            proc = subprocess.run(
                [str(self.python_bin), "-m", "pip", "install", "--quiet"] + B2_PACKAGES,
                capture_output=True,
                text=True,
                timeout=1800,  # 最长 30 分钟
            )

            elapsed = int(time.time() - t0)
            if proc.returncode == 0:
                marker.touch()
                print(f"[B2] 全家桶安装完成，耗时 {elapsed}s")
            else:
                print(f"[B2] 部分包安装失败，耗时 {elapsed}s")
                print(f"[B2] stderr: {proc.stderr[:500]}")
                # 仍标记为已尝试，避免每次都重试
                marker.touch()

        self._ready = True

    def run(self, code: str) -> BaselineResult:
        """在预装 venv 中执行代码。"""
        if not self._ready:
            self.setup()

        result = BaselineResult()
        t0 = time.time()
        result.timeline = []

        # 写入临时文件
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", prefix="preinst_", delete=False
        )
        tmp.write(code)
        tmp.flush()
        tmp_path = Path(tmp.name)

        # 在预装 venv 中执行
        t_exec = time.time()
        try:
            proc = subprocess.run(
                [str(self.python_bin), str(tmp_path)],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            result.exit_code = proc.returncode
            result.stdout = proc.stdout[:50000]
            result.stderr = proc.stderr[:50000]
            result.execution_time_ms = int((time.time() - t_exec) * 1000)
        except subprocess.TimeoutExpired:
            result.timed_out = True
            result.exit_code = -1
            result.stderr = f"执行超时 (>{self.timeout}s)"
            result.execution_time_ms = self.timeout * 1000
        finally:
            tmp_path.unlink(missing_ok=True)

        # 分类
        self._classify_error(result)

        result.total_time_ms = int((time.time() - t0) * 1000)
        result.status = "success" if result.exit_code == 0 and not result.timed_out else "failed"
        result.summary = (
            f"预装执行{'成功' if result.status == 'success' else '失败'}"
            f" (耗时 {result.execution_time_ms}ms)"
        )
        if result.error_summary:
            result.summary += f": {result.error_summary}"

        return result

    def _classify_error(self, result: BaselineResult) -> None:
        if "ModuleNotFoundError" in result.stderr or "ImportError" in result.stderr:
            result.error_type = "import_error"
            for line in result.stderr.split("\n"):
                if "No module named" in line:
                    result.error_summary = line.strip()
                    break
        elif "SyntaxError" in result.stderr:
            result.error_type = "syntax_error"
        elif result.exit_code != 0:
            result.error_type = "runtime_error"

    def teardown(self) -> None:
        """B2 venv 保留复用，不自动删除。"""
        pass
