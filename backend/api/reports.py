"""报告编辑 + 资产管理 API 路由。"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import PROJECT_ROOT, get_settings
from backend.db import get_session
from backend.schemas.course_record import (
    CourseRecordCreate,
    CourseRecordList,
    CourseRecordListItem,
    CourseRecordRead,
    CourseRecordUpdate,
    LogoConfigSchema,
    StatusUpdate,
)
from backend.schemas.template import TemplateListItem
from backend.schemas.batch import BatchGenerateRequest, BatchGenerateResponse, BatchStudentResult
from backend.services import course_records as record_svc
from backend.services.course_records import RecordNotFoundError
from backend.services.pdf_generator import PDFGenerationError, PDFGenerator
from backend.services.report_renderer import (
    ReportRenderer,
    TemplateNotFoundError,
    get_template_config,
    list_templates,
    merge_layout_with_theme,
    wrap_preview_html,
)
from backend.services.pdf_to_image import pdf_to_long_image
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
# 辅助：输出路径构建
# =========================

def _sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符。"""
    # 替换 Windows 和通用非法字符
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip(' .') or '未命名'


def _sanitize_date_dir(course_date: str) -> str:
    """将上课日期格式化为安全的目录名（YYYY-MM-DD）。"""
    # 尝试解析常见格式
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%Y.%m.%d"):
        try:
            return datetime.strptime(course_date.strip(), fmt).strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            continue
    # 回退：只保留数字和横线
    safe = re.sub(r"[^\d-]", "", course_date.strip())
    return safe[:10] if safe else "未设置日期"


def _resolve_logo_config(template_id: str) -> dict:
    """优先从模板 config.json 读 logo_config，没有则用默认 LogoConfigSchema 兜底。

    解决批量生成时 logo_config 被默认值覆盖导致 Logo 丢失的问题。
    """
    try:
        tpl_cfg = get_template_config(template_id)
        if isinstance(tpl_cfg, dict) and tpl_cfg.get("logo_config"):
            return dict(tpl_cfg["logo_config"])
    except Exception:
        pass
    return LogoConfigSchema().model_dump()


PDF_SUBDIR = "PDF(用于打印)"
IMG_SUBDIR = "IMG(用于发送)"


def _resolve_class_name_sync(record) -> str:
    """同步版：从 record.student.class_id 取班级名（前提是关系已加载）。"""
    student_id = getattr(record, "student_id", None)
    if not student_id:
        return "未分班"
    try:
        student = getattr(record, "student", None)
        if not student:
            return "未分班"
        klass = getattr(student, "klass", None)
        if not klass or not getattr(klass, "name", None):
            return "未分班"
        return klass.name
    except Exception:
        return "未分班"


async def _aresolve_class_name(record, session) -> str:
    """异步版：从 record.student → student.klass.name 取班级名。"""
    student_id = getattr(record, "student_id", None)
    if not student_id or session is None:
        return "未分班"
    try:
        from backend.models import Student as _StuM, Class as _ClsM
        student = await session.get(_StuM, student_id)
        if not student or not student.class_id:
            return "未分班"
        klass = await session.get(_ClsM, student.class_id)
        return klass.name if klass else "未分班"
    except Exception:
        return "未分班"


async def _build_output_dir(
    record,
    output_dir_override: str | None = None,
    project_folder: str | None = None,
    session=None,
) -> Path:
    """构建输出父目录 = `{上课日期}_{班级名}`。

    行为：
    1. 指定了 output_dir → {output_dir}/{上课日期_班级名}
    2. 未指定 output_dir 但有项目目录 → {项目目录}/{上课日期_班级名}
    3. 两者都无 → {custom 或 默认 output_dir}/{上课日期_班级名}
    """
    course_date = getattr(record, "course_date", None) or ""
    date_part = _sanitize_date_dir(course_date) if course_date else "未设置日期"
    class_name = await _aresolve_class_name(record, session)
    session_part = f"{date_part}_{_sanitize_filename(class_name)}"

    if output_dir_override:
        base_str = output_dir_override
    elif project_folder:
        base_str = project_folder
    else:
        base_str = settings.report.custom_output_dir or settings.report.output_dir

    base_dir = Path(base_str)
    if not base_dir.is_absolute():
        base_dir = PROJECT_ROOT / base_str

    return base_dir / session_part


