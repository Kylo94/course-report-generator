# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置文件。

用法（macOS/Linux）：
    pyinstaller build.spec

用法（Windows）：
    pyinstaller build.spec

打包前请确保已安装 Playwright 和 Chromium：
    uv add playwright
    python -m playwright install chromium

输出目录：dist/course-report-generator/
"""
from __future__ import annotations

import platform
from pathlib import Path

# ── 项目根目录 ──
PROJECT_ROOT = Path(__file__).resolve().parent

# ── 应用元信息 ──
APP_NAME = "课程报告生成工具"
APP_VERSION = "1.0.0"

# ── 要排除的标准库模块（减小体积） ──
EXCLUDES = [
    "tkinter",
    "test",
    "unittest",
    "email",
    "http.server",
    "distutils",
    "lib2to3",
    "multiprocessing",
    "pdb",  # 调试器
    "pydoc",
    "curses",
    "venv",
    "ensurepip",
]

# ── 隐藏 import（PyInstaller 可能找不到的隐式依赖） ──
HIDDEN_IMPORTS = [
    # FastAPI 运行时动态加载的模块
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    # FastAPI 依赖
    "starlette.middleware",
    "starlette.staticfiles",
    # sqlalchemy
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.sql.default_comparator",
    "aiosqlite",
    # pydantic 运行时
    "pydantic_settings",
    "pydantic",
    # Playwright
    "playwright.async_api",
    "playwright.sync_api",
    # yaml
    "yaml",
]

# ── 数据文件（需随应用一起分发的资源） ──
def _collect_data_files() -> list[tuple[str, str]]:
    """返回 [(源路径, 目标目录), ...] 列表。"""
    files = []

    # 前端静态文件
    frontend_dir = PROJECT_ROOT / "frontend"
    if frontend_dir.exists():
        files.append((str(frontend_dir), "frontend"))

    # 报告模板
    templates_dir = PROJECT_ROOT / "templates"
    if templates_dir.exists():
        files.append((str(templates_dir), "templates"))

    # 配置文件
    config_dir = PROJECT_ROOT / "config"
    if config_dir.exists():
        files.append((str(config_dir / "app.yaml"), "config"))
        # llm.yaml.example 作为配置模板
        example = config_dir / "llm.yaml.example"
        if example.exists():
            files.append((str(example), "config"))
        else:
            # 回退：生成一个示例
            pass

    return files


# ════════════════════════════════════════════
# Analysis
# ════════════════════════════════════════════
a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=_collect_data_files(),
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    excludes=EXCLUDES,
    noarchive=False,
    optimize=1,
)

# ════════════════════════════════════════════
# PYZ（压缩字节码）
# ════════════════════════════════════════════
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# ════════════════════════════════════════════
# EXE（可执行文件）
# ════════════════════════════════════════════
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,          # 开发调试时保留控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "frontend" / "favicon.ico") if (PROJECT_ROOT / "frontend" / "favicon.ico").exists() else None,
)

# ════════════════════════════════════════════
# macOS: 生成 .app 包
# ════════════════════════════════════════════
if platform.system() == "Darwin":
    app = BUNDLE(
        exe,
        name=f"{APP_NAME}.app",
        icon=None,
        display_name=APP_NAME,
        version=APP_VERSION,
        bundle_identifier="com.course-report-generator.app",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": APP_VERSION,
        },
    )
