#!/usr/bin/env python3
"""
构建脚本：打包课程报告生成工具为可分发应用。

用法：
    python build.py               # 构建当前平台包
    python build.py --clean       # 清理后构建
    python build.py --no-chrome   # 不打包 Chromium（需用户自行安装）

工作流程：
  1. 安装/验证依赖
  2. 确保 Playwright Chromium 已安装
  3. 运行 PyInstaller 打包
  4. （可选）将 Chromium 复制到输出目录
  5. 输出构建报告
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DIST_DIR = PROJECT_ROOT / "dist"
APP_NAME = "课程报告生成工具"


def log(msg: str) -> None:
    print(f"  → {msg}")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, **kwargs)


# ── 步骤 1: 环境检测 ──
def check_environment() -> None:
    print("\n📋 环境检测")
    log(f"Python: {sys.version.split()[0]}")
    log(f"平台: {sys.platform}")

    # 检查 PyInstaller
    try:
        import PyInstaller  # noqa: F401
        log("PyInstaller: ✓")
    except ImportError:
        log("PyInstaller 未安装，正在安装...")
        run([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 检查 Playwright
    try:
        import playwright  # noqa: F401
        log("Playwright: ✓")
    except ImportError:
        log("Playwright 未安装，正在安装...")
        run([sys.executable, "-m", "pip", "install", "playwright"])


# ── 步骤 2: Chromium ──
def ensure_chromium() -> None:
    print("\n🌐 Playwright Chromium")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or "already" in result.stdout.lower():
        log("Chromium 已安装: ✓")
    else:
        log("正在安装 Chromium（首次安装约 150MB）...")
        run([sys.executable, "-m", "playwright", "install", "chromium"])


# ── 步骤 3: 获取 Chromium 路径 ──
def find_chromium_exe() -> Path | None:
    """查找 Playwright 安装的 Chromium 可执行文件。"""
    # 典型的缓存路径
    cache_candidates = []
    if sys.platform == "darwin":
        cache_candidates.append(Path.home() / "Library" / "Caches" / "ms-playwright")
    elif sys.platform == "win32":
        cache_candidates.append(Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright")
        cache_candidates.append(Path.home() / "AppData" / "Local" / "ms-playwright")
    else:
        cache_candidates.append(Path.home() / ".cache" / "ms-playwright")

    for cache_dir in cache_candidates:
        if not cache_dir.exists():
            continue
        for entry in cache_dir.iterdir():
            if not entry.name.startswith("chromium-") or not entry.is_dir():
                continue
            # 递归查找可执行文件
            for f in entry.rglob("*"):
                if f.is_file() and f.name in ("Chromium", "chrome", "chrome.exe", "Google Chrome for Testing"):
                    if os.access(str(f), os.X_OK) or f.suffix == ".exe":
                        log(f"找到 Chromium: {f}")
                        return f
    return None


def copy_chromium(chromium_exe: Path, dist_exe_dir: Path) -> None:
    """将 Chromium 复制到打包目录。"""
    target_dir = dist_exe_dir / "browser"
    log(f"正在复制 Chromium 到 {target_dir}...")

    # Chromium 需要整个目录（包含框架、资源等），不仅仅是可执行文件
    browser_root = chromium_exe.parent
    # 向上找到 chrome-mac / chrome-win / chrome-linux 目录
    while browser_root.name not in ("chrome-mac", "chrome-mac-arm64", "chrome-win", "chrome-linux") and browser_root.parent != browser_root:
        browser_root = browser_root.parent

    target_browser = target_dir / browser_root.name
    if target_browser.exists():
        log("Chromium 已存在，跳过复制（执行 --clean 强制重新复制）")
        return

    target_browser.parent.mkdir(parents=True, exist_ok=True)
    # 使用系统 cp/symlink 而非 shutil.copytree（Chromium 可能很大）
    if sys.platform == "darwin":
        # macOS 上使用 ditto 保留符号链接和属性
        run(["ditto", str(browser_root), str(target_browser)])
    else:
        shutil.copytree(str(browser_root), str(target_browser), ignore_dangling_symlinks=True)
    log(f"Chromium 已复制 ({_dir_size(target_browser) // 1024 // 1024} MB)")


def _dir_size(path: Path) -> int:
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


# ── 步骤 4: 构建 ──
def run_pyinstaller(clean: bool = False) -> Path:
    print("\n🔨 PyInstaller 构建")
    if clean and DIST_DIR.exists():
        log("清理 dist/")
        shutil.rmtree(DIST_DIR)

    spec = PROJECT_ROOT / "build.spec"
    if not spec.exists():
        log(f"错误: build.spec 不存在")
        sys.exit(1)

    run([sys.executable, "-m", "PyInstaller", str(spec), "--noconfirm"])

    # 查找构建产物
    if sys.platform == "darwin":
        # macOS 下同时有 .app 和 exe 目录
        app_bundle = DIST_DIR / f"{APP_NAME}.app"
        exe_dir = DIST_DIR / APP_NAME
        if app_bundle.exists():
            log(f"macOS .app 包: {app_bundle}")
        if exe_dir.exists():
            log(f"可执行目录: {exe_dir}")
            return exe_dir
        return app_bundle if app_bundle.exists() else exe_dir
    else:
        exe_dir = DIST_DIR / APP_NAME
        if exe_dir.exists():
            log(f"可执行目录: {exe_dir}")
            return exe_dir
        log(f"错误: 构建产物未找到")
        sys.exit(1)


# ── 步骤 5: 输出报告 ──
def print_report(exe_dir: Path, with_chrome: bool) -> None:
    print("\n✅ 构建完成")
    print(f"   输出目录: {exe_dir}")

    total = _dir_size(exe_dir)
    print(f"   总大小:   {total // 1024 // 1024} MB")

    if sys.platform == "darwin" and exe_dir.suffix == ".app":
        exe_path = exe_dir / "Contents" / "MacOS" / APP_NAME
        print(f"   入口:     {exe_path}")
    else:
        exe_path = exe_dir / (APP_NAME + ".exe" if sys.platform == "win32" else APP_NAME)
        print(f"   入口:     {exe_path}")
        print(f"   用法:     双击 {exe_path.name} 启动，浏览器打开 http://127.0.0.1:8765")

    if with_chrome:
        chrome_size = _dir_size(exe_dir / "browser") if (exe_dir / "browser").exists() else 0
        print(f"   其中 Chromium: {chrome_size // 1024 // 1024} MB")
    else:
        print(f"   注意: 未打包 Chromium")
        print(f"         用户需自行安装: python -m playwright install chromium")

    print()


# ════════════════════════════════════
# Main
# ════════════════════════════════════
def main() -> None:
    parser = argparse.ArgumentParser(description="构建课程报告生成工具")
    parser.add_argument("--clean", action="store_true", help="清理 dist/ 后构建")
    parser.add_argument("--no-chrome", action="store_true", help="不打包 Chromium（需用户自行安装）")
    args = parser.parse_args()

    print(f"📦 {APP_NAME} 构建脚本")
    print(f"   版本: 1.0.0")
    print(f"   目录: {PROJECT_ROOT}")

    check_environment()

    if not args.no_chrome:
        ensure_chromium()

    exe_dir = run_pyinstaller(clean=args.clean)

    with_chrome = False
    if not args.no_chrome:
        chromium_exe = find_chromium_exe()
        if chromium_exe:
            dist_exe_dir = exe_dir if exe_dir.is_dir() else exe_dir.parent
            copy_chromium(chromium_exe, dist_exe_dir)
            with_chrome = True
        else:
            log("警告: 未找到 Chromium 可执行文件，跳过打包")

    print_report(exe_dir, with_chrome)


if __name__ == "__main__":
    main()
