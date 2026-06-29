"""
课程报告生成工具 - 应用入口

启动顺序：
  1. 初始化日志
  2. 加载配置
  3. 启动 FastAPI 后端服务
  4. (计划中) 启动 pywebview 桌面窗口
"""
from __future__ import annotations

import sys

import uvicorn

from backend.config import get_settings
from backend.utils.logger import get_logger, setup_logging


def main() -> int:
    """应用主入口。"""
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
        log.info(
            "FastAPI 服务: http://%s:%d",
            settings.server.host,
            settings.server.port,
        )
        log.info("API 文档: http://%s:%d/docs", settings.server.host, settings.server.port)

        uvicorn.run(
            "backend.app:app",
            host=settings.server.host,
            port=settings.server.port,
            reload=settings.server.reload,
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
