"""批量报告 API 路由（BatchReport CRUD + 导出/预览）。"""
from __future__ import annotations

import json as _json
from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import PROJECT_ROOT, get_settings
from backend.db import get_session
from backend.schemas.batch import BatchReportRead, BatchReportUpdate
from backend.services import batch_reports as batch_svc
from backend.services.batch_reports import BatchReportNotFoundError
from backend.services.pdf_generator import PDFGenerationError, PDFGenerator
from backend.services.report_renderer import (
    ReportRenderer,
    TemplateNotFoundError,
    get_template_config,
    merge_layout_with_theme,
    wrap_preview_html,
)
from backend.services.pdf_to_image import pdf_to_long_image
from backend.utils.logger import get_logger

log = get_logger(__name__)
settings = get_settings()

router = APIRouter(tags=["batch-reports"])

# =========================
# 准备导出/预览用的 record 对象
# =========================

# 渲染器需要 JSON 字符串，而 BatchReport 的共享内容字段也是 JSON 字符串，
# 所以直接 passthrough——把 BatchReport 的原始 db 属性放在 SimpleNamespace 上。
PDF_SUBDIR = "PDF(用于打印)"
IMG_SUBDIR = "IMG(用于发送)"


def _sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符。"""
    import re as _re
    return _re.sub(r'[<>:"/\\|?*]', '_', name).strip(' .') or '未命名'


def _sanitize_date_dir(course_date: str) -> str:
    """将上课日期格式化为安全的目录名（YYYY-MM-DD）。"""
    from datetime import datetime as _dt
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%Y.%m.%d"):
        try:
            return _dt.strptime(course_date.strip(), fmt).strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            continue
    import re as _re
    safe = _re.sub(r"[^\d-]", "", course_date.strip())
    return safe[:10] if safe else "未设置日期"


def _load_json(value: str | None, default=None):
    """安全解析 JSON 字符串。"""
    if value is None:
        return default
    try:
        return _json.loads(value)
    except (_json.JSONDecodeError, TypeError):
        return default


def _build_batch_record(
    batch,
    student_id: int,
    student_name: str,
    evaluation_text: str,
    code_screenshots: list[str] | None = None,
    run_screenshots: list[str] | None = None,
    homework_screenshots: list[str] | None = None,
    screenshot_paths: list[str] | None = None,
    # 共享内容覆盖（不传则使用 DB 中的值）
    homework_override: dict | None = None,
    knowledge_points_override: list[str] | None = None,
    ability_improvement_override: str | None = None,
    content_items_override: list[dict] | None = None,
    vocabulary_override: dict | None = None,
    # PR3: 学生展示图覆盖（不传则从 batch.student_showcase_photos 按 student_id 取）
    showcase_photo: str | None = None,
):
    """从 BatchReport + 学生评价构造 SimpleNamespace 伪 record（与 renderer 兼容）。

    可传共享内容覆盖参数，不传则从 batch 数据库记录读取。
    PR3: showcase_photo 不传时，从 batch.student_showcase_photos JSON 里按 student_id 取对应 url。
    """
    # PR3: 解析该学生的展示图 URL
    if showcase_photo is None:
        try:
            photos = _json.loads(batch.student_showcase_photos or "{}")
        except (_json.JSONDecodeError, TypeError):
            photos = {}
        if isinstance(photos, dict):
            showcase_photo = photos.get(str(student_id))

    record = SimpleNamespace(
        id=batch.id,
        student_id=student_id,
        evaluation=evaluation_text,
        course_topic=batch.course_topic,
        course_date=batch.course_date,
        ability_improvement=ability_improvement_override if ability_improvement_override is not None else (batch.ability_improvement or ""),
        knowledge_points=_json.dumps(knowledge_points_override, ensure_ascii=False) if knowledge_points_override is not None else (batch.knowledge_points or "[]"),
        content_items=_json.dumps(content_items_override, ensure_ascii=False) if content_items_override is not None else (batch.content_items or "[]"),
        vocabulary=_json.dumps(vocabulary_override, ensure_ascii=False) if vocabulary_override is not None else (batch.vocabulary or "{}"),
        homework=_json.dumps(homework_override, ensure_ascii=False) if homework_override is not None else (batch.homework or "{}"),
        logo_config=batch.logo_config or "{}",
        teacher_observation=batch.teacher_observation or "",
        observations=batch.observations or "{}",
        project_folder=batch.project_folder or "",
        project_meta=None,
        ai_meta=batch.ai_meta or None,
        # 截图（覆盖）
        screenshot_paths=_json.dumps(screenshot_paths or [], ensure_ascii=False),
        _code_screenshots=code_screenshots or [],
        _run_screenshots=run_screenshots or [],
        _homework_screenshots=homework_screenshots or [],
        # PR3: 学生展示图（每学生独有）
        _showcase_photo=showcase_photo,
    )
    return record


def _resolve_logo_config(template_id: str) -> dict:
    """优先从模板 config.json 读 logo_config，没有则用空 dict。"""
    try:
        tpl_cfg = get_template_config(template_id)
        if isinstance(tpl_cfg, dict) and tpl_cfg.get("logo_config"):
            return dict(tpl_cfg["logo_config"])
    except Exception:
        pass
    return {}


# =========================
# CRUD
# =========================


@router.get(
    "/api/batch-reports",
    response_model=dict,
    summary="批量报告列表（可指定班级，或全部）",
)
async def list_batch_reports(
    class_id: int | None = Query(None, description="班级 ID（可选，不传则查全部）"),
    keyword: str | None = Query(None, description="按课程名/班级名搜索"),
    status: str | None = Query(None, description="按状态过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """列出批量报告，按创建时间倒序。

    传 class_id 则只查该班级，否则查全部（支持 keyword/status 筛选）。
    """
    offset = (page - 1) * page_size
    if class_id is not None:
        items, total = await batch_svc.list_batch_reports_by_class(
            session, class_id, limit=page_size, offset=offset,
        )
    else:
        items, total = await batch_svc.list_all_batch_reports(
            session, keyword=keyword, status=status, limit=page_size, offset=offset,
        )
    return {
        "items": [batch_svc.to_list_dict(r) for r in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/api/batch-reports/{batch_id}",
    response_model=BatchReportRead,
    summary="获取单条批量报告",
)
async def get_batch_report(
    batch_id: int,
    session: AsyncSession = Depends(get_session),
) -> BatchReportRead:
    try:
        record = await batch_svc.get_batch_report(session, batch_id)
    except BatchReportNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return BatchReportRead(**batch_svc.to_read_dict(record))


@router.patch(
    "/api/batch-reports/{batch_id}",
    response_model=BatchReportRead,
    summary="更新批量报告（评价、共享内容、状态等）",
)
async def update_batch_report(
    batch_id: int,
    data: BatchReportUpdate,
    session: AsyncSession = Depends(get_session),
) -> BatchReportRead:
    """支持更新 evaluations、共享内容、screenshots、status 等。"""
    update_dict = {}

    # JSON 字段序列化辅助
    def _to_json(val):
        return _json.dumps(val, ensure_ascii=False) if val is not None else None

    if data.evaluations is not None:
        update_dict["evaluations"] = _to_json(data.evaluations)
    if data.status is not None:
        update_dict["status"] = data.status
    if data.knowledge_points is not None:
        update_dict["knowledge_points"] = _to_json(data.knowledge_points)
    if data.ability_improvement is not None:
        update_dict["ability_improvement"] = data.ability_improvement
    if data.content_items is not None:
        update_dict["content_items"] = _to_json(data.content_items)
    if data.homework is not None:
        update_dict["homework"] = _to_json(data.homework)
    if data.vocabulary is not None:
        update_dict["vocabulary"] = _to_json(data.vocabulary)
    if data.teacher_observation is not None:
        update_dict["teacher_observation"] = data.teacher_observation
    if data.observations is not None:
        update_dict["observations"] = _to_json(data.observations)
    if data.template_id is not None:
        update_dict["template_id"] = data.template_id
    if data.run_screenshots is not None:
        update_dict["run_screenshots"] = _to_json(data.run_screenshots)
    if data.code_screenshots is not None:
        update_dict["code_screenshots"] = _to_json(data.code_screenshots)
    if data.course_date is not None:
        update_dict["course_date"] = data.course_date
    if data.course_topic is not None:
        update_dict["course_topic"] = data.course_topic
    if data.course_description is not None:
        update_dict["course_description"] = data.course_description
    if data.homework_screenshots is not None:
        update_dict["homework_screenshots"] = _to_json(data.homework_screenshots)
    if data.screenshot_paths is not None:
        update_dict["screenshot_paths"] = _to_json(data.screenshot_paths)

    try:
        record = await batch_svc.update_batch_report(session, batch_id, update_dict)
    except BatchReportNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return BatchReportRead(**batch_svc.to_read_dict(record))


@router.delete(
    "/api/batch-reports/{batch_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除批量报告",
)
async def delete_batch_report(
    batch_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        await batch_svc.delete_batch_report(session, batch_id)
    except BatchReportNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return None


@router.post(
    "/api/batch-reports/batch-delete",
    status_code=status.HTTP_200_OK,
    summary="批量删除批量报告",
)
async def batch_delete_batch_reports(
    body: dict = Body(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """批量删除批量报告。
    POST body: {"ids": [1, 2, 3]}
    """
    ids = body.get("ids", [])
    if not ids or not isinstance(ids, list):
        raise HTTPException(status_code=400, detail="ids 必须是非空数组")
    deleted = 0
    for bid in ids:
        try:
            await batch_svc.delete_batch_report(session, bid)
            deleted += 1
        except BatchReportNotFoundError:
            continue
    return {"deleted": deleted, "total": len(ids)}


@router.patch(
    "/api/batch-reports/{batch_id}/status",
    response_model=BatchReportRead,
    summary="变更批量报告状态",
)
async def update_batch_report_status(
    batch_id: int,
    body: dict = Body(...),
    session: AsyncSession = Depends(get_session),
) -> BatchReportRead:
    """变更批量报告状态。"""
    status_val = body.get("status")
    if status_val not in ("draft", "finalized", "archived"):
        raise HTTPException(status_code=400, detail="无效的状态值")
    try:
        record = await batch_svc.update_batch_report(session, batch_id, {"status": status_val})
    except BatchReportNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return BatchReportRead(**batch_svc.to_read_dict(record))


# =========================
# 预览
# =========================


@router.post(
    "/api/batch-reports/{batch_id}/preview/{student_id}",
    response_class=Response,
    summary="批量报告预览（单个学生）",
)
async def preview_batch_report(
    batch_id: int,
    student_id: int,
    body: dict = Body(default={}),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """预览某个学生在批量报告中的版本。

    POST body 可选字段:
      - template_id (str): 默认使用 batch 的 template_id
      - overrides (dict): 临时覆盖 batch 字段（不写库），如 course_date
      - screenshot_paths, run_screenshots, code_screenshots, homework_screenshots
    """
    template_id = body.get("template_id")

    try:
        batch = await batch_svc.get_batch_report(session, batch_id)
    except BatchReportNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 应用临时 overrides（不写库，仅本次预览生效）
    # 注意：batch 的共享字段以 JSON 字符串存储（如 homework、knowledge_points），
    # 因此传入的 dict/list 需要先序列化。
    overrides = body.get("overrides") or {}
    if overrides:
        json_fields = {"knowledge_points", "content_items", "homework", "vocabulary", "evaluations", "observations"}
        for key, value in overrides.items():
            if hasattr(batch, key):
                if key in json_fields and isinstance(value, (dict, list)):
                    setattr(batch, key, _json.dumps(value, ensure_ascii=False))
                else:
                    setattr(batch, key, value)

    template_id = template_id or batch.template_id or "classic"
    layout_config = body.get("layout_config")

    # 获取学生姓名和评价
    from backend.models import Student as StudentModel
    student = await session.get(StudentModel, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    student_name = student.name

    evaluations = _load_json(batch.evaluations, {})
    student_eval = evaluations.get(str(student_id), {})
    if isinstance(student_eval, dict):
        eval_text = student_eval.get("evaluation", "")
    else:
        eval_text = str(student_eval)

    # 截图参数
    run_screenshots = body.get("run_screenshots", [])
    code_screenshots = body.get("code_screenshots", [])
    homework_screenshots = body.get("homework_screenshots", [])
    screenshot_paths = body.get("screenshot_paths", [])

    # 共享内容覆盖（前端传入，不依赖数据库回读）
    homework_override = body.get("homework")
    knowledge_points_override = body.get("knowledge_points")
    ability_improvement_override = body.get("ability_improvement")
    content_items_override = body.get("content_items")
    vocabulary_override = body.get("vocabulary")

    # ===== DEBUG: 追踪 homework 值 =====
    log.info("预览 DEBUG: batch.homework 类型=%s", type(batch.homework).__name__)
    log.info("预览 DEBUG: batch.homework 原始值(前200)=%s", str(batch.homework)[:200] if batch.homework else "None")

    if homework_override is not None:
        hw_goal = homework_override.get("goal", "")[:40] if isinstance(homework_override, dict) else str(homework_override)[:40]
        log.info("预览 batch=%d student=%d 使用前端 homework.goal=%s", batch_id, student_id, hw_goal)
    else:
        raw = batch.homework or ""
        hw_goal = _json.loads(raw).get("goal", "")[:40] if raw else "(none)"
        log.info("预览 batch=%d student=%d 使用 DB homework.goal=%s", batch_id, student_id, hw_goal)

    record = _build_batch_record(
        batch, student_id, student_name, eval_text,
        code_screenshots=code_screenshots,
        run_screenshots=run_screenshots,
        homework_screenshots=homework_screenshots,
        screenshot_paths=screenshot_paths,
        homework_override=homework_override,
        knowledge_points_override=knowledge_points_override,
        ability_improvement_override=ability_improvement_override,
        content_items_override=content_items_override,
        vocabulary_override=vocabulary_override,
    )

    try:
        renderer = ReportRenderer(template_id)
    except TemplateNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    html = renderer.render(
        record,
        student_name=student_name,
        layout_config=layout_config,
        run_screenshots=run_screenshots,
        code_screenshots=code_screenshots,
        homework_screenshots=homework_screenshots,
        showcase_photo=getattr(record, "_showcase_photo", None),
    )
    html = wrap_preview_html(html)
    return Response(content=html, media_type="text/html; charset=utf-8")


# =========================
# PDF 导出
# =========================


@router.post(
    "/api/batch-reports/{batch_id}/export/{student_id}",
    response_model=dict,
    summary="批量报告导出 PDF（单个学生）",
)
async def export_batch_report(
    batch_id: int,
    student_id: int,
    body: dict = Body(default={}),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """导出某个学生在批量报告中的报告为 PDF。"""
    template_id = body.get("template_id")

    try:
        batch = await batch_svc.get_batch_report(session, batch_id)
    except BatchReportNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    template_id = template_id or batch.template_id or "classic"
    layout_config = body.get("layout_config")
    output_dir = body.get("output_dir")

    # 获取学生姓名和评价
    from backend.models import Student as StudentModel
    student = await session.get(StudentModel, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    student_name = student.name

    evaluations = _load_json(batch.evaluations, {})
    student_eval = evaluations.get(str(student_id), {})
    if isinstance(student_eval, dict):
        eval_text = student_eval.get("evaluation", "")
    else:
        eval_text = str(student_eval)

    # 截图参数
    run_screenshots = body.get("run_screenshots", [])
    code_screenshots = body.get("code_screenshots", [])
    homework_screenshots = body.get("homework_screenshots", [])
    screenshot_paths = body.get("screenshot_paths", [])

    # 共享内容覆盖（前端传入，不依赖数据库回读）
    homework_override = body.get("homework")
    knowledge_points_override = body.get("knowledge_points")
    ability_improvement_override = body.get("ability_improvement")
    content_items_override = body.get("content_items")
    vocabulary_override = body.get("vocabulary")

    record = _build_batch_record(
        batch, student_id, student_name, eval_text,
        code_screenshots=code_screenshots,
        run_screenshots=run_screenshots,
        homework_screenshots=homework_screenshots,
        screenshot_paths=screenshot_paths,
        homework_override=homework_override,
        knowledge_points_override=knowledge_points_override,
        ability_improvement_override=ability_improvement_override,
        content_items_override=content_items_override,
        vocabulary_override=vocabulary_override,
    )

    # 渲染 HTML
    try:
        renderer = ReportRenderer(template_id)
    except TemplateNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    html = renderer.render(
        record,
        student_name=student_name,
        layout_config=layout_config,
        run_screenshots=run_screenshots,
        code_screenshots=code_screenshots,
        homework_screenshots=homework_screenshots,
        showcase_photo=getattr(record, "_showcase_photo", None),
    )

    # 计算页边距
    tpl_config = get_template_config(template_id)
    merged = merge_layout_with_theme(tpl_config, layout_config)
    pdf_margin = {
        "top": f"{merged['page_margin_top']}mm",
        "right": f"{merged['page_margin_right']}mm",
        "bottom": f"{merged['page_margin_bottom']}mm",
        "left": f"{merged['page_margin_left']}mm",
    }

    # 默认输出路径
    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    default_output_dir = Path(settings.report.output_dir)
    default_output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"batch_report_{batch_id}_{student_id}_{timestamp}.pdf"
    output_path = default_output_dir / filename

    try:
        pdf_gen = PDFGenerator()
        await pdf_gen.generate(html, str(output_path), margin=pdf_margin)
    except PDFGenerationError as e:
        log.exception("PDF 生成失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # 自定义路径
    custom_path = None
    jpg_path = None
    has_custom_dir = bool(output_dir or settings.report.custom_output_dir or batch.project_folder)

    if has_custom_dir:
        try:
            # 用 batch 的 class_name + course_date 构建路径
            date_part = _sanitize_date_dir(batch.course_date) if batch.course_date else "未设置日期"
            class_name = batch.class_name or "未分班"
            session_part = f"{date_part}_{_sanitize_filename(class_name)}"

            base_str = output_dir or batch.project_folder or settings.report.custom_output_dir or settings.report.output_dir
            base_dir = Path(base_str)
            if not base_dir.is_absolute():
                base_dir = PROJECT_ROOT / base_str

            session_dir = base_dir / session_part
            safe_name = _sanitize_filename(student_name or "学生")
            safe_topic = _sanitize_filename(batch.course_topic or "课程")
            basename = f"{safe_name}_{safe_topic}"

            pdf_dir = session_dir / PDF_SUBDIR
            img_dir = session_dir / IMG_SUBDIR
            pdf_dir.mkdir(parents=True, exist_ok=True)
            img_dir.mkdir(parents=True, exist_ok=True)

            pdf_out = pdf_dir / f"{basename}.pdf"
            img_out = img_dir / f"{basename}.jpg"

            # 冲突时追加时间戳
            now_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            if pdf_out.exists():
                pdf_out = pdf_dir / f"{basename}_{now_ts}.pdf"
            if img_out.exists():
                img_out = img_dir / f"{basename}_{now_ts}.jpg"

            await pdf_gen.generate(html, str(pdf_out), margin=pdf_margin)
            custom_path = pdf_out
            log.info("批量报告 PDF 已同步到自定义路径: %s", pdf_out)

            if settings.image.enabled:
                img_out.parent.mkdir(parents=True, exist_ok=True)
                jpg_path = pdf_to_long_image(
                    str(pdf_out),
                    output_path=str(img_out),
                    dpi=settings.image.dpi,
                    quality=settings.image.quality,
                )
                log.info("批量报告 JPG 已生成: %s", jpg_path or img_out)
        except Exception as e:
            log.warning("批量报告自定义路径导出失败: %s", e)

    # 默认 PDF 转 JPG
    if not jpg_path and settings.image.enabled:
        try:
            jpg_path = pdf_to_long_image(
                str(output_path),
                dpi=settings.image.dpi,
                quality=settings.image.quality,
            )
        except Exception as e:
            log.warning("批量报告默认 PDF 转长图失败: %s", e)

    # 导出成功后更新状态为 finalized
    if batch.status == "draft":
        try:
            await batch_svc.update_batch_report(session, batch_id, {"status": "finalized"})
            log.info("批量报告状态已更新为 finalized: id=%s", batch_id)
        except Exception as e:
            log.warning("批量报告状态更新失败: %s", e)

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
    "/api/batch-reports/{batch_id}/export-word/{student_id}",
    response_model=dict,
    summary="批量报告导出 Word（单个学生）",
)
async def export_batch_word(
    batch_id: int,
    student_id: int,
    body: dict = Body(default={}),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """导出某个学生在批量报告中的报告为 Word。"""
    template_id = body.get("template_id")

    try:
        batch = await batch_svc.get_batch_report(session, batch_id)
    except BatchReportNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    template_id = template_id or batch.template_id or "classic"
    layout_config = body.get("layout_config")
    output_dir = body.get("output_dir")

    # 获取学生姓名和评价
    from backend.models import Student as StudentModel
    student = await session.get(StudentModel, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    student_name = student.name

    evaluations = _load_json(batch.evaluations, {})
    student_eval = evaluations.get(str(student_id), {})
    if isinstance(student_eval, dict):
        eval_text = student_eval.get("evaluation", "")
    else:
        eval_text = str(student_eval)

    # 截图参数
    run_screenshots = body.get("run_screenshots", [])
    code_screenshots = body.get("code_screenshots", [])
    homework_screenshots = body.get("homework_screenshots", [])
    screenshot_paths = body.get("screenshot_paths", [])

    # 共享内容覆盖（前端传入，不依赖数据库回读）
    homework_override = body.get("homework")
    knowledge_points_override = body.get("knowledge_points")
    ability_improvement_override = body.get("ability_improvement")
    content_items_override = body.get("content_items")
    vocabulary_override = body.get("vocabulary")

    record = _build_batch_record(
        batch, student_id, student_name, eval_text,
        code_screenshots=code_screenshots,
        run_screenshots=run_screenshots,
        homework_screenshots=homework_screenshots,
        screenshot_paths=screenshot_paths,
        homework_override=homework_override,
        knowledge_points_override=knowledge_points_override,
        ability_improvement_override=ability_improvement_override,
        content_items_override=content_items_override,
        vocabulary_override=vocabulary_override,
    )

    # 获取模板配置
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

    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"batch_report_{batch_id}_{student_id}_{timestamp}.docx"
    output_path = Path(settings.report.output_dir) / filename
    output_path.write_bytes(docx_bytes)

    # 自定义路径
    custom_path = None
    if output_dir or settings.report.custom_output_dir or batch.project_folder:
        try:
            date_part = _sanitize_date_dir(batch.course_date) if batch.course_date else "未设置日期"
            class_name = batch.class_name or "未分班"
            session_part = f"{date_part}_{_sanitize_filename(class_name)}"

            base_str = output_dir or batch.project_folder or settings.report.custom_output_dir or settings.report.output_dir
            base_dir = Path(base_str)
            if not base_dir.is_absolute():
                base_dir = PROJECT_ROOT / base_str

            session_dir = base_dir / session_part
            safe_name = _sanitize_filename(student_name or "学生")
            safe_topic = _sanitize_filename(batch.course_topic or "课程")
            basename = f"{safe_name}_{safe_topic}"

            pdf_dir = session_dir / PDF_SUBDIR
            pdf_dir.mkdir(parents=True, exist_ok=True)
            docx_path = pdf_dir / f"{basename}.docx"
            docx_path.parent.mkdir(parents=True, exist_ok=True)
            docx_path.write_bytes(docx_bytes)
            custom_path = docx_path
            log.info("批量报告 Word 已同步到自定义路径: %s", docx_path)
        except Exception as e:
            log.warning("批量报告 Word 自定义路径保存失败: %s", e)

    # 导出成功后更新状态为 finalized
    if batch.status == "draft":
        try:
            await batch_svc.update_batch_report(session, batch_id, {"status": "finalized"})
            log.info("批量报告 Word 状态已更新为 finalized: id=%s", batch_id)
        except Exception as e:
            log.warning("批量报告 Word 状态更新失败: %s", e)

    log.info("批量报告 Word 导出成功: batch_id=%s student_id=%s", batch_id, student_id)
    resp = {
        "docx_path": f"/api/reports/pdf/{filename}",
        "filename": filename,
    }
    if custom_path:
        resp["custom_path"] = str(custom_path)
    return resp


# =========================
# 批量多学生导出（PR2：报告中心批量导出）
# =========================
#
# 设计要点：
# - 不重构现有 export_batch_report / export_batch_word，避免破坏既有调用
# - 抽出内部 helper _do_export_one，复制 export_batch_report / export_batch_word 的
#   核心逻辑并支持 fmt="pdf" / "word" / "both"
# - 新增 /export-multi 端点，循环调 helper，聚合结果
# - 个人报告（type='record'）暂不支持批量导出，按钮只对批量报告启用


async def _do_export_one(
    session: AsyncSession,
    batch_id: int,
    student_id: int,
    body: dict,
    fmt: str,
) -> dict:
    """单个学生在某个批量报告中导出（PDF/Word/两者）的内部 helper。

    返回 dict：
      - 成功：{success: True, name, student_id, batch_id, pdf_path?, docx_path?,
              custom_path?, jpg_path?, template_id, filename, http_status: 200}
      - 失败：{success: False, error: str, http_status: int}
    """
    fmt = (fmt or "pdf").lower()
    if fmt not in ("pdf", "word", "both"):
        return {"success": False, "error": f"不支持的 format: {fmt}", "http_status": 400}

    # 1) 取 batch
    try:
        batch = await batch_svc.get_batch_report(session, batch_id)
    except BatchReportNotFoundError as e:
        return {"success": False, "error": str(e), "http_status": 404}

    template_id = body.get("template_id") or batch.template_id or "classic"
    layout_config = body.get("layout_config")
    output_dir = body.get("output_dir")

    # 2) 取学生
    from backend.models import Student as StudentModel

    student = await session.get(StudentModel, student_id)
    if not student:
        return {"success": False, "error": f"学生不存在: id={student_id}", "http_status": 404}
    student_name = student.name

    # 3) 评价
    evaluations = _load_json(batch.evaluations, {})
    student_eval = evaluations.get(str(student_id), {})
    if isinstance(student_eval, dict):
        eval_text = student_eval.get("evaluation", "")
    else:
        eval_text = str(student_eval)

    # 4) 截图
    run_screenshots = body.get("run_screenshots", [])
    code_screenshots = body.get("code_screenshots", [])
    homework_screenshots = body.get("homework_screenshots", [])
    screenshot_paths = body.get("screenshot_paths", [])

    # 5) 共享内容覆盖
    homework_override = body.get("homework")
    knowledge_points_override = body.get("knowledge_points")
    ability_improvement_override = body.get("ability_improvement")
    content_items_override = body.get("content_items")
    vocabulary_override = body.get("vocabulary")

    record = _build_batch_record(
        batch, student_id, student_name, eval_text,
        code_screenshots=code_screenshots,
        run_screenshots=run_screenshots,
        homework_screenshots=homework_screenshots,
        screenshot_paths=screenshot_paths,
        homework_override=homework_override,
        knowledge_points_override=knowledge_points_override,
        ability_improvement_override=ability_improvement_override,
        content_items_override=content_items_override,
        vocabulary_override=vocabulary_override,
    )

    # 6) 渲染 HTML（PDF/Word 都基于同一 HTML）
    try:
        renderer = ReportRenderer(template_id)
    except TemplateNotFoundError as e:
        return {"success": False, "error": str(e), "http_status": 400}

    html = renderer.render(
        record,
        student_name=student_name,
        layout_config=layout_config,
        run_screenshots=run_screenshots,
        code_screenshots=code_screenshots,
        homework_screenshots=homework_screenshots,
        showcase_photo=getattr(record, "_showcase_photo", None),
    )

    # 7) PDF 路径
    pdf_path = None
    pdf_filename = None
    if fmt in ("pdf", "both"):
        tpl_config = get_template_config(template_id)
        merged = merge_layout_with_theme(tpl_config, layout_config)
        pdf_margin = {
            "top": f"{merged['page_margin_top']}mm",
            "right": f"{merged['page_margin_right']}mm",
            "bottom": f"{merged['page_margin_bottom']}mm",
            "left": f"{merged['page_margin_left']}mm",
        }
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        default_output_dir = Path(settings.report.output_dir)
        default_output_dir.mkdir(parents=True, exist_ok=True)
        pdf_filename = f"batch_report_{batch_id}_{student_id}_{timestamp}.pdf"
        pdf_path = default_output_dir / pdf_filename
        try:
            pdf_gen = PDFGenerator()
            await pdf_gen.generate(html, str(pdf_path), margin=pdf_margin)
        except PDFGenerationError as e:
            log.exception("PDF 生成失败: %s", e)
            return {"success": False, "error": f"PDF 生成失败: {e}", "http_status": 500}

    # 8) Word 路径
    docx_bytes = None
    docx_filename = None
    if fmt in ("word", "both"):
        template_config = None
        try:
            template_config = get_template_config(template_id)
        except (TemplateNotFoundError, FileNotFoundError):
            pass
        from backend.services.docx_generator import DocxGenerationError, generate as generate_docx
        try:
            docx_bytes = generate_docx(record, student_name, template_config, layout_config)
        except DocxGenerationError as e:
            return {"success": False, "error": f"Word 生成失败: {e}", "http_status": 500}
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        docx_filename = f"batch_report_{batch_id}_{student_id}_{timestamp}.docx"

    # 9) 自定义路径（PDF + Word 都写一份到 session_dir）
    custom_path = None
    jpg_path = None
    if output_dir or settings.report.custom_output_dir or batch.project_folder:
        try:
            date_part = _sanitize_date_dir(batch.course_date) if batch.course_date else "未设置日期"
            class_name = batch.class_name or "未分班"
            session_part = f"{date_part}_{_sanitize_filename(class_name)}"

            base_str = output_dir or batch.project_folder or settings.report.custom_output_dir or settings.report.output_dir
            base_dir = Path(base_str)
            if not base_dir.is_absolute():
                base_dir = PROJECT_ROOT / base_str

            session_dir = base_dir / session_part
            safe_name = _sanitize_filename(student_name or "学生")
            safe_topic = _sanitize_filename(batch.course_topic or "课程")
            basename = f"{safe_name}_{safe_topic}"

            pdf_dir = session_dir / PDF_SUBDIR
            img_dir = session_dir / IMG_SUBDIR
            pdf_dir.mkdir(parents=True, exist_ok=True)
            img_dir.mkdir(parents=True, exist_ok=True)

            if pdf_path:
                pdf_out = pdf_dir / f"{basename}.pdf"
                img_out = img_dir / f"{basename}.jpg"
                from datetime import datetime, timezone
                now_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                if pdf_out.exists():
                    pdf_out = pdf_dir / f"{basename}_{now_ts}.pdf"
                if img_out.exists():
                    img_out = img_dir / f"{basename}_{now_ts}.jpg"
                pdf_gen = PDFGenerator()
                await pdf_gen.generate(html, str(pdf_out), margin=pdf_margin)
                custom_path = str(pdf_out)
                if settings.image.enabled:
                    jpg_path = pdf_to_long_image(
                        str(pdf_out),
                        output_path=str(img_out),
                        dpi=settings.image.dpi,
                        quality=settings.image.quality,
                    )

            if docx_bytes is not None:
                docx_out = pdf_dir / (basename + ".docx")
                docx_out.parent.mkdir(parents=True, exist_ok=True)
                docx_out.write_bytes(docx_bytes)
                if not custom_path:
                    custom_path = str(docx_out)
        except Exception as e:
            log.warning("批量报告自定义路径写入失败: %s", e)

    # 10) PDF → JPG（默认路径下的）
    if not jpg_path and pdf_path and settings.image.enabled and fmt in ("pdf", "both"):
        try:
            jpg_path = pdf_to_long_image(
                str(pdf_path),
                dpi=settings.image.dpi,
                quality=settings.image.quality,
            )
        except Exception as e:
            log.warning("批量报告默认 PDF 转长图失败: %s", e)

    # 11) 状态更新（任何一个成功就标 finalized）
    if batch.status == "draft":
        try:
            await batch_svc.update_batch_report(session, batch_id, {"status": "finalized"})
        except Exception as e:
            log.warning("批量报告状态更新失败: %s", e)

    # 12) 组装响应
    resp: dict = {
        "success": True,
        "http_status": 200,
        "batch_id": batch_id,
        "student_id": student_id,
        "name": student_name,
        "template_id": template_id,
    }
    if pdf_path:
        resp["pdf_path"] = f"/api/reports/pdf/{pdf_filename}"
        resp["filename"] = pdf_filename
    if docx_bytes is not None:
        resp["docx_path"] = f"/api/reports/pdf/{docx_filename}"
        # 多个格式时 filename 优先 PDF
        if "filename" not in resp:
            resp["filename"] = docx_filename
    if custom_path:
        resp["custom_path"] = custom_path
    if jpg_path:
        resp["jpg_path"] = jpg_path
    return resp


@router.post(
    "/api/batch-reports/export-multi",
    response_model=dict,
    summary="批量报告多学生导出（PDF/Word/两者）",
)
async def export_batch_multi(
    body: dict = Body(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """对多个批量报告的多个学生执行批量导出。

    Body:
      - items: list[{batch_id: int, student_ids: list[int], body?: dict}]
        每个 item 表示「某个批量报告下的某些学生」，可附带独立的 body
        （如 template_id、output_dir、screenshot_paths 等覆盖参数）
      - format: "pdf" | "word" | "both"   默认 "pdf"
      - output_dir: 全局输出目录（可被 item.body.output_dir 覆盖）

    Response:
      {
        "success": 成功数,
        "failed": 失败数,
        "results": [{batch_id, student_id, name, pdf_path?, docx_path?}, ...],
        "errors":  [{batch_id, student_id, error}, ...]
      }
    """
    items = body.get("items") or []
    fmt = (body.get("format") or "pdf").lower()
    global_output_dir = body.get("output_dir")

    if not isinstance(items, list) or len(items) == 0:
        raise HTTPException(status_code=400, detail="items 不能为空")
    if fmt not in ("pdf", "word", "both"):
        raise HTTPException(status_code=400, detail=f"不支持的 format: {fmt}")

    results: list[dict] = []
    errors: list[dict] = []

    log.info("批量多学生导出: items=%d format=%s", len(items), fmt)

    for item in items:
        if not isinstance(item, dict):
            continue
        batch_id = item.get("batch_id")
        student_ids = item.get("student_ids") or []
        if not batch_id or not isinstance(student_ids, list) or not student_ids:
            errors.append({"batch_id": batch_id, "student_id": None,
                           "error": "item 缺少 batch_id 或 student_ids"})
            continue

        # 合并 body：item 内的 body 优先，全局 output_dir 作默认
        sub_body: dict = dict(item.get("body") or {})
        if global_output_dir and "output_dir" not in sub_body:
            sub_body["output_dir"] = global_output_dir

        for sid in student_ids:
            try:
                r = await _do_export_one(session, int(batch_id), int(sid), sub_body, fmt)
                if r.get("success"):
                    results.append({
                        "batch_id": r["batch_id"],
                        "student_id": r["student_id"],
                        "name": r.get("name"),
                        "pdf_path": r.get("pdf_path"),
                        "docx_path": r.get("docx_path"),
                        "custom_path": r.get("custom_path"),
                        "filename": r.get("filename"),
                    })
                else:
                    errors.append({
                        "batch_id": batch_id,
                        "student_id": sid,
                        "error": r.get("error", "未知错误"),
                    })
            except Exception as e:
                log.exception("批量导出异常: batch=%s student=%s", batch_id, sid)
                errors.append({
                    "batch_id": batch_id,
                    "student_id": sid,
                    "error": str(e),
                })

    log.info("批量多学生导出完成: 成功=%d 失败=%d", len(results), len(errors))

    return {
        "success": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors,
        "format": fmt,
    }
