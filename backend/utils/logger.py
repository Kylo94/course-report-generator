"""
日志系统

设计要点：
1. 控制台 + 文件双输出
2. 文件按大小滚动（RotatingFileHandler），避免单文件过大
3. 日志格式统一（时间、级别、模块、消息）
4. 异常堆栈自动记录
5. 可通过环境变量调整级别
"""
import logging
import logging.handlers
import os
import sys
from pathlib import Path

# 日志目录
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 日志格式
CONSOLE_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-30s | %(message)s"
FILE_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-30s | %(filename)s:%(lineno)d | %(message)s"

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 日志级别（可通过环境变量覆盖）
DEFAULT_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def setup_logging(
    level: str = DEFAULT_LEVEL,
    log_file: str = "app.log",
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> None:
    """
    初始化全局日志配置。

    - 控制台：INFO 以上，带颜色（简化版）
    - 文件：DEBUG 以上，按大小滚动，保留 5 个备份
    - 错误日志单独输出到 error.log
    """
    root = logging.getLogger()
    root.setLevel(level)

    # 清除已有 handler（避免重复添加）
    for h in list(root.handlers):
        root.removeHandler(h)

    formatter = logging.Formatter(FILE_FORMAT, DATE_FORMAT)

    # 控制台 handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(CONSOLE_FORMAT, DATE_FORMAT))
    root.addHandler(console)

    # 文件 handler（按大小滚动）
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # 错误日志单独输出
    error_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "error.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root.addHandler(error_handler)

    # 降低噪音库
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("multipart").setLevel(logging.WARNING)

    root.info("=" * 70)
    root.info("日志系统初始化完成 level=%s log_dir=%s", level, LOG_DIR)
    root.info("=" * 70)


def get_logger(name: str | None = None) -> logging.Logger:
    """获取命名 logger。"""
    return logging.getLogger(name)
