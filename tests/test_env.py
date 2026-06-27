"""env 配置加载 / maven 发现 / opts 拼装的离线测试。"""
import pytest

from jacov.env import DEFAULT_JACOCO_VERSION, _with_defaults, find_maven, load_config, maven_opts


def test_with_defaults_empty_uses_builtin():
    cfg = _with_defaults({})
    assert cfg["jacoco_version"] == DEFAULT_JACOCO_VERSION
    assert cfg["settings"] == ""
    assert cfg["add_opens"]  # 默认 add-opens 非空


def test_with_defaults_override():
    cfg = _with_defaults({"jacoco": {"version": "0.8.9"}, "maven": {"settings": "s.xml"}})
    assert cfg["jacoco_version"] == "0.8.9"
    assert cfg["settings"] == "s.xml"


def test_load_config_reads_toml(tmp_path):
    (tmp_path / "jacov.toml").write_text('[jacoco]\nversion = "0.8.7"\n', encoding="utf-8")
    cfg = load_config(str(tmp_path))
    assert cfg["jacoco_version"] == "0.8.7"


def test_find_maven_prefers_explicit_exec():
    cfg = _with_defaults({"maven": {"exec": "/path/to/mvn"}})
    assert find_maven(cfg) == "/path/to/mvn"


def test_maven_opts_has_no_idea_params():
    cfg = _with_defaults({"maven": {"settings": "s.xml", "local_repo": "/repo"}})
    opts = maven_opts(cfg)
    joined = " ".join(opts)
    # 关键：剔除了所有 IDEA 集成参数
    assert "idea.version" not in joined
    assert "maven.ext.class.path" not in joined
    assert "jansi" not in joined
    # 保留标准参数
    assert "-s" in opts and "s.xml" in opts
    assert "-Dmaven.repo.local=/repo" in opts
    assert "add-opens" in joined and "file.encoding=UTF-8" in joined


def test_maven_opts_omits_settings_and_repo_when_absent():
    opts = maven_opts(_with_defaults({}))
    assert "-s" not in opts
    assert not any("maven.repo.local" in opt for opt in opts)
