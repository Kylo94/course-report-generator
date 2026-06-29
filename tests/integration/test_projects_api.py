"""项目扫描 API 集成测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio


class TestScanProject:
    async def test_scan_pygame_project(self, api_client, tmp_dir: Path) -> None:
        project = tmp_dir / "demo"
        project.mkdir()
        (project / "main.py").write_text(
            '''# Course: 飞翔的小鸟第一课
import pygame
import random

class Bird:
    def __init__(self):
        self.y = 200
''',
            encoding="utf-8",
        )
        (project / "config.py").write_text("WIDTH = 800\n", encoding="utf-8")

        resp = await api_client.post(
            "/api/projects/scan", json={"folder": str(project)}
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["entry_file"] == "main.py"
        assert data["project_type"] == "pygame"
        assert data["course_title"] == "飞翔的小鸟第一课"
        assert "pygame" in data["all_imports"]
        assert data["total_lines"] > 0
        assert len(data["py_files"]) == 2
        assert len(data["all_files"]) == 2

    async def test_scan_with_warnings(self, api_client, tmp_dir: Path) -> None:
        project = tmp_dir / "no_comment"
        project.mkdir()
        (project / "main.py").write_text("import os\n", encoding="utf-8")

        resp = await api_client.post(
            "/api/projects/scan", json={"folder": str(project)}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["course_title"] is None
        assert any("课程主题" in w for w in data["warnings"])

    async def test_scan_nonexistent_folder(self, api_client) -> None:
        resp = await api_client.post(
            "/api/projects/scan",
            json={"folder": "/nonexistent/path/12345"},
        )
        assert resp.status_code == 404

    async def test_scan_not_a_directory(
        self, api_client, tmp_dir: Path
    ) -> None:
        file_path = tmp_dir / "a_file.py"
        file_path.write_text("import os\n", encoding="utf-8")

        resp = await api_client.post(
            "/api/projects/scan", json={"folder": str(file_path)}
        )
        assert resp.status_code == 400

    async def test_scan_empty_folder(self, api_client, tmp_dir: Path) -> None:
        empty = tmp_dir / "empty"
        empty.mkdir()

        resp = await api_client.post(
            "/api/projects/scan", json={"folder": str(empty)}
        )
        assert resp.status_code == 400

    async def test_scan_no_python_files(
        self, api_client, tmp_dir: Path
    ) -> None:
        no_py = tmp_dir / "no_py"
        no_py.mkdir()
        (no_py / "readme.md").write_text("hi", encoding="utf-8")

        resp = await api_client.post(
            "/api/projects/scan", json={"folder": str(no_py)}
        )
        assert resp.status_code == 400

    async def test_scan_validates_request(self, api_client) -> None:
        # folder 为空
        resp = await api_client.post(
            "/api/projects/scan", json={"folder": ""}
        )
        assert resp.status_code == 422

    async def test_scan_turtle_project(self, api_client, tmp_dir: Path) -> None:
        project = tmp_dir / "turtle_demo"
        project.mkdir()
        (project / "main.py").write_text(
            "# 课程：绘制五角星\nimport turtle\n",
            encoding="utf-8",
        )
        resp = await api_client.post(
            "/api/projects/scan", json={"folder": str(project)}
        )
        data = resp.json()
        assert data["project_type"] == "turtle"
        assert data["course_title"] == "绘制五角星"

    async def test_py_file_structure(self, api_client, tmp_dir: Path) -> None:
        project = tmp_dir / "structured"
        project.mkdir()
        (project / "main.py").write_text(
            '''# Course: 测试
import os
from typing import List

def foo():
    pass

class Bar:
    pass

@staticmethod
def baz():
    pass
''',
            encoding="utf-8",
        )
        resp = await api_client.post(
            "/api/projects/scan", json={"folder": str(project)}
        )
        data = resp.json()
        entry = next(f for f in data["py_files"] if f["path"] == "main.py")
        assert entry["course_title"] == "测试"
        assert "os" in entry["imports"]
        assert {"module": "typing", "name": "List"} in entry["from_imports"]
        assert "foo" in entry["function_names"]
        assert "Bar" in entry["class_names"]
        assert "staticmethod" in entry["decorators"]
