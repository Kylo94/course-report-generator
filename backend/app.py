"""
FastAPI 应用工厂

提供 create_app() 用于创建 FastAPI 实例，支持测试时覆盖数据库 URL。
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.api import api_router
from backend.config import get_settings
from backend.db import dispose_engine, init_db
from backend.utils.logger import get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库，关闭时释放资源。"""
    settings = get_settings()
    log.info("应用启动: %s v%s", settings.app.name, settings.app.version)

    # 初始化数据库（创建表）
    await init_db()
    log.info("数据库初始化完成")

    yield

    log.info("应用关闭中...")
    await dispose_engine()
    log.info("应用已关闭")


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    settings = get_settings()

    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        description="少儿编程课程报告自动生成工具 API",
        lifespan=lifespan,
        debug=settings.app.debug,
    )

    # 注册路由
    app.include_router(api_router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        """健康检查。"""
        return {
            "status": "ok",
            "name": settings.app.name,
            "version": settings.app.version,
        }

    @app.get("/", tags=["meta"])
    async def root() -> dict:
        """根路径。"""
        return {
            "name": settings.app.name,
            "version": settings.app.version,
            "docs": "/docs",
        }

    return app


# 默认 app 实例（uvicorn backend.app:app 启动）
app = create_app()
