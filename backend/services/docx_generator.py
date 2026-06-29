"""Word 文档生成服务：CourseRecord → .docx。

采用 altChunk（Alternative Format Import）方案：
复用 report_renderer 的 HTML 输出，直接嵌入 docx，
使 Word 文档结构与 PDF/预览保持一致。

仅当 altChunk 失败时回退到 python-docx 原生生成。
"""
from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from backend.config import get_settings
from backend.utils.logger import get_logger

log = get_logger(__name__)


class DocxGenerationError(Exception):
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


# ═══════════════════════════════════════════════════════════
# altChunk 方案（主要）
# ═══════════════════════════════════════════════════════════

def _build_altchunk_docx(html: str) -> bytes:
    """创建一个仅包含 altChunk 引用的 .docx 文件。

    Word 打开时会将 HTML 转换为 OOXML，呈现效果与预览/PDF 几乎一致。
    """
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # ── [Content_Types].xml ──
        zf.writestr('[Content_Types].xml',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
            '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
            '  <Default Extension="xml" ContentType="application/xml"/>\n'
            '  <Default Extension="html" ContentType="text/html; charset=utf-8"/>\n'
            '  <Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>\n'
            '</Types>'
        )

        # ── _rels/.rels ──
        zf.writestr('_rels/.rels',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            '  <Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/>\n'
            '</Relationships>'
        )

        # ── word/_rels/document.xml.rels ──
        zf.writestr('word/_rels/document.xml.rels',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            '  <Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/aFChunk" '
            'Target="htmlchunk.html"/>\n'
            '</Relationships>'
        )

        # ── word/document.xml ──
        zf.writestr('word/document.xml',
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"\n'
            '             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">\n'
            '  <w:body>\n'
            '    <w:altChunk r:id="rId1"/>\n'
            '  </w:body>\n'
            '</w:document>'
        )

        # ── word/htmlchunk.html ──
        zf.writestr('word/htmlchunk.html', html.encode('utf-8'))

    return buf.getvalue()


def _generate_altchunk(
    record,
    student_name: str,
    template_config: dict | None,
    layout_config: dict | None,
) -> bytes | None:
    """尝试通过 altChunk 生成 docx。失败返回 None。"""
    try:
        from backend.services.report_renderer import ReportRenderer

        template_id = "classic"
        if template_config:
            template_id = template_config.get("id", "classic")

        renderer = ReportRenderer(template_id)
        html = renderer.render(record, student_name, layout_config)

        return _build_altchunk_docx(html)
    except Exception as e:
        log.warning("altChunk 生成失败，将回退到 python-docx: %s", e)
        return None


# ═══════════════════════════════════════════════════════════
# python-docx 回退方案
# ═══════════════════════════════════════════════════════════

