"""MCP server：把覆盖率反馈暴露给 agent（FastMCP / stdio）。

定位：Java 分支级、按测试类、能指到未覆盖分支行的 agent 覆盖率反馈器。
启动：python -m jacov.server
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import check

mcp = FastMCP("jacov")


@mcp.tool()
def coverage_check(module_dir: str, tests: str = "", cover: str = "", min_branch: float = 0,
                   compile_first: bool = True, reuse_forks: bool = True, package: str = "") -> dict:
    """跑指定测试类并按类卡分支覆盖率，返回测试结果 / 覆盖率 / 未覆盖分支行。

    Args:
        module_dir: 模块目录（含 pom.xml）
        tests: 测试类，逗号分隔（可带或不带 .java）；给了 package 可留空
        cover: 卡覆盖率的业务类，逗号分隔；空=ALL 汇总
        min_branch: 最小分支覆盖率，支持 80 或 0.8
        compile_first: True=含增量编译，保证测最新代码（默认）；False=跳过编译，代码已编译时更快
        reuse_forks: True=多测试类复用同一 fork JVM（默认，快得多）；False=每类独立 JVM（严格隔离）
        package: 业务包（如 fanya/schedule）；给了就自动收集该包全部测试类+业务类，tests/cover 可留空
    """
    return check.check_coverage(module_dir, tests, cover, min_branch,
                                compile_first, reuse_forks, package)


def run():
    mcp.run()


if __name__ == "__main__":
    run()
