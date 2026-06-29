"""学生管理 API 路由。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_session
from backend.schemas.student import (
    StudentCreate,
    StudentList,
    StudentRead,
    StudentUpdate,
)
from backend.services import students as student_svc
from backend.services.students import (
    ClassNotFoundError,
    StudentNotFoundError,
)

router = APIRouter(prefix="/api/students", tags=["students"])


@router.post(
    "",
    response_model=StudentRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建学生",
)
async def create_student(
    data: StudentCreate, session: AsyncSession = Depends(get_session)
) -> StudentRead:
    try:
        student = await student_svc.create_student(session, data)
    except ClassNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return StudentRead.model_validate(student)


@router.get("", response_model=StudentList, summary="学生列表（分页 + 过滤）")
async def list_students(
    class_id: int | None = Query(None, description="按班级过滤"),
    base_level: str | None = Query(None, description="按基础水平过滤"),
    keyword: str | None = Query(None, description="按姓名模糊搜索"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
    session: AsyncSession = Depends(get_session),
) -> StudentList:
    items, total = await student_svc.list_students(
        session,
        class_id=class_id,
        base_level=base_level,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return StudentList(
        items=[StudentRead.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/export-csv",
    summary="导出学生列表为 CSV（支持过滤）",
)
async def export_students_csv(
    class_id: int | None = Query(None, description="按班级过滤"),
    base_level: str | None = Query(None, description="按基础水平过滤"),
    keyword: str | None = Query(None, description="按姓名模糊搜索"),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """导出当前过滤条件下的学生为 CSV 文件。"""
    csv_text = await student_svc.export_students_csv(
        session,
        class_id=class_id,
        base_level=base_level,
        keyword=keyword,
    )
    filename = f"students_{datetime.now().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([csv_text.encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{student_id}", response_model=StudentRead, summary="学生详情")
async def get_student(
    student_id: int, session: AsyncSession = Depends(get_session)
) -> StudentRead:
    try:
        student = await student_svc.get_student(session, student_id)
    except StudentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return StudentRead.model_validate(student)


@router.patch("/{student_id}", response_model=StudentRead, summary="更新学生")
async def update_student(
    student_id: int,
    data: StudentUpdate,
    session: AsyncSession = Depends(get_session),
) -> StudentRead:
    try:
        student = await student_svc.update_student(session, student_id, data)
    except StudentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ClassNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return StudentRead.model_validate(student)


@router.delete(
    "/{student_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除学生",
)
async def delete_student(
    student_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    try:
        await student_svc.delete_student(session, student_id)
    except StudentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/batch",
    response_model=list[StudentRead],
    status_code=status.HTTP_201_CREATED,
    summary="批量创建学生",
)
async def batch_create(
    data: list[StudentCreate], session: AsyncSession = Depends(get_session)
) -> list[StudentRead]:
    if not data:
        raise HTTPException(status_code=400, detail="批量数据不能为空")
    try:
        students = await student_svc.batch_create_students(session, data)
    except ClassNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return [StudentRead.model_validate(s) for s in students]
