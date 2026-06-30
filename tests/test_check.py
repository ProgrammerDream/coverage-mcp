"""check 编排层离线测试：纯函数直测 + mock runner/collect/jacoco 覆盖编排与人读打印（不跑 maven）。"""
import os

import pytest

from jacov import check
from jacov.model import CoverageSummary, SuiteResult


# ── 纯函数 ──

def test_split_strips_blanks_and_java_suffix():
    assert check._split("A.java, B , ,C.JAVA") == ["A", "B", "C"]
    assert check._split("") == []


def test_verdict_all_branches():
    assert check._verdict([SuiteResult("FooTest", 0, 0)], True) == "PASS"   # 有报告且全通过
    assert check._verdict([SuiteResult("FooTest", 1, 0)], True) == "FAIL"   # 有报告但失败
    assert check._verdict([], True) == "PASS"                                # 无报告 + 整体跑通兜底
    assert check._verdict([], False) == "FAIL"                               # 无报告 + 整体失败


def test_relativize_same_drive(tmp_path):
    target = tmp_path / "src" / "Foo.java"
    assert check._relativize(str(target), str(tmp_path)) == os.path.join("src", "Foo.java")


def test_relativize_cross_drive_returns_original(monkeypatch):
    def raise_value_error(path, base):
        raise ValueError("跨盘无法相对化")
    monkeypatch.setattr(check.os.path, "relpath", raise_value_error)
    assert check._relativize("X:/a/Foo.java", "C:/b") == "X:/a/Foo.java"


# ── 目标解析 ──

def test_resolve_targets_tests_mode():
    tests, cover, strict = check._resolve_targets("/m", "A,B", "Foo", "")
    assert tests == ["A", "B"] and cover == ["Foo"] and strict is True


def test_resolve_targets_requires_tests_or_package():
    with pytest.raises(ValueError, match="需指定"):
        check._resolve_targets("/m", "", "", "")


def test_resolve_targets_package_mode(monkeypatch):
    monkeypatch.setattr(check.collect, "collect_package", lambda module, pkg: (["FooTest"], ["Foo"]))
    tests, cover, strict = check._resolve_targets("/m", "", "", "fanya.x")
    assert tests == ["FooTest"] and cover == ["Foo"] and strict is False


def test_resolve_targets_package_empty_raises(monkeypatch):
    monkeypatch.setattr(check.collect, "collect_package", lambda module, pkg: ([], []))
    with pytest.raises(ValueError, match="没找到测试类"):
        check._resolve_targets("/m", "", "", "fanya.x")


def test_resolve_test_classes_modes(monkeypatch):
    monkeypatch.setattr(check.collect, "collect_package", lambda module, pkg: (["FooTest"], []))
    assert check._resolve_test_classes("/m", "", "fanya.x") == ["FooTest"]
    assert check._resolve_test_classes("/m", "A,B", "") == ["A", "B"]


# ── 编排：mock 掉真实 maven 与解析 ──

def test_run_and_collect_assembles_result(monkeypatch):
    monkeypatch.setattr(check.runner, "run_coverage",
                        lambda *a, **k: {"csv": "c.csv", "xml": "x.xml", "test_ok": True})
    monkeypatch.setattr(check.jacoco, "parse_csv_summary", lambda *a, **k: [CoverageSummary("Foo", 0, 10)])
    monkeypatch.setattr(check.jacoco, "parse_uncovered_branches", lambda *a, **k: [])
    monkeypatch.setattr(check, "_parse_all_surefire", lambda module: [SuiteResult("FooTest", 0, 0)])
    result = check.run_and_collect("/m", ["FooTest"], ["Foo"], 0.8, strict=True)
    assert result["status"] == "PASS"
    assert result["reports"]["xml"] == "x.xml"
    assert result["reports"]["html"].endswith("index.html")


def test_check_coverage_end_to_end(monkeypatch):
    monkeypatch.setattr(check.runner, "run_coverage",
                        lambda *a, **k: {"csv": "c", "xml": "x", "test_ok": True})
    monkeypatch.setattr(check.jacoco, "parse_csv_summary", lambda *a, **k: [CoverageSummary("Foo", 0, 10)])
    monkeypatch.setattr(check.jacoco, "parse_uncovered_branches", lambda *a, **k: [])
    monkeypatch.setattr(check, "_parse_all_surefire", lambda module: [])
    result = check.check_coverage("/m", tests="FooTest", cover="Foo", min_branch=80)
    assert result["status"] == "PASS"


def test_run_tests_summarizes(monkeypatch):
    monkeypatch.setattr(check.runner, "run_tests", lambda *a, **k: {"test_ok": True})
    monkeypatch.setattr(check, "_parse_all_surefire",
                        lambda module: [SuiteResult("FooTest", 0, 0, tests=3)])
    out = check.run_tests("/m", tests="FooTest")
    assert out["status"] == "PASS" and out["tests"] == 3


def test_parse_all_surefire_empty(monkeypatch):
    monkeypatch.setattr(check.glob, "glob", lambda pattern: [])
    assert check._parse_all_surefire("/m") == []


# ── main + 人读打印 ──

def test_main_pass_prints_summary(monkeypatch, capsys):
    monkeypatch.setattr(check, "check_coverage", lambda *a, **k: {
        "status": "PASS", "module": "m",
        "tests": {"total": 1, "passed": 1, "failed": []},
        "coverage": [{"class": "Foo", "branch_total": 10, "branch_covered": 10,
                      "branch_missed": 0, "ratio": 1.0, "pass": True}],
        "uncovered": []})
    assert check.main(["--module-dir", "/m", "--tests", "FooTest"]) == 0
    out = capsys.readouterr().out
    assert "测试结果汇总" in out and "分支覆盖率汇总" in out


def test_main_fail_prints_failures_and_uncovered(monkeypatch, capsys):
    monkeypatch.setattr(check, "check_coverage", lambda *a, **k: {
        "status": "FAIL", "module": "m",
        "tests": {"total": 1, "passed": 0, "failed": ["FooTest"]},
        "coverage": [{"class": "Foo", "branch_total": 10, "branch_covered": 4,
                      "branch_missed": 6, "ratio": 0.4, "pass": False}],
        "uncovered": [{"class": "Foo", "file": "Foo.java", "line": 5, "kind": "MISS",
                       "missed": 2, "covered": 0, "code": "if (x)"}]})
    assert check.main(["--module-dir", "/m", "--tests", "FooTest"]) == 1
    out = capsys.readouterr().out
    assert "[FAIL] FooTest" in out
    assert "未完全覆盖分支" in out
    assert "Foo.java:5" in out
