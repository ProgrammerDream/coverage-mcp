"""项目编译入口：把 tool/compile.sh 的策略调度迁到 Python。

这里只负责项目名到 Maven 步骤的编排；Maven 执行、配置加载和日志输出继续复用 runner/env。
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

from . import env, project_registry, runner


def compile_project(project_name: str, workspace_root: str = "", strategy: str = "") -> dict:
    """编译目标，三级回退（对齐 tool/compile.sh 的 dispatch）：

    1. 注册项目名/短名，或显式 strategy → 按策略推导目录布局编译；
    2. 未注册但能解析成「含 pom.xml 的目录」（相对/绝对/嵌套/双层同名均可）→ path 策略 clean+compile；
    3. 都不命中 → 报错并列出可用项目。
    """
    resolved_root = project_registry.resolve_workspace_root(workspace_root)
    started_at = datetime.now()
    started_ticks = time.monotonic()
    config = env.load_config(resolved_root)

    # 1) 注册项目（全名/短名）或显式策略覆盖：按策略布局编译
    canonical = project_registry.canonical_project_name(project_name)
    if strategy or canonical:
        name = canonical or project_name
        resolved_strategy = project_registry.project_strategy(name, strategy)
        if resolved_strategy not in ("default", "top-level", "shared-jar", "rpc"):
            raise ValueError(f"未知策略 '{resolved_strategy}'（项目 {name}）")
        log_dir = os.path.join(resolved_root, "target", "maven-logs")
        steps = []
        if resolved_strategy in ("default", "top-level"):
            _build_clean_then(steps, resolved_root, name, resolved_strategy, "编译", ["compile"],
                              config, log_dir, started_ticks)
        if resolved_strategy == "shared-jar":
            _build_clean_then(steps, resolved_root, name, resolved_strategy, "安装",
                              ["install", "-Dmaven.test.skip=true"], config, log_dir, started_ticks)
        if resolved_strategy == "rpc":
            _build_rpc(steps, resolved_root, name, config, log_dir, started_ticks)
        return _finish(name, resolved_root, resolved_strategy, steps, log_dir, started_at, started_ticks)

    # 2) 未注册：当目录路径回退（相对优先，减少绝对路径带来的问题）
    target_dir = project_registry.resolve_dir_target(resolved_root, project_name)
    if target_dir:
        # clean 会删除 module_dir/target，日志放父级目录，避免删掉使用中的日志文件
        log_dir = os.path.join(os.path.dirname(target_dir), "target", "maven-logs")
        steps = []
        _build_path(steps, target_dir, config, log_dir, started_ticks)
        return _finish(project_name, resolved_root, "path", steps, log_dir, started_at, started_ticks)

    # 3) 既非注册项目也非有效目录
    names = ", ".join(item["name"] for item in project_registry.available_projects())
    raise ValueError(f"未注册的项目，且不是含 pom.xml 的目录: {project_name}\n可用项目: {names}")


def _finish(project_name, resolved_root, strategy, steps, log_dir, started_at, started_ticks):
    """收尾：统一计算耗时并组装返回结构。"""
    ended_at = datetime.now()
    duration_seconds = round(time.monotonic() - started_ticks, 3)
    return _build_result(project_name, resolved_root, strategy, steps,
                         log_dir, started_at, ended_at, duration_seconds)


def compile_module(module_dir: str, goals=None) -> dict:
    """直接对一个含 pom.xml 的模块执行 Maven goals；默认 clean + compile。"""
    resolved_dir = os.path.abspath(module_dir)
    resolved_goals = goals or ["clean", "compile"]
    steps = []
    config = env.load_config(resolved_dir)
    started_ticks = time.monotonic()
    # clean 会删除 module_dir/target，日志必须放在模块目录外，避免清理时删除打开中的日志文件。
    log_dir = os.path.join(os.path.dirname(resolved_dir), "target", "maven-logs")
    _run_step(steps, resolved_dir, "编译模块", resolved_goals, config, log_dir, 1, 1, started_ticks)
    return {
        "status": _status_from_steps(steps),
        "module_dir": resolved_dir,
        "log_dir": log_dir,
        "steps": steps,
    }


def main(argv=None):
    args = _parse_args(argv)
    try:
        result = compile_project(args.project, args.workspace_root, args.strategy)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    _print_summary(result)
    if result["status"] == "FAIL":
        return 1
    return 0


def _build_clean_then(steps, workspace_root, project_name, strategy, pass_label, pass_goals,
                      config, log_dir, build_started_ticks):
    """default/top-level/shared-jar 共用：先 clean，再执行目标 goals。"""
    module_dir = project_registry.project_module_dir(workspace_root, project_name, strategy)
    if not _run_step(steps, module_dir, f"[1/2] 清理 {project_name}", ["clean"],
                     config, log_dir, 1, 2, build_started_ticks):
        return
    _run_step(steps, module_dir, f"[2/2] {pass_label} {project_name}", pass_goals,
              config, log_dir, 2, 2, build_started_ticks)


def _build_rpc(steps, workspace_root, project_name, config, log_dir, build_started_ticks):
    """RPC 策略：按旧脚本顺序串联根/API/SVC 七步，任一步失败即停止。"""
    dirs = project_registry.rpc_module_dirs(workspace_root, project_name)
    plan = [
        (dirs["root"], "[1/7] 清理 RPC 根模块", ["clean"]),
        (dirs["api"], "[2/7] 清理 RPC API 模块", ["clean"]),
        (dirs["svc"], "[3/7] 清理 RPC SVC 模块", ["clean"]),
        (dirs["api"], "[4/7] 安装 RPC API 模块", ["install"]),
        (dirs["svc"], "[5/7] 第一次编译 RPC SVC 模块", ["compile"]),
        (dirs["svc"], "[6/7] 第二次编译 RPC SVC 模块", ["compile"]),
        (dirs["api"], "[7/7] 再次安装 RPC API 模块", ["install"]),
    ]
    for index, item in enumerate(plan, start=1):
        module_dir, label, goals = item
        if not _run_step(steps, module_dir, label, goals, config, log_dir, index, len(plan), build_started_ticks):
            return


def _build_path(steps, module_dir, config, log_dir, build_started_ticks):
    """path 策略：对任意「含 pom.xml 的目录」执行 clean + compile，无需预先注册。"""
    name = os.path.basename(module_dir)
    if not _run_step(steps, module_dir, f"[1/2] 清理 {name}", ["clean"],
                     config, log_dir, 1, 2, build_started_ticks):
        return
    _run_step(steps, module_dir, f"[2/2] 编译 {name}", ["compile"],
              config, log_dir, 2, 2, build_started_ticks)


def _run_step(steps, module_dir, label, goals, config, log_dir, step_index, step_total, build_started_ticks):
    """校验 pom.xml 后执行 Maven，并把结果压成 MCP 友好的 step dict。"""
    started_at = datetime.now()
    step_started_ticks = time.monotonic()
    step = {
        "name": label,
        "module_dir": module_dir,
        "goals": goals,
        "progress": f"{step_index}/{step_total}",
        "status": "PENDING",
        "exit_code": None,
        "log": "",
        "started_at": started_at.isoformat(timespec="seconds"),
        "ended_at": "",
        "duration_seconds": 0,
        "elapsed_seconds": round(step_started_ticks - build_started_ticks, 3),
    }
    _print_progress(step, step_index, step_total)
    if not os.path.isfile(os.path.join(module_dir, "pom.xml")):
        ended_at = datetime.now()
        step["status"] = "FAIL"
        step["error"] = f"POM not found: {os.path.join(module_dir, 'pom.xml')}"
        step["ended_at"] = ended_at.isoformat(timespec="seconds")
        step["duration_seconds"] = round(time.monotonic() - step_started_ticks, 3)
        steps.append(step)
        return False

    # Maven 输出由 runner 统一处理；这里仅保存退出码和日志路径，方便 MCP 消费。
    result = runner.invoke_maven(module_dir, goals, label, config, log_dir)
    step["exit_code"] = result["exit_code"]
    step["log"] = result["log"]
    step["ended_at"] = result["ended_at"]
    step["duration_seconds"] = result["duration_seconds"]
    step["status"] = "PASS" if result["exit_code"] == 0 else "FAIL"
    steps.append(step)
    return step["status"] == "PASS"


def _build_result(project_name, workspace_root, strategy, steps, log_dir, started_at, ended_at, duration_seconds):
    return {
        "status": _status_from_steps(steps),
        "project": project_name,
        "workspace_root": workspace_root,
        "strategy": strategy,
        "log_dir": log_dir,
        "started_at": started_at.isoformat(timespec="seconds"),
        "ended_at": ended_at.isoformat(timespec="seconds"),
        "duration_seconds": duration_seconds,
        "steps": steps,
        "available_projects": project_registry.available_projects(),
    }


def _status_from_steps(steps):
    if not steps or any(step["status"] == "FAIL" for step in steps):
        return "FAIL"
    return "PASS"


def _parse_args(argv):
    parser = argparse.ArgumentParser(prog="jacov.compile")
    parser.add_argument("project", help="项目名（全名/短名，如 fanyajwproject-course-v2 或 course-v2），"
                                        "或含 pom.xml 的目录路径（相对/绝对/嵌套均可）")
    parser.add_argument("--workspace-root", default="", help="工作区根目录；空则自动推导")
    parser.add_argument("--strategy", default="", help="覆盖注册表策略：default/top-level/shared-jar/rpc")
    return parser.parse_args(argv)


def _print_summary(result):
    print("\n" + "=" * 44)
    print(f"项目编译结果（{result['project']}）")
    print("=" * 44)
    print(
        f"策略: {result['strategy']}, 状态: {result['status']}, 总用时: {_format_duration(result['duration_seconds'])}")
    print(f"Start Time: {result['started_at']}")
    print(f"End Time: {result['ended_at']}")
    print(f"日志目录: {result['log_dir']}")
    for step in result["steps"]:
        log = step.get("log", "")
        print(f"[{step['status']}] {step['name']} progress={step['progress']} "
              f"duration={_format_duration(step['duration_seconds'])} goals={' '.join(step['goals'])}")
        if step.get("error"):
            print(f"  {step['error']}")
        if log:
            print(f"  日志: {log}")


def _print_progress(step, step_index, step_total):
    """每步启动前打印进度，让长编译能看到当前执行到哪一步。"""
    print("\n" + "-" * 44)
    print(f"当前进度: {step_index}/{step_total}  已耗时: {_format_duration(step['elapsed_seconds'])}")
    print(f"执行步骤: {step['name']}")
    print(f"模块目录: {step['module_dir']}")
    print(f"Goals: {' '.join(step['goals'])}")


def _format_duration(seconds):
    """秒数转成人读耗时，和 tool/compile.sh 的汇总风格保持一致。"""
    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{hours}h {minutes}m {secs}s"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
