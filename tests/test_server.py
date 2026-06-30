"""server MCP 入口离线测试：import 触发工具注册，验证两个工具转发与 run() 委托。"""
from jacov import server


def test_coverage_check_forwards_to_check(monkeypatch):
    monkeypatch.setattr(server.check, "check_coverage", lambda *a, **k: {"forwarded": "coverage"})
    assert server.coverage_check("/m", tests="FooTest")["forwarded"] == "coverage"


def test_compile_project_forwards_to_compile(monkeypatch):
    monkeypatch.setattr(server.jacov_compile, "compile_project", lambda *a, **k: {"forwarded": "compile"})
    assert server.compile_project("course-v2")["forwarded"] == "compile"


def test_run_delegates_to_mcp(monkeypatch):
    flag = {}
    monkeypatch.setattr(server.mcp, "run", lambda: flag.setdefault("ran", True))
    server.run()
    assert flag.get("ran") is True
