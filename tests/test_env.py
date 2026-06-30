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


from jacov import env                       # noqa: E402  (追加块按需 import)
from jacov.env import _find_config, _mvn_in_home


def _make_home_with_mvn(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "mvn.cmd").write_text("", encoding="utf-8")
    (bindir / "mvn").write_text("", encoding="utf-8")
    return str(tmp_path)


def test_find_maven_from_home(tmp_path):
    cfg = _with_defaults({"maven": {"home": _make_home_with_mvn(tmp_path)}})
    found = find_maven(cfg)
    assert found.endswith("mvn.cmd") or found.endswith("mvn")


def test_find_maven_from_path(monkeypatch):
    monkeypatch.setattr(env.shutil, "which",
                        lambda name: "C:/tools/mvn.cmd" if name in ("mvn", "mvn.cmd") else None)
    assert find_maven(_with_defaults({})) == "C:/tools/mvn.cmd"


def test_find_maven_from_env_var(tmp_path, monkeypatch):
    home = _make_home_with_mvn(tmp_path)
    monkeypatch.setattr(env.shutil, "which", lambda name: None)
    monkeypatch.setenv("MAVEN_HOME", home)
    found = find_maven(_with_defaults({}))
    assert found.endswith("mvn.cmd") or found.endswith("mvn")


def test_find_maven_home_without_mvn_falls_through_to_raise(tmp_path, monkeypatch):
    # home 设了但目录下没有 bin/mvn → 不返回，继续 PATH/env，最终都没有 → raise
    monkeypatch.setattr(env.shutil, "which", lambda name: None)
    monkeypatch.delenv("MAVEN_HOME", raising=False)
    monkeypatch.delenv("M2_HOME", raising=False)
    cfg = _with_defaults({"maven": {"home": str(tmp_path)}})
    with pytest.raises(RuntimeError, match="找不到 maven"):
        find_maven(cfg)


def test_find_maven_not_found_raises(monkeypatch):
    monkeypatch.setattr(env.shutil, "which", lambda name: None)
    monkeypatch.delenv("MAVEN_HOME", raising=False)
    monkeypatch.delenv("M2_HOME", raising=False)
    with pytest.raises(RuntimeError, match="找不到 maven"):
        find_maven(_with_defaults({}))


def test_mvn_in_home_found_and_missing(tmp_path):
    assert _mvn_in_home(str(tmp_path)) == ""        # 空目录无 bin/mvn
    home = _make_home_with_mvn(tmp_path)
    assert _mvn_in_home(home)                        # 有 bin/mvn(.cmd)


def test_load_config_defaults_when_no_toml(monkeypatch):
    monkeypatch.setattr(env, "_find_config", lambda start_dir: "")
    cfg = load_config("/whatever")
    assert cfg["jacoco_version"] == DEFAULT_JACOCO_VERSION


def test_find_config_returns_empty_when_none(tmp_path, monkeypatch):
    monkeypatch.setattr(env.os.path, "isfile", lambda path: False)
    assert _find_config(str(tmp_path)) == ""


def test_find_config_finds_toml_upwards(tmp_path):
    (tmp_path / "jacov.toml").write_text("", encoding="utf-8")
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    # 从子目录上溯应找到 tmp_path/jacov.toml
    assert _find_config(str(sub)) == str(tmp_path / "jacov.toml")


def test_find_maven_env_var_dir_without_mvn_falls_through(tmp_path, monkeypatch):
    # MAVEN_HOME 指向无 bin/mvn 的目录 → 不返回，继续下一个 env 变量，最终 raise（覆盖 49->45）
    monkeypatch.setattr(env.shutil, "which", lambda name: None)
    monkeypatch.setenv("MAVEN_HOME", str(tmp_path))
    monkeypatch.delenv("M2_HOME", raising=False)
    with pytest.raises(RuntimeError, match="找不到 maven"):
        find_maven(_with_defaults({}))


def test_find_config_without_start_dir(monkeypatch):
    # start_dir 为空 → 跳过上溯循环（覆盖 66->72）；pkg_root 也置不存在 → 返回空
    monkeypatch.setattr(env.os.path, "isfile", lambda path: False)
    assert _find_config(None) == ""
