"""M0 离线解析等价：对固定 fixture 断言确定性 golden 值。

fixture 取自 optaplanner-jxjy 的真实 JaCoCo / surefire 报告（快照），
golden 值由报告内容直接导出，用于锁定解析逻辑与 bash 一致、防回归。
"""
from pathlib import Path

import pytest

from jacov.jacoco import parse_csv_summary, parse_surefire, parse_uncovered_branches
from jacov.model import convert_to_coverage_ratio

FIXTURES = Path(__file__).parent / "fixtures"
CSV = str(FIXTURES / "jacoco.csv")
XML = str(FIXTURES / "jacoco.xml")
SRCROOT = str(FIXTURES / "srcroot")
SUREFIRE = str(FIXTURES / "TEST-TimeTableServiceTest_unit.xml")

# golden 类：jacoco.csv 中 BRANCH_MISSED=18, BRANCH_COVERED=4（部分覆盖，ratio 非 0 非 1）
GOLDEN_CLASS = "TeacherDayOfWeekParseStrategy"


def test_csv_summary_for_named_class():
    [summary] = parse_csv_summary(CSV, [GOLDEN_CLASS])
    assert summary.name == GOLDEN_CLASS
    assert summary.branch_missed == 18
    assert summary.branch_covered == 4
    assert summary.total == 22
    assert summary.ratio == pytest.approx(4 / 22)


def test_csv_summary_all_aggregates_every_row():
    [summary] = parse_csv_summary(CSV)
    assert summary.name == "ALL"
    assert summary.total == summary.branch_missed + summary.branch_covered
    assert summary.branch_missed > 0


def test_csv_summary_unknown_class_raises():
    with pytest.raises(ValueError):
        parse_csv_summary(CSV, ["NoSuchClass"])


def test_csv_summary_unknown_class_lenient_returns_zero():
    # strict=False：未找到的类记 total=0 条目而非报错（按包自动收集场景）
    [summary] = parse_csv_summary(CSV, ["NoSuchClass"], strict=False)
    assert summary.name == "NoSuchClass"
    assert summary.total == 0
    assert summary.branch_covered == 0


def test_uncovered_branches_named_class():
    lines = parse_uncovered_branches(XML, SRCROOT, [GOLDEN_CLASS])
    assert lines, "应解析出未覆盖分支行"
    assert all(line.class_name == GOLDEN_CLASS for line in lines)

    by_nr = {line.line_number: line for line in lines}
    # 取自 jacoco.xml 快照：nr=29 mb=2 cb=0 → MISS，且源码行文本应被读到
    assert 29 in by_nr
    assert by_nr[29].missed_branches == 2
    assert by_nr[29].covered_branches == 0
    assert by_nr[29].status == "MISS"
    assert by_nr[29].code


def test_surefire_pass():
    suite = parse_surefire(SUREFIRE)
    assert suite.name == "fanya.services.TimeTableServiceTest_unit"
    assert suite.failures == 0
    assert suite.errors == 0
    assert suite.tests == 84
    assert suite.skipped == 0
    assert suite.result == "PASS"


@pytest.mark.parametrize(
    "value,expected",
    [(80, 0.8), (0.8, 0.8), ("80", 0.8), (0, 0.0), (100, 1.0)],
)
def test_convert_ratio(value, expected):
    assert convert_to_coverage_ratio(value) == pytest.approx(expected)


def test_convert_ratio_negative_raises():
    with pytest.raises(ValueError):
        convert_to_coverage_ratio(-1)
