"""
课程报告生成工具 - 应用入口

启动顺序：
  1. 初始化日志
  2. 加载配置
  3. 启动 FastAPI 后端服务
  4. (计划中) 启动 pywebview 桌面窗口
"""
from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from backend.config import get_settings
from backend.utils.logger import get_logger, setup_logging


def _ensure_data_dir() -> None:
    """打包模式下切换到 exe 同级目录，确保 ./data/ 路径正确。"""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        os.chdir(str(exe_dir))


def _schedule_browser_open(url: str, delay: float = 1.5) -> None:
    """延迟打开默认浏览器访问应用 URL。

    延迟是为了等 uvicorn 完成 socket 绑定，否则浏览器会先撞到拒绝连接。
    通过 CRG_NO_BROWSER=1 环境变量可以关闭（CI/测试场景用）。
    """
    if os.environ.get("CRG_NO_BROWSER") == "1":
        return

    def _open() -> None:
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            # 浏览器打开失败不影响主进程
            pass

    threading.Thread(target=_open, daemon=True, name="browser-launcher").start()


def main() -> int:
    """应用主入口。"""
    _ensure_data_dir()

    # 1. 初始化日志
    setup_logging()
    log = get_logger("main")

    settings = get_settings()
    log.info(
        "%s v%s 启动中... (Python %s)",
        settings.app.name,
        settings.app.version,
        sys.version.split()[0],
    )

    try:
        # 2. 启动 FastAPI 服务
        # 打包模式下强制关闭 reload：uvicorn 的 reload 机制会 fork/spawn
        # 子进程重新 import app，对 frozen 可执行文件无效且会找不到 backend.app
        is_frozen = getattr(sys, "frozen", False)
        reload_enabled = settings.server.reload and not is_frozen
        if is_frozen and settings.server.reload:
            log.info("检测到打包模式，强制关闭 reload")

        log.info(
            "FastAPI 服务: http://%s:%d",
            settings.server.host,
            settings.server.port,
        )
        log.info("API 文档: http://%s:%d/docs", settings.server.host, settings.server.port)

        # 自动打开默认浏览器（可通过 CRG_NO_BROWSER=1 关闭）
        _schedule_browser_open(
            f"http://{settings.server.host}:{settings.server.port}"
        )

        uvicorn.run(
            "backend.app:app",
            host=settings.server.host,
            port=settings.server.port,
            reload=reload_enabled,
            log_config=None,  # 使用我们自己的日志配置
        )
        return 0

    except KeyboardInterrupt:
        log.info("用户中断，正在退出...")
        return 0
    except Exception as e:
        log.exception("启动失败: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