def merge_layout_with_theme(
    template_config: dict | None,
    layout_config: dict | None,
) -> dict:
    """将布局覆盖与模板主题合并（与 report_renderer 逻辑一致）。"""
    theme = (template_config or {}).get("theme", {})
    result = {
        "primary_color": theme.get("primary_color", "#2B5FC3"),
        "secondary_color": theme.get("secondary_color", "#F0F4FA"),
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


def _generate_fallback(
    record,
    student_name: str,
    template_config: dict | None,
    layout_config: dict | None,
) -> bytes:
    """python-docx 原生生成（altChunk 不可用时的回退方案）。"""
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Mm, Pt, RGBColor, Cm

    merged = merge_layout_with_theme(template_config, layout_config)
    doc = Document()

    # 页面设置
    section = doc.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Mm(merged["page_margin_top"])
    section.bottom_margin = Mm(merged["page_margin_bottom"])
    section.left_margin = Mm(merged["page_margin_left"])
    section.right_margin = Mm(merged["page_margin_right"])

    fb = merged["font_body"]
    fbs = merged["font_size_body"]
    ft = merged["font_title"]
    fts = merged["font_size_title"]
    pc = merged["primary_color"]

    style = doc.styles["Normal"]
    style.font.name = fb
    style.font.size = Pt(fbs)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), fb)

    # ── 数据 ──
    kp = _load_json(getattr(record, "knowledge_points", None), [])
    content_items = _load_json(getattr(record, "content_items", None), [])
    vocabulary = _load_json(getattr(record, "vocabulary", None), {})
    homework = _load_json(getattr(record, "homework", None), {})
    screenshots = _load_json(getattr(record, "screenshot_paths", None), [])

    code_excerpt = ""
    try:
        project_meta = _load_json(getattr(record, "project_meta", None), {})
        ai_meta = _load_json(getattr(record, "ai_meta", None), {})
        key_funcs = ai_meta.get("key_functions", [])
        if key_funcs and project_meta:
            folder = project_meta.get("folder", "")
            blocks = []
            for func in key_funcs[:2]:
                fp = func.get("file_path", "")
                sl = func.get("start_line")
                el = func.get("end_line")
                if fp and sl and el and folder:
                    fpath = Path(folder) / fp
                    if fpath.exists():
                        lines = fpath.read_text("utf-8").splitlines()
                        selected = lines[sl - 1: el]
                        blocks.append(f"# {fp}:{sl}\n" + "\n".join(selected))
            if blocks:
                code_excerpt = "\n\n".join(blocks)
    except Exception:
        pass

    def _set_font(run, name=fb, size=fbs, bold=False, color=None, ascii_name=None):
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.name = ascii_name or name
        rpr = run._element.get_or_add_rPr()
        rFonts = rpr.find(qn("w:rFonts"))
        if rFonts is None:
            rFonts = OxmlElement("w:rFonts")
            rpr.insert(0, rFonts)
        rFonts.set(qn("w:eastAsia"), name)
        if ascii_name:
            rFonts.set(qn("w:ascii"), ascii_name)
            rFonts.set(qn("w:hAnsi"), ascii_name)
        if color:
            try:
                run.font.color.rgb = RGBColor(
                    int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
                )
            except (ValueError, IndexError):
                pass

    def _heading(text):
        p = doc.add_paragraph()
        p.space_before = Pt(8)
        p.space_after = Pt(4)
        pPr = p._element.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        left = OxmlElement("w:left")
        left.set(qn("w:val"), "single")
        left.set(qn("w:sz"), "18")
        left.set(qn("w:space"), "8")
        left.set(qn("w:color"), pc.lstrip("#"))
        pBdr.append(left)
        pPr.append(pBdr)
        r = p.add_run(text)
        _set_font(r, ft, max(13, fbs + 1), True, pc)

    def _body(text):
        p = doc.add_paragraph(text)
        p.space_before = Pt(2)
        p.space_after = Pt(2)
        for run in p.runs:
            _set_font(run, fb, fbs)

    def _page_break():
        p = doc.add_paragraph()
        br = OxmlElement("w:br")
        br.set(qn("w:type"), "page")
        p.add_run()._element.append(br)

    def _page_header(text):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.space_before = Pt(4)
        p.space_after = Pt(8)
        pPr = p._element.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "6")
        bottom.set(qn("w:space"), "4")
        bottom.set(qn("w:color"), pc.lstrip("#"))
        pBdr.append(bottom)
        pPr.append(pBdr)
        r = p.add_run(text)
        _set_font(r, ft, max(14, fbs + 2), True, pc)

    # ═══ Page 1 ═══
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_p.space_before = Pt(24)
    title_p.space_after = Pt(6)
    r = title_p.add_run(getattr(record, "course_topic", "") or "课程报告")
    _set_font(r, ft, max(22, fts), True, pc)

    info_p = doc.add_paragraph()
    info_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    info_p.space_after = Pt(12)
    info_r = info_p.add_run(f"{student_name} ｜ {getattr(record, 'course_date', '') or ''}")
    _set_font(info_r, fb, fbs, color="#666666")

    if screenshots:
        fs_paths = []
        for s in screenshots[:2]:
            if isinstance(s, str):
                fp = _url_to_fs_path(s)
                if fp:
                    fs_paths.append(fp)
        if fs_paths:
            tbl = doc.add_table(rows=1, cols=len(fs_paths))
            tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            for i, fp in enumerate(fs_paths):
                try:
                    cp = tbl.rows[0].cells[i].paragraphs[0]
                    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    cp.add_run().add_picture(fp, width=Mm(70))
                except Exception as e:
                    log.warning("截图嵌入失败 %s: %s", fp, e)
            doc.add_paragraph()

    if kp:
        _heading("🎯 本节课知识点")
        for point in kp:
            p = doc.add_paragraph()
            p.space_before = Pt(3)
            p.space_after = Pt(3)
            pPr = p._element.get_or_add_pPr()
            pBdr = OxmlElement("w:pBdr")
            left = OxmlElement("w:left")
            left.set(qn("w:val"), "single")
            left.set(qn("w:sz"), "24")
            left.set(qn("w:space"), "6")
            left.set(qn("w:color"), pc.lstrip("#"))
            pBdr.append(left)
            pPr.append(pBdr)
            r = p.add_run(f"  {point}")
            _set_font(r, fb, fbs)

    ability = getattr(record, "ability_improvement", "") or ""
    if ability:
        _heading("💪 能力提升")
        _body(ability)

    # ═══ Page 2 ═══
    _page_break()
    _page_header("课程内容详解")
    for item in content_items[:2]:
        _heading(item.get("kp", ""))
        _body(item.get("text", ""))
    if code_excerpt:
        _heading("💻 本节课代码展示")
        for line in code_excerpt.split("\n"):
            p = doc.add_paragraph()
            p.space_before = Pt(0)
            p.space_after = Pt(0)
            pPr = p._element.get_or_add_pPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), "F5F5F5")
            pPr.append(shd)
            r = p.add_run(line or " ")
            _set_font(r, "Courier New", fbs - 1, ascii_name="Courier New")

    # ═══ Page 3 ═══
    _page_break()
    _page_header("课程内容（续）& 单词学习")
    if len(content_items) > 2:
        for item in content_items[2:]:
            _heading(item.get("kp", ""))
            _body(item.get("text", ""))
    else:
        _body("本课知识点详解已在前页完整展示。")

    if vocabulary and vocabulary.get("word"):
        _heading("📖 核心词汇")
        tbl = doc.add_table(rows=3, cols=2)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.style = "Table Grid"
        for row in tbl.rows:
            row.cells[0].width = Cm(2)
            row.cells[1].width = Cm(14)
        vdata = [
            ("单词", f"{vocabulary.get('word', '')}  {vocabulary.get('phonetic', '')}"),
            ("释义", vocabulary.get("meaning", "")),
            ("例句", vocabulary.get("example", "")),
        ]
        for i, (label, value) in enumerate(vdata):
            p0 = tbl.rows[i].cells[0].paragraphs[0]
            r0 = p0.add_run(label)
            _set_font(r0, fb, fbs, True, pc)
            p1 = tbl.rows[i].cells[1].paragraphs[0]
            r1 = p1.add_run(value)
            _set_font(r1, fb, fbs)

    # ═══ Page 4 ═══
    _page_break()
    if homework and homework.get("goal"):
        _heading("📚 课后作业")
        p = doc.add_paragraph()
        r1 = p.add_run("目标：")
        _set_font(r1, fb, fbs, True)
        r2 = p.add_run(homework.get("goal", ""))
        _set_font(r2, fb, fbs)
        for label, items in [("💡 提示：", homework.get("hints", [])),
                              ("✅ 评分标准：", homework.get("criteria", []))]:
            if items:
                _body(label)
                for item in items:
                    bp = doc.add_paragraph(item, style="List Bullet")
                    for run in bp.runs:
                        _set_font(run, fb, fbs)

    evaluation = getattr(record, "evaluation", "") or ""
    if evaluation:
        _heading("⭐ 学生评价")
        _body(evaluation)

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════

def generate(
    record,
    student_name: str = "",
    template_config: dict | None = None,
    layout_config: dict | None = None,
) -> bytes:
    """生成 Word 文档字节流。

    优先通过 altChunk 嵌入预览 HTML（与 PDF/预览效果一致），
    失败时回退到 python-docx 原生生成。
    """
    docx = _generate_altchunk(record, student_name, template_config, layout_config)
    if docx is not None:
        return docx
    log.info("回退到 python-docx 原生生成")
    return _generate_fallback(record, student_name, template_config, layout_config)
