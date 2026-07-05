"""模板管理 API 路由（CRUD + 预览）。"""
from __future__ import annotations

from fastapi import APIRouter, Body, File, HTTPException, UploadFile, status
from fastapi.responses import Response

from backend.schemas.template import TemplateListItem
from backend.services.report_renderer import get_template_config, list_templates, wrap_preview_html
from backend.services.template_manager import (
    TemplateError,
    TemplateNotDeletableError,
    TemplateNotFoundError as SvcTemplateNotFoundError,
    create_template,
    delete_template,
    render_template_preview,
    update_template_config,
    upload_template,
)

router = APIRouter(tags=["template-management"])


@router.get(
    "/api/templates",
    response_model=list[TemplateListItem],
    summary="列出所有模板（内置 + 自定义）",
)
async def api_list_templates() -> list[TemplateListItem]:
    """列出所有可用模板。"""
    return [TemplateListItem(**t) for t in list_templates()]


@router.get(
    "/api/templates/{template_id}/config",
    response_model=dict,
    summary="获取模板完整配置",
)
async def api_get_template_config(template_id: str) -> dict:
    """获取模板的完整 config.json（含 theme）。"""
    try:
        return get_template_config(template_id)
    except SvcTemplateNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/api/templates",
    response_model=TemplateListItem,
    status_code=status.HTTP_201_CREATED,
    summary="创建自定义模板（克隆自指定模板）",
)
async def api_create_template(body: dict) -> TemplateListItem:
    """创建新的自定义模板，克隆自指定的基础模板。"""
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="模板名称不能为空")
    if len(name) > 50:
        raise HTTPException(status_code=400, detail="模板名称不能超过50个字符")

    base_id = (body.get("base_template_id") or "").strip()
    if not base_id:
        raise HTTPException(status_code=400, detail="请指定基础模板")

    description = (body.get("description") or "").strip()
    theme_overrides = body.get("theme_overrides")

    try:
        result = create_template(name, description, base_id, theme_overrides)
    except SvcTemplateNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建模板失败: {e}")

    return TemplateListItem(**result)


@router.put(
    "/api/templates/{template_id}",
    response_model=dict,
    summary="更新自定义模板配置",
)
async def api_update_template(template_id: str, body: dict) -> dict:
    """更新自定义模板的 name / description / theme 字段。"""
    try:
        config = update_template_config(template_id, body)
    except SvcTemplateNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新模板失败: {e}")
    return config


@router.delete(
    "/api/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除自定义模板",
)
async def api_delete_template(template_id: str) -> None:
    """删除自定义模板（内置模板不可删除）。"""
    try:
        delete_template(template_id)
    except SvcTemplateNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TemplateNotDeletableError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post(
    "/api/templates/upload",
    response_model=TemplateListItem,
    status_code=status.HTTP_201_CREATED,
    summary="上传自定义模板 (ZIP)",
)
async def api_upload_template(file: UploadFile = File(...)) -> TemplateListItem:
    """上传 ZIP 格式的自定义模板。

    ZIP 必须包含 config.json, template.html, style.css 三个文件，无子目录。
    系统自动生成 template ID，覆盖 config.json 中的 id/is_builtin/parent_template。
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="仅支持 .zip 文件")

    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取文件失败: {e}")

    try:
        result = upload_template(content)
    except TemplateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模板上传失败: {e}")

    return TemplateListItem(**result)


@router.post(
    "/api/templates/{template_id}/preview",
    response_class=Response,
    summary="预览模板（用示例数据渲染）",
)
async def api_preview_template(template_id: str, body: dict = Body(None)) -> Response:
    """用示例数据渲染模板并返回预览 HTML。

    可选传入 theme_overrides 实现编辑过程中实时预览（不保存即看到效果）。
    """
    theme_overrides = (body or {}).get("theme_overrides")
    try:
        html = render_template_preview(template_id, theme_overrides)
        html = wrap_preview_html(html)
    except SvcTemplateNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"预览生成失败: {e}")
    return Response(content=html, media_type="text/html; charset=utf-8")
