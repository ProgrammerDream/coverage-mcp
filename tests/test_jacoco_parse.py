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


import os                                              # noqa: E402  (追加块按需 import)
import xml.etree.ElementTree as ET                     # noqa: E402
from jacov import jacoco                                # noqa: E402
from jacov.jacoco import _find_class_node, _find_sourcefile_node, _resolve_source_path  # noqa: E402


def test_csv_summary_empty_raises(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="为空"):
        parse_csv_summary(str(empty))


def test_uncovered_branches_no_package_raises(tmp_path):
    no_pkg = tmp_path / "j.xml"
    no_pkg.write_text("<report></report>", encoding="utf-8")
    with pytest.raises(ValueError, match="package"):
        parse_uncovered_branches(str(no_pkg), str(tmp_path))


def test_find_class_node_not_found_returns_none():
    packages = [ET.fromstring('<package name="p"><class name="p/Foo" sourcefilename="Foo.java"/></package>')]
    assert _find_class_node(packages, "Bar") == (None, None)


def test_find_sourcefile_node_not_found_returns_none():
    package = ET.fromstring('<package name="p"><sourcefile name="Foo.java"/></package>')
    assert _find_sourcefile_node(package, "Bar.java") is None


def test_resolve_source_path_empty_and_nested_package():
    flat = _resolve_source_path("/root", "", "Foo.java")
    assert flat.endswith(os.path.join("src", "main", "java", "Foo.java"))
    nested = _resolve_source_path("/root", "fanya/x", "Foo.java")
    assert nested.endswith(os.path.join("fanya", "x", "Foo.java"))


def test_uncovered_lines_class_node_missing_raises():
    packages = [ET.fromstring('<package name="p"><class name="p/Foo" sourcefilename="Foo.java"/></package>')]
    with pytest.raises(ValueError, match="未找到业务类节点"):
        jacoco._uncovered_lines_for_class(packages, "NoSuch", "/root")


def test_uncovered_lines_sourcefile_node_missing_raises():
    packages = [ET.fromstring('<package name="p"><class name="p/Foo" sourcefilename="Foo.java"/></package>')]
    with pytest.raises(ValueError, match="源码文件节点"):
        jacoco._uncovered_lines_for_class(packages, "Foo", "/root")


def test_uncovered_lines_source_file_missing_raises(tmp_path):
    xml = ('<package name="p"><class name="p/Foo" sourcefilename="Foo.java"/>'
           '<sourcefile name="Foo.java"><line nr="1" mb="2" cb="0"/></sourcefile></package>')
    packages = [ET.fromstring(xml)]
    with pytest.raises(ValueError, match="未找到覆盖率源码文件"):
        jacoco._uncovered_lines_for_class(packages, "Foo", str(tmp_path))


def test_to_uncovered_line_out_of_range_and_partial():
    node = ET.fromstring('<line nr="999" mb="2" cb="1"/>')
    line = jacoco._to_uncovered_line("Foo", "/x/Foo.java", node, ["only one line"])
    assert line.code == ""          # 行号越界 → code 留空（覆盖 134->136 跳过分支）
    assert line.status == "PARTIAL"  # cb>0 → PARTIAL（非 MISS）
