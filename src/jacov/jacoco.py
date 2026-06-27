"""JaCoCo / surefire 报告解析。

逐行对齐 tool/run-module-test.sh 内嵌的三段 Python：
  - collect_coverage_summary       → parse_csv_summary
  - collect_uncovered_branch_lines → parse_uncovered_branches
  - surefire TEST-*.xml 解析        → parse_surefire
把这套已验证的解析逻辑从 bash heredoc 抽成可单测、浅嵌套的纯函数：
判断逻辑下沉到单一职责的小函数，主流程只剩一层循环 + 卫语句。
"""
from __future__ import annotations

import csv
import os
import xml.etree.ElementTree as ET

from .model import CoverageSummary, SuiteResult, UncoveredLine


def parse_csv_summary(csv_path, coverage_classes=None, strict=True):
    """解析 jacoco.csv，按类汇总分支覆盖率；不指定类时汇总为单条 ALL。

    strict=False 时，报告里没有的类（未被任何测试加载）记为 total=0 条目而非报错，
    供「按包自动收集」场景容忍孤儿业务类。
    """
    with open(csv_path, encoding="utf-8") as fp:
        rows = list(csv.DictReader(fp))
    if not rows:
        raise ValueError(f"JaCoCo 覆盖率报告为空: {csv_path}")
    if not coverage_classes:
        return [_summarize("ALL", rows)]

    summaries = []
    for coverage_class in coverage_classes:
        # CSV 的 CLASS 列是简单类名，精确匹配（对齐 bash 的 row['CLASS'] == coverage_class）
        matched = [row for row in rows if row["CLASS"] == coverage_class]
        if matched:
            summaries.append(_summarize(coverage_class, matched))
            continue
        if not strict:
            summaries.append(CoverageSummary(coverage_class, 0, 0))
            continue
        raise ValueError(f"jacoco.csv 中未找到业务类覆盖率记录: {coverage_class}")
    return summaries


def parse_uncovered_branches(xml_path, source_root, coverage_classes=None):
    """解析 jacoco.xml，列出未完全覆盖的分支所在源码行（MISS/PARTIAL）。

    source_root 为模块根目录，源码按 <source_root>/src/main/java/<package>/<file> 定位。
    """
    root = ET.parse(xml_path).getroot()
    packages = root.findall("package")
    if not packages:
        raise ValueError(f"JaCoCo XML 报告未包含 package 节点: {xml_path}")

    wanted = set(coverage_classes) if coverage_classes else set()
    results = []
    for target_class in _collect_target_classes(packages, wanted):
        results.extend(_uncovered_lines_for_class(packages, target_class, source_root))
    return results


def parse_surefire(report_path):
    """解析单个 surefire TEST-*.xml，取套件名与 tests/failures/errors/skipped 计数。"""
    root = ET.parse(report_path).getroot()
    name = root.get("name", "")
    failures = int(root.get("failures", "0"))
    errors = int(root.get("errors", "0"))
    tests = int(root.get("tests", "0"))
    skipped = int(root.get("skipped", "0"))
    return SuiteResult(name=name, failures=failures, errors=errors, tests=tests, skipped=skipped)


def _summarize(name, rows):
    """把若干 CSV 行汇总成一条分支覆盖率。"""
    missed = sum(int(row["BRANCH_MISSED"]) for row in rows)
    covered = sum(int(row["BRANCH_COVERED"]) for row in rows)
    return CoverageSummary(name=name, branch_missed=missed, branch_covered=covered)


def _collect_target_classes(packages, wanted):
    """收集目标类的简单名（去重保序）；过滤逻辑下沉到 _simple_name，循环体保持浅。"""
    collected = []
    for package in packages:
        for class_node in package.findall("class"):
            simple = _simple_name(class_node, wanted)
            if simple and simple not in collected:
                collected.append(simple)
    return collected


def _simple_name(class_node, wanted):
    """取类的简单名；匿名/内部类（名含 '$'）或不在 wanted 中则返回空串表示跳过。"""
    class_name = class_node.get("name", "")
    if not class_name or "$" in class_name:
        return ""
    simple = class_name.split("/")[-1]
    if wanted and simple not in wanted:
        return ""
    return simple


def _uncovered_lines_for_class(packages, target_class, source_root):
    """单个类的未覆盖分支行列表；各步前置校验失败即抛错（对齐 bash 的逐项 error）。"""
    package, class_node = _find_class_node(packages, target_class)
    if class_node is None or package is None:
        raise ValueError(f"jacoco.xml 中未找到业务类节点: {target_class}")

    source_file_name = class_node.get("sourcefilename", "")
    source_node = _find_sourcefile_node(package, source_file_name)
    if source_node is None:
        raise ValueError(f"jacoco.xml 中未找到源码文件节点: {source_file_name}")

    source_file_path = _resolve_source_path(source_root, package.get("name", ""), source_file_name)
    if not os.path.exists(source_file_path):
        raise ValueError(f"未找到覆盖率源码文件: {source_file_path}")
    source_lines = _read_source_lines(source_file_path)

    # 只保留存在未覆盖分支的行（mb>0），逐行转成模型
    branch_nodes = [node for node in source_node.findall("line") if int(node.get("mb", "0")) > 0]
    return [_to_uncovered_line(target_class, source_file_path, node, source_lines) for node in branch_nodes]


def _to_uncovered_line(class_name, source_file, line_node, source_lines):
    """把一个有未覆盖分支的 <line> 节点转成 UncoveredLine。"""
    line_number = int(line_node.get("nr", "0"))
    missed = int(line_node.get("mb", "0"))
    covered = int(line_node.get("cb", "0"))
    # 默认 PARTIAL（部分覆盖），分支全未覆盖时才是 MISS
    status = "PARTIAL"
    if covered == 0:
        status = "MISS"
    code = ""
    if 0 < line_number <= len(source_lines):
        code = source_lines[line_number - 1].strip()
    return UncoveredLine(
        class_name=class_name,
        source_file=source_file,
        line_number=line_number,
        missed_branches=missed,
        covered_branches=covered,
        status=status,
        code=code,
    )


def _find_class_node(packages, target_class):
    """按简单类名定位 (package, class)：name 全等或以 '/<simple>' 结尾。"""
    for package in packages:
        for class_node in package.findall("class"):
            class_name = class_node.get("name", "")
            if class_name == target_class or class_name.endswith("/" + target_class):
                return package, class_node
    return None, None


def _find_sourcefile_node(package, source_file_name):
    for node in package.findall("sourcefile"):
        if node.get("name") == source_file_name:
            return node
    return None


def _resolve_source_path(source_root, package_name, source_file_name):
    base = os.path.join(source_root, "src", "main", "java")
    # 空包名时源码直接位于源根下；否则按包名分层拼接
    if not package_name:
        return os.path.join(base, source_file_name)
    return os.path.join(base, *package_name.split("/"), source_file_name)


def _read_source_lines(path):
    with open(path, encoding="utf-8") as fp:
        return fp.read().splitlines()
