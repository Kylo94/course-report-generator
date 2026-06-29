"""班级管理 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_session
from backend.models import Class, Student
from backend.schemas.klass import (
    ClassCreate,
    ClassList,
    ClassRead,
    ClassUpdate,
)
from backend.services import classes as class_svc
from backend.services.classes import ClassNotFoundError

router = APIRouter(prefix="/api/classes", tags=["classes"])


@router.post(
    "",
    response_model=ClassRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建班级",
)
async def create_class(
    data: ClassCreate, session: AsyncSession = Depends(get_session)
) -> ClassRead:
    klass = await class_svc.create_class(session, data)
    return await _to_read(session, klass)


@router.get("", response_model=ClassList, summary="班级列表")
async def list_classes(session: AsyncSession = Depends(get_session)) -> ClassList:
    items, total = await class_svc.list_classes(session)
    reads = []
    for k in items:
        reads.append(await _to_read(session, k))
    return ClassList(items=reads, total=total)


@router.get("/{class_id}", response_model=ClassRead, summary="班级详情")
async def get_class(
    class_id: int, session: AsyncSession = Depends(get_session)
) -> ClassRead:
    try:
        klass = await class_svc.get_class(session, class_id)
    except ClassNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return await _to_read(session, klass)


@router.patch("/{class_id}", response_model=ClassRead, summary="更新班级")
async def update_class(
    class_id: int,
    data: ClassUpdate,
    session: AsyncSession = Depends(get_session),
) -> ClassRead:
    try:
        klass = await class_svc.update_class(session, class_id, data)
    except ClassNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return await _to_read(session, klass)


@router.delete(
    "/{class_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除班级",
)
async def delete_class(
    class_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    try:
        await class_svc.delete_class(session, class_id)
    except ClassNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


async def _to_read(session: AsyncSession, klass: Class) -> ClassRead:
    """将 ORM 转为 Read schema 并附带学生人数。"""
    count_stmt = select(func.count()).select_from(Student).where(
        Student.class_id == klass.id
    )
    student_count = (await session.execute(count_stmt)).scalar_one()
    return ClassRead(
        id=klass.id,
        name=klass.name,
        schedule_day=klass.schedule_day,
        schedule_time=klass.schedule_time,
        student_count=student_count,
        created_at=klass.created_at,
        updated_at=klass.updated_at,
    )
