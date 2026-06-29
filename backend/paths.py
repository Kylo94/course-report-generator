"""
应用路径解析：兼容开发模式与 PyInstaller 打包模式。

在开发时使用 `__file__` 推导项目根目录，
在 PyInstaller 打包后使用 `sys._MEIPASS` 获取解压目录。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _is_frozen() -> bool:
    """是否运行在 PyInstaller 打包环境中。"""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _meipass() -> Path:
    """PyInstaller 解压临时目录。"""
    return Path(sys._MEIPASS)


def _dev_root() -> Path:
    """开发模式下后端模块所在目录的父级。"""
    return Path(__file__).resolve().parent.parent


def get_app_root() -> Path:
    """应用根目录（含 frontend/、templates/、config/、main.py 的目录）。"""
    if _is_frozen():
        return _meipass()
    return _dev_root()


def get_data_root() -> Path:
    """运行期数据目录（SQLite、报告、截图、Logo 等）。

    打包模式下默认与应用同级目录下的 data/ 文件夹。
    用户可通过环境变量 CRG_REPORT__OUTPUT_DIR 等覆盖各个路径。
    """
    if _is_frozen():
        # 打包后数据目录不能放在临时解压目录，放在 exe 同级
        return Path(sys.executable).resolve().parent / "data"
    return get_app_root() / "data"


def get_user_config_dir() -> Path:
    """用户可编辑的配置目录。

    打包模式下返回 exe 同级 config/ 目录，
    开发模式下返回项目 config/ 目录。
    """
    if _is_frozen():
        return Path(sys.executable).resolve().parent / "config"
    return get_app_root() / "config"


def get_chromium_path() -> str | None:
    """查找 Playwright Chromium 可执行文件路径。

    打包模式下尝试从 exe 同级 browser/ 目录查找 Chromium，
    否则返回 None（Playwright 自动从缓存加载）。
    """
    base = _get_browser_dir()
    if base is None:
        return None

    # 递归查找常见的 Chromium 可执行文件名
    targets = ("Chromium", "chrome", "chrome.exe", "Google Chrome for Testing")
    for f in base.rglob("*"):
        if f.is_file() and f.name in targets and (os.access(str(f), os.X_OK) or f.suffix == ".exe"):
            return str(f)

    return None


def _get_browser_dir() -> Path | None:
    """打包模式下 browser/ 目录的路径。"""
    if not _is_frozen():
        return None
    base = Path(sys.executable).resolve().parent / "browser"
    return base if base.exists() else None
