"""collect_package 离线测试：按业务包自动收集业务类（main）与测试类（test）。"""
from jacov.collect import collect_package


def test_collect_package_splits_main_and_test(tmp_path):
    main = tmp_path / "src" / "main" / "java" / "fanya" / "schedule"
    main_service = main / "service"
    test_service = tmp_path / "src" / "test" / "java" / "fanya" / "schedule" / "service"
    for directory in (main, main_service, test_service):
        directory.mkdir(parents=True, exist_ok=True)

    (main / "AutoScheduleClassMode.java").write_text("", encoding="utf-8")
    (main_service / "ScheduleRunService.java").write_text("", encoding="utf-8")
    (main / "package-info.java").write_text("", encoding="utf-8")          # 应跳过
    (test_service / "ScheduleRunServiceTest.java").write_text("", encoding="utf-8")
    (test_service / "ScheduleFixture.java").write_text("", encoding="utf-8")  # 非 *Test，应跳过

    tests, cover = collect_package(str(tmp_path), "fanya.schedule")
    assert set(cover) == {"AutoScheduleClassMode", "ScheduleRunService"}
    assert set(tests) == {"ScheduleRunServiceTest"}


def test_collect_package_missing_dir_returns_empty(tmp_path):
    tests, cover = collect_package(str(tmp_path), "no/such/pkg")
    assert tests == []
    assert cover == []
