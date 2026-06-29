"""Word 文档生成服务：CourseRecord → .docx。

使用 python-docx 原生生成可编辑的 Word 文档。
每个字段使用 Heading 1 样式分隔，截图嵌入，作业用表格。
"""
from __future__ import annotations

import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Mm, Pt, RGBColor

from backend.config import PROJECT_ROOT, get_settings
from backend.utils.logger import get_logger

log = get_logger(__name__)


class DocxGenerationError(Exception):
    """Word 文档生成失败。"""

    def __init__(self, message: str, original: Exception | None = None):
        self.original = original
        super().__init__(message)


def _load_json(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _url_to_fs_path(url_path: str) -> str | None:
    """将 HTTP 路径转为绝对文件路径。"""
    settings = get_settings()
    if url_path.startswith("/api/assets/screenshots/"):
        filename = url_path[len("/api/assets/screenshots/"):]
        full = Path(settings.report.screenshot_dir) / filename
        if full.exists():
            return str(full.resolve())
    elif url_path.startswith("/api/assets/"):
        filename = url_path[len("/api/assets/"):]
        full = Path(settings.report.asset_dir) / filename
        if full.exists():
            return str(full.resolve())
    return None


def _set_run_font(run, font_name: str = "宋体", size: int = 11, bold: bool = False,
                  color: str | None = None) -> None:
    """设置 run 的字体属性。"""
    run.font.name = font_name
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        try:
            run.font.color.rgb = RGBColor(
                int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            )
        except (ValueError, IndexError):
            pass
    # 中文字体回退
    from docx.oxml.ns import qn
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font_name)


def merge_layout_with_theme(
    template_config: dict | None,
    layout_config: dict | None,
) -> dict:
    """将布局覆盖与模板主题合并（与 report_renderer 逻辑一致）。"""
    theme = (template_config or {}).get("theme", {})
    result = {
        "primary_color": theme.get("primary_color", "#3B7DDD"),
        "secondary_color": theme.get("secondary_color", "#F5F5F5"),
        "font_title": theme.get("font_title", "Heiti SC"),
        "font_body": theme.get("font_body", "STSong"),
        "font_size_title": theme.get("font_size_title", 24),
        "font_size_body": theme.get("font_size_body", 11),
        "page_margin_top": 20,
        "page_margin_bottom": 18,
        "page_margin_left": 18,
        "page_margin_right": 18,
    }
    if layout_config:
        for key in result:
            if key in layout_config and layout_config[key] is not None:
                result[key] = layout_config[key]
    return result


def generate(
    record,
    student_name: str = "",
    template_config: dict | None = None,
    layout_config: dict | None = None,
) -> bytes:
    """生成 Word 文档字节流。

    Args:
        record: CourseRecord ORM 对象
        student_name: 学生姓名
        template_config: 模板配置 dict（可选）
        layout_config: 布局覆盖配置 dict（可选）

    Returns:
        .docx 文件 bytes
    """
    merged = merge_layout_with_theme(template_config, layout_config)

    doc = Document()

    # 应用页边距
    section = doc.sections[0]
    section.top_margin = Mm(merged["page_margin_top"])
    section.bottom_margin = Mm(merged["page_margin_bottom"])
    section.left_margin = Mm(merged["page_margin_left"])
    section.right_margin = Mm(merged["page_margin_right"])

    font_body_name = merged["font_body"]
    font_body_size = merged["font_size_body"]

    # 设置默认样式
    style = doc.styles["Normal"]
    style.font.name = font_body_name
    style.font.size = Pt(font_body_size)
    from docx.oxml.ns import qn
    style.element.rPr.rFonts.set(qn("w:eastAsia"), font_body_name)

    # 主题
    primary_color = merged["primary_color"]
    font_title_name = merged["font_title"]
    font_title_size = merged["font_size_title"]

    # 反序列化 JSON 字段
    kp = _load_json(getattr(record, "knowledge_points", None), [])
    content_items = _load_json(getattr(record, "content_items", None), [])
    vocabulary = _load_json(getattr(record, "vocabulary", None), {})
    homework = _load_json(getattr(record, "homework", None), {})
    screenshots = _load_json(getattr(record, "screenshot_paths", None), [])

    def add_heading(text: str) -> None:
        h = doc.add_heading(text, level=1)
        for run in h.runs:
            _set_run_font(run, font_title_name, max(14, font_body_size + 2), bold=True, color=primary_color)

    def add_body(text: str) -> None:
        p = doc.add_paragraph(text)
        for run in p.runs:
            _set_run_font(run, font_body_name, font_body_size)

    def add_bullet(text: str) -> None:
        p = doc.add_paragraph(text, style="List Bullet")
        for run in p.runs:
            _set_run_font(run, font_body_name, font_body_size)

    def add_labeled(label: str, value: str) -> None:
        p = doc.add_paragraph()
        r1 = p.add_run(f"{label}：")
        _set_run_font(r1, font_title_name, font_body_size, bold=True)
        r2 = p.add_run(value)
        _set_run_font(r2, font_body_name, font_body_size)

    # ===== 正文 =====
    # 标题
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title_p.add_run("课程报告")
    _set_run_font(r, font_title_name, max(18, font_body_size + 8), bold=True, color=primary_color)

    # 基本信息
    add_heading("基本信息")
    add_labeled("上课时间", getattr(record, "course_date", "") or "")
    add_labeled("学生姓名", student_name)
    add_labeled("课程名称", getattr(record, "course_topic", "") or "")
    add_labeled("项目文件夹", getattr(record, "project_folder", "") or "")

    # 知识点概括
    if kp:
        add_heading("知识点概括")
        for point in kp:
            add_bullet(str(point))

    # 能力提升
    ability = getattr(record, "ability_improvement", "") or ""
    if ability:
        add_heading("能力提升")
        add_body(ability)

    # 内容概述
    if content_items:
        add_heading("内容概述")
        for item in content_items:
            kp_name = item.get("kp", "")
            text = item.get("text", "")
            add_labeled(kp_name, text)

    # 单词学习
    if vocabulary and vocabulary.get("word"):
        add_heading("单词学习")
        vocab = vocabulary
        add_labeled("单词", f"{vocab.get('word', '')} /{vocab.get('phonetic', '')}/")
        add_labeled("释义", vocab.get("meaning", ""))
        add_labeled("例句", vocab.get("example", ""))

    # 课后作业
    if homework and homework.get("goal"):
        add_heading("课后作业")
        add_labeled("目标", homework.get("goal", ""))
        hints = homework.get("hints", [])
        if hints:
            add_body("提示：")
            for h in hints:
                add_bullet(h)
        criteria = homework.get("criteria", [])
        if criteria:
            add_body("评分点：")
            for c in criteria:
                add_bullet(c)

    # 嵌入截图
    if screenshots:
        add_heading("课程截图")
        for s_path in screenshots[:3]:
            fs_path = _url_to_fs_path(s_path) if isinstance(s_path, str) else None
            if fs_path:
                try:
                    doc.add_picture(fs_path, width=Mm(120))
                except Exception as e:
                    log.warning("截图嵌入失败 %s: %s", fs_path, e)

    # 学生评价
    evaluation = getattr(record, "evaluation", "") or ""
    if evaluation:
        add_heading("学生评价")
        add_body(evaluation)

    # 保存
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()
