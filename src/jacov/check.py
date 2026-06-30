"""端到端编排 + 人读输出。

check_coverage() 是 CLI 与 MCP 共用的高层入口：跑覆盖率 → 解析 → 组装结构化 dict。
给 package（业务包）则自动收集测试类/业务类；否则用手列 tests/cover。
build_result() 是纯组装函数（无 IO），便于离线单测。
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

from . import collect, jacoco, runner
from .model import convert_to_coverage_ratio


def check_coverage(module_dir, tests="", cover="", min_branch=0,
                   compile_first=True, reuse_forks=True, package=""):
    """高层入口：跑覆盖率并返回结构化结果 dict。CLI 与 MCP 共用。

    给 package（业务包，如 fanya/schedule）则自动收集测试类/业务类（宽容模式）；
    否则用手列的 tests/cover（严格模式）。
    """
    abs_module = os.path.abspath(module_dir)
    min_ratio = convert_to_coverage_ratio(min_branch)
    test_classes, cover_classes, strict = _resolve_targets(abs_module, tests, cover, package)
    return run_and_collect(abs_module, test_classes, cover_classes, min_ratio,
                           compile_first, reuse_forks, strict)


def _resolve_targets(module_dir, tests, cover, package):
    """有 package 则自动收集（宽容模式）；否则用手列 tests/cover（严格模式）。"""
    if package:
        test_classes, cover_classes = collect.collect_package(module_dir, package)
        if not test_classes:
            pkg_path = package.replace(".", "/")
            raise ValueError(f"业务包 {package} 下没找到测试类（src/test/java/{pkg_path} 无 *Test.java）")
        return test_classes, cover_classes, False
    if not tests:
        raise ValueError("需指定 tests 或 package")
    return _split(tests), _split(cover), True


def run_and_collect(module_dir, test_classes, cover_classes, min_ratio,
                    compile_first=True, reuse_forks=True, strict=True):
    """跑 maven 覆盖率 → 解析 csv/xml/surefire → 组装结构化结果。"""
    run = runner.run_coverage(module_dir, test_classes, compile_first, reuse_forks)
    summaries = jacoco.parse_csv_summary(run["csv"], cover_classes or None, strict)
    uncovered = jacoco.parse_uncovered_branches(run["xml"], module_dir, cover_classes or None)
    suites = _parse_all_surefire(module_dir)
    reports = {
        "csv": run["csv"],
        "xml": run["xml"],
        "html": os.path.join(os.path.dirname(run["csv"]), "index.html"),
    }
    return build_result(module_dir, test_classes, suites, summaries,
                        uncovered, min_ratio, run["test_ok"], reports)


def build_result(module_dir, test_classes, suites, summaries, uncovered, min_ratio, test_ok, reports):
    """纯组装：把解析结果汇成给 agent 的结构化 dict，并判定整体 status。

    uncovered 的 file 相对 module_dir（省 token），顶层 module_dir 给绝对路径供拼接。
    """
    failed = _failed_tests(test_classes, suites, test_ok)
    coverage = [_coverage_entry(summary, min_ratio) for summary in summaries]
    status = "PASS"
    if failed or any(not entry["pass"] for entry in coverage):
        status = "FAIL"
    return {
        "status": status,
        "module": os.path.basename(module_dir),
        "module_dir": module_dir,
        "min_branch": min_ratio,
        "tests": {"total": len(test_classes), "passed": len(test_classes) - len(failed), "failed": failed},
        "coverage": coverage,
        "uncovered": [_uncovered_entry(line, module_dir) for line in uncovered],
        "reports": reports,
    }


def run_tests(module_dir, tests="", package="", compile_first=True, reuse_forks=True):
    """跑测试（不覆盖率，Jenkins 式）。tests/package 都空 = 全量（模块下所有 *Test.java）。返回汇总 dict。"""
    abs_module = os.path.abspath(module_dir)
    test_classes = _resolve_test_classes(abs_module, tests, package)
    runner.run_tests(abs_module, test_classes, compile_first, reuse_forks)
    suites = _parse_all_surefire(abs_module)
    return _build_test_summary(abs_module, suites)


def _resolve_test_classes(module_dir, tests, package):
    """package → 收集该包测试类；tests → 拆分；都空 → []（全量）。"""
    if package:
        test_classes, _cover = collect.collect_package(module_dir, package)
        return test_classes
    return _split(tests)


def _build_test_summary(module_dir, suites):
    """把所有 surefire 套件汇成 Jenkins 式结果 dict。"""
    tests = sum(suite.tests for suite in suites)
    failures = sum(suite.failures for suite in suites)
    errors = sum(suite.errors for suite in suites)
    skipped = sum(suite.skipped for suite in suites)
    failed_suites = [suite.name for suite in suites if suite.result == "FAIL"]
    status = "PASS"
    if failed_suites:
        status = "FAIL"
    return {
        "status": status,
        "module": os.path.basename(module_dir),
        "suites": len(suites),
        "tests": tests,
        "passed": tests - failures - errors - skipped,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "failed_suites": failed_suites,
    }


def main(argv=None):
    args = _parse_args(argv)
    result = check_coverage(args.module_dir, args.tests, args.cover, args.min_branch,
                            compile_first=not args.no_compile, reuse_forks=not args.no_reuse,
                            package=args.package)
    _print_human(result)
    if result["status"] == "FAIL":
        return 1
    return 0


def _parse_args(argv):
    parser = argparse.ArgumentParser(prog="jacov.check")
    parser.add_argument("--module-dir", required=True, help="模块目录（含 pom.xml）")
    parser.add_argument("--tests", default="", help="测试类，逗号分隔（与 --package 二选一）")
    parser.add_argument("--cover", default="", help="卡覆盖率的业务类，逗号分隔；空=ALL 汇总")
    parser.add_argument("--package", default="", help="业务包（如 fanya/schedule），自动收集测试类+业务类")
    parser.add_argument("--min-branch", default="0", help="最小分支覆盖率，支持 80 或 0.8")
    parser.add_argument("--no-compile", action="store_true",
                        help="跳过编译用 surefire:test（代码已编译时更快）")
    parser.add_argument("--no-reuse", action="store_true",
                        help="每个测试类用独立 JVM（严格隔离，但多测试类时慢）")
    return parser.parse_args(argv)


def _split(value):
    """逗号分隔 → 去空白去空项，并剥掉可能的 .java 后缀。"""
    items = []
    for part in value.split(","):
        name = part.strip()
        if not name:
            continue
        if name.lower().endswith(".java"):
            name = name[:-5]
        items.append(name)
    return items


def _parse_all_surefire(module_dir):
    pattern = os.path.join(module_dir, "target", "surefire-reports", "TEST-*.xml")
    return [jacoco.parse_surefire(path) for path in sorted(glob.glob(pattern))]


def _failed_tests(test_classes, suites, run_ok):
    """逐个测试类判定，收集失败者。"""
    failed = []
    for test_class in test_classes:
        matched = [s for s in suites if s.name == test_class or s.name.endswith("." + test_class)]
        if _verdict(matched, run_ok) == "FAIL":
            failed.append(test_class)
    return failed


def _verdict(matched, run_ok):
    """单个测试类判定：有报告按报告（全 PASS 才 PASS）；无报告时以整体跑通兜底（对齐 bash RUN_OK）。"""
    if matched and all(suite.result == "PASS" for suite in matched):
        return "PASS"
    if matched:
        return "FAIL"
    if run_ok:
        return "PASS"
    return "FAIL"


def _coverage_entry(summary, min_ratio):
    # 达标：该类存在分支且覆盖率不低于阈值
    passed = summary.total > 0 and summary.ratio >= min_ratio
    return {
        "class": summary.name,
        "branch_total": summary.total,
        "branch_covered": summary.branch_covered,
        "branch_missed": summary.branch_missed,
        "ratio": round(summary.ratio, 4),
        "pass": passed,
    }


def _uncovered_entry(line, module_dir):
    return {
        "class": line.class_name,
        "file": _relativize(line.source_file, module_dir),
        "line": line.line_number,
        "kind": line.status,
        "missed": line.missed_branches,
        "covered": line.covered_branches,
        "code": line.code,
    }


def _relativize(path, base):
    """把绝对源码路径转成相对模块目录（省 token）；跨盘等失败时原样返回。"""
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return path


def _print_human(result):
    """把结构化结果渲染成对齐 run-module-test.sh 的人读汇总。"""
    tests = result["tests"]
    print("\n" + "=" * 44)
    print("测试结果汇总")
    print("=" * 44)
    print(f"总数: {tests['total']}, 通过: {tests['passed']}, 失败: {len(tests['failed'])}")
    for name in tests["failed"]:
        print(f"  [FAIL] {name}")

    print("\n" + "=" * 44)
    print("分支覆盖率汇总")
    print("=" * 44)
    for entry in result["coverage"]:
        tag = "PASS"
        if not entry["pass"]:
            tag = "FAIL"
        print(f"[{tag}] {entry['class']} 分支总数={entry['branch_total']}, 已覆盖={entry['branch_covered']}, "
              f"未覆盖={entry['branch_missed']}, 覆盖率={entry['ratio'] * 100:.2f}%")

    _print_uncovered(result["uncovered"])


def _print_uncovered(uncovered):
    if not uncovered:
        return
    print("-" * 44)
    print("未完全覆盖分支对应源码行")
    print("-" * 44)
    for line in uncovered:
        print(f"[{line['kind']}] {line['file']}:{line['line']} 未覆盖分支={line['missed']}, "
              f"已覆盖分支={line['covered']}, 代码={line['code']}")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
