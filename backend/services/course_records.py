"""课程记录（报告草稿）业务逻辑层。"""
from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import CourseRecord
from backend.schemas.course_record import CourseRecordCreate, CourseRecordUpdate
from backend.utils.logger import get_logger

log = get_logger(__name__)


class RecordNotFoundError(Exception):
    """课程记录不存在。"""

    def __init__(self, record_id: int):
        self.record_id = record_id
        super().__init__(f"课程记录不存在: id={record_id}")


# =========================
# JSON 序列化辅助
# =========================

def _dump_json(value: Any) -> str | None:
    """将 Python 对象序列化为 JSON 字符串（或 None）。"""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _load_json(value: str | None, default: Any = None) -> Any:
    """将 JSON 字符串反序列化为 Python 对象。"""
    if value is None:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _serialize_for_db(data: CourseRecordCreate) -> dict[str, Any]:
    """将创建请求转为 ORM 可接受的 dict（JSON 字段序列化）。"""
    result = data.model_dump()

    # 序列化 JSON 字段
    result["knowledge_points"] = _dump_json(data.knowledge_points)
    result["content_items"] = _dump_json(
        [c.model_dump() for c in data.content_items] if data.content_items else None
    )
    result["homework"] = _dump_json(
        data.homework.model_dump() if data.homework else None
    )
    result["vocabulary"] = _dump_json(
        data.vocabulary.model_dump() if data.vocabulary else None
    )
    result["screenshot_paths"] = _dump_json(data.screenshot_paths)
    result["logo_config"] = _dump_json(
        data.logo_config.model_dump() if data.logo_config else None
    )
    result["layout_config"] = _dump_json(
        data.layout_config.model_dump(exclude_none=True) if data.layout_config else None
    )
    result["project_meta"] = _dump_json(data.project_meta)
    result["ai_meta"] = _dump_json(
        data.ai_meta.model_dump() if data.ai_meta else None
    )

    return result


def _deserialize_from_record(record: CourseRecord, include_content: bool = True) -> dict[str, Any]:
    """将 ORM 记录反序列化为响应 dict。"""
    result: dict[str, Any] = {
        "id": record.id,
        "student_id": record.student_id,
        "course_date": record.course_date,
        "course_topic": record.course_topic,
        "project_folder": record.project_folder,
        "project_meta": _load_json(record.project_meta),
        "status": record.status,
        "template_id": record.template_id,
        "last_auto_saved_at": record.last_auto_saved_at,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }

    if include_content:
        result.update({
            "knowledge_points": _load_json(record.knowledge_points, []),
            "ability_improvement": record.ability_improvement or "",
            "content_items": _load_json(record.content_items, []),
            "homework": _load_json(record.homework, {}),
            "vocabulary": _load_json(record.vocabulary, {}),
            "evaluation": record.evaluation or "",
            "screenshot_paths": _load_json(record.screenshot_paths, []),
            "logo_config": _load_json(record.logo_config, {}),
            "layout_config": _load_json(record.layout_config, {}),
            "ai_meta": _load_json(record.ai_meta, {}),
        })

    return result


# =========================
# CRUD
# =========================

async def create_record(
    session: AsyncSession, data: CourseRecordCreate
) -> CourseRecord:
    """创建课程记录。"""
    db_data = _serialize_for_db(data)
    record = CourseRecord(**db_data)
    session.add(record)
    await session.commit()
    await session.refresh(record)
    log.info("课程记录已创建: id=%s student_id=%s", record.id, record.student_id)
    return record


async def get_record(session: AsyncSession, record_id: int) -> CourseRecord:
    """获取单个课程记录。"""
    record = await session.get(CourseRecord, record_id)
    if record is None:
        raise RecordNotFoundError(record_id)
    return record


async def list_records(
    session: AsyncSession,
    *,
    student_id: int | None = None,
    status: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[Sequence[CourseRecord], int]:
    """获取课程记录列表（分页 + 过滤）。"""
    stmt = select(CourseRecord)
    count_stmt = select(func.count()).select_from(CourseRecord)

    if student_id is not None:
        stmt = stmt.where(CourseRecord.student_id == student_id)
        count_stmt = count_stmt.where(CourseRecord.student_id == student_id)
    if status is not None:
        stmt = stmt.where(CourseRecord.status == status)
        count_stmt = count_stmt.where(CourseRecord.status == status)
    if keyword:
        kw = f"%{keyword}%"
        stmt = stmt.where(CourseRecord.course_topic.like(kw))
        count_stmt = count_stmt.where(CourseRecord.course_topic.like(kw))

    total = (await session.execute(count_stmt)).scalar_one()
    offset = (page - 1) * page_size
    stmt = stmt.order_by(CourseRecord.updated_at.desc()).offset(offset).limit(page_size)
    result = await session.execute(stmt)
    items = result.scalars().all()
    return items, total


async def update_record(
    session: AsyncSession, record_id: int, data: CourseRecordUpdate
) -> CourseRecord:
    """更新课程记录（局部更新）。"""
    record = await get_record(session, record_id)

    update_data = data.model_dump(exclude_unset=True)

    # 序列化 JSON 字段（如果提供了）
    # 注意：model_dump() 已将嵌套 Pydantic 模型转为 dict，直接序列化即可
    for json_field in ["knowledge_points", "content_items", "homework", "vocabulary",
                       "screenshot_paths", "logo_config", "layout_config", "project_meta", "ai_meta"]:
        if json_field in update_data:
            update_data[json_field] = _dump_json(update_data[json_field])

    for key, value in update_data.items():
        setattr(record, key, value)
    await session.commit()
    await session.refresh(record)
    log.info("课程记录已更新: id=%s", record_id)
    return record


async def update_record_status(
    session: AsyncSession, record_id: int, new_status: str
) -> CourseRecord:
    """更新课程记录状态。"""
    record = await get_record(session, record_id)
    record.status = new_status
    await session.commit()
    await session.refresh(record)
    log.info("课程记录状态已更新: id=%s status=%s", record_id, new_status)
    return record


async def update_auto_save_timestamp(
    session: AsyncSession, record_id: int
) -> CourseRecord:
    """更新自动保存时间戳。"""
    from datetime import datetime
    record = await get_record(session, record_id)
    record.last_auto_saved_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(record)
    return record


async def delete_record(session: AsyncSession, record_id: int) -> None:
    """删除课程记录。"""
    record = await get_record(session, record_id)
    await session.delete(record)
    await session.commit()
    log.info("课程记录已删除: id=%s", record_id)


# =========================
# 批量操作
# =========================

async def batch_create_records(
    session: AsyncSession, records_data: list[dict[str, Any]]
) -> list[CourseRecord]:
    """批量创建课程记录（单个事务）。

    records_data: 每个 dict 包含 CourseRecord 的所有字段（JSON 字段需已序列化为字符串）。
    """
    records = [CourseRecord(**data) for data in records_data]
    for rec in records:
        session.add(rec)
    await session.commit()
    for rec in records:
        await session.refresh(rec)
    log.info("批量创建课程记录完成: %d 条", len(records))
    return records
