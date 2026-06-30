"""项目注册表：把 tool/projects.sh 的项目名、策略和目录推导迁到 Python。

compile.py 与后续测试入口都可以复用这里，避免项目目录规则在多个入口里漂移。
"""
from __future__ import annotations

import os


PROJECT_STRATEGY = {
    "fanyajwproject-rpc": "rpc",
    "fanyajw-shared-jar": "shared-jar",
    "fanyajwproject-course-v2": "default",
    "fanyajwproject-ftf-teaching": "default",
    "fanyajwproject-task": "default",
    "fanyajw-support": "default",
    "fanyajw-student-v2": "default",
    "fanyajwproject-thesis-v2": "default",
    "fanyajw-exam-task": "default",
    "es-jxjy": "default",
    "optaplanner-jxjy": "default",
    "fanyajwproject-exam-v2": "default",
    "smart-marking-papers": "default",
}

PROJECT_ORDER = list(PROJECT_STRATEGY.keys())


def default_workspace_root() -> str:
    """推导工作区根目录；优先用当前目录，其次用 coverage-mcp 的父目录。"""
    cwd = os.getcwd()
    if os.path.isdir(os.path.join(cwd, "tool")):
        return cwd

    # coverage-mcp 放在工程根下时，用包目录的父目录作为默认工作区。
    package_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    workspace_root = os.path.dirname(package_root)
    if os.path.isdir(os.path.join(workspace_root, "tool")):
        return workspace_root
    return cwd


def resolve_workspace_root(workspace_root: str = "") -> str:
    """把空值转成默认工作区，并统一成绝对路径。"""
    if workspace_root:
        return os.path.abspath(workspace_root)
    return os.path.abspath(default_workspace_root())


def project_strategy(project_name: str, strategy: str = "") -> str:
    """取项目策略；显式 strategy 可覆盖注册表，便于临时项目试跑。"""
    if strategy:
        return strategy
    resolved = PROJECT_STRATEGY.get(project_name)
    if resolved:
        return resolved
    raise ValueError(f"未注册的项目: {project_name}")


def strategy_to_layout(strategy: str) -> str:
    """编译策略转目录布局：对齐 tool/projects.sh 的 strategy_to_layout。"""
    if strategy == "top-level":
        return "top"
    if strategy == "rpc":
        return "rpc"
    return "nested"


def project_module_dir(workspace_root: str, project_name: str, strategy: str = "") -> str:
    """按项目策略推导主模块目录；rpc 返回根 pom 所在目录。"""
    layout = strategy_to_layout(project_strategy(project_name, strategy))
    if layout in ("top", "rpc"):
        return os.path.join(workspace_root, project_name)
    return os.path.join(workspace_root, project_name, project_name)


def rpc_module_dirs(workspace_root: str, project_name: str) -> dict:
    """按 RPC 约定推导根/API/SVC 三个模块目录。"""
    rpc_dir = os.path.join(workspace_root, project_name)
    return {
        "root": rpc_dir,
        "api": os.path.join(rpc_dir, f"{project_name}-api"),
        "svc": os.path.join(rpc_dir, f"{project_name}-svc"),
    }


def available_projects() -> list[dict]:
    """返回稳定顺序的项目清单，供 CLI/MCP 错误提示和 UI 展示。"""
    return [{"name": name, "strategy": PROJECT_STRATEGY[name]} for name in PROJECT_ORDER]
