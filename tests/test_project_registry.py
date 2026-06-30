"""项目注册表离线测试：锁定 tool/projects.sh 迁移后的目录推导规则。"""
import os
from pathlib import Path

import pytest

from jacov import project_registry


def test_default_project_uses_nested_module_dir(tmp_path):
    module_dir = project_registry.project_module_dir(str(tmp_path), "fanyajwproject-course-v2")
    assert Path(module_dir).parts[-2:] == ("fanyajwproject-course-v2", "fanyajwproject-course-v2")


def test_top_level_strategy_uses_project_root(tmp_path):
    module_dir = project_registry.project_module_dir(str(tmp_path), "demo-project", "top-level")
    assert Path(module_dir).name == "demo-project"


def test_rpc_dirs_follow_api_svc_convention(tmp_path):
    dirs = project_registry.rpc_module_dirs(str(tmp_path), "fanyajwproject-rpc")
    assert Path(dirs["root"]).name == "fanyajwproject-rpc"
    assert Path(dirs["api"]).parts[-2:] == ("fanyajwproject-rpc", "fanyajwproject-rpc-api")
    assert Path(dirs["svc"]).parts[-2:] == ("fanyajwproject-rpc", "fanyajwproject-rpc-svc")


def test_reject_drive_relative_workspace_root():
    with pytest.raises(ValueError, match="Git Bash"):
        project_registry.resolve_workspace_root("C:UserslinIdeaProjects")


def test_project_short_name_strips_vendor_prefix():
    assert project_registry.project_short_name("fanyajwproject-course-v2") == "course-v2"
    assert project_registry.project_short_name("fanyajw-support") == "support"
    assert project_registry.project_short_name("es-jxjy") == "es-jxjy"


def test_canonical_project_name_accepts_full_and_short():
    assert project_registry.canonical_project_name("fanyajwproject-course-v2") == "fanyajwproject-course-v2"
    assert project_registry.canonical_project_name("course-v2") == "fanyajwproject-course-v2"
    assert project_registry.canonical_project_name("support") == "fanyajw-support"
    assert project_registry.canonical_project_name("不存在的项目") == ""
    # 含路径分隔符视为目录路径，不做短名匹配
    assert project_registry.canonical_project_name("a/b/course-v2") == ""


def test_resolve_dir_target_prefers_pom_in_nested_layout(tmp_path):
    # 双层同名：<root>/<name>/<name>/pom.xml，传短目录名也能命中内层 pom
    name = "demo-nested"
    inner = tmp_path / name / name
    inner.mkdir(parents=True)
    (inner / "pom.xml").write_text("<project/>", encoding="utf-8")
    resolved = project_registry.resolve_dir_target(str(tmp_path), name)
    assert resolved == str(inner)


def test_resolve_dir_target_relative_to_workspace(tmp_path):
    # 任意深层嵌套的相对路径（相对 workspace_root）也能解析
    rel = "projects/group/log-agent-server"
    module = tmp_path / rel
    module.mkdir(parents=True)
    (module / "pom.xml").write_text("<project/>", encoding="utf-8")
    resolved = project_registry.resolve_dir_target(str(tmp_path), rel)
    assert resolved == str(module)


def test_resolve_dir_target_normalizes_backslash(tmp_path):
    module = tmp_path / "a" / "b"
    module.mkdir(parents=True)
    (module / "pom.xml").write_text("<project/>", encoding="utf-8")
    resolved = project_registry.resolve_dir_target(str(tmp_path), "a\\b")
    assert resolved == str(module)


def test_resolve_dir_target_returns_empty_when_missing(tmp_path):
    assert project_registry.resolve_dir_target(str(tmp_path), "nope/not-here") == ""


def test_resolve_module_dir_short_name_and_rpc_submodules(tmp_path):
    # 短名解析到双层同名目录
    course = project_registry.resolve_module_dir(str(tmp_path), "course-v2")
    assert Path(course).parts[-2:] == ("fanyajwproject-course-v2", "fanyajwproject-course-v2")
    # rpc 展开 api/svc 子模块短名
    svc = project_registry.resolve_module_dir(str(tmp_path), "rpc-svc")
    assert Path(svc).parts[-2:] == ("fanyajwproject-rpc", "fanyajwproject-rpc-svc")
    api = project_registry.resolve_module_dir(str(tmp_path), "rpc-api")
    assert Path(api).name == "fanyajwproject-rpc-api"


