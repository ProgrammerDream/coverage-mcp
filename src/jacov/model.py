"""覆盖率/测试结果的数据模型。

字段命名对齐 JaCoCo 报告语义（branch_missed / branch_covered 等），
便于与 tool/run-module-test.sh 的既有解析逐字段比对等价。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoverageSummary:
    """单个类（或 ALL 汇总）的分支覆盖率。"""

    name: str
    branch_missed: int
    branch_covered: int

    @property
    def total(self) -> int:
        return self.branch_missed + self.branch_covered

    @property
    def ratio(self) -> float:
        # total 为 0 时覆盖率定义为 0，对齐 bash collect_coverage_summary 的 `0 if total == 0`
        if self.total == 0:
            return 0.0
        return self.branch_covered / self.total


@dataclass(frozen=True)
class UncoveredLine:
    """一条未完全覆盖的分支所在的源码行。"""

    class_name: str
    source_file: str
    line_number: int
    missed_branches: int
    covered_branches: int
    status: str  # MISS（分支全未覆盖）/ PARTIAL（部分覆盖）
    code: str


@dataclass(frozen=True)
class SuiteResult:
    """单个 surefire 测试套件结果。"""

    name: str
    failures: int
    errors: int
    tests: int = 0
    skipped: int = 0

    @property
    def result(self) -> str:
        if self.failures + self.errors > 0:
            return "FAIL"
        return "PASS"


def convert_to_coverage_ratio(value: float | str) -> float:
    """把阈值统一成 0~1 的比率，兼容 `80` 与 `0.8` 两种写法。

    对齐 bash convert_to_coverage_ratio：>1 视作百分制除以 100，<0 报错。
    """
    number = float(value)
    if number < 0:
        raise ValueError(f"覆盖率阈值不能小于 0: {value}")
    if number > 1:
        return number / 100
    return number
