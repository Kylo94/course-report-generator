"""版本号单一来源测试。"""
from __future__ import annotations

import tomllib
from pathlib import Path

from backend.config import APP_VERSION, get_settings
from backend.version import __version__


def test_version_is_single_source() -> None:
    assert APP_VERSION == __version__
    assert get_settings().app.version == __version__


def test_pyproject_uses_dynamic_version() -> None:
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert "version" not in data["project"]
    assert data["project"]["dynamic"] == ["version"]
    assert data["tool"]["hatch"]["version"]["path"] == "backend/version.py"


def test_uv_lock_project_entry_is_dynamic() -> None:
    lock = Path("uv.lock").read_text(encoding="utf-8")
    # 动态版本项目在 uv.lock 里不写 version，由 backend/version.py 提供
    assert 'name = "course-report-generator"\nsource = { editable = "." }' in lock


def test_version_is_semver() -> None:
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