def test_resolve_module_dir_falls_back_to_path(tmp_path):
    module = tmp_path / "standalone"
    module.mkdir()
    (module / "pom.xml").write_text("<project/>", encoding="utf-8")
    assert project_registry.resolve_module_dir(str(tmp_path), "standalone") == str(module)


def test_canonical_project_name_empty_and_slash_only():
    # not key 分支：空串 / 仅斜杠 strip 后为空
    assert project_registry.canonical_project_name("") == ""
    assert project_registry.canonical_project_name("/") == ""


def test_resolve_dir_target_absolute_path_triggers_dedup(tmp_path):
    # 传绝对路径：「原样」与「相对 workspace」候选归一成同一绝对路径，触发去重分支
    module = tmp_path / "abs-mod"
    module.mkdir()
    (module / "pom.xml").write_text("<project/>", encoding="utf-8")
    assert project_registry.resolve_dir_target(str(tmp_path), str(module)) == str(module)


def test_resolve_dir_target_dir_without_pom_uses_second_pass(tmp_path):
    # 目录存在但无 pom.xml：走第二轮「目录存在」回退
    module = tmp_path / "no-pom"
    module.mkdir()
    assert project_registry.resolve_dir_target(str(tmp_path), "no-pom") == str(module)


def test_resolve_dir_target_empty_target_skips_blank_candidates(tmp_path):
    # 空 target：原样/双层候选为空被跳过（not cand 分支），最终回退到 workspace 根
    assert project_registry.resolve_dir_target(str(tmp_path), "") == str(tmp_path)


def test_resolve_module_dir_accepts_full_name(tmp_path):
    # 传全名经 project_short_name 二级回退命中短名索引
    resolved = project_registry.resolve_module_dir(str(tmp_path), "fanyajwproject-course-v2")
    assert Path(resolved).parts[-2:] == ("fanyajwproject-course-v2", "fanyajwproject-course-v2")


def test_available_modules_lists_short_names(tmp_path):
    modules = project_registry.available_modules(str(tmp_path))
    names = [item["module"] for item in modules]
    assert "course-v2" in names
    assert "rpc-api" in names and "rpc-svc" in names
    assert all(item["dir"] for item in modules)


def test_build_module_index_top_layout_and_dedup(monkeypatch):
    # 临时注册表覆盖 top-level 布局 + 同短名去重两条分支
    strategy = {"fanyajwproject-demo": "top-level", "fanyajw-demo": "default"}
    monkeypatch.setattr(project_registry, "PROJECT_STRATEGY", strategy)
    monkeypatch.setattr(project_registry, "PROJECT_ORDER", list(strategy.keys()))
    index, order = project_registry.build_module_index("/ws")
    # 两个项目短名都是 demo，后注册的重复键被跳过；top-level 用单层目录
    assert order == ["demo"]
    assert Path(index["demo"]).name == "fanyajwproject-demo"


def test_project_strategy_unregistered_raises():
    with pytest.raises(ValueError, match="未注册的项目"):
        project_registry.project_strategy("definitely-not-registered")


def test_default_workspace_root_prefers_cwd_with_tool(tmp_path, monkeypatch):
    (tmp_path / "tool").mkdir()
    monkeypatch.chdir(tmp_path)
    assert project_registry.default_workspace_root() == str(tmp_path)
    # resolve_workspace_root 空值 → 走默认推导
    assert project_registry.resolve_workspace_root("") == str(tmp_path)


def test_default_workspace_root_uses_package_parent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # cwd 无 tool
    pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(project_registry.__file__))))
    workspace_parent = os.path.dirname(pkg_root)
    real_isdir = os.path.isdir

    def fake_isdir(path):
        if path == os.path.join(workspace_parent, "tool"):
            return True
        if path == os.path.join(str(tmp_path), "tool"):
            return False
        return real_isdir(path)

    monkeypatch.setattr(project_registry.os.path, "isdir", fake_isdir)
    assert project_registry.default_workspace_root() == workspace_parent


def test_default_workspace_root_falls_back_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    real_isdir = os.path.isdir

    def no_tool_isdir(path):
        if path.replace("\\", "/").endswith("/tool"):
            return False
        return real_isdir(path)

    monkeypatch.setattr(project_registry.os.path, "isdir", no_tool_isdir)
    assert project_registry.default_workspace_root() == str(tmp_path)
