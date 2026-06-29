"""报告渲染服务：CourseRecord → HTML 字符串。

使用 Jinja2 渲染模板，内联 CSS，处理 Logo 和截图路径。"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from backend.config import PROJECT_ROOT, get_settings
from backend.utils.logger import get_logger

log = get_logger(__name__)

TEMPLATES_DIR = PROJECT_ROOT / "templates"


class TemplateNotFoundError(Exception):
    """模板不存在。"""

    def __init__(self, template_id: str):
        self.template_id = template_id
        super().__init__(f"模板不存在: {template_id}")


def _load_json(value: str | None, default: Any = None) -> Any:
    """安全解析 JSON 字符串。"""
    if value is None:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _url_to_fs_path(url_path: str) -> str | None:
    """将 HTTP 访问路径（如 /api/assets/screenshots/abc.jpg）转为绝对文件路径。"""
    settings = get_settings()
    if url_path.startswith("/api/assets/screenshots/"):
        filename = url_path[len("/api/assets/screenshots/"):]
        full = Path(settings.report.screenshot_dir) / filename
        if full.exists():
            return str(full.resolve())
    elif url_path.startswith("/api/assets/logo"):
        filename = url_path[len("/api/assets/"):]
        full = Path(settings.report.asset_dir) / filename
        if full.exists():
            return str(full.resolve())
    return None


def _image_to_data_uri(image_path: str) -> str | None:
    """将图片文件转为 base64 data URI。"""
    try:
        p = Path(image_path)
        if not p.exists():
            return None
        ext = p.suffix.lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(ext, "image/png")
        data = p.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception as e:
        log.warning("图片转 data URI 失败: %s", e)
        return None


def list_templates() -> list[dict[str, Any]]:
    """扫描 templates/ 目录，返回内置模板列表。"""
    if not TEMPLATES_DIR.exists():
        return []
    templates: list[dict[str, Any]] = []
    for entry in sorted(TEMPLATES_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        config_path = entry / "config.json"
        if not config_path.exists():
            continue
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            templates.append({
                "id": config.get("id", entry.name),
                "name": config.get("name", entry.name),
                "version": config.get("version", "1.0"),
                "is_builtin": config.get("is_builtin", True),
                "thumbnail": config.get("thumbnail", ""),
                "description": config.get("description", ""),
                "page_size": config.get("page_size", "A4"),
            })
        except Exception as e:
            log.warning("模板配置加载失败 %s: %s", entry.name, e)
    return templates


def get_template_config(template_id: str) -> dict[str, Any]:
    """加载单个模板配置。"""
    template_dir = TEMPLATES_DIR / template_id
    config_path = template_dir / "config.json"
    if not config_path.exists():
        raise TemplateNotFoundError(template_id)
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise TemplateNotFoundError(template_id) from e


class ReportRenderer:
    """报告渲染器。

    加载指定模板的 HTML + CSS，传入 CourseRecord 数据，
    返回完整 HTML 字符串（内联 CSS）。
    """

    def __init__(self, template_id: str = "classic"):
        self.template_id = template_id
        self.template_dir = TEMPLATES_DIR / template_id

        if not self.template_dir.exists():
            raise TemplateNotFoundError(template_id)

        # 加载模板文件
        self.html_template = self._load_file("template.html")
        self.css_content = self._load_file("style.css")

        # 加载配置
        self.config = get_template_config(template_id)

    def _load_file(self, filename: str) -> str:
        path = self.template_dir / filename
        if not path.exists():
            log.warning("模板文件缺失: %s", path)
            return ""
        return path.read_text("utf-8")

    def render(
        self,
        record,
        student_name: str = "",
    ) -> str:
        """渲染完整报告 HTML。"""
        # 反序列化 JSON 字段
        kp = _load_json(record.knowledge_points, [])
        content_items = _load_json(record.content_items, [])
        vocabulary = _load_json(record.vocabulary, {})
        homework = _load_json(record.homework, {})
        screenshots = _load_json(record.screenshot_paths, [])
        logo_cfg = _load_json(record.logo_config, {})

        # 处理 Logo
        logo_data: dict[str, Any] | None = None
        if logo_cfg.get("enabled", False):
            settings = get_settings()
            asset_dir = Path(settings.report.asset_dir)
            for ext in (".png", ".jpg", ".jpeg", ".webp"):
                logo_path = asset_dir / f"logo{ext}"
                if logo_path.exists():
                    data_uri = _image_to_data_uri(str(logo_path))
                    if data_uri:
                        size_map = {"small": 20, "medium": 30, "large": 45}
                        logo_data = {
                            "data_uri": data_uri,
                            "position": logo_cfg.get("position", "top-right"),
                            "width_mm": size_map.get(logo_cfg.get("size", "medium"), 30),
                            "show_on_all_pages": logo_cfg.get("show_on_all_pages", True),
                        }
                    break

        # 处理截图路径：URL → 文件路径
        resolved_screenshots: list[str] = []
        for s in screenshots[:1]:  # 只取第一张作为封面图
            fs_path = _url_to_fs_path(s) if isinstance(s, str) else None
            if fs_path:
                data_uri = _image_to_data_uri(fs_path)
                resolved_screenshots.append(data_uri or fs_path)

        # 模板上下文
        ctx = {
            "css_content": self.css_content,
            "course_topic": record.course_topic or "",
            "student_name": student_name,
            "course_date": record.course_date or "",
            "knowledge_points": kp,
            "ability_improvement": record.ability_improvement or "",
            "content_items": content_items,
            "vocabulary": vocabulary or {},
            "homework": homework or {},
            "evaluation": record.evaluation or "",
            "screenshots": resolved_screenshots,
            "logo": logo_data,
        }

        # 使用 Jinja2 渲染
        env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=True,
        )
        template = env.from_string(self.html_template)
        html = template.render(ctx)

        return html
