"""项目注册表：把 tool/projects.sh 的项目名、策略和目录推导迁到 Python。

compile.py 与后续测试入口都可以复用这里，避免项目目录规则在多个入口里漂移。
"""
from __future__ import annotations

import os
import ntpath

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
        _reject_drive_relative_path(workspace_root)
        return os.path.abspath(workspace_root)
    return os.path.abspath(default_workspace_root())


def _reject_drive_relative_path(path: str) -> None:
    """拦截 `C:Users...` 这类 Git Bash 反斜杠被吞后的 Windows 相对盘符路径。"""
    # ntpath 能在 Linux CI 上按 Windows 规则识别 C:Users...，避免跨平台测试漏判。
    drive, tail = ntpath.splitdrive(path)
    if drive and tail and not tail.startswith(("\\", "/")):
        raise ValueError(
            "workspace_root 不是合法绝对路径。Git Bash 下请用正斜杠，例如 "
            "--workspace-root C:/Users/lin/IdeaProjects，不要写 C:\\Users\\lin\\IdeaProjects"
        )


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


# ══════════════════════════════════════════════
#  通用目标解析：项目名 / 短名 / 任意目录路径（相对优先）
#  对齐 tool/projects.sh 的 project_short_name / resolve_module_dir / resolve_dir_target，
#  目标是「越通用越好」：尽量吃相对路径与嵌套目录，减少强制绝对路径带来的问题。
# ══════════════════════════════════════════════

_VENDOR_PREFIXES = ("fanyajwproject-", "fanyajw-")


def project_short_name(name: str) -> str:
    """去掉厂商前缀得到模块短名：fanyajwproject-course-v2 → course-v2；fanyajw-support → support。"""
    for prefix in _VENDOR_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def normalize_path(raw: str) -> str:
    """反斜杠归一为正斜杠：Git Bash / Windows 混用时统一按正斜杠解析。"""
    return raw.replace("\\", "/")


def canonical_project_name(name: str) -> str:
    """把全名或短名归一到注册全名；命中返回全名，未命中返回空串。

    含路径分隔符（视为目录路径）或匹配不到注册项目时返回空串，交给目录回退解析。
    """
    if name in PROJECT_STRATEGY:
        return name
    key = normalize_path(name).strip().strip("/")
    if not key or "/" in key:  # 含分隔符的当目录路径，不做短名匹配
        return ""
    lowered = key.lower()
    for registered in PROJECT_ORDER:
        if registered.lower() == lowered or project_short_name(registered).lower() == lowered:
            return registered
    return ""


def _dir_candidates(workspace_root: str, target: str) -> list[str]:
    """生成目录候选（绝对路径，去重保序）：原样(绝对/相对CWD)、相对 workspace、双层同名嵌套。"""
    norm = normalize_path(target).strip()
    base = os.path.basename(norm.rstrip("/"))
    raw_candidates = [
        norm,
        os.path.join(workspace_root, norm),
        os.path.join(workspace_root, norm, base) if base else "",
    ]
    seen = set()
    candidates = []
    for cand in raw_candidates:
        if not cand:
            continue
        absolute = os.path.abspath(cand)
        if absolute in seen:
            continue
        seen.add(absolute)
        candidates.append(absolute)
    return candidates


def resolve_dir_target(workspace_root: str = "", target: str = "") -> str:
    """把入参当目录路径解析为可编译目录；优先含 pom.xml 者，其次退而求目录存在。

    支持绝对路径、相对 CWD、相对 workspace_root、双层同名嵌套；反斜杠自动归一。
    命中返回绝对路径，未命中返回空串。
    """
    resolved_root = resolve_workspace_root(workspace_root)
    candidates = _dir_candidates(resolved_root, target)
    for cand in candidates:
        if os.path.isfile(os.path.join(cand, "pom.xml")):
            return cand
    for cand in candidates:
        if os.path.isdir(cand):
            return cand
    return ""


def build_module_index(workspace_root: str = "") -> "tuple[dict, list]":
    """派生「模块短名 → 目录」索引；rpc 展开 root/api/svc 三个子模块。返回 (index, 短名顺序)。"""
    resolved_root = resolve_workspace_root(workspace_root)
    index: dict = {}
    order: list = []

    def add(module_short: str, module_dir: str) -> None:
        key = module_short.lower()
        if key in index:
            return
        index[key] = module_dir
        order.append(module_short)

    for name in PROJECT_ORDER:
        short = project_short_name(name)
        layout = strategy_to_layout(PROJECT_STRATEGY[name])
        if layout == "rpc":
            dirs = rpc_module_dirs(resolved_root, name)
            add(short, dirs["root"])
            add(f"{short}-api", dirs["api"])
            add(f"{short}-svc", dirs["svc"])
            continue
        if layout == "top":
            add(short, os.path.join(resolved_root, name))
            continue
        # nested：双层同名 <root>/<name>/<name>
        add(short, os.path.join(resolved_root, name, name))
    return index, order


def resolve_module_dir(workspace_root: str = "", module: str = "") -> str:
    """模块短名 / 全名 / 任意目录路径 → 目录：先查短名索引，未命中回退目录解析。"""
    resolved_root = resolve_workspace_root(workspace_root)
    index, _ = build_module_index(resolved_root)
    key = normalize_path(module).strip().lower()
    if key in index:
        return index[key]
    short = project_short_name(key)
    if short in index:
        return index[short]
    return resolve_dir_target(resolved_root, module)


def available_modules(workspace_root: str = "") -> list[dict]:
    """返回稳定顺序的模块短名 + 目录，供 CLI/MCP 错误提示与 UI 展示。"""
    resolved_root = resolve_workspace_root(workspace_root)
    index, order = build_module_index(resolved_root)
    return [{"module": short, "dir": index[short.lower()]} for short in order]
