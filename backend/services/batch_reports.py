"""批量报告业务逻辑层。"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import BatchReport
from backend.utils.logger import get_logger

log = get_logger(__name__)


class BatchReportNotFoundError(Exception):
    """批量报告不存在。"""

    def __init__(self, batch_id: int):
        self.batch_id = batch_id
        super().__init__(f"批量报告不存在: id={batch_id}")


# =========================
# JSON 辅助
# =========================

def _dump_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _load_json(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


# =========================
# CRUD
# =========================

async def create_batch_report(
    session: AsyncSession,
    data: dict[str, Any],
) -> BatchReport:
    """创建批量报告。"""
    record = BatchReport(**data)
    session.add(record)
    await session.commit()
    await session.refresh(record)
    log.info("批量报告创建成功: id=%s class_id=%s", record.id, record.class_id)
    return record


async def get_batch_report(
    session: AsyncSession,
    batch_id: int,
) -> BatchReport:
    """获取单条批量报告。"""
    record = await session.get(BatchReport, batch_id)
    if record is None:
        raise BatchReportNotFoundError(batch_id)
    return record


async def update_batch_report(
    session: AsyncSession,
    batch_id: int,
    data: dict[str, Any],
) -> BatchReport:
    """更新批量报告（部分更新）。"""
    record = await get_batch_report(session, batch_id)
    for key, value in data.items():
        if hasattr(record, key):
            setattr(record, key, value)
    record.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(record)
    log.info("批量报告更新成功: id=%s", batch_id)
    return record


async def delete_batch_report(
    session: AsyncSession,
    batch_id: int,
) -> None:
    """删除批量报告。"""
    record = await get_batch_report(session, batch_id)
    await session.delete(record)
    await session.commit()
    log.info("批量报告删除成功: id=%s", batch_id)


async def list_batch_reports_by_class(
    session: AsyncSession,
    class_id: int,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[BatchReport], int]:
    """按班级列出批量报告（按创建时间倒序）。"""
    # total count
    count_q = select(BatchReport).where(BatchReport.class_id == class_id)
    total_q = select(func.count()).select_from(count_q.subquery())
    total_result = await session.execute(total_q)
    total = total_result.scalar() or 0

    # paginated
    q = (
        select(BatchReport)
        .where(BatchReport.class_id == class_id)
        .order_by(BatchReport.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(q)
    records = list(result.scalars().all())
    return records, total


async def list_all_batch_reports(
    session: AsyncSession,
    keyword: str | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[BatchReport], int]:
    """列出全部批量报告，支持关键词搜索和状态筛选。"""
    base_q = select(BatchReport)
    if keyword:
        base_q = base_q.where(
            BatchReport.course_topic.ilike(f"%{keyword}%")
            | BatchReport.class_name.ilike(f"%{keyword}%")
        )
    if status:
        base_q = base_q.where(BatchReport.status == status)

    # total count
    total_q = select(func.count()).select_from(base_q.subquery())
    total_result = await session.execute(total_q)
    total = total_result.scalar() or 0

    # paginated
    q = (
        base_q
        .order_by(BatchReport.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(q)
    records = list(result.scalars().all())
    return records, total


# =========================
# 序列化
# =========================

def to_list_dict(record: BatchReport) -> dict[str, Any]:
    """将 ORM BatchReport 转为列表展示用的轻量 dict（不含大字段内容）。"""
    # 计算学生数量
    evals = _load_json(record.evaluations, {})
    student_count = len(evals) if isinstance(evals, dict) else 0
    return {
        "id": record.id,
        "class_id": record.class_id,
        "class_name": record.class_name,
        "course_date": record.course_date,
        "course_topic": record.course_topic,
        "course_description": record.course_description or "",
        "template_id": record.template_id,
        "status": record.status,
        "student_count": student_count,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "_type": "batch",  # 前端区分报告类型
    }


def to_read_dict(record: BatchReport) -> dict[str, Any]:
    """将 ORM BatchReport 转为可序列化的 dict（JSON 字段反序列化）。"""
    return {
        "id": record.id,
        "class_id": record.class_id,
        "class_name": record.class_name,
        "course_date": record.course_date,
        "course_topic": record.course_topic,
        "course_description": record.course_description or "",
        "project_folder": record.project_folder,
        "template_id": record.template_id,
        "knowledge_points": _load_json(record.knowledge_points, []),
        "ability_improvement": record.ability_improvement or "",
        "content_items": _load_json(record.content_items, []),
        "homework": _load_json(record.homework, {}),
        "vocabulary": _load_json(record.vocabulary, {}),
        "evaluations": _load_json(record.evaluations, {}),
        "screenshot_paths": _load_json(record.screenshot_paths, []),
        "run_screenshots": _load_json(record.run_screenshots, []),
        "code_screenshots": _load_json(record.code_screenshots, []),
        "homework_screenshots": _load_json(record.homework_screenshots, []),
        "logo_config": _load_json(record.logo_config, {}),
        "teacher_observation": record.teacher_observation or "",
        "observations": _load_json(record.observations, {}),
        "ai_meta": _load_json(record.ai_meta, {}),
        "status": record.status,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }
