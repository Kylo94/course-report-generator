"""模板管理服务：创建/编辑/删除用户自定义模板。"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from backend.services.report_renderer import CUSTOM_TEMPLATES_DIR, TEMPLATES_DIR, get_template_config, list_templates

# 内置模板 ID（不可删除/覆盖）
BUILTIN_TEMPLATES = {"classic", "academic", "cartoon"}


class TemplateError(Exception):
    """模板操作异常基类。"""


class TemplateNotFoundError(TemplateError):
    """模板不存在。"""


class TemplateNotDeletableError(TemplateError):
    """模板不可删除（内置模板）。"""


class TemplateNameConflictError(TemplateError):
    """模板名称冲突。"""


def _sanitize_id(name: str) -> str:
    """将模板名转为安全的目录 ID。

    规则：小写、空格→下划线、去除非字母数字下划线连字符汉字。
    """
    sanitized = re.sub(r"[^a-zA-Z0-9_一-鿿\-]", "", name.replace(" ", "_"))
    if not sanitized:
        import uuid

        sanitized = f"template_{uuid.uuid4().hex[:8]}"
    return sanitized.lower()


def _generate_unique_id(base_name: str) -> str:
    """从名称生成唯一目录 ID，处理与已有模板的冲突。"""
    candidate = _sanitize_id(base_name)
    if not ((TEMPLATES_DIR / candidate).exists() or (CUSTOM_TEMPLATES_DIR / candidate).exists()):
        return candidate
    for i in range(1, 100):
        alt = f"{candidate}_{i}"
        if not ((TEMPLATES_DIR / alt).exists() or (CUSTOM_TEMPLATES_DIR / alt).exists()):
            return alt
    import uuid

    return f"{candidate}_{uuid.uuid4().hex[:6]}"


def list_custom_templates() -> list[dict[str, Any]]:
    """返回仅用户自定义模板列表。"""
    return [t for t in list_templates() if not t.get("is_builtin", True)]


def create_template(
    name: str,
    description: str,
    base_template_id: str,
    theme_overrides: dict | None = None,
) -> dict[str, Any]:
    """创建自定义模板（克隆自指定模板）。

    步骤：
    1. 验证 base_template_id 存在
    2. 生成唯一 template_id
    3. 创建目录 data/custom_templates/{id}/
    4. 复制 template.html 和 style.css 从基础模板
    5. 写入 config.json
    6. 返回列表项 dict
    """
    # 1. 验证基础模板
    try:
        base_config = get_template_config(base_template_id)
    except Exception as e:
        raise TemplateNotFoundError(str(e)) from e

    # 找到基础模板的目录（可能在 templates/ 或 data/custom_templates/）
    base_dir = None
    for d in (TEMPLATES_DIR, CUSTOM_TEMPLATES_DIR):
        cand = d / base_template_id
        if cand.exists():
            base_dir = cand
            break
    if base_dir is None:
        raise TemplateNotFoundError(base_template_id)

    # 2. 生成 ID
    template_id = _generate_unique_id(name)

    # 3. 创建自定义模板目录（在 CUSTOM_TEMPLATES_DIR 下）
    CUSTOM_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    template_dir = CUSTOM_TEMPLATES_DIR / template_id
    template_dir.mkdir(parents=True, exist_ok=True)

    # 4. 复制 template.html 和 style.css
    for filename in ("template.html", "style.css"):
        src = base_dir / filename
        if src.exists():
            shutil.copy2(str(src), str(template_dir / filename))
        else:
            (template_dir / filename).write_text("", encoding="utf-8")

    # 5. 合并主题覆盖
    base_theme = base_config.get("theme", {})
    merged_theme = dict(base_theme)
    if theme_overrides:
        theme_keys = {
            "primary_color",
            "secondary_color",
            "font_title",
            "font_body",
            "font_size_title",
            "font_size_body",
            "background_color",
            "background_image",
            "page_margin_top",
            "page_margin_bottom",
            "page_margin_left",
            "page_margin_right",
        }
        for key in theme_keys:
            if key in theme_overrides and theme_overrides[key] is not None:
                merged_theme[key] = theme_overrides[key]

    page_size = (
        theme_overrides.get("page_size", base_config.get("page_size", "A4"))
        if theme_overrides
        else base_config.get("page_size", "A4")
    )

    config = {
        "id": template_id,
        "name": name,
        "version": "1.0",
        "is_builtin": False,
        "parent_template": base_template_id,
        "thumbnail": "",
        "description": description or "",
        "theme": merged_theme,
        "page_size": page_size,
    }

    # 复制 Logo 配置从基础模板
    if "logo_config" in base_config:
        config["logo_config"] = dict(base_config["logo_config"])
    else:
        config["logo_config"] = {
            "enabled": True,
            "position": "top-right",
            "size": 30,
            "show_on_all_pages": True,
        }

    # 复制 logo 图片数据
    if "logo_data_uri" in base_config:
        config["logo_data_uri"] = base_config["logo_data_uri"]

    config_path = template_dir / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    return {
        "id": template_id,
        "name": name,
        "version": "1.0",
        "is_builtin": False,
        "parent_template": base_template_id,
        "thumbnail": "",
        "description": description or "",
        "page_size": page_size,
    }


def _find_custom_template_dir(template_id: str) -> Path:
    """在 CUSTOM_TEMPLATES_DIR 中查找自定义模板目录。"""
    d = CUSTOM_TEMPLATES_DIR / template_id
    if d.exists() and (d / "config.json").exists():
        return d
    # 兼容旧路径：允许在 TEMPLATES_DIR 中寻找
    old = TEMPLATES_DIR / template_id
    if old.exists() and (old / "config.json").exists() and not old.name in BUILTIN_TEMPLATES:
        return old
    raise TemplateNotFoundError(f"模板不存在: {template_id}")


def update_template_config(
    template_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """更新自定义模板的 config.json。

    允许更新的字段：
      - name, description, page_size
      - theme.*（主色、辅色、字体、字号）
    """
    template_dir = _find_custom_template_dir(template_id)
    config_path = template_dir / "config.json"

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 更新顶层字段
    if "name" in updates and updates["name"]:
        config["name"] = updates["name"]
    if "description" in updates:
        config["description"] = updates.get("description", "")
    if "page_size" in updates:
        config["page_size"] = updates["page_size"]

    # 更新 theme 子字段
    theme = config.setdefault("theme", {})
    theme_keys = {
        "primary_color",
        "secondary_color",
        "font_title",
        "font_body",
        "font_size_title",
        "font_size_body",
        "background_color",
        "background_image",
        "page_margin_top",
        "page_margin_bottom",
        "page_margin_left",
        "page_margin_right",
    }
    for key in theme_keys:
        if key in updates and updates[key] is not None:
            theme[key] = updates[key]

    # 更新 logo_config（整个覆盖）
    if "logo_config" in updates and isinstance(updates["logo_config"], dict):
        logo = config.setdefault("logo_config", {})
        for lk in ("enabled", "position", "size", "show_on_all_pages", "margin"):
            if lk in updates["logo_config"]:
                logo[lk] = updates["logo_config"][lk]

    # 更新 logo 图片数据（data URI）
    if "logo_data_uri" in updates:
        if updates["logo_data_uri"]:
            config["logo_data_uri"] = updates["logo_data_uri"]
        else:
            config.pop("logo_data_uri", None)

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    return config


def delete_template(template_id: str) -> None:
    """删除自定义模板。

    安全校验：
    - 内置模板不可删除（基于 ID 集合 + config.json 双重校验）
    """
    if template_id in BUILTIN_TEMPLATES:
        raise TemplateNotDeletableError(f"内置模板不可删除: {template_id}")

    template_dir = _find_custom_template_dir(template_id)

    # 额外检查 config.json 中的 is_builtin
    config_path = template_dir / "config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        if config.get("is_builtin", False):
            raise TemplateNotDeletableError(f"内置模板不可删除: {template_id}")

    shutil.rmtree(template_dir)


def render_template_preview(template_id: str, theme_overrides: dict | None = None) -> str:
    """用示例数据渲染模板预览 HTML。

    不依赖真实的报告记录，使用占位数据。
    theme_overrides: 编辑对话框未保存时的临时主题覆盖。
    """
    from backend.config import get_settings as _get_preview_settings
    from backend.services.report_renderer import ReportRenderer, TemplateNotFoundError as RendererTemplateNotFoundError

    _tpl_id = template_id  # 解决类作用域闭包问题

    try:
        renderer = ReportRenderer(template_id)
    except RendererTemplateNotFoundError as e:
        raise TemplateNotFoundError(str(e)) from e

    # 临时覆盖未保存的主题字段（在 renderer.config 上直接修改）
    if theme_overrides:
        theme = renderer.config.setdefault("theme", {})
        for key, value in theme_overrides.items():
            if value is not None:
                theme[key] = value
        # 单独处理 logo_data_uri
        if "logo_data_uri" in theme_overrides:
            if theme_overrides["logo_data_uri"]:
                renderer.config["logo_data_uri"] = theme_overrides["logo_data_uri"]
            else:
                renderer.config.pop("logo_data_uri", None)
        # 单独处理 logo_margin（属于 logo_config，不是 theme）
        if "logo_margin" in theme_overrides and theme_overrides["logo_margin"] is not None:
            logo_cfg = renderer.config.setdefault("logo_config", {})
            logo_cfg["margin"] = theme_overrides["logo_margin"]
        # 单独处理 logo_size
        if "logo_size" in theme_overrides and theme_overrides["logo_size"] is not None:
            logo_cfg = renderer.config.setdefault("logo_config", {})
            logo_cfg["size"] = theme_overrides["logo_size"]

    _logo_cfg = renderer.config.get("logo_config", {})
    # 如果模板没有自己的 logo_data_uri 且没有全局 logo 文件，预览时禁用 Logo
    if not renderer.config.get("logo_data_uri"):
        _asset_dir = Path(_get_preview_settings().report.asset_dir)
        _has_global_logo = any((_asset_dir / f"logo{ext}").exists() for ext in (".png", ".jpg", ".jpeg", ".webp"))
        if not _has_global_logo:
            _logo_cfg = dict(_logo_cfg)
            _logo_cfg["enabled"] = False

    class PreviewRecord:
        template_id = _tpl_id
        course_topic = "示例课程名称"
        course_date = "2026-06-29"
        knowledge_points = '["知识点一", "知识点二", "知识点三"]'
        ability_improvement = "通过本课程示例内容的学习，学生的逻辑思维和问题解决能力得到了有效提升。"
        content_items = json.dumps(
            [
                {"kp": "示例知识点1", "text": "这是示例知识点1的详细内容描述，用于展示模板的排版效果。"},
                {"kp": "示例知识点2", "text": "这是示例知识点2的详细内容描述，用于展示模板的排版效果。"},
            ],
            ensure_ascii=False,
        )
        vocabulary = json.dumps(
            {
                "word": "example",
                "phonetic": "/ɪɡˈzɑːmpl/",
                "meaning": "示例；榜样",
                "example": "This is an example sentence.",
            },
            ensure_ascii=False,
        )
        homework = json.dumps(
            {
                "goal": "练习使用示例模板的格式",
                "hints": ["参考课堂示例", "注意格式规范"],
                "criteria": ["完整性", "正确性"],
            },
            ensure_ascii=False,
        )
        evaluation = "学生在本示例课程中表现良好，积极参与互动，对课程知识点理解透彻。建议继续巩固练习，加强对重点内容的掌握。"
        screenshot_paths = "[]"
        logo_config = json.dumps(_logo_cfg)
        project_folder = ""
        project_meta = None
        status = "draft"

    html = renderer.render(PreviewRecord(), student_name="示例学生")
    return html
