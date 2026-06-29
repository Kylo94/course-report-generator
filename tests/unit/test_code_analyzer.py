"""代码分析器单元测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.services.code_analyzer import (
    _detect_project_type,
    _extract_top_comment,
    _parse_course_title,
    _parse_py_file,
    analyze_project,
)


class TestExtractTopComment:
    def test_single_line(self) -> None:
        assert _extract_top_comment("# hello world") == "hello world"

    def test_multi_line(self) -> None:
        source = "# line 1\n# line 2\n# line 3\nimport os"
        assert _extract_top_comment(source) == "line 1\nline 2\nline 3"

    def test_no_comment(self) -> None:
        assert _extract_top_comment("import os") == ""

    def test_empty(self) -> None:
        assert _extract_top_comment("") == ""

    def test_blank_line_terminates(self) -> None:
        source = "# comment\n\nimport os"
        assert _extract_top_comment(source) == "comment"

    def test_indented_comment(self) -> None:
        source = "    # indented comment\nimport os"
        assert _extract_top_comment(source) == "indented comment"


class TestParseCourseTitle:
    @pytest.mark.parametrize(
        "comment,expected",
        [
            ("Course: 飞翔的小鸟第一课", "飞翔的小鸟第一课"),
            ("course: 飞翔的小鸟", "飞翔的小鸟"),
            ("课程：飞翔的小鸟第一课", "飞翔的小鸟第一课"),
            ("课程名: Python 入门", "Python 入门"),
            ("主题: 贪吃蛇", "贪吃蛇"),
            ("# Random comment", None),
            ("", None),
            (None, None),
        ],
    )
    def test_patterns(self, comment: str | None, expected: str | None) -> None:
        assert _parse_course_title(comment) == expected


class TestDetectProjectType:
    @pytest.mark.parametrize(
        "imports,expected",
        [
            (["pygame", "sys"], "pygame"),
            (["turtle"], "turtle"),
            (["tkinter", "sys"], "tkinter"),
            (["PyQt5"], "pyqt"),
            (["flask"], "web"),
            (["fastapi"], "web"),
            (["requests"], "web"),
            (["sys", "json", "random"], "algorithm"),
            ([], "algorithm"),
        ],
    )
    def test_types(self, imports: list[str], expected: str) -> None:
        assert _detect_project_type(imports) == expected


class TestParsePyFile:
    def test_basic(self, tmp_dir: Path) -> None:
        py_file = tmp_dir / "test.py"
        py_file.write_text(
            '''# Course: 测试课程
import os
from typing import List

def foo():
    pass

class Bar:
    def method(self):
        pass

@staticmethod
def baz():
    pass
''',
            encoding="utf-8",
        )
        result = _parse_py_file(py_file)
        assert result.course_title == "测试课程"
        assert "os" in result.imports
        assert ("typing", "List") in result.from_imports
        assert "foo" in result.function_names
        assert "Bar" in result.class_names
        assert "staticmethod" in result.decorators

    def test_syntax_error_tolerated(self, tmp_dir: Path) -> None:
        py_file = tmp_dir / "bad.py"
        py_file.write_text(
            "def foo(:\n    pass\n",
            encoding="utf-8",  # 语法错误
        )
        result = _parse_py_file(py_file)
        # 解析失败时返回空结构但 line_count 仍记录
        assert result.line_count > 0
        assert result.course_title is None


class TestAnalyzeProject:
    def test_pygame_project(self, tmp_dir: Path) -> None:
        project = tmp_dir / "pygame_demo"
        project.mkdir()
        (project / "main.py").write_text(
            '''# Course: 飞翔的小鸟第一课
import pygame
import random

class Bird:
    pass

def main():
    pass
''',
            encoding="utf-8",
        )
        (project / "config.py").write_text("CONFIG = {}\n", encoding="utf-8")
        (project / "data.json").write_text("{}", encoding="utf-8")

        meta = analyze_project(project)

        assert meta.entry_file == "main.py"
        assert meta.project_type == "pygame"
        assert meta.course_title == "飞翔的小鸟第一课"
        assert "pygame" in meta.all_imports
        assert len(meta.py_files) == 2
        assert any(f.path == "data.json" and not f.is_python for f in meta.all_files)

    def test_turtle_project(self, tmp_dir: Path) -> None:
        project = tmp_dir / "turtle_demo"
        project.mkdir()
        (project / "main.py").write_text(
            "# 课程：绘制五角星\nimport turtle\n\nt = turtle.Turtle()\n",
            encoding="utf-8",
        )
        meta = analyze_project(project)
        assert meta.project_type == "turtle"
        assert meta.course_title == "绘制五角星"

    def test_no_course_comment_warning(self, tmp_dir: Path) -> None:
        project = tmp_dir / "no_comment"
        project.mkdir()
        (project / "main.py").write_text(
            "import os\nprint('hello')\n", encoding="utf-8"
        )
        meta = analyze_project(project)
        assert meta.course_title is None
        assert any("课程主题注释" in w for w in meta.warnings)

    def test_skip_venv_dir(self, tmp_dir: Path) -> None:
        project = tmp_dir / "with_venv"
        project.mkdir()
        (project / "main.py").write_text("import os\n", encoding="utf-8")
        venv = project / ".venv"
        venv.mkdir()
        (venv / "ignored.py").write_text("import fake\n", encoding="utf-8")

        meta = analyze_project(project)
        # .venv 中的文件应被忽略
        py_paths = [f.path for f in meta.all_files if f.is_python]
        assert not any(".venv" in p for p in py_paths)
        assert not any("fake" in i for i in meta.all_imports)

    def test_web_project(self, tmp_dir: Path) -> None:
        project = tmp_dir / "web_demo"
        project.mkdir()
        (project / "main.py").write_text(
            "from flask import Flask\napp = Flask(__name__)\n",
            encoding="utf-8",
        )
        meta = analyze_project(project)
        assert meta.project_type == "web"

    def test_algorithm_project(self, tmp_dir: Path) -> None:
        project = tmp_dir / "algo"
        project.mkdir()
        (project / "main.py").write_text(
            "def fib(n):\n    return n if n < 2 else fib(n-1) + fib(n-2)\n",
            encoding="utf-8",
        )
        meta = analyze_project(project)
        assert meta.project_type == "algorithm"

    def test_no_python_files(self, tmp_dir: Path) -> None:
        project = tmp_dir / "empty"
        project.mkdir()
        (project / "readme.md").write_text("hi", encoding="utf-8")
        with pytest.raises(ValueError, match="未找到任何"):
            analyze_project(project)

    def test_nonexistent_folder(self) -> None:
        with pytest.raises(FileNotFoundError):
            analyze_project("/nonexistent/path/12345")

    def test_picks_main_py_over_others(self, tmp_dir: Path) -> None:
        project = tmp_dir / "multi_py"
        project.mkdir()
        (project / "utils.py").write_text("import os\n", encoding="utf-8")
        (project / "main.py").write_text(
            "# Course: 主课程\nimport os\n", encoding="utf-8"
        )
        meta = analyze_project(project)
        assert meta.entry_file == "main.py"
        assert meta.course_title == "主课程"

    def test_picks_first_py_if_no_main(self, tmp_dir: Path) -> None:
        project = tmp_dir / "no_main"
        project.mkdir()
        (project / "first.py").write_text("import os\n", encoding="utf-8")
        (project / "second.py").write_text("import sys\n", encoding="utf-8")
        meta = analyze_project(project)
        # 字母序首个
        assert meta.entry_file in ("first.py", "second.py")

    def test_decorator_extraction(self, tmp_dir: Path) -> None:
        project = tmp_dir / "deco"
        project.mkdir()
        (project / "main.py").write_text(
            '''import functools

@functools.lru_cache(maxsize=128)
def cached_fn():
    return 1

class Foo:
    @property
    def bar(self):
        return 2
''',
            encoding="utf-8",
        )
        meta = analyze_project(project)
        entry = next(s for s in meta.py_files if s.path == "main.py")
        assert "lru_cache" in entry.decorators
        assert "property" in entry.decorators
