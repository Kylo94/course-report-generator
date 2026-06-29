"""测试日志系统。"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from backend.utils.logger import get_logger, setup_logging


class TestSetupLogging:
    """测试 setup_logging 是否正确初始化。"""

    def test_setup_logging_creates_handlers(self) -> None:
        setup_logging(level="DEBUG")
        root = logging.getLogger()
        # 至少 3 个 handler：console + app.log + error.log
        assert len(root.handlers) >= 3

    def test_setup_logging_creates_log_files(self, tmp_path: Path, monkeypatch) -> None:
        # 重定向 LOG_DIR 到临时目录
        import backend.utils.logger as logger_mod
        monkeypatch.setattr(logger_mod, "LOG_DIR", tmp_path)

        setup_logging(level="DEBUG", log_file="test.log")
        log = get_logger("test.module")
        log.info("hello world")
        log.error("an error")

        assert (tmp_path / "test.log").exists()
        assert (tmp_path / "error.log").exists()

    def test_get_logger_returns_named_logger(self) -> None:
        log = get_logger("foo.bar")
        assert log.name == "foo.bar"
        assert isinstance(log, logging.Logger)


class TestLogLevels:
    """测试不同 level 行为。"""

    def test_debug_filtered_when_level_info(self, caplog) -> None:
        """logger 级别为 INFO 时，DEBUG 被过滤，INFO 透传。"""
        # 不调用 setup_logging，避免覆盖 caplog handler
        # 直接用基础 logger
        log = logging.getLogger("test.level")
        log.setLevel(logging.INFO)
        log.handlers.clear()  # 清除可能的 handler
        log.propagate = True  # 关键：让消息冒泡到 root，caplog 才能捕获

        with caplog.at_level(logging.INFO, logger="test.level"):
            log.debug("debug msg")      # 应被过滤
            log.info("info msg")        # 应出现
            log.warning("warn msg")     # 应出现

        records = [r for r in caplog.records if r.name == "test.level"]
        levels = [r.levelno for r in records]
        assert logging.INFO in levels
        assert logging.WARNING in levels
        assert logging.DEBUG not in levels

    def test_debug_passes_when_level_debug(self, caplog) -> None:
        """logger 级别为 DEBUG 时，DEBUG 也能透传。"""
        log = logging.getLogger("test.debug")
        log.setLevel(logging.DEBUG)
        log.handlers.clear()
        log.propagate = True

        with caplog.at_level(logging.DEBUG, logger="test.debug"):
            log.debug("debug msg")
            log.info("info msg")

        records = [r for r in caplog.records if r.name == "test.debug"]
        levels = [r.levelno for r in records]
        assert logging.DEBUG in levels
        assert logging.INFO in levels
