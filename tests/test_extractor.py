"""AST 依赖提取器单元测试。"""

import sys
sys.path.insert(0, "src")

import pytest
from depot.extractor import (
    DependencyExtractor,
    DependencyInfo,
    ExtractionResult,
    extract_dependencies,
)


class TestExtractStandardLibrary:
    """标准库 import 提取。"""

    def test_import_stdlib(self):
        code = "import os"
        r = extract_dependencies(code)
        assert len(r.standard_library) == 1
        assert r.standard_library[0].name == "os"
        assert not r.third_party

    def test_import_multiple_stdlib(self):
        code = "import os, sys, json"
        r = extract_dependencies(code)
        stdlib_names = {d.name for d in r.standard_library}
        assert stdlib_names >= {"os", "sys", "json"}

    def test_from_import_stdlib(self):
        code = "from pathlib import Path"
        r = extract_dependencies(code)
        assert len(r.standard_library) == 1
        assert r.standard_library[0].name == "pathlib"

    def test_import_as_alias(self):
        code = "import numpy as np"
        r = extract_dependencies(code)
        assert r.third_party[0].alias == "np"


class TestExtractThirdParty:
    """第三方库 import 提取。"""

    def test_import_third_party(self):
        code = "import numpy"
        r = extract_dependencies(code)
        assert len(r.third_party) == 1
        assert r.third_party[0].name == "numpy"

    def test_from_import_third_party(self):
        code = "from torch import nn, optim"
        r = extract_dependencies(code)
        assert r.third_party[0].name == "torch"

    def test_mixed_stdlib_and_third_party(self):
        code = "import os\nimport numpy\nfrom pathlib import Path"
        r = extract_dependencies(code)
        assert {d.name for d in r.standard_library} >= {"os", "pathlib"}
        assert {d.name for d in r.third_party} == {"numpy"}

    def test_deduplication(self):
        code = "import numpy\nimport numpy as np\nfrom numpy import array"
        r = extract_dependencies(code)
        assert len(r.package_names) == 1
        assert "numpy" in r.package_names

    def test_submodule_extracts_top_level(self):
        code = "from sklearn.ensemble import RandomForest"
        r = extract_dependencies(code)
        assert r.third_party[0].name == "sklearn"

    def test_empty_code(self):
        code = ""
        r = extract_dependencies(code)
        assert len(r.dependencies) == 0

    def test_comment_only(self):
        code = "# import numpy\nprint('hello')"
        r = extract_dependencies(code)
        third = [d for d in r.third_party if d.name == 'numpy']
        assert len(third) == 0


class TestLocalImports:
    """本地导入提取。"""

    def test_relative_import(self):
        code = "from .utils import helper"
        r = extract_dependencies(code)
        assert len(r.local_imports) == 1
        assert r.local_imports[0].name == "helper"

    def test_relative_import_parent(self):
        code = "from ..config import settings"
        r = extract_dependencies(code)
        assert len(r.local_imports) == 1
        assert r.local_imports[0].name == "settings"

    def test_known_local_module(self):
        ext = DependencyExtractor(known_local_modules={"my_package"})
        code = "import my_package"
        r = ext.extract(code)
        assert len(r.local_imports) == 1
        assert r.local_imports[0].name == "my_package"


class TestDynamicImports:
    """动态导入提取。"""

    def test_importlib_import_module(self):
        code = 'importlib.import_module("requests")'
        r = extract_dependencies(code)
        assert len(r.dynamic_imports) == 1
        assert r.dynamic_imports[0].name == "requests"

    def test_builtin___import__(self):
        code = '__import__("pickle")'
        r = extract_dependencies(code)
        assert len(r.dynamic_imports) == 1
        assert r.dynamic_imports[0].name == "pickle"

    def test_dynamic_not_duplicated(self):
        code = 'import requests\nimportlib.import_module("requests")'
        r = extract_dependencies(code)
        requests_deps = [d for d in r.dependencies if d.name == "requests"]
        assert len(requests_deps) == 1


class TestConditionalImports:
    """条件导入（try-except 包裹）。"""

    def test_try_except_import(self):
        code = "try:\n    import cv2\nexcept ImportError:\n    cv2 = None"
        r = extract_dependencies(code)
        # cv2 应该在条件导入中
        cond_names = {d.name for d in r.conditional_imports}
        assert "cv2" in cond_names

    def test_non_conditional_still_third_party(self):
        code = "import numpy\ntry:\n    import cv2\nexcept ImportError:\n    pass"
        r = extract_dependencies(code)
        assert "numpy" in {d.name for d in r.third_party}
        assert "cv2" in {d.name for d in r.conditional_imports}

    def test_multiple_try_imports(self):
        code = """
try:
    import orjson
except ImportError:
    import json as orjson
try:
    import uvloop
except ImportError:
    pass
"""
        r = extract_dependencies(code)
        cond_names = {d.name for d in r.conditional_imports}
        assert "orjson" in cond_names
        assert "uvloop" in cond_names


class TestExtractionResult:
    """ExtractionResult 数据类测试。"""

    def test_package_names_dedup(self):
        r = ExtractionResult(dependencies=[
            DependencyInfo("numpy", "third_party", "import"),
            DependencyInfo("numpy", "third_party", "from"),
        ])
        assert r.package_names == ["numpy"]

    def test_installable_excludes_stdlib(self):
        r = ExtractionResult(dependencies=[
            DependencyInfo("os", "standard_library", "import"),
            DependencyInfo("numpy", "third_party", "import"),
            DependencyInfo("helper", "local", "from"),
            DependencyInfo("cv2", "conditional", "import"),
        ])
        installable_names = {d.name for d in r.installable}
        assert "numpy" in installable_names
        assert "cv2" in installable_names  # conditional 仍视为 installable
        assert "os" not in installable_names
        assert "helper" not in installable_names

    def test_is_installable(self):
        assert DependencyInfo("numpy", "third_party", "import").is_installable()
        assert DependencyInfo("cv2", "conditional", "import").is_installable()
        assert not DependencyInfo("os", "standard_library", "import").is_installable()
        assert not DependencyInfo("utils", "local", "import").is_installable()


class TestSyntaxErrors:
    """语法错误代码的容错处理。"""

    def test_syntax_error_fallback(self):
        code = "import numpy; ; ; ; for while if ::::"
        r = extract_dependencies(code)
        # 即使有语法错误，也应尽力提取 import
        assert len(r.errors) > 0 or len(r.dependencies) > 0

    def test_syntax_error_still_extracts(self):
        code = "import numpy\ndef broken("
        r = extract_dependencies(code)
        assert any(d.name == "numpy" for d in r.dependencies)


class TestEdgeCases:
    """边界情况。"""

    def test_inline_import(self):
        code = "if True:\n    import numpy"
        r = extract_dependencies(code)
        assert any(d.name == "numpy" for d in r.third_party)

    def test_function_scope_import(self):
        code = "def foo():\n    import numpy\n    pass"
        r = extract_dependencies(code)
        assert any(d.name == "numpy" for d in r.third_party)

    def test_class_scope_import(self):
        code = "class Foo:\n    import numpy"
        r = extract_dependencies(code)
        assert any(d.name == "numpy" for d in r.third_party)

    def test_multiline_import(self):
        code = "import numpy, \\\n       pandas, \\\n       scipy"
        r = extract_dependencies(code)
        names = {d.name for d in r.third_party}
        assert names >= {"numpy", "pandas", "scipy"}
