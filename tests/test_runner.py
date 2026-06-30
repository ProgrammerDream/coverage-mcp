"""runner 离线测试：mock subprocess 与 env，覆盖 Maven 执行引擎的每条分支（不真跑 mvn）。"""
import pytest

from jacov import runner


class _FakeProc:
    """假 subprocess.Popen：按行吐 stdout、可 wait、带 returncode。"""

    def __init__(self, lines, returncode):
        self.stdout = iter(lines)
        self.returncode = returncode

    def wait(self):
        return self.returncode


def _patch_maven(monkeypatch, lines, returncode):
    monkeypatch.setattr(runner.env, "find_maven", lambda config: "mvn")
    monkeypatch.setattr(runner.env, "maven_opts", lambda config: [])
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: _FakeProc(lines, returncode))


# ── _invoke_maven：成功 / 失败两条输出分支 ──

def test_invoke_maven_success_streams_key_lines(tmp_path, monkeypatch, capsys):
    lines = ["[INFO] Building x\n", "[INFO] BUILD SUCCESS\n", "随便的非关键行\n"]
    _patch_maven(monkeypatch, lines, 0)
    log_dir = str(tmp_path / "logs")
    result = runner.invoke_maven(str(tmp_path), ["compile"], "[1/1] 编译", config={}, log_dir=log_dir)
    assert result["exit_code"] == 0
    assert result["status"] == "PASS"
    out = capsys.readouterr().out
    assert "── [1/1] 编译" in out
    assert "BUILD SUCCESS" in out          # 关键行透传
    assert "随便的非关键行" not in out      # 非关键行被过滤
    assert "[PASS] 用时" in out
    assert "日志:" not in out               # 成功不附日志路径


def test_invoke_maven_failure_appends_log(tmp_path, monkeypatch, capsys):
    lines = ["[ERROR] boom\n", "[INFO] BUILD FAILURE\n"]
    _patch_maven(monkeypatch, lines, 1)
    result = runner.invoke_maven(str(tmp_path), ["compile"], "[1/1] 编译", config={}, log_dir=str(tmp_path / "l"))
    assert result["exit_code"] == 1
    assert result["status"] == "FAIL(exit 1)"
    out = capsys.readouterr().out
    assert "[FAIL(exit 1)] 用时" in out
    assert "日志:" in out                   # 失败才附日志路径


def test_invoke_maven_defaults_config_and_logdir(tmp_path, monkeypatch):
    # config=None → load_config；log_dir="" → 默认 module_dir/target/maven-logs
    monkeypatch.setattr(runner.env, "load_config", lambda module_dir: {})
    _patch_maven(monkeypatch, ["[INFO] BUILD SUCCESS\n"], 0)
    result = runner.invoke_maven(str(tmp_path), ["clean"], "[1/1] 清理")
    assert result["exit_code"] == 0
    assert result["log"].endswith(".log")


# ── 顶层入口：run_coverage / run_tests（mock 掉真正的 _invoke_maven）──

def test_run_coverage_builds_report_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.env, "load_config", lambda module_dir: {
        "jacoco_version": "0.8.11", "jacoco_excludes": "", "add_opens": ["java.base/java.lang"]})
    monkeypatch.setattr(runner, "_invoke_maven", lambda *a, **k: {"exit_code": 0})
    out = runner.run_coverage(str(tmp_path), ["FooTest"], compile_first=True, reuse_forks=False)
    assert out["test_ok"] is True
    assert out["csv"].endswith("jacoco.csv")
    assert out["xml"].endswith("jacoco.xml")


def test_run_tests_specified_and_full(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.env, "load_config", lambda module_dir: {})
    monkeypatch.setattr(runner, "_invoke_maven", lambda *a, **k: {"exit_code": 0})
    # 指定测试类
    assert runner.run_tests(str(tmp_path), ["FooTest"])["test_ok"] is True
    # 全量（test_classes 为空）+ 触发清理已存在的 surefire-reports
    reports = tmp_path / "target" / "surefire-reports"
    reports.mkdir(parents=True)
    assert runner.run_tests(str(tmp_path), [])["test_ok"] is True
    assert not reports.exists()


# ── 纯函数分支：goals 构造 / 关键行识别 / 平台命令 / 耗时格式 / 清理 ──

def test_coverage_goals_variants():
    cfg = {"jacoco_version": "0.8.11", "jacoco_excludes": "com.x.*", "add_opens": ["java.base/java.lang"]}
    goals = runner._coverage_goals("FooTest", "/tmp/exec", compile_first=True, reuse_forks=True, config=cfg)
    assert "test" in goals
    assert any("prepare-agent" in g for g in goals)
    assert any("jacoco.excludes" in g for g in goals)       # 有 excludes 分支
    assert "-DreuseForks=true" in goals
    cfg2 = {"jacoco_version": "0.8.11", "jacoco_excludes": "", "add_opens": ["java.base/java.lang"]}
    goals2 = runner._coverage_goals("FooTest", "/tmp/exec", compile_first=False, reuse_forks=False, config=cfg2)
    assert "surefire:test" in goals2                          # compile_first=False 分支
    assert not any("jacoco.excludes" in g for g in goals2)    # 无 excludes 分支
    assert "-DreuseForks=false" in goals2


def test_test_goals_variants():
    goals = runner._test_goals(["FooTest"], compile_first=True, reuse_forks=True)
    assert "test" in goals
    assert any(g.startswith("-Dtest=") for g in goals)
    goals2 = runner._test_goals([], compile_first=False, reuse_forks=False)
    assert "surefire:test" in goals2
    assert not any(g.startswith("-Dtest=") for g in goals2)   # 空 test_classes 不加 -Dtest


def test_is_key_line_matches_and_rejects():
    assert runner._is_key_line("[ERROR] something")
    assert runner._is_key_line("foo BUILD SUCCESS")
    assert runner._is_key_line("foo BUILD FAILURE")
    assert runner._is_key_line("[INFO] Building module")
    assert runner._is_key_line("[INFO] Compiling 3 source files")
    assert runner._is_key_line("[INFO] Running fanya.FooTest")
    assert runner._is_key_line("Tests run: 5, Failures: 0")
    assert not runner._is_key_line("[INFO] plain noise line")


def test_platform_cmd_windows_and_posix(monkeypatch):
    monkeypatch.setattr(runner.os, "name", "nt")
    win = runner._platform_cmd(["mvn", "-X"])
    assert win.startswith('cmd /c "') and win.endswith('"')
    monkeypatch.setattr(runner.os, "name", "posix")
    assert runner._platform_cmd(["mvn", "-X"]) == ["mvn", "-X"]


def test_format_duration():
    assert runner._format_duration(0) == "0h 0m 0s"
    assert runner._format_duration(3661) == "1h 1m 1s"


def test_clean_stale_removes_reports_and_files(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    exec_file = target / "jacoco.exec"
    exec_file.write_text("x", encoding="utf-8")
    reports = target / "surefire-reports"
    reports.mkdir()
    missing = target / "not-there.csv"      # 不存在的也要安全跳过
    runner._clean_stale(str(target), (str(exec_file), str(missing)))
    assert not exec_file.exists()
    assert not reports.exists()
