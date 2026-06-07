#!/usr/bin/env python3
"""
Depot 实验执行脚本。

运行所有 Baseline（B1 裸执行、B2 预装全家桶、B3 Depot）对所有 15 个 Benchmark 任务，
收集数据并生成对比报告。
"""

import json
import sys
import time
from pathlib import Path

# 项目路径
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from depot.config import DepotConfig
from depot.pipeline import DepotPipeline
from depot.feedback import RunStatus

from baselines.b1_bare import BareExecutionBaseline
from baselines.b2_preinstalled import PreInstalledBaseline
from tasks.tasks import registry as task_registry


def run_experiment(
    output_dir: str = "./experiment-results",
    run_b2_setup: bool = False,
    timeout: int = 30,
) -> None:
    """运行完整实验。

    Args:
        output_dir: 结果输出目录
        run_b2_setup: 是否运行 B2 环境准备（首次需 10-20 分钟）
        timeout: 每个任务的超时（秒）
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 初始化 Baselines ──────────────────────────────────
    results = []

    # Depot (B3)
    depot_config = DepotConfig(
        data_dir=out_dir / "depot-data",
        execution_timeout=timeout,
        cache_enabled=True,
        allow_network=True,
    )
    depot = DepotPipeline(depot_config)

    # B1: 裸执行
    b1 = BareExecutionBaseline(timeout=timeout)

    # B2: 预装全家桶（可选 —— 首次需安装 50+ 包）
    b2 = PreInstalledBaseline(timeout=timeout, data_dir=str(out_dir / "b2-data"))
    if run_b2_setup:
        print("[EXPERIMENT] 初始化 B2 预装全家桶 ...")
        b2.setup()

    baselines = [
        ("B1-裸执行", b1),
        ("B2-预装全家桶", b2),
        ("Depot", depot),
    ]

    tasks = task_registry.all()
    tasks.sort(key=lambda t: (t.difficulty, t.id))

    print(f"[EXPERIMENT] {len(tasks)} 个任务, {len(baselines)} 个 Baseline")
    print(f"[EXPERIMENT] 输出目录: {out_dir}")
    print("=" * 60)

    for task in tasks:
        print(f"\n{'='*60}")
        print(f"  [{task.id}] L{task.difficulty} | {task.prompt[:80]}...")
        print(f"  Expected deps: {task.expected_deps}")
        print(f"{'='*60}")

        for baseline_name, baseline in baselines:
            print(f"  -> {baseline_name} ...", end=" ", flush=True)

            try:
                t0 = time.time()

                if baseline_name == "Depot":
                    report = depot.run(task.code)

                    result_entry = {
                        "task_id": task.id,
                        "baseline": baseline_name,
                        "difficulty": task.difficulty,
                        "status": report.status.value,
                        "exit_code": report.execution_summary.get("exit_code", -1),
                        "success": report.execution_summary.get("success", False),
                        "execution_time_ms": report.execution_summary.get("execution_time_ms", 0),
                        "install_time_ms": report.install_summary.get("total_time_ms", 0),
                        "total_time_ms": next(
                            (t["total_duration_ms"] for t in report.timeline if "total_duration_ms" in t), 0
                        ),
                        "deps_detected": len(report.dependency_summary.get("third_party", [])),
                        "deps_installed": len(report.install_summary.get("installed", [])),
                        "deps_skipped": len(report.install_summary.get("skipped", [])),
                        "summary": report.summary,
                        "errors": report.execution_summary.get("stderr_preview", "")[:200],
                    }
                else:
                    result = baseline.run(task.code)

                    result_entry = {
                        "task_id": task.id,
                        "baseline": baseline_name,
                        "difficulty": task.difficulty,
                        "status": result.status,
                        "exit_code": result.exit_code,
                        "success": result.status == "success",
                        "execution_time_ms": result.execution_time_ms,
                        "install_time_ms": 0,
                        "total_time_ms": result.total_time_ms,
                        "deps_detected": 0,
                        "deps_installed": 0,
                        "deps_skipped": 0,
                        "summary": result.summary,
                        "errors": result.stderr[:200],
                    }

                results.append(result_entry)
                status_icon = "✓" if result_entry["success"] else "✗"
                total_ms = result_entry["total_time_ms"]
                print(f"{status_icon} ({total_ms}ms)")

            except Exception as e:
                results.append({
                    "task_id": task.id,
                    "baseline": baseline_name,
                    "difficulty": task.difficulty,
                    "status": "error",
                    "success": False,
                    "error": str(e),
                })
                print(f"✗ ERROR: {e}")

    # ── 生成报告 ──────────────────────────────────────────
    _generate_report(results, out_dir)
    print(f"\n[EXPERIMENT] 完成。报告已保存到 {out_dir}")


def _generate_report(results: list[dict], out_dir: Path) -> None:
    """生成实验报告（JSON + Markdown）。"""

    # JSON
    json_path = out_dir / "results.json"
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    # Markdown
    md_lines = [
        "# Depot Benchmark 实验结果",
        "",
        f"**实验时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**任务数**: {len(set(r['task_id'] for r in results))}",
        f"**Baseline数**: {len(set(r['baseline'] for r in results))}",
        "",
        "## 总览",
        "",
    ]

    # 按 baseline 汇总
    baselines = sorted(set(r["baseline"] for r in results))
    md_lines.append("| Baseline | 成功率 | 平均耗时 |")
    md_lines.append("|----------|--------|---------|")

    for bl in baselines:
        bl_results = [r for r in results if r["baseline"] == bl]
        success_count = sum(1 for r in bl_results if r.get("success"))
        total = len(bl_results)
        success_rate = f"{success_count}/{total} ({success_count/total*100:.0f}%)"
        avg_time = int(sum(r.get("total_time_ms", 0) for r in bl_results) / total) if total > 0 else 0
        md_lines.append(f"| {bl} | {success_rate} | {avg_time}ms |")

    # 按难度细分
    for difficulty in [1, 2, 3]:
        md_lines.extend(["", f"## L{difficulty} 任务", ""])
        md_lines.append("| Task | Baseline | 状态 | 耗时 | 摘要 |")
        md_lines.append("|------|----------|------|------|------|")

        diff_results = [r for r in results if r.get("difficulty") == difficulty]
        diff_results.sort(key=lambda r: (r["task_id"], r["baseline"]))

        for r in diff_results:
            status_icon = "✓" if r.get("success") else "✗"
            total_ms = r.get("total_time_ms", "N/A")
            summary = r.get("summary", "")[:80]
            md_lines.append(
                f"| {r['task_id']} | {r['baseline']} | {status_icon} | {total_ms}ms | {summary} |"
            )

    md_path = out_dir / "report.md"
    md_path.write_text("\n".join(md_lines))
    print(f"[REPORT] JSON: {json_path}")
    print(f"[REPORT] Markdown: {md_path}")


# ── CLI 入口 ────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Depot Benchmark 实验")
    parser.add_argument(
        "--output-dir", default="./experiment-results",
        help="输出目录（默认: ./experiment-results）",
    )
    parser.add_argument(
        "--timeout", type=int, default=30,
        help="每任务超时秒数（默认: 30）",
    )
    parser.add_argument(
        "--b2-setup", action="store_true",
        help="运行 B2 环境准备（首次需 10-20 分钟）",
    )
    parser.add_argument(
        "--tasks", nargs="*", default=None,
        help="指定要运行的任务 ID（如 --tasks T1 T2 T6）",
    )
    parser.add_argument(
        "--difficulty", type=int, nargs="*", default=None,
        help="指定难度级别（如 --difficulty 1 2）",
    )
    parser.add_argument(
        "--baselines", nargs="*", default=None,
        help="指定要运行的 baseline（如 --baselines B1 Depot）",
    )

    args = parser.parse_args()

    run_experiment(
        output_dir=args.output_dir,
        run_b2_setup=args.b2_setup,
        timeout=args.timeout,
    )
