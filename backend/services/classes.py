"""班级业务逻辑层。"""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Class
from backend.schemas.klass import ClassCreate, ClassUpdate
from backend.utils.logger import get_logger

log = get_logger(__name__)


class ClassNotFoundError(Exception):
    """班级不存在。"""

    def __init__(self, class_id: int):
        self.class_id = class_id
        super().__init__(f"班级不存在: id={class_id}")


async def create_class(session: AsyncSession, data: ClassCreate) -> Class:
    """创建班级。"""
    klass = Class(**data.model_dump())
    session.add(klass)
    await session.commit()
    await session.refresh(klass)
    log.info("班级已创建: id=%s name=%s", klass.id, klass.name)
    return klass


async def get_class(session: AsyncSession, class_id: int) -> Class:
    """获取单个班级。"""
    klass = await session.get(Class, class_id)
    if klass is None:
        raise ClassNotFoundError(class_id)
    return klass


async def list_classes(session: AsyncSession) -> tuple[Sequence[Class], int]:
    """获取班级列表。"""
    stmt = select(Class).order_by(Class.id.desc())
    count_stmt = select(func.count()).select_from(Class)
    items = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()
    return items, total


async def update_class(
    session: AsyncSession, class_id: int, data: ClassUpdate
) -> Class:
    """更新班级。"""
    klass = await get_class(session, class_id)
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(klass, key, value)
    await session.commit()
    await session.refresh(klass)
    log.info("班级已更新: id=%s", class_id)
    return klass


async def delete_class(session: AsyncSession, class_id: int) -> None:
    """删除班级（学生 class_id 自动置 NULL）。"""
    klass = await get_class(session, class_id)
    await session.delete(klass)
    await session.commit()
    log.info("班级已删除: id=%s", class_id)
