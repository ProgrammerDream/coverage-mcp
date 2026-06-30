"""M2 组装层离线测试：build_result 把解析结果汇成结构化 dict，并正确判定 status。

不跑 maven，直接用构造的解析对象，锁定给 agent 的 JSON 结构与判定逻辑。
"""
from jacov.check import _build_test_summary, build_result
from jacov.model import CoverageSummary, SuiteResult, UncoveredLine


def test_pass_when_tests_green_and_coverage_meets_threshold():
    suites = [SuiteResult("fanya.x.FooTest", 0, 0)]
    summaries = [CoverageSummary("Foo", 2, 8)]  # total 10, ratio 0.8
    result = build_result("mod", ["FooTest"], suites, summaries, [], 0.8, True,
                          {"csv": "c", "xml": "x", "html": "h"})
    assert result["status"] == "PASS"
    assert result["tests"] == {"total": 1, "passed": 1, "failed": []}
    assert result["coverage"][0]["pass"] is True
    assert result["coverage"][0]["ratio"] == 0.8
    assert result["uncovered"] == []
    assert result["reports"]["csv"] == "c"


def test_fail_when_coverage_below_threshold_and_lists_uncovered():
    suites = [SuiteResult("FooTest", 0, 0)]
    summaries = [CoverageSummary("Foo", 16, 8)]  # ratio 8/24 ≈ 0.333
    uncovered = [UncoveredLine("Foo", "Foo.java", 35, 2, 0, "MISS", "for (...)")]
    result = build_result("mod", ["FooTest"], suites, summaries, uncovered, 0.8, True, {})
    assert result["status"] == "FAIL"
    assert result["coverage"][0]["pass"] is False
    assert result["uncovered"][0]["line"] == 35
    assert result["uncovered"][0]["kind"] == "MISS"
    assert result["uncovered"][0]["code"] == "for (...)"


def test_fail_when_test_suite_has_failures():
    suites = [SuiteResult("FooTest", 1, 0)]  # failures=1
    summaries = [CoverageSummary("Foo", 0, 10)]  # 100% 覆盖但测试失败
    result = build_result("mod", ["FooTest"], suites, summaries, [], 0, True, {})
    assert result["status"] == "FAIL"
    assert "FooTest" in result["tests"]["failed"]
    assert result["tests"]["passed"] == 0


def test_build_test_summary_aggregates_all_suites():
    # Jenkins 式全量汇总：跨套件求和 tests/failures/skipped，任一套件失败则整体 FAIL
    suites = [
        SuiteResult("fanya.ATest", 0, 0, tests=5, skipped=0),
        SuiteResult("fanya.BTest", 1, 0, tests=3, skipped=1),
    ]
    summary = _build_test_summary("mod", suites)
    assert summary["suites"] == 2
    assert summary["tests"] == 8
    assert summary["failures"] == 1
    assert summary["passed"] == 6  # 8 - 1失败 - 0错误 - 1跳过
    assert summary["status"] == "FAIL"
    assert "fanya.BTest" in summary["failed_suites"]


def test_coverage_summary_ratio_zero_when_no_branches():
    # total==0 时 ratio 定义为 0（覆盖 model.CoverageSummary.ratio 的零分支分支）
    summary = CoverageSummary("X", 0, 0)
    assert summary.total == 0
    assert summary.ratio == 0.0
