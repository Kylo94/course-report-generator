"""
课程报告生成工具 - 应用入口

启动顺序：
  1. 初始化日志
  2. 加载配置
  3. 启动后端服务（FastAPI）
  4. 启动 pywebview 桌面窗口（计划中）
"""
from __future__ import annotations

import sys

from backend.utils.logger import get_logger, setup_logging


def main() -> int:
    """应用主入口。"""
    # 1. 初始化日志
    setup_logging()
    log = get_logger("main")

    log.info("课程报告生成工具启动中... (Python %s)", sys.version.split()[0])

    try:
        # 2. 加载配置
        from backend.config import get_settings
        settings = get_settings()
        log.info("配置加载完成: app=%s v%s", settings.app.name, settings.app.version)

        # 3. 启动后端服务（占位 - 将在 v0.4.0 完整实现）
        log.info("P0 阶段：项目脚手架已完成，AI 集成将在 v0.4.0 启用")
        log.info("下一步：v0.2.0 - 学生/班级管理")

        return 0

    except Exception as e:
        log.exception("启动失败: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
