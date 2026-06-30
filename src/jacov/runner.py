"""Maven 执行：纯 Python subprocess 直调 mvn（不经 bash / tool/env.sh）。

maven 可执行与 opts 来自 env.py（jacov.toml 配置 + 默认）。
保留实时流式逐行读 + _is_key_line 进度透传（编译/测试阶段都不静默）。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from datetime import datetime

from . import env


def run_coverage(module_dir, test_classes, compile_first=True, reuse_forks=False):
    """跑覆盖率：单条 maven 命令 prepare-agent → 测试 → report。

    compile_first=True 用 `test`（含增量编译）；False 用 `surefire:test`。
    reuse_forks=True 复用 fork JVM（多测试类快）；False 每类独立 JVM（严格隔离）。
    返回 dict：{csv, xml, exec, test_ok}。
    """
    config = env.load_config(module_dir)
    target = os.path.join(module_dir, "target")
    exec_path = os.path.join(target, "jacoco.exec")
    site = os.path.join(target, "site", "jacoco")
    csv_path = os.path.join(site, "jacoco.csv")
    xml_path = os.path.join(site, "jacoco.xml")
    log_dir = os.path.join(target, "maven-logs")

    _clean_stale(target, (exec_path, csv_path, xml_path))
    test_arg = ",".join(test_classes)
    goals = _coverage_goals(test_arg, exec_path, compile_first, reuse_forks, config)
    result = _invoke_maven(module_dir, goals, config, log_dir, f"跑覆盖率测试 {test_arg}")
    return {"csv": csv_path, "xml": xml_path, "exec": exec_path, "test_ok": result["exit_code"] == 0}


def run_tests(module_dir, test_classes, compile_first=True, reuse_forks=True):
    """跑测试不带覆盖率（纯 surefire，比覆盖率快）。test_classes 为空 = 全量（模块所有 *Test.java）。"""
    config = env.load_config(module_dir)
    target = os.path.join(module_dir, "target")
    log_dir = os.path.join(target, "maven-logs")
    reports = os.path.join(target, "surefire-reports")
    if os.path.isdir(reports):
        shutil.rmtree(reports)
    label = "跑全量测试"
    if test_classes:
        label = f"跑测试 {','.join(test_classes)}"
    result = _invoke_maven(module_dir, _test_goals(test_classes, compile_first, reuse_forks), config, log_dir, label)
    return {"test_ok": result["exit_code"] == 0}


def invoke_maven(module_dir, goals, step_label, config=None, log_dir=""):
    """给编译调度复用的 Maven 执行入口，返回退出码与日志路径。"""
    if config is None:
        config = env.load_config(module_dir)
    if not log_dir:
        log_dir = os.path.join(module_dir, "target", "maven-logs")
    return _invoke_maven(module_dir, goals, config, log_dir, step_label)


def _clean_stale(target, report_paths):
    """清旧产物，避免上一次结果污染解析。"""
    for path in report_paths:
        if os.path.exists(path):
            os.remove(path)
    reports = os.path.join(target, "surefire-reports")
    if os.path.isdir(reports):
        shutil.rmtree(reports)


def _coverage_goals(test_arg, exec_path, compile_first, reuse_forks, config):
    """单条 maven 命令的全部 goals：prepare-agent → 测试 → report。jacoco 版本/排除/argLine 取自配置。"""
    plugin = f"org.jacoco:jacoco-maven-plugin:{config['jacoco_version']}"
    test_goal = "test"
    if not compile_first:
        test_goal = "surefire:test"
    reuse = "false"
    if reuse_forks:
        reuse = "true"
    goals = [
        f"{plugin}:prepare-agent",
        "-Djacoco.propertyName=coverageAgentArgLine",
        f"-Djacoco.destFile={exec_path}",
    ]
    if config["jacoco_excludes"]:
        goals.append(f"-Djacoco.excludes={config['jacoco_excludes']}")
    goals.extend([
        f"-DargLine=@{{coverageAgentArgLine}} {env.arg_line(config)}",
        f"-Dtest={test_arg}",
        "-DforkCount=1",
        f"-DreuseForks={reuse}",
        "-DfailIfNoTests=false",
        "-Dmaven.test.failure.ignore=true",
        test_goal,
        f"{plugin}:report",
        f"-Djacoco.dataFile={exec_path}",
    ])
    return goals


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


def _invoke_maven(module_dir, goals, config, log_dir, step_label):
    """纯 subprocess 直调 mvn（跨平台），实时流式逐行读，关键行即时打屏。"""
    os.makedirs(log_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = os.path.join(log_dir, f"{os.path.basename(module_dir)}-{stamp}.log")
    maven = env.find_maven(config)
    args = [maven, *env.maven_opts(config), "--batch-mode", "--no-transfer-progress", *goals]

    started_at = datetime.now()
    start_ticks = time.monotonic()
    print(f"\n{step_label}", flush=True)
    print(f"Step Start Time: {started_at.strftime('%H:%M:%S')}", flush=True)
    proc = subprocess.Popen(
        _platform_cmd(args), cwd=module_dir,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1,
    )
    with open(log_file, "w", encoding="utf-8", errors="replace") as fp:
        for line in proc.stdout:
            fp.write(line)
            if _is_key_line(line):
                print(line.rstrip(), flush=True)
    proc.wait()

    ended_at = datetime.now()
    duration_seconds = round(time.monotonic() - start_ticks, 3)
    status = "PASS"
    if proc.returncode != 0:
        status = f"FAIL(exit {proc.returncode})"
    print(f"Step End Time: {ended_at.strftime('%H:%M:%S')}", flush=True)
    print(f"[STEP {status}] {step_label}  用时: {_format_duration(duration_seconds)}  日志: {log_file}",
          flush=True)
    return {
        "exit_code": proc.returncode,
        "status": status,
        "log": log_file,
        "started_at": started_at.isoformat(timespec="seconds"),
        "ended_at": ended_at.isoformat(timespec="seconds"),
        "duration_seconds": duration_seconds,
    }


def _platform_cmd(args):
    # @formatter:off
    # Windows 的 mvn.cmd 经 cmd.exe 执行；含空格路径（如 "Program Files"）有引号陷阱：
    # cmd /c 会把整条命令的首尾引号 strip。故外面再包一层引号——外层被 strip 掉，
    # 内层（list2cmdline 给含空格可执行加的引号）得以保留，路径不被空格拆开。
    # *nix 的 mvn(shell 脚本) 直接按 list 调即可。
    # @formatter:on
    if os.name == "nt":
        return 'cmd /c "' + subprocess.list2cmdline(args) + '"'
    return args


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


def _format_duration(seconds):
    """秒数转成人读耗时，供长时间 Maven 步骤持续反馈。"""
    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{hours}h {minutes}m {secs}s"
