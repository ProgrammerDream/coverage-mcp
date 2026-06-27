"""按业务包自动收集测试类与业务类，免去手列一长串类名。"""
from __future__ import annotations

import os


def collect_package(module_dir, package):
    """给业务包（如 'fanya/schedule' 或 'fanya.schedule'），收集业务类与测试类的简单名。

    业务类 = src/main/java/<包> 下全部 .java；测试类 = src/test/java/<包> 下全部 *Test.java。
    返回 (test_classes, cover_classes)，均按名排序。
    """
    pkg_path = package.replace(".", "/").strip("/")
    main_root = os.path.join(module_dir, "src", "main", "java", pkg_path)
    test_root = os.path.join(module_dir, "src", "test", "java", pkg_path)
    cover_classes = _collect_class_names(main_root, "")
    test_classes = _collect_class_names(test_root, "Test")
    return test_classes, cover_classes


def _collect_class_names(root, suffix):
    """递归收集目录下 .java 的简单类名（去 .java）；suffix 非空时只取以其结尾者。"""
    if not os.path.isdir(root):
        return []
    names = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            name = _class_name(filename, suffix)
            if name:
                names.append(name)
    return sorted(names)


def _class_name(filename, suffix):
    """文件名 → 简单类名；非 .java / package-info / 不匹配 suffix 则返回空串表示跳过。"""
    if not filename.endswith(".java"):
        return ""
    name = filename[:-5]
    if name == "package-info":
        return ""
    if suffix and not name.endswith(suffix):
        return ""
    return name
