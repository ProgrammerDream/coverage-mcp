"""全量/指定 纯测试入口（不跑覆盖率，模拟 Jenkins 的 mvn test）。

用法：
  python -m jacov.runtests --module course-v2                      # 短名（相对优先，自动解析目录）
  python -m jacov.runtests --module-dir <dir>                      # 全量（所有 *Test.java）
  python -m jacov.runtests --module rpc-svc --package fanya/schedule
  python -m jacov.runtests --module-dir <dir> --tests FooTest,BarTest
"""
from __future__ import annotations

import argparse
import sys

from . import check, project_registry


def main(argv=None):
    args = _parse_args(argv)
    try:
        module_dir = _resolve_module_dir(args)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    result = check.run_tests(module_dir, args.tests, args.package,
                             compile_first=not args.no_compile, reuse_forks=not args.no_reuse)
    _print_summary(result)
    if result["status"] == "FAIL":
        return 1
    return 0


def _resolve_module_dir(args):
    """--module-dir 直给目录优先；否则用 --module 经注册表解析（短名/全名/路径，相对优先）。"""
    if args.module_dir:
        return args.module_dir
    if args.module:
        module_dir = project_registry.resolve_module_dir(args.workspace_root, args.module)
        if not module_dir:
            available = ", ".join(item["module"] for item in project_registry.available_modules(args.workspace_root))
            raise ValueError(f"无法解析模块: {args.module}\n可用模块: {available}")
        return module_dir
    raise ValueError("必须提供 --module-dir 或 --module")


def _parse_args(argv):
    parser = argparse.ArgumentParser(prog="jacov.runtests")
    parser.add_argument("--module-dir", default="", help="模块目录（含 pom.xml）；与 --module 二选一")
    parser.add_argument("--module", default="", help="模块短名/全名/目录路径（相对 workspace 亦可），自动解析目录")
    parser.add_argument("--workspace-root", default="", help="工作区根目录；配合 --module，空则自动推导")
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


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
