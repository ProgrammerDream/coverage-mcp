"""Maven 执行：复刻 tool/maven-run.sh + run-module-test.sh 的覆盖率链路。

M1 阶段复用 tool/env.sh 提供的 Maven 环境（MVN_EXEC + MVN_OPTS：settings.xml /
本地仓 / idea.version 等），runner 只负责 goals 拼装、JaCoCo 注入、日志落盘与屏幕精简。
保持与 bash 同一条 Maven 命令，端到端数字才可逐字段比对。
各步骤拆成单一职责小函数，主流程扁平、卫语句。
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from datetime import datetime

# 与 tool/run-module-test.sh 保持一致
JACOCO_VERSION = "0.8.11"
JACOCO_EXCLUDES = (
    "com.alibaba.dubbo.common.bytecode.Wrapper*:"
    "com.alibaba.dubbo.common.bytecode.Proxy*:"
    "jdk.proxy*.*:com.sun.proxy.*"
)
# @formatter:off
# JDK17 fork 测试所需 add-opens（复刻 env.sh 的 ARG_LINE）。
# 由 runner 经命令行末尾追加，覆盖 MVN_OPTS 里那条 -DargLine。
# @formatter:on
ARG_LINE = (
    "--add-opens=java.base/java.lang=ALL-UNNAMED "
    "--add-opens=java.base/java.util=ALL-UNNAMED "
    "--add-opens=java.base/java.math=ALL-UNNAMED "
    "-Dfile.encoding=UTF-8"
)


def run_coverage(module_dir, test_classes, tool_dir, compile_first=True, reuse_forks=False):
    """跑覆盖率：单条 maven 命令完成 prepare-agent → 测试 → report（仅 1 次 JVM 启动）。

    compile_first=True 用 `test`（含增量编译，保证测最新代码）；
    False 用 `surefire:test`（跳过编译，仅当类已编译时更快）。
    reuse_forks=False 每个测试类 fork 独立 JVM（隔离强，对齐 bash）；
    True 复用同一 fork JVM（多测试类时快得多，但要求测试间无静态状态污染）。
    返回 dict：{csv, xml, exec, test_ok}。
    """
    target = os.path.join(module_dir, "target")
    exec_path = os.path.join(target, "jacoco.exec")
    site = os.path.join(target, "site", "jacoco")
    csv_path = os.path.join(site, "jacoco.csv")
    xml_path = os.path.join(site, "jacoco.xml")
    log_dir = os.path.join(target, "maven-logs")

    _clean_stale(target, (exec_path, csv_path, xml_path))
    test_arg = ",".join(test_classes)
    goals = _coverage_goals(test_arg, exec_path, compile_first, reuse_forks)
    # @formatter:off
    # 单条命令内 prepare-agent→测试→report 顺序执行，省去多次 JVM 冷启动；
    # -Dmaven.test.failure.ignore 让测试断言失败也继续生成报告。
    # rc!=0 仅由编译失败等致命错误触发；测试通过/失败以 surefire 报告为准。
    # @formatter:on
    rc = _invoke_maven(module_dir, goals, tool_dir, log_dir, f"跑覆盖率测试 {test_arg}")
    return {"csv": csv_path, "xml": xml_path, "exec": exec_path, "test_ok": rc == 0}


def _clean_stale(target, report_paths):
    """清旧产物，避免上一次结果污染解析。"""
    for path in report_paths:
        if os.path.exists(path):
            os.remove(path)
    reports = os.path.join(target, "surefire-reports")
    if os.path.isdir(reports):
        shutil.rmtree(reports)


def _coverage_goals(test_arg, exec_path, compile_first, reuse_forks):
    """单条 maven 命令的全部 goals：prepare-agent → 测试 → report。"""
    plugin = f"org.jacoco:jacoco-maven-plugin:{JACOCO_VERSION}"
    # 默认 test（含增量编译）；compile_first=False 时用 surefire:test 跳过编译
    test_goal = "test"
    if not compile_first:
        test_goal = "surefire:test"
    reuse = "false"
    if reuse_forks:
        reuse = "true"
    return [
        f"{plugin}:prepare-agent",
        "-Djacoco.propertyName=coverageAgentArgLine",
        f"-Djacoco.destFile={exec_path}",
        f"-Djacoco.excludes={JACOCO_EXCLUDES}",
        f"-DargLine=@{{coverageAgentArgLine}} {ARG_LINE}",
        f"-Dtest={test_arg}",
        "-DforkCount=1",
        f"-DreuseForks={reuse}",
        "-DfailIfNoTests=false",
        "-Dmaven.test.failure.ignore=true",
        test_goal,
        f"{plugin}:report",
        f"-Djacoco.dataFile={exec_path}",
    ]


def _invoke_maven(module_dir, goals, tool_dir, log_dir, step_label):
    """在 module_dir 下跑一组 maven goals；复用 env.sh 环境。

    实时逐行读取 maven 输出：关键行（编译/测试进度、ERROR、BUILD 结果）即时打屏（flush），
    全量写日志。这样长任务不再静默，用户能看到逐个测试类跑过。返回退出码。
    """
    os.makedirs(log_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = os.path.join(log_dir, f"{os.path.basename(module_dir)}-{stamp}.log")

    print(f"\n{step_label}", flush=True)
    proc = subprocess.Popen(
        ["bash", "-c", _build_bash_cmd(tool_dir, goals)], cwd=module_dir,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1,
    )
    with open(log_file, "w", encoding="utf-8", errors="replace") as fp:
        for line in proc.stdout:
            fp.write(line)
            if _is_key_line(line):
                print(line.rstrip(), flush=True)
    proc.wait()

    status = "PASS"
    if proc.returncode != 0:
        status = f"FAIL(exit {proc.returncode})"
    print(f"[STEP {status}] {step_label}  日志: {log_file}", flush=True)
    return proc.returncode


def _build_bash_cmd(tool_dir, goals):
    """source env.sh 拿到 MVN_EXEC/MVN_OPTS；goals 排在其后，故 runner 追加的同名 -D 覆盖默认值。"""
    env_sh = os.path.join(tool_dir, "env.sh")
    goals_str = " ".join(shlex.quote(goal) for goal in goals)
    return (
        f"source {shlex.quote(env_sh)} >/dev/null && "
        f'"${{MVN_EXEC}}" "${{MVN_OPTS[@]}}" --batch-mode --no-transfer-progress {goals_str} < /dev/null'
    )


def _is_key_line(line):
    line = line.rstrip()
    if line.startswith("[ERROR]"):
        return True
    if "BUILD SUCCESS" in line or "BUILD FAILURE" in line:
        return True
    # 编译阶段进度：让编译那几十秒也有迹象，不再静默
    if "] Building " in line or "] Compiling " in line:
        return True
    # 测试进度：surefire 的 Running/Tests run，让用户实时看到逐个测试类跑过
    if "] Running " in line or "Tests run:" in line:
        return True
    return False


def run_tests(module_dir, test_classes, tool_dir, compile_first=True, reuse_forks=True):
    """跑测试不带覆盖率（纯 surefire，比覆盖率快）。test_classes 为空 = 全量。返回 {test_ok}。"""
    target = os.path.join(module_dir, "target")
    log_dir = os.path.join(target, "maven-logs")
    reports = os.path.join(target, "surefire-reports")
    if os.path.isdir(reports):
        shutil.rmtree(reports)
    label = "跑全量测试"
    if test_classes:
        label = f"跑测试 {','.join(test_classes)}"
    rc = _invoke_maven(module_dir, _test_goals(test_classes, compile_first, reuse_forks),
                       tool_dir, log_dir, label)
    return {"test_ok": rc == 0}


def _test_goals(test_classes, compile_first, reuse_forks):
    """纯测试 goals（无 JaCoCo）。test_classes 为空则不加 -Dtest，maven 跑全部 *Test.java。"""
    test_goal = "test"
    if not compile_first:
        test_goal = "surefire:test"
    reuse = "false"
    if reuse_forks:
        reuse = "true"
    goals = [
        "-DforkCount=1",
        f"-DreuseForks={reuse}",
        "-DfailIfNoTests=false",
        "-Dmaven.test.failure.ignore=true",
    ]
    if test_classes:
        goals.append(f"-Dtest={','.join(test_classes)}")
    goals.append(test_goal)
    return goals
