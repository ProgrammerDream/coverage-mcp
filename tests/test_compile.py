"""compile_project 离线测试：模拟 Maven 调用，只验证策略调度和返回结构。"""
from jacov import compile as jacov_compile


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
