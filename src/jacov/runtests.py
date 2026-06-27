"""全量/指定 纯测试入口（不跑覆盖率，模拟 Jenkins 的 mvn test）。

用法：
  python -m jacov.runtests --module-dir <dir>                      # 全量（所有 *Test.java）
  python -m jacov.runtests --module-dir <dir> --package fanya/schedule
  python -m jacov.runtests --module-dir <dir> --tests FooTest,BarTest
"""
from __future__ import annotations

import argparse
import sys

from . import check


def main(argv=None):
    args = _parse_args(argv)
    result = check.run_tests(args.module_dir, args.tests, args.package,
                             compile_first=not args.no_compile, reuse_forks=not args.no_reuse)
    _print_summary(result)
    if result["status"] == "FAIL":
        return 1
    return 0


def _parse_args(argv):
    parser = argparse.ArgumentParser(prog="jacov.runtests")
    parser.add_argument("--module-dir", required=True, help="模块目录（含 pom.xml）")
    parser.add_argument("--tests", default="", help="测试类，逗号分隔；不填且不填 package = 全量")
    parser.add_argument("--package", default="", help="业务包（如 fanya/schedule），只测该包")
    parser.add_argument("--no-compile", action="store_true", help="跳过编译（代码已编译时更快）")
    parser.add_argument("--no-reuse", action="store_true", help="每个测试类独立 JVM（严格隔离，慢）")
    return parser.parse_args(argv)


def _print_summary(result):
    print("\n" + "=" * 44)
    print(f"测试结果汇总（{result['module']}）")
    print("=" * 44)
    print(f"套件: {result['suites']}, 用例: {result['tests']}, 通过: {result['passed']}, "
          f"失败: {result['failures']}, 错误: {result['errors']}, 跳过: {result['skipped']}")
    for name in result["failed_suites"]:
        print(f"  [FAIL] {name}")
    print(f"[{result['status']}]")


if __name__ == "__main__":
    sys.exit(main())
