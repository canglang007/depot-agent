#!/usr/bin/env python3
"""
Depot CLI —— 面向代码生成 Agent 的按需依赖解析系统。

用法:
    depot run <file>             执行 Python 文件
    depot run -c "code"          执行内联代码
    depot check <file>           检查依赖（不执行）
    depot cache list             列出缓存
    depot cache clear            清除缓存
    depot --help                 帮助
"""

import argparse
import sys
from pathlib import Path

from .config import DepotConfig
from .pipeline import DepotPipeline
from .cache import CacheManager


def main():
    parser = argparse.ArgumentParser(
        prog="depot",
        description="Depot —— 面向代码生成Agent的按需依赖解析系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  depot run script.py
  depot run -c "import numpy; print(numpy.__version__)"
  depot check script.py
  depot cache list
  depot cache clear
  depot run --offline script.py
  depot run --pm uv script.py
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # ── run 命令 ──────────────────────────────────────
    run_parser = subparsers.add_parser("run", help="执行 Python 代码")
    run_parser.add_argument("file", nargs="?", help="Python 文件路径")
    run_parser.add_argument("-c", "--code", help="内联 Python 代码")
    run_parser.add_argument("--no-install", action="store_true", help="不自动安装依赖")
    run_parser.add_argument("--offline", action="store_true", help="离线模式（禁止网络）")
    run_parser.add_argument("--timeout", type=int, default=30, help="执行超时（秒）")
    run_parser.add_argument("--pm", choices=["pip", "uv", "poetry"], help="包管理器")
    run_parser.add_argument("--mirror", help="PyPI 镜像 URL")
    run_parser.add_argument("--json", action="store_true", help="JSON 格式输出")

    # ── check 命令 ────────────────────────────────────
    check_parser = subparsers.add_parser("check", help="检查代码依赖（不执行）")
    check_parser.add_argument("file", nargs="?", help="Python 文件路径")
    check_parser.add_argument("-c", "--code", help="内联 Python 代码")
    check_parser.add_argument("--json", action="store_true", help="JSON 格式输出")

    # ── cache 命令 ────────────────────────────────────
    cache_parser = subparsers.add_parser("cache", help="缓存管理")
    cache_sub = cache_parser.add_subparsers(dest="cache_cmd")
    cache_sub.add_parser("list", help="列出缓存的包")
    cache_sub.add_parser("clear", help="清除所有缓存")
    cache_sub.add_parser("info", help="缓存统计信息")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    config = DepotConfig(
        data_dir=Path("./depot-data"),
        execution_timeout=args.timeout if hasattr(args, "timeout") else 30,
        allow_network=not getattr(args, "offline", False),
        preferred_pm=getattr(args, "pm", "") or "",
        pypi_mirror=getattr(args, "mirror", None),
    )
    pipeline = DepotPipeline(config)

    if args.command == "run":
        _cmd_run(args, pipeline, config)
    elif args.command == "check":
        _cmd_check(args, pipeline)
    elif args.command == "cache":
        _cmd_cache(args, config)


def _get_code(args) -> str:
    """从参数中提取代码。"""
    if args.code:
        return args.code
    if args.file:
        return Path(args.file).read_text()
    # 从 stdin 读取
    return sys.stdin.read()


def _cmd_run(args, pipeline: DepotPipeline, config: DepotConfig) -> None:
    code = _get_code(args)
    if not code.strip():
        print("错误: 未提供代码。使用 -c 或指定文件路径。", file=sys.stderr)
        sys.exit(1)

    auto_install = not getattr(args, "no_install", False)
    report = pipeline.run_safe(code, auto_install=auto_install)

    if getattr(args, "json", False):
        print(pipeline.report_to_json(report))
    else:
        print(pipeline.report_to_markdown(report))

    sys.exit(0 if report.status.value == "success" else 1)


def _cmd_check(args, pipeline: DepotPipeline) -> None:
    code = _get_code(args)
    if not code.strip():
        print("错误: 未提供代码。", file=sys.stderr)
        sys.exit(1)

    result = pipeline.check(code)

    if getattr(args, "json", False):
        import json
        from dataclasses import asdict
        data = {
            "total_deps": len(result.dependencies),
            "stdlib": [d.name for d in result.standard_library],
            "third_party": [d.name for d in result.third_party],
            "local": [d.name for d in result.local_imports],
            "conditional": [d.name for d in result.conditional_imports],
            "dynamic": [d.name for d in result.dynamic_imports],
            "needs_install": result.package_names,
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print("\n=== Depot 依赖检查 ===")
        print(f"共检测到 {len(result.dependencies)} 个导入")
        if result.standard_library:
            print(f"  标准库: {', '.join(d.name for d in result.standard_library)}")
        if result.third_party:
            print(f"  第三方: {', '.join(d.name for d in result.third_party)}")
        if result.conditional_imports:
            print(f"  条件导入: {', '.join(d.name for d in result.conditional_imports)}")
        if result.dynamic_imports:
            print(f"  动态导入: {', '.join(d.name for d in result.dynamic_imports)}")
        if result.local_imports:
            print(f"  本地模块: {', '.join(d.name for d in result.local_imports)}")
        if result.package_names:
            print(f"\n需要安装: {', '.join(result.package_names)}")
        else:
            print("\n无需安装任何外部依赖")
        if result.errors:
            print(f"\n错误: {', '.join(result.errors)}")


def _cmd_cache(args, config: DepotConfig) -> None:
    cache = CacheManager(config)

    if args.cache_cmd == "list":
        pkgs = cache.list_all()
        if pkgs:
            print(f"缓存的包 ({len(pkgs)}):")
            for name, ver in sorted(pkgs.items()):
                print(f"  {name} == {ver}")
        else:
            print("缓存为空")

    elif args.cache_cmd == "clear":
        cache.clear()
        print("缓存已清除")

    elif args.cache_cmd == "info":
        info = cache.get_info()
        print(f"锁文件: {info.lock_file_path}")
        print(f"缓存包数: {info.packages_count}")
        if info.last_updated:
            from datetime import datetime
            ts = datetime.fromtimestamp(info.last_updated)
            print(f"最后更新: {ts.strftime('%Y-%m-%d %H:%M:%S')}")

    else:
        print("用法: depot cache [list|clear|info]")


if __name__ == "__main__":
    main()
