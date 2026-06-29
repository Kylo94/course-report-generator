"""
数据库模块

约定：
- 使用异步 SQLAlchemy 2.0 + aiosqlite
- 单一 engine 单例（基于配置中的 database.url）
- 通过 get_session 依赖注入获取 AsyncSession
- 测试可使用 init_db(create_all=True) 初始化内存库
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.config import get_settings
from backend.utils.logger import get_logger

log = get_logger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类。"""
    pass


# =========================
# Engine & Session Factory
# =========================
_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    """获取全局异步 engine（懒加载）。"""
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database.url
        log.info("初始化数据库引擎: %s", url)

        # SQLite 需要特殊配置
        connect_args = {}
        if "sqlite" in url:
            connect_args["check_same_thread"] = False

        _engine = create_async_engine(
            url,
            echo=settings.database.echo,
            connect_args=connect_args,
            future=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取全局 session factory。"""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """
    FastAPI 依赖：提供一个 AsyncSession，结束自动关闭。

    用法：
        @router.get("/items")
        async def list_items(session: AsyncSession = Depends(get_session)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# =========================
# 初始化 / 销毁
# =========================
async def init_db(echo: bool = False) -> None:
    """
    初始化数据库：创建所有表。

    注意：生产环境应使用 Alembic 迁移，而非 create_all。
    """
    # 确保所有 model 已导入（register tables）
    from backend.models import student, klass  # noqa: F401

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("数据库表已创建")


async def reset_db() -> None:
    """删除所有表（仅用于测试）。"""
    from backend.models import student, klass  # noqa: F401

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    log.info("数据库表已删除")


async def dispose_engine() -> None:
    """关闭 engine（应用退出时调用）。"""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        log.info("数据库引擎已关闭")
