"""runtests 入口离线测试：验证模块解析与返回码，mock 掉真实 Maven 测试执行。"""
import types
from pathlib import Path

import pytest

from jacov import runtests


def _args(**kw):
    base = {"module_dir": "", "module": "", "workspace_root": "",
            "tests": "", "package": "", "no_compile": False, "no_reuse": False}
    base.update(kw)
    return types.SimpleNamespace(**base)


def _ok_result(module="m"):
    return {"status": "PASS", "module": module, "suites": 1, "tests": 1,
            "passed": 1, "failures": 0, "errors": 0, "skipped": 0, "failed_suites": []}


def test_resolve_prefers_explicit_module_dir():
    assert runtests._resolve_module_dir(_args(module_dir="/some/dir")) == "/some/dir"


def test_resolve_module_short_name(tmp_path):
    module_dir = runtests._resolve_module_dir(_args(module="course-v2", workspace_root=str(tmp_path)))
    assert Path(module_dir).parts[-2:] == ("fanyajwproject-course-v2", "fanyajwproject-course-v2")


def test_resolve_unresolvable_module_raises(tmp_path):
    with pytest.raises(ValueError, match="无法解析模块"):
        runtests._resolve_module_dir(_args(module="nope/not/here", workspace_root=str(tmp_path)))


def test_resolve_requires_module_or_dir():
    with pytest.raises(ValueError, match="必须提供"):
        runtests._resolve_module_dir(_args())


def test_main_returns_zero_on_pass(tmp_path, monkeypatch, capsys):
    captured = {}

    def fake_run_tests(module_dir, *args, **kwargs):
        captured["module_dir"] = module_dir
        return _ok_result(module_dir)

    monkeypatch.setattr(runtests.check, "run_tests", fake_run_tests)
    rc = runtests.main(["--module", "course-v2", "--workspace-root", str(tmp_path)])
    assert rc == 0
    assert "fanyajwproject-course-v2" in captured["module_dir"]
    assert "测试结果汇总" in capsys.readouterr().out


def test_main_returns_one_on_unresolvable(tmp_path, capsys):
    rc = runtests.main(["--module", "nope/x", "--workspace-root", str(tmp_path)])
    assert rc == 1
    assert "Error:" in capsys.readouterr().err


def test_main_returns_one_on_fail(tmp_path, monkeypatch):
    failed = {"status": "FAIL", "module": "m", "suites": 1, "tests": 1, "passed": 0,
              "failures": 1, "errors": 0, "skipped": 0, "failed_suites": ["FooTest"]}
    monkeypatch.setattr(runtests.check, "run_tests", lambda *a, **k: failed)
    rc = runtests.main(["--module-dir", str(tmp_path)])
    assert rc == 1
