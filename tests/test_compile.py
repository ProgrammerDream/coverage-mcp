"""compile_project 离线测试：模拟 Maven 调用，只验证策略调度和返回结构。"""
import pytest

from jacov import compile as jacov_compile


def _fake_maven(exit_code=0):
    """构造 invoke_maven 替身：记录调用并返回固定退出码。"""
    calls = []

    def invoke(work_dir, goals, label, config, log_dir):
        calls.append((work_dir, goals, label))
        status = "PASS" if exit_code == 0 else "FAIL"
        return {"exit_code": exit_code, "status": status, "log": f"{log_dir}/maven.log",
                "started_at": "2026-06-30T10:00:00", "ended_at": "2026-06-30T10:00:01", "duration_seconds": 1}

    return invoke, calls


def test_compile_default_runs_clean_then_compile(tmp_path, monkeypatch):
    project = "fanyajwproject-course-v2"
    module_dir = tmp_path / project / project
    module_dir.mkdir(parents=True)
    (module_dir / "pom.xml").write_text("<project/>", encoding="utf-8")
    calls = []

    def fake_invoke_maven(work_dir, goals, label, config, log_dir):
        calls.append((work_dir, goals, label))
        return {
            "exit_code": 0,
            "status": "PASS",
            "log": f"{log_dir}/maven.log",
            "started_at": "2026-06-30T10:00:00",
            "ended_at": "2026-06-30T10:00:01",
            "duration_seconds": 1,
        }

    monkeypatch.setattr(jacov_compile.runner, "invoke_maven", fake_invoke_maven)
    result = jacov_compile.compile_project(project, str(tmp_path))

    assert result["status"] == "PASS"
    assert result["strategy"] == "default"
    assert result["log_dir"].endswith("target\\maven-logs") or result["log_dir"].endswith("target/maven-logs")
    assert [call[1] for call in calls] == [["clean"], ["compile"]]
    assert len(result["steps"]) == 2
    assert result["steps"][0]["progress"] == "1/2"


def test_compile_shared_jar_runs_install_skip_tests(tmp_path, monkeypatch):
    project = "fanyajw-shared-jar"
    module_dir = tmp_path / project / project
    module_dir.mkdir(parents=True)
    (module_dir / "pom.xml").write_text("<project/>", encoding="utf-8")
    calls = []

    def fake_invoke_maven(work_dir, goals, label, config, log_dir):
        calls.append(goals)
        return {
            "exit_code": 0,
            "status": "PASS",
            "log": f"{log_dir}/maven.log",
            "started_at": "2026-06-30T10:00:00",
            "ended_at": "2026-06-30T10:00:01",
            "duration_seconds": 1,
        }

    monkeypatch.setattr(jacov_compile.runner, "invoke_maven", fake_invoke_maven)
    result = jacov_compile.compile_project(project, str(tmp_path))

    assert result["status"] == "PASS"
    assert calls == [["clean"], ["install", "-Dmaven.test.skip=true"]]


def test_compile_rpc_runs_seven_steps(tmp_path, monkeypatch):
    project = "fanyajwproject-rpc"
    for rel in (project, f"{project}/{project}-api", f"{project}/{project}-svc"):
        module_dir = tmp_path / rel
        module_dir.mkdir(parents=True)
        (module_dir / "pom.xml").write_text("<project/>", encoding="utf-8")
    calls = []

    def fake_invoke_maven(work_dir, goals, label, config, log_dir):
        calls.append((work_dir, goals, label))
        return {
            "exit_code": 0,
            "status": "PASS",
            "log": f"{log_dir}/maven.log",
            "started_at": "2026-06-30T10:00:00",
            "ended_at": "2026-06-30T10:00:01",
            "duration_seconds": 1,
        }

    monkeypatch.setattr(jacov_compile.runner, "invoke_maven", fake_invoke_maven)
    result = jacov_compile.compile_project(project, str(tmp_path))

    assert result["status"] == "PASS"
    assert result["strategy"] == "rpc"
    assert len(calls) == 7
    assert result["steps"][6]["progress"] == "7/7"
    assert [call[1] for call in calls] == [
        ["clean"],
        ["clean"],
        ["clean"],
        ["install"],
        ["compile"],
        ["compile"],
        ["install"],
    ]


def test_compile_stops_when_pom_is_missing(tmp_path):
    result = jacov_compile.compile_project("fanyajwproject-course-v2", str(tmp_path))
    assert result["status"] == "FAIL"
    assert result["steps"][0]["status"] == "FAIL"
    assert "POM not found" in result["steps"][0]["error"]


