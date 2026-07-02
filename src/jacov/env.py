"""Maven 环境发现 + 配置加载（纯 Python，不依赖 tool/env.sh / bash）。

配置来源：jacov.toml（从起始目录上溯 → 包目录），缺省走内置默认（开源零配置可用）。
maven 可执行发现优先级：配置 exec/home > PATH > MAVEN_HOME/M2_HOME。
maven opts 只含标准参数（settings/本地仓/argLine/编码），不含任何 IDEA 集成参数。
"""
from __future__ import annotations

import os
import shutil
import sys
import tomllib

# 默认值（开源零配置可用）
DEFAULT_JACOCO_VERSION = "0.8.11"
DEFAULT_ADD_OPENS = [
    "java.base/java.lang",
    "java.base/java.util",
    "java.base/java.math",
]


def force_utf8_stdio():
    """CLI 入口统一把 stdout/stderr 定死为 UTF-8 输出。

    Windows 下 Python 对管道/重定向默认按 ANSI 代码页（中文系统即 GBK）编码，
    中文经 UTF-8 终端（Git Bash、新版 PowerShell）显示为乱码；定死 UTF-8 后各终端一致。
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def load_config(start_dir=None):
    """读 jacov.toml（起始目录上溯 → 包目录），缺省返回默认配置。"""
    path = _find_config(start_dir)
    raw = {}
    if path:
        with open(path, "rb") as fp:
            raw = tomllib.load(fp)
    return _with_defaults(raw)


def find_maven(config):
    """发现 maven 可执行：配置 exec/home > PATH > MAVEN_HOME/M2_HOME。找不到则抛错。"""
    if config.get("maven_exec"):
        return config["maven_exec"]
    home = config.get("maven_home")
    if home:
        found = _mvn_in_home(home)
        if found:
            return found
    for name in ("mvn", "mvn.cmd"):
        found = shutil.which(name)
        if found:
            return found
    for env_var in ("MAVEN_HOME", "M2_HOME"):
        home = os.environ.get(env_var)
        if home:
            found = _mvn_in_home(home)
            if found:
                return found
    raise RuntimeError("找不到 maven：请在 jacov.toml 配 [maven] home/exec，或把 mvn 加入 PATH")


def maven_opts(config):
    """标准 maven opts（无任何 IDEA 集成参数）。settings/本地仓缺省时不加，走 maven 默认。"""
    opts = ["-Dfile.encoding=UTF-8", f"-DargLine={arg_line(config)}"]
    if config.get("settings"):
        opts.extend(["-s", config["settings"]])
    if config.get("local_repo"):
        opts.append(f"-Dmaven.repo.local={config['local_repo']}")
    return opts


def _find_config(start_dir):
    candidates = []
    if start_dir:
        current = os.path.abspath(start_dir)
        for _ in range(6):
            candidates.append(os.path.join(current, "jacov.toml"))
            current = os.path.dirname(current)
    # 包所在 coverage-mcp 目录（src/jacov/env.py 的上三级）
    pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates.append(os.path.join(pkg_root, "jacov.toml"))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return ""


def _with_defaults(raw):
    maven = raw.get("maven", {})
    jacoco = raw.get("jacoco", {})
    test = raw.get("test", {})
    return {
        "maven_home": maven.get("home", ""),
        "maven_exec": maven.get("exec", ""),
        "settings": maven.get("settings", ""),
        "local_repo": maven.get("local_repo", ""),
        "jacoco_version": jacoco.get("version", DEFAULT_JACOCO_VERSION),
        "jacoco_excludes": jacoco.get("excludes", ""),
        "add_opens": test.get("add_opens", DEFAULT_ADD_OPENS),
    }


def _mvn_in_home(home):
    # Windows 用 mvn.cmd（批处理，cmd.exe 可执行）；*nix 用 mvn（shell 脚本）
    names = ("bin/mvn.cmd", "bin/mvn") if os.name == "nt" else ("bin/mvn", "bin/mvn.cmd")
    for rel in names:
        candidate = os.path.join(home, *rel.split("/"))
        if os.path.isfile(candidate):
            return candidate
    return ""


def arg_line(config):
    """JDK17 fork 测试的 argLine（add-opens + 编码）；覆盖率时 runner 会在前面拼 @{coverageAgentArgLine}。"""
    parts = [f"--add-opens={item}=ALL-UNNAMED" for item in config["add_opens"]]
    parts.append("-Dfile.encoding=UTF-8")
    return " ".join(parts)
