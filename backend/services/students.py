"""学生业务逻辑层。"""
from __future__ import annotations

from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Class, Student
from backend.schemas.student import StudentCreate, StudentUpdate
from backend.utils.logger import get_logger

log = get_logger(__name__)


class StudentNotFoundError(Exception):
    """学生不存在。"""

    def __init__(self, student_id: int):
        self.student_id = student_id
        super().__init__(f"学生不存在: id={student_id}")


class ClassNotFoundError(Exception):
    """班级不存在。"""

    def __init__(self, class_id: int):
        self.class_id = class_id
        super().__init__(f"班级不存在: id={class_id}")


async def create_student(session: AsyncSession, data: StudentCreate) -> Student:
    """创建学生。"""
    if data.class_id is not None:
        klass = await session.get(Class, data.class_id)
        if klass is None:
            raise ClassNotFoundError(data.class_id)

    student = Student(**data.model_dump())
    session.add(student)
    await session.commit()
    await session.refresh(student)
    log.info("学生已创建: id=%s name=%s", student.id, student.name)
    return student


async def get_student(session: AsyncSession, student_id: int) -> Student:
    """获取单个学生。"""
    student = await session.get(Student, student_id)
    if student is None:
        raise StudentNotFoundError(student_id)
    return student


async def list_students(
    session: AsyncSession,
    *,
    class_id: int | None = None,
    base_level: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[Sequence[Student], int]:
    """获取学生列表（分页 + 过滤）。"""
    stmt = select(Student)
    count_stmt = select(func.count()).select_from(Student)

    if class_id is not None:
        stmt = stmt.where(Student.class_id == class_id)
        count_stmt = count_stmt.where(Student.class_id == class_id)
    if base_level is not None:
        stmt = stmt.where(Student.base_level == base_level)
        count_stmt = count_stmt.where(Student.base_level == base_level)
    if keyword:
        kw = f"%{keyword}%"
        stmt = stmt.where(Student.name.like(kw))
        count_stmt = count_stmt.where(Student.name.like(kw))

    total = (await session.execute(count_stmt)).scalar_one()
    offset = (page - 1) * page_size
    stmt = stmt.order_by(Student.id.desc()).offset(offset).limit(page_size)
    result = await session.execute(stmt)
    items = result.scalars().all()
    return items, total


async def update_student(
    session: AsyncSession, student_id: int, data: StudentUpdate
) -> Student:
    """更新学生。"""
    student = await get_student(session, student_id)

    if data.class_id is not None and data.class_id != student.class_id:
        klass = await session.get(Class, data.class_id)
        if klass is None:
            raise ClassNotFoundError(data.class_id)

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(student, key, value)
    await session.commit()
    await session.refresh(student)
    log.info("学生已更新: id=%s", student_id)
    return student


async def delete_student(session: AsyncSession, student_id: int) -> None:
    """删除学生。"""
    student = await get_student(session, student_id)
    await session.delete(student)
    await session.commit()
    log.info("学生已删除: id=%s", student_id)


async def batch_create_students(
    session: AsyncSession, data_list: list[StudentCreate]
) -> list[Student]:
    """批量创建学生（事务内）。"""
    # 预校验 class_id
    class_ids = {d.class_id for d in data_list if d.class_id is not None}
    if class_ids:
        stmt = select(Class.id).where(Class.id.in_(class_ids))
        existing = set((await session.execute(stmt)).scalars().all())
        missing = class_ids - existing
        if missing:
            raise ClassNotFoundError(next(iter(missing)))

    students = [Student(**d.model_dump()) for d in data_list]
    session.add_all(students)
    await session.commit()
    for s in students:
        await session.refresh(s)
    log.info("批量创建学生: %d 条", len(students))
    return students