def test_compile_short_name_uses_registered_strategy(tmp_path, monkeypatch):
    # 传短名 course-v2 也按注册的 default 策略（双层同名目录）编译
    full = "fanyajwproject-course-v2"
    module_dir = tmp_path / full / full
    module_dir.mkdir(parents=True)
    (module_dir / "pom.xml").write_text("<project/>", encoding="utf-8")
    calls = []

    def fake_invoke_maven(work_dir, goals, label, config, log_dir):
        calls.append(goals)
        return {"exit_code": 0, "status": "PASS", "log": f"{log_dir}/maven.log",
                "started_at": "2026-06-30T10:00:00", "ended_at": "2026-06-30T10:00:01", "duration_seconds": 1}

    monkeypatch.setattr(jacov_compile.runner, "invoke_maven", fake_invoke_maven)
    result = jacov_compile.compile_project("course-v2", str(tmp_path))

    assert result["status"] == "PASS"
    assert result["strategy"] == "default"
    assert result["project"] == full
    assert [g for g in calls] == [["clean"], ["compile"]]


def test_compile_unregistered_path_uses_path_strategy(tmp_path, monkeypatch):
    # 未注册的任意嵌套目录（含 pom.xml）走 path 策略 clean+compile
    module_dir = tmp_path / "projects" / "group" / "log-agent-server"
    module_dir.mkdir(parents=True)
    (module_dir / "pom.xml").write_text("<project/>", encoding="utf-8")
    calls = []

    def fake_invoke_maven(work_dir, goals, label, config, log_dir):
        calls.append((work_dir, goals))
        return {"exit_code": 0, "status": "PASS", "log": f"{log_dir}/maven.log",
                "started_at": "2026-06-30T10:00:00", "ended_at": "2026-06-30T10:00:01", "duration_seconds": 1}

    monkeypatch.setattr(jacov_compile.runner, "invoke_maven", fake_invoke_maven)
    result = jacov_compile.compile_project("projects/group/log-agent-server", str(tmp_path))

    assert result["status"] == "PASS"
    assert result["strategy"] == "path"
    assert [goals for _, goals in calls] == [["clean"], ["compile"]]
    assert all(work_dir == str(module_dir) for work_dir, _ in calls)


def test_compile_unknown_target_raises(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="未注册的项目"):
        jacov_compile.compile_project("totally-unknown-thing", str(tmp_path))


def test_compile_unknown_strategy_raises(tmp_path):
    # 显式传非法 strategy：进策略分支后被前置卫语句挡下（覆盖未知策略 raise）
    with pytest.raises(ValueError, match="未知策略"):
        jacov_compile.compile_project("fanyajwproject-course-v2", str(tmp_path), strategy="bogus")


def _make_pom(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "pom.xml").write_text("<project/>", encoding="utf-8")


def test_compile_module_runs_clean_compile(tmp_path, monkeypatch):
    module = tmp_path / "m"
    _make_pom(module)
    invoke, calls = _fake_maven()
    monkeypatch.setattr(jacov_compile.runner, "invoke_maven", invoke)
    result = jacov_compile.compile_module(str(module))
    assert result["status"] == "PASS"
    assert result["module_dir"] == str(module)
    assert [goals for _, goals, _ in calls] == [["clean", "compile"]]


def test_compile_rpc_stops_on_step_failure(tmp_path, monkeypatch):
    project = "fanyajwproject-rpc"
    for rel in (project, f"{project}/{project}-api", f"{project}/{project}-svc"):
        _make_pom(tmp_path / rel)
    invoke, calls = _fake_maven(exit_code=1)
    monkeypatch.setattr(jacov_compile.runner, "invoke_maven", invoke)
    result = jacov_compile.compile_project(project, str(tmp_path))
    assert result["status"] == "FAIL"
    assert len(result["steps"]) == 1  # 第一步失败即停，覆盖 _build_rpc 提前返回


def test_compile_path_stops_when_clean_fails(tmp_path, monkeypatch):
    module = tmp_path / "projects" / "x"
    _make_pom(module)
    invoke, _ = _fake_maven(exit_code=1)
    monkeypatch.setattr(jacov_compile.runner, "invoke_maven", invoke)
    result = jacov_compile.compile_project("projects/x", str(tmp_path))
    assert result["status"] == "FAIL"
    assert len(result["steps"]) == 1  # clean 失败即停，覆盖 _build_path 提前返回


def test_main_returns_zero_on_pass(tmp_path, monkeypatch, capsys):
    project = "fanyajwproject-course-v2"
    _make_pom(tmp_path / project / project)
    invoke, _ = _fake_maven()
    monkeypatch.setattr(jacov_compile.runner, "invoke_maven", invoke)
    rc = jacov_compile.main([project, "--workspace-root", str(tmp_path)])
    assert rc == 0
    assert "项目编译结果" in capsys.readouterr().out


def test_main_returns_one_on_fail(tmp_path, capsys):
    # pom 缺失 → 步骤 FAIL → 退出码 1（覆盖 main FAIL 分支 + _print_summary 的 error 打印）
    rc = jacov_compile.main(["fanyajwproject-course-v2", "--workspace-root", str(tmp_path)])
    assert rc == 1
    assert "POM not found" in capsys.readouterr().out


def test_main_returns_one_on_value_error(tmp_path, capsys):
    rc = jacov_compile.main(["totally-unknown-thing", "--workspace-root", str(tmp_path)])
    assert rc == 1
    assert "Error:" in capsys.readouterr().err