async def _export_paths(
    record,
    student_name: str,
    output_dir_override: str | None = None,
    project_folder: str | None = None,
    session=None,
) -> tuple[Path, Path]:
    """构建 PDF 和 IMG 输出路径。

    父目录 = `{上课日期}_{班级名}`，子目录：
    - PDF(用于打印)/{name}_{topic}.pdf
    - IMG(用于发送)/{name}_{topic}.jpg

    Returns:
        (pdf_path, img_path)
    """
    base_dir = await _build_output_dir(record, output_dir_override, project_folder, session)
    base_dir.mkdir(parents=True, exist_ok=True)

    pdf_dir = base_dir / PDF_SUBDIR
    img_dir = base_dir / IMG_SUBDIR
    pdf_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _sanitize_filename(student_name or "学生")
    safe_topic = _sanitize_filename(getattr(record, "course_topic", None) or "课程")
    basename = f"{safe_name}_{safe_topic}"

    pdf_path = pdf_dir / f"{basename}.pdf"
    img_path = img_dir / f"{basename}.jpg"

    # 文件名冲突时追加时间戳
    now_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if pdf_path.exists():
        pdf_path = pdf_dir / f"{basename}_{now_ts}.pdf"
    if img_path.exists():
        img_path = img_dir / f"{basename}_{now_ts}.jpg"

    return pdf_path, img_path


def _date_subdir_name(course_date: str | None) -> str:
    """（已废弃）原 YYYY年MM月 子目录名生成器，保留以免导入错误。"""
    if not course_date:
        return datetime.now().strftime("%Y年%m月")
    try:
        dt = datetime.strptime(course_date, "%Y-%m-%d")
        return dt.strftime("%Y年%m月")
    except (ValueError, TypeError):
        return datetime.now().strftime("%Y年%m月")


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


