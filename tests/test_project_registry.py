"""项目注册表离线测试：锁定 tool/projects.sh 迁移后的目录推导规则。"""
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
