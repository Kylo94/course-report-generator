"""报告编辑 + 资产管理 API 路由。"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.db import get_session
from backend.schemas.course_record import (
    CourseRecordCreate,
    CourseRecordList,
    CourseRecordListItem,
    CourseRecordRead,
    CourseRecordUpdate,
    StatusUpdate,
)
from backend.services import course_records as record_svc
from backend.services.course_records import RecordNotFoundError
from backend.utils.logger import get_logger

log = get_logger(__name__)
settings = get_settings()

router = APIRouter(tags=["reports"])
assets_router = APIRouter(prefix="/api/assets", tags=["assets"])


# =========================
# 辅助：ORM → Read Schema
# =========================

def _record_to_read(record) -> CourseRecordRead:
    """将 ORM 记录转为 Read schema（反序列化 JSON 字段）。"""
    from backend.services.course_records import _deserialize_from_record
    data = _deserialize_from_record(record, include_content=True)
    return CourseRecordRead(**data)


def _record_to_list_item(record) -> CourseRecordListItem:
    """将 ORM 记录转为 List schema（不含大字段内容）。"""
    from backend.services.course_records import _deserialize_from_record
    data = _deserialize_from_record(record, include_content=False)
    return CourseRecordListItem(**data)


# =========================
# 报告 CRUD
# =========================

@router.post(
    "/api/reports",
    response_model=CourseRecordRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建课程记录（草稿）",
)
async def create_record(
    data: CourseRecordCreate, session: AsyncSession = Depends(get_session)
) -> CourseRecordRead:
    try:
        record = await record_svc.create_record(session, data)
    except Exception as e:
        log.exception("创建课程记录失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    return _record_to_read(record)


@router.get(
    "/api/reports",
    response_model=CourseRecordList,
    summary="课程记录列表（分页 + 过滤）",
)
async def list_records(
    student_id: int | None = Query(None, description="按学生过滤"),
    status: str | None = Query(None, description="按状态过滤"),
    keyword: str | None = Query(None, description="按课程名模糊搜索"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
    session: AsyncSession = Depends(get_session),
) -> CourseRecordList:
    items, total = await record_svc.list_records(
        session,
        student_id=student_id,
        status=status,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return CourseRecordList(
        items=[_record_to_list_item(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/api/reports/{record_id}",
    response_model=CourseRecordRead,
    summary="加载单个课程记录",
)
async def get_record(
    record_id: int, session: AsyncSession = Depends(get_session)
) -> CourseRecordRead:
    try:
        record = await record_svc.get_record(session, record_id)
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _record_to_read(record)


@router.put(
    "/api/reports/{record_id}",
    response_model=CourseRecordRead,
    summary="全量更新课程记录",
)
async def update_record(
    record_id: int,
    data: CourseRecordUpdate,
    session: AsyncSession = Depends(get_session),
) -> CourseRecordRead:
    try:
        record = await record_svc.update_record(session, record_id, data)
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.exception("更新课程记录失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    return _record_to_read(record)


@router.patch(
    "/api/reports/{record_id}",
    response_model=CourseRecordRead,
    summary="局部更新课程记录（含自动保存）",
)
async def patch_record(
    record_id: int,
    data: CourseRecordUpdate,
    session: AsyncSession = Depends(get_session),
) -> CourseRecordRead:
    try:
        record = await record_svc.update_record(session, record_id, data)
        # 标记自动保存时间
        await record_svc.update_auto_save_timestamp(session, record_id)
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.exception("自动保存失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    return _record_to_read(record)


@router.patch(
    "/api/reports/{record_id}/status",
    response_model=CourseRecordRead,
    summary="变更课程记录状态",
)
async def update_record_status(
    record_id: int,
    data: StatusUpdate,
    session: AsyncSession = Depends(get_session),
) -> CourseRecordRead:
    try:
        record = await record_svc.update_record_status(
            session, record_id, data.status
        )
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _record_to_read(record)


@router.delete(
    "/api/reports/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除课程记录",
)
async def delete_record(
    record_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    try:
        await record_svc.delete_record(session, record_id)
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =========================
# 资产管理（截图上传）
# =========================

SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


@assets_router.post(
    "/screenshot",
    response_model=dict,
    summary="上传课程截图",
)
async def upload_screenshot(
    file: UploadFile,
) -> dict:
    """上传截图，保存到 data/screenshots/，返回访问路径。"""
    if file.content_type not in SUPPORTED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式: {file.content_type}，支持: {SUPPORTED_IMAGE_TYPES}",
        )

    ext = _guess_extension(file.content_type)
    filename = f"{uuid.uuid4().hex}{ext}"
    save_dir = Path(settings.report.screenshot_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / filename

    try:
        content = await file.read()
        save_path.write_bytes(content)
    except Exception as e:
        log.exception("截图上传写入失败: %s", e)
        raise HTTPException(status_code=500, detail="截图保存失败")

    log.info("截图已上传: %s (%d bytes)", filename, len(content))
    return {
        "filename": filename,
        "path": f"/api/assets/screenshots/{filename}",
        "size_bytes": len(content),
        "mime_type": file.content_type,
    }


@assets_router.post(
    "/logo",
    response_model=dict,
    summary="上传 Logo",
)
async def upload_logo(
    file: UploadFile,
) -> dict:
    """上传机构 Logo，保存到 data/assets/，覆盖旧文件。"""
    if file.content_type not in SUPPORTED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式: {file.content_type}，支持: {SUPPORTED_IMAGE_TYPES}",
        )

    ext = _guess_extension(file.content_type)
    filename = f"logo{ext}"
    save_dir = Path(settings.report.asset_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / filename

    try:
        content = await file.read()
        save_path.write_bytes(content)
    except Exception as e:
        log.exception("Logo 上传写入失败: %s", e)
        raise HTTPException(status_code=500, detail="Logo 保存失败")

    log.info("Logo 已上传: %s (%d bytes)", filename, len(content))
    return {
        "filename": filename,
        "path": f"/api/assets/logo{ext}",
        "size_bytes": len(content),
        "mime_type": file.content_type,
    }


@assets_router.get(
    "/logo",
    response_model=dict,
    summary="获取当前 Logo 信息",
)
async def get_logo_info() -> dict:
    """返回当前 Logo 是否存在、路径、尺寸等信息。"""
    from PIL import Image, UnidentifiedImageError

    asset_dir = Path(settings.report.asset_dir)
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        logo_path = asset_dir / f"logo{ext}"
        if logo_path.exists():
            try:
                img = Image.open(logo_path)
                width, height = img.size
                return {
                    "exists": True,
                    "path": f"/api/assets/logo{ext}",
                    "filename": f"logo{ext}",
                    "width": width,
                    "height": height,
                    "format": img.format,
                    "mime_type": f"image/{img.format.lower()}" if img.format else "image/png",
                }
            except (UnidentifiedImageError, OSError):
                # 文件存在但无法识别为图片，视为不存在
                continue
    return {"exists": False, "path": None}


# =========================
# 静态文件挂载（截图/Logo 访问）
# =========================
def _guess_extension(mime_type: str) -> str:
    """从 MIME 类型推断文件扩展名。"""
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(mime_type, ".bin")