@router.post(
    "/api/reports/batch-delete",
    status_code=status.HTTP_200_OK,
    summary="批量删除课程记录",
)
async def batch_delete_records(
    body: dict = Body(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """批量删除课程记录。

    POST body:
      {"ids": [1, 2, 3]}
    """
    ids = body.get("ids", [])
    if not ids or not isinstance(ids, list):
        raise HTTPException(status_code=400, detail="ids 必须是非空数组")
    try:
        deleted = await record_svc.batch_delete_records(session, ids)
        return {"deleted": deleted, "total": len(ids)}
    except Exception as e:
        log.exception("批量删除失败: %s", e)
        raise HTTPException(status_code=500, detail=f"批量删除失败: {e}")


# =========================
# PDF 导出
# =========================

@router.post(
    "/api/reports/{record_id}/export",
    response_model=dict,
    summary="导出课程报告为 PDF",
)
async def export_report(
    record_id: int,
    body: dict = Body(default={"template_id": "classic"}),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """导出指定报告为 PDF 文件。

    - 加载报告和学生信息
    - 用指定模板渲染 HTML
    - Playwright（Chromium）渲染 PDF
    - 保存到 data/reports/ 并返回下载路径
    - 同时将报告状态更新为 finalized
    """
    template_id = body.get("template_id", "classic")
    layout_config = body.get("layout_config")
    output_dir = body.get("output_dir")

    # 1. 加载报告
    try:
        record = await record_svc.get_record(session, record_id)
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 如果没有传 layout_config，尝试从数据库记录加载
    if layout_config is None:
        from backend.services.course_records import _load_json
        layout_config = _load_json(getattr(record, "layout_config", None))

    # 如果请求中传了截图路径，覆盖数据库中的（与预览接口一致）
    body_screenshots = body.get("screenshot_paths")
    if body_screenshots is not None:
        import json as _json
        log.info("PDF导出: 收到截图路径 %d 条: %s", len(body_screenshots), body_screenshots[:3])
        record.screenshot_paths = _json.dumps(body_screenshots, ensure_ascii=False)
    else:
        log.info("PDF导出: 请求体中没有 screenshot_paths，使用 DB 中的原始值 (type=%s)", type(record.screenshot_paths).__name__)

    # 提取分类截图（单独传递给模板，用于图片展示）
    body_run_screenshots = body.get("run_screenshots")
    body_code_screenshots = body.get("code_screenshots")
    body_homework_screenshots = body.get("homework_screenshots")

    # 如果请求中没有传入分类截图，尝试从 project_meta 中恢复
    if not body_run_screenshots and not body_code_screenshots and not body_homework_screenshots:
        _pm = _load_json(getattr(record, "project_meta", None), {})
        _extra = _pm.get("_extra_screenshots", {})
        if not body_run_screenshots:
            body_run_screenshots = _extra.get("run", [])
        if not body_code_screenshots:
            body_code_screenshots = _extra.get("code", [])
        if not body_homework_screenshots:
            body_homework_screenshots = _extra.get("homework", [])

    # 2. 获取学生名
    student_name = ""
    if record.student_id:
        try:
            from backend.models import Student as StudentModel
            student = await session.get(
                StudentModel,
                record.student_id,
            )
            if student:
                student_name = student.name
        except Exception:
            pass

    # 3. 渲染 HTML
    try:
        renderer = ReportRenderer(template_id)
    except TemplateNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    html = renderer.render(
        record,
        student_name=student_name,
        layout_config=layout_config,
        run_screenshots=body_run_screenshots,
        code_screenshots=body_code_screenshots,
        homework_screenshots=body_homework_screenshots,
    )

    # 4. 生成 PDF（先保存到默认目录用于下载链接）
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    default_output_dir = Path(settings.report.output_dir)
    default_output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"report_{record_id}_{timestamp}.pdf"
    output_path = default_output_dir / filename

    # 从模板 + 布局配置计算页边距
    template_config = get_template_config(template_id)
    merged = merge_layout_with_theme(template_config, layout_config)
    pdf_margin = {
        "top": f"{merged['page_margin_top']}mm",
        "right": f"{merged['page_margin_right']}mm",
        "bottom": f"{merged['page_margin_bottom']}mm",
        "left": f"{merged['page_margin_left']}mm",
    }

    try:
        pdf_gen = PDFGenerator()
        await pdf_gen.generate(html, str(output_path), margin=pdf_margin)
    except PDFGenerationError as e:
        log.exception("PDF 生成失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # 5. 若有自定义输出路径，额外保存一份到指定目录，同时生成 JPG 长图
    custom_path = None
    jpg_path = None
    has_custom_dir = bool(output_dir or settings.report.custom_output_dir)
    if has_custom_dir:
        try:
            pdf_out, img_out = await _export_paths(record, student_name, output_dir, getattr(record, "project_folder", None), session)
            await pdf_gen.generate(html, str(pdf_out), margin=pdf_margin)
            custom_path = pdf_out
            log.info("PDF 已同步到自定义路径: %s", pdf_out)

            # 从自定义 PDF 生成 JPG 到 IMG 子目录
            if settings.image.enabled:
                img_out_dir = img_out.parent
                img_out_dir.mkdir(parents=True, exist_ok=True)
                jpg_path = pdf_to_long_image(
                    str(pdf_out),
                    output_path=str(img_out),
                    dpi=settings.image.dpi,
                    quality=settings.image.quality,
                )
                log.info("JPG 已生成到: %s", jpg_path or img_out)
        except Exception as e:
            log.warning("自定义路径导出失败: %s", e)

    # 6. 将默认 PDF 也转为 JPG（当没有自定义路径时）
    if not jpg_path and settings.image.enabled:
        try:
            jpg_path = pdf_to_long_image(
                str(output_path),
                dpi=settings.image.dpi,
                quality=settings.image.quality,
            )
        except Exception as e:
            log.warning("默认 PDF 转长图失败: %s", e)

    # 7. 更新状态为 finalized
    if record.status == "draft":
        await record_svc.update_record_status(session, record_id, "finalized")

    log.info("报告导出成功: record_id=%s template=%s pdf=%s", record_id, template_id, filename)
    resp = {
        "pdf_path": f"/api/reports/pdf/{filename}",
        "filename": filename,
        "template_id": template_id,
        "page_size": renderer.config.get("page_size", "A4"),
    }
    if custom_path:
        resp["custom_path"] = str(custom_path)
    if jpg_path:
        resp["jpg_path"] = jpg_path
    return resp


# =========================
# Word 导出
# =========================

@router.post(
    "/api/reports/{record_id}/export-word",
    response_model=dict,
    summary="导出课程报告为 Word 格式",
)
async def export_report_word(
    record_id: int,
    body: dict = Body(default={"template_id": "classic"}),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """导出指定课程报告为 .docx 文件。"""
    try:
        record = await record_svc.get_record(session, record_id)
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 获取学生姓名
    student_name = ""
    if record.student_id:
        from backend.models import Student as StudentModel
        student = await session.get(StudentModel, record.student_id)
        if student:
            student_name = student.name

    # 获取模板配置
    template_id = body.get("template_id", "classic")
    layout_config = body.get("layout_config")
    output_dir = body.get("output_dir")

    # 如果请求中传了截图路径，覆盖数据库中的（与 PDF 导出一致）
    body_screenshots = body.get("screenshot_paths")
    if body_screenshots is not None:
        import json as _json
        log.info("Word导出: 收到截图路径 %d 条", len(body_screenshots))
        record.screenshot_paths = _json.dumps(body_screenshots, ensure_ascii=False)
    else:
        log.info("Word导出: 使用 DB 中的截图路径 (type=%s)", type(record.screenshot_paths).__name__)

    template_config = None
    try:
        template_config = get_template_config(template_id)
    except (TemplateNotFoundError, FileNotFoundError):
        pass

    from backend.services.docx_generator import DocxGenerationError, generate as generate_docx

    try:
        docx_bytes = generate_docx(record, student_name, template_config, layout_config)
    except DocxGenerationError as e:
        raise HTTPException(status_code=500, detail=str(e))

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"report_{record_id}_{timestamp}.docx"
    output_path = Path(settings.report.output_dir) / filename
    output_path.write_bytes(docx_bytes)

    # 若有自定义输出路径，额外保存一份
    custom_path = None
    if output_dir or settings.report.custom_output_dir:
        try:
            pdf_out, _ = await _export_paths(record, student_name, output_dir, getattr(record, "project_folder", None), session)
            docx_path = pdf_out.with_suffix(".docx")
            docx_path.parent.mkdir(parents=True, exist_ok=True)
            docx_path.write_bytes(docx_bytes)
            custom_path = docx_path
            log.info("Word 已同步到自定义路径: %s", docx_path)
        except Exception as e:
            log.warning("自定义输出路径保存失败: %s", e)

    log.info("Word 导出成功: record_id=%s template=%s", record_id, template_id)
    resp = {
        "docx_path": f"/api/reports/pdf/{filename}",
        "filename": filename,
    }
    if custom_path:
        resp["custom_path"] = str(custom_path)
    return resp


@router.post(
    "/api/reports/{record_id}/export-word-stream",
    summary="导出课程报告为 Word 格式（流式下载）",
)
async def export_report_word_stream(
    record_id: int,
    body: dict = Body(default={"template_id": "classic"}),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """导出指定课程报告为 .docx 文件（流式下载）。"""
    from io import BytesIO

    try:
        record = await record_svc.get_record(session, record_id)
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    student_name = ""
    if record.student_id:
        from backend.models import Student as StudentModel
        student = await session.get(StudentModel, record.student_id)
        if student:
            student_name = student.name

    template_id = body.get("template_id", "classic")
    layout_config = body.get("layout_config")
    template_config = None
    try:
        template_config = get_template_config(template_id)
    except (TemplateNotFoundError, FileNotFoundError):
        pass

    from backend.services.docx_generator import DocxGenerationError, generate as generate_docx

    try:
        docx_bytes = generate_docx(record, student_name, template_config, layout_config)
    except DocxGenerationError as e:
        raise HTTPException(status_code=500, detail=str(e))

    filename = f"report_{record_id}_{record.course_date or 'unknown'}.docx"
    return StreamingResponse(
        BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# =========================
# 批量报告生成（以班级为单位）
# =========================

@router.post(
    "/api/reports/batch",
    response_model=BatchGenerateResponse,
    summary="批量生成班级报告",
)
async def batch_generate_reports(
    body: BatchGenerateRequest,
    session: AsyncSession = Depends(get_session),
) -> BatchGenerateResponse:
    """为班级内所有学生批量生成报告。

    流程：
    1. 验证班级存在，获取学生列表
    2. 若有 project_folder 则扫描项目
    3. 执行 AI 共享内容生成（Steps 1-3）
    4. 为每个学生生成个性评价（Step 4）
    5. 为每个学生创建 CourseRecord
    6. 若 auto_export 则导出 PDF
    """
    from datetime import date

    from backend.models import Class as ClassModel, Student as StudentModel
    from backend.schemas.project import ProjectMetaSchema
    from backend.schemas.student import StudentRead
    from backend.services.ai_orchestrator import AIOrchestrator

    # 1. 获取班级
    klass = await session.get(ClassModel, body.class_id)
    if klass is None:
        raise HTTPException(status_code=404, detail="班级不存在")

    # 2. 获取班级所有学生
    stmt = select(StudentModel).where(StudentModel.class_id == body.class_id)
    result = await session.execute(stmt)
    students = list(result.scalars().all())
    if not students:
        raise HTTPException(status_code=400, detail="该班级没有学生")

    # 3. 构建 ProjectMeta
    project_meta: ProjectMetaSchema | None = None
    scan_error: str | None = None
    if body.project_folder:
        from backend.schemas.project import FileInfoSchema, PyStructureSchema
        from backend.services import code_analyzer
        try:
            meta = code_analyzer.analyze_project(body.project_folder)
            project_meta = ProjectMetaSchema(
                folder=meta.folder,
                entry_file=meta.entry_file,
                project_type=meta.project_type,
                course_title=meta.course_title,
                all_files=[FileInfoSchema(**vars(f)) for f in meta.all_files],
                py_files=[
                    PyStructureSchema(
                        path=s.path,
                        imports=s.imports,
                        from_imports=[{"module": m, "name": n} for m, n in s.from_imports],
                        function_names=s.function_names,
                        class_names=s.class_names,
                        decorators=s.decorators,
                        top_comment=s.top_comment,
                        course_title=s.course_title,
                        line_count=s.line_count,
                    )
                    for s in meta.py_files
                ],
                all_imports=meta.all_imports,
                total_lines=meta.total_lines,
                warnings=meta.warnings,
            )
        except Exception as e:
            log.warning("项目扫描失败: %s", e)
            scan_error = str(e)

    # 补充 course_topic
    course_topic = body.course_topic or (project_meta.course_title if project_meta else "") or "课程报告"
    course_date = body.course_date or date.today().isoformat()

    # 4. 生成共享内容（Steps 1-3）
    orchestrator = AIOrchestrator()
    shared = {}
    shared_error = None
    if project_meta:
        try:
            # 使用第一个学生作为"默认学生"（仅用于 homework_vocab 中的 level 参考）
            default_student_read = StudentRead(
                id=students[0].id,
                name=students[0].name,
                gender=students[0].gender or "",
                grade=students[0].grade or "",
                base_level=students[0].base_level,
                characteristics=students[0].characteristics or [],
                parent_contact=students[0].parent_contact or "",
                note=students[0].note or "",
                class_id=students[0].class_id,
                created_at=students[0].created_at,
                updated_at=students[0].updated_at,
            )
            shared = await orchestrator.generate_shared(
                project_meta,
                default_student_read,
                teacher_observation=body.teacher_observation,
                code_screenshots=body.code_screenshots,
                homework_screenshots=body.homework_screenshots,
                create_vocabulary=body.create_vocabulary,
                skip_code_analysis=bool(body.code_screenshots),
                skip_homework_gen=bool(body.homework_screenshots),
                existing_content=body.existing_content,
            )
        except Exception as e:
            log.exception("共享内容生成失败: %s", e)
            shared_error = str(e)

    # 5. 为每个学生生成评价
    student_reads = [
        StudentRead(
            id=s.id, name=s.name, gender=s.gender or "", grade=s.grade or "",
            base_level=s.base_level, characteristics=s.characteristics or [],
            parent_contact=s.parent_contact or "", note=s.note or "",
            class_id=s.class_id,
            created_at=s.created_at, updated_at=s.updated_at,
        )
        for s in students
    ]

    # 批量生成评价（利用共享会话的记忆，不重复调用 LLM 读代码）
    evaluations: list[str | Exception] = []
    if project_meta and shared and not shared_error:
        try:
            evaluations = await orchestrator.generate_evaluations(
                project_meta, student_reads, shared,
                teacher_observation=body.teacher_observation,
                observations=body.observations,
            )
        except Exception as e:
            log.exception("批量评价生成失败: %s", e)
            evaluations = [e] * len(students)
    elif scan_error:
        evaluations = [f"项目扫描失败: {scan_error}"] * len(students)
    elif not body.project_folder:
        evaluations = [""] * len(students)
    elif shared_error:
        evaluations = [f"AI 内容生成失败: {shared_error}"] * len(students)
    else:
        evaluations = [""] * len(students)

    # 6. 构建批量报告（1 条 BatchReport，替代 N 条 CourseRecord）
    from backend.services import batch_reports as batch_svc

    results: list[BatchStudentResult] = []
    evaluations_dict: dict[str, dict] = {}

    for i, student in enumerate(students):
        evaluation_text = ""
        error_text = None

        eval_result = evaluations[i] if i < len(evaluations) else None
        if isinstance(eval_result, Exception):
            error_text = str(eval_result)
        elif isinstance(eval_result, str):
            evaluation_text = eval_result
        elif eval_result is None:
            error_text = "评价生成为空"

        evaluations_dict[str(student.id)] = {
            "name": student.name,
            "evaluation": evaluation_text,
        }

        results.append(BatchStudentResult(
            student_id=student.id,
            student_name=student.name,
            evaluation=evaluation_text[:300] if evaluation_text else "",
            error=error_text,
        ))

    # 创建 BatchReport
    batch_id = None
    try:
        batch_data = {
            "class_id": body.class_id,
            "class_name": klass.name,
            "course_date": course_date,
            "course_topic": course_topic,
            "project_folder": body.project_folder or "",
            "template_id": body.template_id,
            "knowledge_points": json.dumps(shared.get("knowledge_points", []), ensure_ascii=False),
            "ability_improvement": shared.get("ability_improvement", ""),
            "content_items": json.dumps(shared.get("content_items", []), ensure_ascii=False),
            "homework": json.dumps(shared.get("homework", {}), ensure_ascii=False),
            "vocabulary": json.dumps(shared.get("vocabulary", {}), ensure_ascii=False),
            "evaluations": json.dumps(evaluations_dict, ensure_ascii=False),
            "screenshot_paths": json.dumps(list(body.screenshot_paths), ensure_ascii=False),
            "run_screenshots": json.dumps(list(body.run_screenshots), ensure_ascii=False),
            "code_screenshots": json.dumps(list(body.code_screenshots), ensure_ascii=False),
            "homework_screenshots": json.dumps(list(body.homework_screenshots), ensure_ascii=False),
            "logo_config": json.dumps(_resolve_logo_config(body.template_id), ensure_ascii=False),
            "teacher_observation": body.teacher_observation or "",
            "observations": json.dumps(body.observations or {}, ensure_ascii=False),
            "ai_meta": json.dumps(shared.get("code_analysis"), ensure_ascii=False) if shared.get("code_analysis") else None,
            "status": "draft",
        }
        batch = await batch_svc.create_batch_report(session, batch_data)
        batch_id = batch.id
        log.info("批量报告创建成功: id=%s class=%s", batch_id, klass.name)
    except Exception as e:
        log.exception("创建批量报告失败: %s", e)

    # 7. 若 auto_export 则导出 PDF
    if body.auto_export and not shared_error and batch_id:
        from types import SimpleNamespace as _NS

        # 构造伪 record 供渲染（共享内容 + 当前学生评价）
        def _make_record(student_id: int, eval_text: str) -> _NS:
            return _NS(
                id=batch_id,
                student_id=student_id,
                evaluation=eval_text,
                course_topic=course_topic,
                course_date=course_date,
                ability_improvement=shared.get("ability_improvement", ""),
                knowledge_points=json.dumps(shared.get("knowledge_points", []), ensure_ascii=False),
                content_items=json.dumps(shared.get("content_items", []), ensure_ascii=False),
                vocabulary=json.dumps(shared.get("vocabulary", {}), ensure_ascii=False),
                homework=json.dumps(shared.get("homework", {}), ensure_ascii=False),
                logo_config=json.dumps(_resolve_logo_config(body.template_id), ensure_ascii=False),
                teacher_observation=body.teacher_observation or "",
                observations=json.dumps(body.observations or {}, ensure_ascii=False),
                project_folder=body.project_folder or "",
                project_meta=None,
                ai_meta=None,
                screenshot_paths=json.dumps(list(body.screenshot_paths), ensure_ascii=False),
            )

        tpl_cfg = get_template_config(body.template_id)
        tpl_merged = merge_layout_with_theme(tpl_cfg, None)
        batch_margin = {
            "top": f"{tpl_merged['page_margin_top']}mm",
            "right": f"{tpl_merged['page_margin_right']}mm",
            "bottom": f"{tpl_merged['page_margin_bottom']}mm",
            "left": f"{tpl_merged['page_margin_left']}mm",
        }
        pdf_gen = PDFGenerator()
        for i, result in enumerate(results):
            try:
                student_name = result.student_name or "学生"
                template_id = body.template_id
                rec = _make_record(result.student_id, result.evaluation or "")
                renderer = ReportRenderer(template_id)
                html = renderer.render(
                    rec, student_name=student_name,
                    run_screenshots=body.run_screenshots,
                    code_screenshots=body.code_screenshots,
                    homework_screenshots=body.homework_screenshots,
                )

                has_custom_dir = bool(body.output_dir or settings.report.custom_output_dir or body.project_folder)
                if has_custom_dir:
                    pdf_out, img_out = await _export_paths(rec, student_name, body.output_dir, body.project_folder, session)
                    output_path = pdf_out
                else:
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                    output_path = Path(settings.report.output_dir) / f"batch_{batch_id}_{result.student_id}_{timestamp}.pdf"

                await pdf_gen.generate(html, str(output_path), margin=batch_margin)
                log.info("批量导出 PDF 成功: student_id=%s path=%s", result.student_id, output_path)

                # 自动将 PDF 转为 JPG 长图
                if has_custom_dir and settings.image.enabled:
                    try:
                        img_out.parent.mkdir(parents=True, exist_ok=True)
                        pdf_to_long_image(
                            str(output_path),
                            output_path=str(img_out),
                            dpi=settings.image.dpi,
                            quality=settings.image.quality,
                        )
                        log.info("批量 JPG 已生成: %s", img_out)
                    except Exception as e:
                        log.warning("批量 PDF 转长图失败 student_id=%s: %s", result.student_id, e)
                elif output_path.exists() and settings.image.enabled:
                    try:
                        pdf_to_long_image(str(output_path))
                    except Exception as e:
                        log.warning("批量 PDF 转长图失败 student_id=%s: %s", result.student_id, e)
            except Exception as e:
                log.warning("批量导出 PDF 失败 student_id=%s: %s", result.student_id, e)

    success_count = sum(1 for r in results if r.error is None)
    return BatchGenerateResponse(
        class_name=klass.name,
        total=len(results),
        success=success_count,
        failed=len(results) - success_count,
        results=results,
        batch_id=batch_id,
    )


# =========================
# 报告预览
# =========================

@router.post(
    "/api/reports/{record_id}/preview",
    response_class=Response,
    summary="预览报告 HTML（可带布局覆盖）",
)
async def preview_report(
    record_id: int,
    body: dict = Body(default={}),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """预览报告 HTML，支持传递 layout_config 即时生效。

    POST body 可选字段:
      - template_id (str): 默认 "classic"
      - layout_config (dict): 布局覆盖（与 LayoutConfigSchema 一致）
      - screenshot_paths (list[str]): 覆盖截图路径（不传则使用数据库记录中的截图）

    返回 Content-Type: text/html，可直接在 iframe 中展示。
    """
    import json as _json

    template_id = body.get("template_id", "classic")
    layout_config = body.get("layout_config")
    body_screenshots = body.get("screenshot_paths")

    try:
        record = await record_svc.get_record(session, record_id)
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 如果请求中传了截图路径，覆盖数据库中的
    if body_screenshots is not None:
        log.info("预览: 收到截图路径 %d 条: %s", len(body_screenshots), body_screenshots[:3])
        record.screenshot_paths = _json.dumps(body_screenshots, ensure_ascii=False)
    else:
        log.info("预览: 请求体中没有 screenshot_paths，使用 DB 原始值 (type=%s)", type(record.screenshot_paths).__name__)

    # 提取分类截图
    body_run_screenshots = body.get("run_screenshots")
    body_code_screenshots = body.get("code_screenshots")
    body_homework_screenshots = body.get("homework_screenshots")

    # 如果请求中没有传入分类截图，尝试从 project_meta 中恢复
    if not body_run_screenshots and not body_code_screenshots and not body_homework_screenshots:
        _pm = _load_json(getattr(record, "project_meta", None), {})
        _extra = _pm.get("_extra_screenshots", {})
        if not body_run_screenshots:
            body_run_screenshots = _extra.get("run", [])
        if not body_code_screenshots:
            body_code_screenshots = _extra.get("code", [])
        if not body_homework_screenshots:
            body_homework_screenshots = _extra.get("homework", [])

    student_name = ""
    if record.student_id:
        try:
            from backend.models import Student as StudentModel
            student = await session.get(StudentModel, record.student_id)
            if student:
                student_name = student.name
        except Exception:
            pass

    try:
        renderer = ReportRenderer(template_id)
    except TemplateNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    html = renderer.render(record, student_name=student_name, layout_config=layout_config, run_screenshots=body_run_screenshots, code_screenshots=body_code_screenshots, homework_screenshots=body_homework_screenshots)
    html = wrap_preview_html(html)
    return Response(content=html, media_type="text/html; charset=utf-8")


# =========================
# 模板管理
# =========================

@router.get(
    "/api/templates",
    response_model=list[TemplateListItem],
    summary="获取可用内置模板列表",
)
async def templates_list() -> list[TemplateListItem]:
    """返回所有可用模板及其元信息。"""
    templates = list_templates()
    return [TemplateListItem(**t) for t in templates]


@router.get(
    "/api/templates/{template_id}/config",
    response_model=dict,
    summary="获取单个模板完整配置（含主题默认值）",
)
async def template_config(
    template_id: str,
) -> dict:
    """返回指定模板的完整 config.json。

    前端可用此接口初始化布局设置面板的默认值。
    """
    try:
        config = get_template_config(template_id)
        return config
    except TemplateNotFoundError as e:
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
