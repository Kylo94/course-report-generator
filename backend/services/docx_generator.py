"""Word 文档生成服务：CourseRecord → .docx。

采用原生 python-docx 生成，而不是 altChunk 嵌入 HTML：

* 页面固定 A4（210 × 297 mm），可直接打印；
* 全部内容为普通段落 / 表格，二次编辑时无需手动调整任何元素位置；
* 所有文字都是可编辑的 run，不是图片或文本框；
* 所有图片都是嵌入型（inline）图片，右键“更改图片”即可替换，
  且替换后保持生成时的显示尺寸；
* 图片按固定最大宽高等比缩放，不拉伸、不超出页面。

文档结构与 HTML 模板保持一致：
第 1 页 基本信息 + 知识点 + 项目运行效果
第 2 页 课程内容详解
第 3 页 代码展示 + 核心词汇 + 能力提升
第 4 页 课后作业 + 学生评价

Classic 模板使用 PDF 风格版式：模板背景图整页锚定在页眉、卡片式知识点/
内容/词汇/作业/评价、固定尺寸截图；其他模板暂时沿用简洁原生版式。
"""
from __future__ import annotations

import json
import math
from io import BytesIO
from pathlib import Path
from typing import Any

from backend.config import PROJECT_ROOT, get_settings
from backend.utils.logger import get_logger

log = get_logger(__name__)

_CPP_EXTS = {".cpp", ".cc", ".cxx", ".c++", ".c", ".h", ".hpp", ".hh", ".hxx"}


class DocxGenerationError(Exception):
    def __init__(self, message: str, original: Exception | None = None):
        self.original = original
        super().__init__(message)


# =========================
# 数据读取
# =========================


def _load_json(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _url_to_fs_path(url_path: str) -> str | None:
    """将 HTTP 访问路径（如 /api/assets/screenshots/abc.jpg）转为绝对文件路径。"""
    if not isinstance(url_path, str) or not url_path:
        return None

    settings = get_settings()
    if url_path.startswith("/api/assets/screenshots/"):
        filename = url_path[len("/api/assets/screenshots/"):]
        full = Path(settings.report.screenshot_dir) / filename
        if full.exists():
            return str(full.resolve())
    elif url_path.startswith("/api/assets/showcase/"):
        filename = url_path[len("/api/assets/showcase/"):]
        full = Path(settings.report.screenshot_dir).parent / "showcase" / filename
        if full.exists():
            return str(full.resolve())
    elif url_path.startswith("/api/assets/"):
        filename = url_path[len("/api/assets/"):]
        full = Path(settings.report.asset_dir) / filename
        if full.exists():
            return str(full.resolve())
        # 回退到内置静态资源（背景图等）
        static_full = PROJECT_ROOT / "static" / "assets" / filename
        if static_full.exists():
            return str(static_full.resolve())

    # 也兼容直接传入本地绝对路径
    try:
        full = Path(url_path)
        if full.is_absolute() and full.exists():
            return str(full.resolve())
    except (OSError, ValueError):
        pass
    return None


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _resolve_images(urls: Any) -> list[str]:
    """把 URL/本地路径列表转换为存在的本地文件路径列表。"""
    resolved: list[str] = []
    for item in _as_list(urls):
        if not isinstance(item, str):
            continue
        path = _url_to_fs_path(item)
        if path:
            resolved.append(path)
    return resolved


def _collect_data(record) -> dict[str, Any]:
    """从 CourseRecord / BatchRecord 伪对象中读取生成 Word 所需的全部数据。"""
    kp = _load_json(getattr(record, "knowledge_points", None), []) or []
    content_items = _load_json(getattr(record, "content_items", None), []) or []
    vocabulary = _load_json(getattr(record, "vocabulary", None), {}) or {}
    homework = _load_json(getattr(record, "homework", None), {}) or {}
    screenshots = _load_json(getattr(record, "screenshot_paths", None), []) or []

    project_meta = _load_json(getattr(record, "project_meta", None), {}) or {}
    extra = project_meta.get("_extra_screenshots", {}) if isinstance(project_meta, dict) else {}

    run_screenshots = getattr(record, "_run_screenshots", None)
    code_screenshots = getattr(record, "_code_screenshots", None)
    homework_screenshots = getattr(record, "_homework_screenshots", None)
    if not isinstance(run_screenshots, list):
        run_screenshots = extra.get("run", []) if isinstance(extra, dict) else []
    if not isinstance(code_screenshots, list):
        code_screenshots = extra.get("code", []) if isinstance(extra, dict) else []
    if not isinstance(homework_screenshots, list):
        homework_screenshots = extra.get("homework", []) if isinstance(extra, dict) else []

    showcase = getattr(record, "_showcase_photo", None)

    # 首页「项目运行效果」：展示图优先，随后运行截图、其他截图
    raw_effect: list[str] = []
    for image in ([showcase] if isinstance(showcase, str) and showcase else []) + \
            _as_list(run_screenshots) + _as_list(screenshots):
        if isinstance(image, str) and image not in raw_effect:
            raw_effect.append(image)
    effect_images = _resolve_images(raw_effect)[:4]

    return {
        "course_topic": getattr(record, "course_topic", "") or "",
        "course_date": getattr(record, "course_date", "") or "",
        "ability_improvement": getattr(record, "ability_improvement", "") or "",
        "evaluation": getattr(record, "evaluation", "") or "",
        "knowledge_points": kp if isinstance(kp, list) else [],
        "content_items": content_items if isinstance(content_items, list) else [],
        "vocabulary": vocabulary if isinstance(vocabulary, dict) else {},
        "homework": homework if isinstance(homework, dict) else {},
        "effect_images": effect_images,
        "code_images": _resolve_images(code_screenshots)[:2],
        "homework_images": _resolve_images(homework_screenshots)[:2],
        "code_excerpt": _extract_code_excerpt(record, content_items),
        "logo_config": _load_json(getattr(record, "logo_config", None), {}) or {},
    }


def _extract_code_excerpt(record, content_items: list) -> str:
    """从 ai_meta 的行号信息中截取代码片段（最多 15 行）。"""
    if not getattr(record, "project_meta", None) or not getattr(record, "project_folder", None):
        return ""
    try:
        import ast as _ast
        import re as _re

        pm = _load_json(record.project_meta, {}) or {}
        folder = Path(pm.get("folder", record.project_folder))
        ai_meta = _load_json(getattr(record, "ai_meta", None), {}) or {}
        key_funcs = ai_meta.get("key_functions", [])

        referenced_funcs: set[str] = set()
        for item in content_items:
            if isinstance(item, dict):
                for match in _re.finditer(r'`([a-zA-Z_]\w*)\(\)', item.get("text", "") or ""):
                    referenced_funcs.add(match.group(1))

        code_blocks: list[dict] = []
        if referenced_funcs:
            for func_name in referenced_funcs:
                for m in key_funcs:
                    if m.get("name", "").strip("()") == func_name:
                        fp, sl, el = m.get("file_path", ""), m.get("start_line"), m.get("end_line")
                        if fp and sl and el:
                            code_blocks.append({"file": fp, "start": sl - 1, "end": el})
        else:
            for m in key_funcs[:2]:
                fp, sl, el = m.get("file_path", ""), m.get("start_line"), m.get("end_line")
                if fp and sl and el:
                    code_blocks.append({"file": fp, "start": sl - 1, "end": el})

        def _read_block(block: dict) -> str:
            fpath = folder / block["file"]
            if not fpath.exists():
                return ""
            try:
                lines = fpath.read_text("utf-8").splitlines()
                selected = lines[block["start"]:block["end"]]
                marker = "//" if fpath.suffix.lower() in _CPP_EXTS else "#"
                return f"{marker} {block['file']}:{block['start'] + 1}\n" + "\n".join(selected)
            except (OSError, IndexError):
                return ""

        raw_blocks = [b for b in (_read_block(b) for b in code_blocks) if b]

        # 没有行号信息时，退化为 AST 解析入口文件
        if not raw_blocks:
            entry_path = None
            if pm.get("entry_file"):
                entry_path = folder / pm["entry_file"]
            elif pm.get("py_files"):
                entry_path = folder / pm["py_files"][0]["path"]
            if entry_path and entry_path.exists():
                source = entry_path.read_text("utf-8")
                source_lines = source.splitlines()
                if entry_path.suffix.lower() in _CPP_EXTS:
                    start = 0
                    for idx, line in enumerate(source_lines):
                        if re.search(r"\bmain\s*\(", line):
                            start = idx
                            break
                    raw_blocks.append(
                        f"// {entry_path.name}:{start + 1}\n"
                        + "\n".join(source_lines[start:start + 15])
                    )
                else:
                    try:
                        tree = _ast.parse(source)
                        for node in _ast.walk(tree):
                            if not isinstance(node, _ast.FunctionDef):
                                continue
                            if referenced_funcs and node.name not in referenced_funcs:
                                continue
                            start = node.lineno - 1
                            end = getattr(node, "end_lineno", None) or start + 5
                            raw_blocks.append(
                                f"# {entry_path.name}:{node.lineno}\n"
                                + "\n".join(source_lines[start:end])
                            )
                            if len("\n\n".join(raw_blocks)) > 800:
                                break
                    except SyntaxError:
                        body = [
                            line for line in source_lines
                            if line.strip() and not line.strip().startswith(("import ", "from ", "#"))
                        ]
                        raw_blocks = body[:15]

        if raw_blocks:
            return "\n".join("\n\n".join(raw_blocks).splitlines()[:15])
    except Exception as e:
        log.warning("提取代码片段失败: %s", e)
    return ""


# =========================
# 布局合并
# =========================


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
        "background_color": theme.get("background_color", "#FFFFFF"),
        "background_image": theme.get("background_image"),
        "heading_fill": theme.get("heading_fill"),
        "card_fill": theme.get("card_fill"),
        "page_margin_top": theme.get("page_margin_top", 20),
        "page_margin_bottom": theme.get("page_margin_bottom", 18),
        "page_margin_left": theme.get("page_margin_left", 18),
        "page_margin_right": theme.get("page_margin_right", 18),
    }
    if layout_config:
        for key in result:
            if key in layout_config and layout_config[key] is not None:
                result[key] = layout_config[key]
    return result


# =========================
# OOXML 小工具
# =========================

# pPr 中 w:shd / w:pBdr 之后的合法子元素（用于按 schema 顺序插入）
_PPR_AFTER_PBDR = (
    "w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap",
    "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN",
    "w:bidi", "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind",
    "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc",
    "w:textDirection", "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl",
    "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange",
)
_PPR_AFTER_SHD = _PPR_AFTER_PBDR[1:]
_TCPR_AFTER_SHD = (
    "w:noWrap", "w:tcMar", "w:textDirection", "w:tcFitText", "w:vAlign",
    "w:hideMark", "w:headers", "w:cellIns", "w:cellDel", "w:cellMerge",
    "w:tcPrChange",
)
_TBLPR_AFTER_BORDERS = (
    "w:shd", "w:tblLayout", "w:tblCellMar", "w:tblLook", "w:tblCaption",
    "w:tblDescription", "w:tblPrChange",
)


def _rgb(hex_color: str):
    from docx.shared import RGBColor

    try:
        color = (hex_color or "").lstrip("#")
        if len(color) != 6:
            return None
        return RGBColor(int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16))
    except (ValueError, IndexError):
        return None


def _set_run_font(
    run,
    name: str,
    size_pt: float,
    bold: bool = False,
    color: str | None = None,
    italic: bool = False,
    ascii_name: str | None = None,
):
    """设置 run 字体，同时写入 eastAsia，保证中英文在 Word 中正常显示。"""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt

    run.font.name = ascii_name or name
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.italic = italic
    rgb = _rgb(color) if color else None
    if rgb is not None:
        run.font.color.rgb = rgb

    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    rfonts.set(qn("w:eastAsia"), name)
    rfonts.set(qn("w:ascii"), ascii_name or name)
    rfonts.set(qn("w:hAnsi"), ascii_name or name)


def _set_paragraph_shading(paragraph, fill: str):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    ppr = paragraph._p.get_or_add_pPr()
    shd = ppr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        ppr.insert_element_before(shd, *_PPR_AFTER_SHD)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), (fill or "FFFFFF").lstrip("#").upper())


def _set_paragraph_border(
    paragraph,
    side: str,
    color: str,
    size: int = 8,
    space: int = 4,
    val: str = "single",
):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    ppr = paragraph._p.get_or_add_pPr()
    pbdr = ppr.find(qn("w:pBdr"))
    if pbdr is None:
        pbdr = OxmlElement("w:pBdr")
        ppr.insert_element_before(pbdr, *_PPR_AFTER_PBDR)
    edge = pbdr.find(qn(f"w:{side}"))
    if edge is None:
        edge = OxmlElement(f"w:{side}")
        pbdr.append(edge)
    edge.set(qn("w:val"), val)
    edge.set(qn("w:sz"), str(size))
    edge.set(qn("w:space"), str(space))
    edge.set(qn("w:color"), (color or "000000").lstrip("#").upper())


def _set_cell_shading(cell, fill: str):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tcpr = cell._tc.get_or_add_tcPr()
    shd = tcpr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tcpr.insert_element_before(shd, *_TCPR_AFTER_SHD)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), (fill or "FFFFFF").lstrip("#").upper())


def _set_cell_margins(cell, top=20, bottom=20, left=80, right=80):
    """设置单元格内边距（单位 twips：1mm ≈ 56.7 twips）。"""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tcpr = cell._tc.get_or_add_tcPr()
    mar = tcpr.find(qn("w:tcMar"))
    if mar is None:
        mar = OxmlElement("w:tcMar")
        tcpr.insert_element_before(mar, *_TCPR_AFTER_SHD[1:])
    for tag, value in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        el = mar.find(qn(f"w:{tag}"))
        if el is None:
            el = OxmlElement(f"w:{tag}")
            mar.append(el)
        el.set(qn("w:w"), str(value))
        el.set(qn("w:type"), "dxa")


def _set_table_borders(tbl, color: str | None = None):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tblpr = tbl._tbl.tblPr
    borders = tblpr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tblpr.insert_element_before(borders, *_TBLPR_AFTER_BORDERS)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        if color:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), color.lstrip("#").upper())
        else:
            el.set(qn("w:val"), "none")
            el.set(qn("w:sz"), "0")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "auto")
        borders.append(el)


def _set_cell_borders(cell, color: str | None = None):
    """显式设置单元格边框；None 表示无边框（兼容 LibreOffice/Word）。"""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tcpr = cell._tc.get_or_add_tcPr()
    borders = tcpr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tcpr.insert_element_before(
            borders, "w:shd", "w:noWrap", "w:tcMar", "w:textDirection",
            "w:tcFitText", "w:vAlign", "w:hideMark", "w:tcPrChange",
        )
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        if color:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), color.lstrip("#").upper())
        else:
            el.set(qn("w:val"), "none")
            el.set(qn("w:sz"), "0")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "auto")
        borders.append(el)


def _set_cell_borders_sides(cell, sides: dict[str, tuple[str, int]] | None = None):
    """按边设置单元格边框；sides 形如 {"left": (color, sz)}，未给出的边为无边框。"""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    sides = sides or {}
    tcpr = cell._tc.get_or_add_tcPr()
    borders = tcpr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tcpr.insert_element_before(
            borders, "w:shd", "w:noWrap", "w:tcMar", "w:textDirection",
            "w:tcFitText", "w:vAlign", "w:hideMark", "w:tcPrChange",
        )
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        spec = sides.get(edge)
        if spec:
            color, size = spec
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(size))
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), (color or "auto").lstrip("#").upper())
        else:
            el.set(qn("w:val"), "none")
            el.set(qn("w:sz"), "0")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "auto")
        borders.append(el)


def _set_table_width(tbl, width_mm: float, col_widths_mm: list[float] | None = None):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Mm

    tbl.autofit = False
    tblpr = tbl._tbl.tblPr
    tblw = tblpr.find(qn("w:tblW"))
    if tblw is None:
        tblw = OxmlElement("w:tblW")
        tblpr.append(tblw)
    tblw.set(qn("w:type"), "dxa")
    tblw.set(qn("w:w"), str(int(width_mm / 25.4 * 1440)))

    layout = tblpr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tblpr.insert_element_before(layout, "w:tblCellMar", "w:tblLook", "w:tblPrChange")
    layout.set(qn("w:type"), "fixed")

    if col_widths_mm:
        for idx, width in enumerate(col_widths_mm):
            if idx < len(tbl.columns):
                tbl.columns[idx].width = Mm(width)
            for row in tbl.rows:
                if idx < len(row.cells):
                    row.cells[idx].width = Mm(width)


def _prevent_row_split(tbl):
    """禁止表格行跨页断开，保证图片/词汇表整行打印。"""
    from docx.oxml import OxmlElement

    for row in tbl.rows:
        trpr = row._tr.get_or_add_trPr()
        if trpr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}cantSplit") is None:
            trpr.append(OxmlElement("w:cantSplit"))


def _add_field(paragraph, instruction: str):
    """在段落中插入 Word 域（如 PAGE / NUMPAGES）。"""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    def _fld_char(kind: str):
        run = paragraph.add_run()
        el = OxmlElement("w:fldChar")
        el.set(qn("w:fldCharType"), kind)
        run._r.append(el)

    _fld_char("begin")
    run = paragraph.add_run()
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    run._r.append(instr)
    _fld_char("separate")
    paragraph.add_run("1")
    _fld_char("end")


# =========================
# 图片
# =========================


def _fit_image_mm(path: str, max_w_mm: float, max_h_mm: float) -> tuple[float, float] | None:
    """按最大宽高等比缩放，返回 (宽mm, 高mm)。失败返回 None。"""
    try:
        from PIL import Image

        with Image.open(path) as image:
            width_px, height_px = image.size
            # 处理手机照片的 EXIF 旋转
            try:
                orientation = image.getexif().get(274)
                if orientation in (5, 6, 7, 8):
                    width_px, height_px = height_px, width_px
            except Exception:
                pass
        if width_px <= 0 or height_px <= 0:
            return None
        ratio = width_px / height_px
        box_ratio = max_w_mm / max_h_mm if max_h_mm else ratio
        if ratio >= box_ratio:
            return max_w_mm, max_w_mm / ratio
        return max_h_mm * ratio, max_h_mm
    except Exception as e:
        log.warning("读取图片尺寸失败 %s: %s", path, e)
        return None


def _image_stream_for_docx(
    path: str,
    max_w_mm: float,
    max_h_mm: float,
    dpi: int = 180,
    quality: int = 88,
    preserve_alpha: bool = False,
):
    """把图片缩放到显示尺寸所需的分辨率并压缩，避免 Word 文件过大。

    preserve_alpha=True 时，带透明通道的图片（Logo）保存为 PNG，避免白底方块。
    返回 (BytesIO, (width_mm, height_mm))；失败返回 (None, None)。
    """
    dims = _fit_image_mm(path, max_w_mm, max_h_mm)
    if not dims:
        return None, None
    try:
        from PIL import Image, ImageOps

        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            has_alpha = image.mode in ("RGBA", "LA") or (
                image.mode == "P" and "transparency" in image.info
            )

            target_w = max(1, int(round(dims[0] / 25.4 * dpi)))
            target_h = max(1, int(round(dims[1] / 25.4 * dpi)))

            if has_alpha and preserve_alpha:
                image = image.convert("RGBA")
                if image.width > target_w or image.height > target_h:
                    image.thumbnail((target_w, target_h), Image.LANCZOS)
                buf = BytesIO()
                image.save(buf, format="PNG", optimize=True)
            else:
                if has_alpha:
                    rgba = image.convert("RGBA")
                    background = Image.new("RGB", rgba.size, "white")
                    background.paste(rgba, mask=rgba.split()[-1])
                    image = background
                else:
                    image = image.convert("RGB")
                if image.width > target_w or image.height > target_h:
                    image.thumbnail((target_w, target_h), Image.LANCZOS)
                buf = BytesIO()
                image.save(buf, format="JPEG", quality=quality, optimize=True)

            buf.seek(0)
            return buf, dims
    except Exception as e:
        log.warning("图片压缩失败 %s: %s", path, e)
        return None, None


def _background_stream(path: str, dpi: int = 150):
    """生成适合 A4 背景的压缩 JPEG，避免每份 Word 都嵌入数 MB 原图。"""
    try:
        from PIL import Image, ImageOps

        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.split()[-1])
                image = background
            else:
                image = image.convert("RGB")
            target_w = max(1, int(round(21.0 / 2.54 * dpi)))
            target_h = max(1, int(round(29.7 / 2.54 * dpi)))
            if image.width > target_w or image.height > target_h:
                image.thumbnail((target_w, target_h), Image.LANCZOS)
            buf = BytesIO()
            image.save(buf, format="JPEG", quality=90, optimize=True)
            buf.seek(0)
            return buf
    except Exception as e:
        log.warning("背景图压缩失败 %s: %s", path, e)
        return None


def _add_inline_image(
    paragraph,
    path: str,
    max_w_mm: float,
    max_h_mm: float,
    alt: str = "",
    preserve_alpha: bool = False,
):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Mm

    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Mm(1)
    paragraph.paragraph_format.space_after = Mm(1)

    dims = _fit_image_mm(path, max_w_mm, max_h_mm)
    run = paragraph.add_run()
    try:
        stream, dims = _image_stream_for_docx(
            path, max_w_mm, max_h_mm, preserve_alpha=preserve_alpha,
        )
        if stream is not None and dims:
            shape = run.add_picture(stream, width=Mm(dims[0]), height=Mm(dims[1]))
        elif dims:
            shape = run.add_picture(path, width=Mm(dims[0]), height=Mm(dims[1]))
        else:
            shape = run.add_picture(path, width=Mm(max_w_mm))
        if alt:
            try:
                shape._inline.docPr.set("descr", alt)
            except Exception:
                pass
        return shape
    except Exception as e:
        log.warning("Word 图片嵌入失败 %s: %s", path, e)
        return None


def _add_image_grid(
    doc,
    paths: list[str],
    content_width_mm: float,
    max_h_mm: float,
    cols: int = 2,
    alt_prefix: str = "图片",
):
    """图片按网格排布；单张时居中，多张时使用无边框固定列宽表格。"""
    paths = [p for p in paths if p]
    if not paths:
        return

    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Mm

    if len(paths) == 1:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Mm(2)
        _add_inline_image(p, paths[0], content_width_mm, max_h_mm, f"{alt_prefix} 1")
        return

    cols = max(1, min(cols, len(paths)))
    rows = math.ceil(len(paths) / cols)
    gap_mm = 4.0
    cell_w = (content_width_mm - gap_mm * (cols - 1)) / cols

    tbl = doc.add_table(rows=rows, cols=cols)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(tbl, None)
    _set_table_width(tbl, content_width_mm, [cell_w] * cols)

    from docx.enum.table import WD_ALIGN_VERTICAL

    _prevent_row_split(tbl)
    for cell in tbl._cells:
        _set_cell_borders(cell, None)
        _set_cell_margins(cell, 0, 0, 30, 30)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    for index, path in enumerate(paths):
        row, col = divmod(index, cols)
        cell = tbl.cell(row, col)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_inline_image(p, path, max(10.0, cell_w - 1.5), max_h_mm, f"{alt_prefix} {index + 1}")


# =========================
# 文档样式
# =========================


def _setup_page(doc, merged: dict):
    from docx.shared import Mm

    section = doc.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Mm(merged["page_margin_top"])
    section.bottom_margin = Mm(merged["page_margin_bottom"])
    section.left_margin = Mm(merged["page_margin_left"])
    section.right_margin = Mm(merged["page_margin_right"])
    section.header_distance = Mm(6)
    section.footer_distance = Mm(8)


def _setup_styles(doc, merged: dict):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt

    body_font = merged["font_body"]
    body_size = float(merged["font_size_body"])

    normal = doc.styles["Normal"]
    normal.font.name = body_font
    normal.font.size = Pt(body_size)
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    rfonts.set(qn("w:eastAsia"), body_font)
    rfonts.set(qn("w:ascii"), body_font)
    rfonts.set(qn("w:hAnsi"), body_font)

    pf = normal.paragraph_format
    pf.line_spacing = 1.5
    pf.space_before = Pt(0)
    pf.space_after = Pt(3)
    pf.widow_control = True

    # 把内置 Heading 1/2 样式也改成模板配色，这样二次编辑标题时
    # 新输入的文字仍然保持统一样式，不需要手动调格式。
    title_font = merged["font_title"]
    primary_rgb = _rgb(merged["primary_color"])
    for level, size, before, after in (
        (1, max(15, body_size + 4), 14, 6),
        (2, max(12, body_size + 1.5), 9, 3),
    ):
        style = doc.styles[f"Heading {level}"]
        style.font.name = title_font
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.italic = False
        if primary_rgb is not None:
            style.font.color.rgb = primary_rgb
        sr_rpr = style.element.get_or_add_rPr()
        sr_fonts = sr_rpr.find(qn("w:rFonts"))
        if sr_fonts is None:
            sr_fonts = OxmlElement("w:rFonts")
            sr_rpr.insert(0, sr_fonts)
        sr_fonts.set(qn("w:eastAsia"), title_font)
        sr_fonts.set(qn("w:ascii"), title_font)
        sr_fonts.set(qn("w:hAnsi"), title_font)
        spf = style.paragraph_format
        spf.space_before = Pt(before)
        spf.space_after = Pt(after)
        spf.keep_with_next = True
        spf.line_spacing = 1.2


def _content_width_mm(merged: dict) -> float:
    return 210.0 - float(merged["page_margin_left"]) - float(merged["page_margin_right"])


def _add_heading(
    doc,
    text: str,
    merged: dict,
    level: int = 1,
    page_break: bool = False,
    compact: bool = False,
):
    """添加一个 Heading 1/2 段落（Heading 1 供 Word 导航和重新导入识别）。"""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    p = doc.add_paragraph(style=f"Heading {level}")
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.line_spacing = 1.2
    if page_break:
        p.paragraph_format.page_break_before = True

    title_font = merged["font_title"]
    primary = merged["primary_color"]
    body_size = float(merged["font_size_body"])

    if compact:
        # “基本信息”这类小标签，保持低调但仍是可编辑文字
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run(text)
        _set_run_font(run, title_font, max(8, body_size - 2), bold=False, color="#8A94A6")
        return p

    if level == 1:
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(6)
        _set_paragraph_border(p, "bottom", primary, size=8, space=4)
        run = p.add_run(text)
        _set_run_font(run, title_font, max(15, body_size + 4), bold=True, color=primary)
    else:
        p.paragraph_format.space_before = Pt(9)
        p.paragraph_format.space_after = Pt(3)
        run = p.add_run(text)
        _set_run_font(run, title_font, max(12, body_size + 1.5), bold=True, color=primary)
    return p


def _add_body(
    doc,
    text: str,
    merged: dict,
    shaded: bool = False,
    first_line_indent: bool = False,
    keep_with_next: bool = False,
):
    from docx.shared import Pt

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = keep_with_next
    if first_line_indent:
        p.paragraph_format.first_line_indent = Pt(float(merged["font_size_body"]) * 2)
    if shaded:
        p.paragraph_format.left_indent = Pt(6)
        _set_paragraph_shading(p, merged["secondary_color"])
        _set_paragraph_border(p, "left", merged["primary_color"], size=18, space=6)

    run = p.add_run(text)
    _set_run_font(run, merged["font_body"], float(merged["font_size_body"]))
    return p


def _add_knowledge_points(doc, points: list, merged: dict):
    from docx.shared import Pt

    for point in points:
        if not str(point).strip():
            continue
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Pt(4)
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        _set_paragraph_shading(p, merged["secondary_color"])
        _set_paragraph_border(p, "left", merged["primary_color"], size=20, space=6)
        bullet = p.add_run("• ")
        _set_run_font(bullet, merged["font_title"], float(merged["font_size_body"]), bold=True,
                      color=merged["primary_color"])
        run = p.add_run(str(point))
        _set_run_font(run, merged["font_body"], float(merged["font_size_body"]))


# =========================
# 页眉 / 页脚
# =========================


def _resolve_logo(
    template_config: dict | None,
    record_logo_cfg: dict | None = None,
) -> tuple[str | None, dict]:
    cfg = template_config or {}
    logo_cfg = dict(cfg.get("logo_config") or {})
    if isinstance(record_logo_cfg, dict):
        for key in ("enabled", "position", "size", "show_on_all_pages", "margin"):
            if key in record_logo_cfg and record_logo_cfg[key] is not None:
                logo_cfg[key] = record_logo_cfg[key]
    if logo_cfg.get("enabled") is False:
        return None, logo_cfg

    raw = cfg.get("logo_data_uri")
    path = _url_to_fs_path(raw) if isinstance(raw, str) else None
    if not path:
        asset_dir = Path(get_settings().report.asset_dir)
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            candidate = asset_dir / f"logo{ext}"
            if candidate.exists():
                path = str(candidate)
                break
    return path, logo_cfg


def _add_logo_to_header(header, logo_path: str, logo_cfg: dict):
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    p = header.paragraphs[0]
    position = logo_cfg.get("position", "top-right")
    _add_inline_image(p, logo_path, 38, 12, "Logo", preserve_alpha=True)
    if position.endswith("left"):
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    elif position.endswith("center"):
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    else:
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.space_after = 0


def _add_page_number_footer(section, merged: dict):
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = 0
    p.paragraph_format.space_after = 0
    run = p.add_run("第 ")
    _set_run_font(run, merged["font_body"], 9, color="#94A3B8")
    _add_field(p, " PAGE ")
    run = p.add_run(" 页 / 共 ")
    _set_run_font(run, merged["font_body"], 9, color="#94A3B8")
    _add_field(p, " NUMPAGES ")
    run = p.add_run(" 页")
    _set_run_font(run, merged["font_body"], 9, color="#94A3B8")


def _setup_header_footer(
    doc,
    template_config: dict | None,
    merged: dict,
    record_logo_cfg: dict | None = None,
):
    section = doc.sections[0]
    # 首页不显示页码；Logo 根据 show_on_all_pages 决定是否出现在内页
    section.different_first_page_header_footer = True

    logo_path, logo_cfg = _resolve_logo(template_config, record_logo_cfg)
    if logo_path:
        _add_logo_to_header(section.first_page_header, logo_path, logo_cfg)
        if logo_cfg.get("show_on_all_pages", True):
            _add_logo_to_header(section.header, logo_path, logo_cfg)

    _add_page_number_footer(section, merged)


# =========================
# 页面构建
# =========================


def _build_cover(doc, data: dict, student_name: str, merged: dict):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    body_size = float(merged["font_size_body"])
    title_size = float(merged["font_size_title"])
    primary = merged["primary_color"]

    # Heading 1 仅作为可被 Word 导航/重新导入识别的小标签
    _add_heading(doc, "基本信息", merged, level=1, compact=True)

    # 课程名称（大标题）
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.0
    label = p.add_run("课程名称：")
    _set_run_font(label, merged["font_body"], max(10, body_size - 1), color="#8A94A6")
    run = p.add_run(data["course_topic"] or "课程报告")
    _set_run_font(run, merged["font_title"], max(20, title_size), bold=True, color=primary)

    # 学生姓名 / 日期
    for label_text, value in (
        ("学生姓名：", student_name or "—"),
        ("上课时间：", data["course_date"] or "—"),
    ):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(1)
        p.paragraph_format.line_spacing = 1.2
        label = p.add_run(label_text)
        _set_run_font(label, merged["font_body"], body_size, color="#64748B")
        run = p.add_run(value)
        _set_run_font(run, merged["font_title"], body_size + 1.5, bold=True, color="#1E293B")

    # 分隔线
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(10)
    _set_paragraph_border(p, "bottom", primary, size=6, space=1)

    # 本节课知识点
    _add_heading(doc, "本节课知识点", merged, level=1)
    if data["knowledge_points"]:
        _add_knowledge_points(doc, data["knowledge_points"], merged)
    else:
        _add_body(doc, "本节课暂无知识点记录。", merged, shaded=True)

    # 项目运行效果（含学生展示图 / 运行截图 / 其他截图）
    _add_heading(doc, "项目运行效果", merged, level=1, page_break=False)
    if data["effect_images"]:
        effect_count = len(data["effect_images"])
        _add_image_grid(
            doc,
            data["effect_images"],
            _content_width_mm(merged),
            # 1~2 张时占满整行高度；3~4 张时按 2×2 各占一半高度
            max_h_mm=92 if effect_count <= 2 else 44,
            cols=1 if effect_count == 1 else 2,
            alt_prefix="项目运行效果",
        )
    else:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(12)
        _set_paragraph_border(p, "top", "#CBD5E1", size=6, space=4, val="dashed")
        _set_paragraph_border(p, "bottom", "#CBD5E1", size=6, space=4, val="dashed")
        run = p.add_run("运行截图位置（可在 Word 中直接插入图片）")
        _set_run_font(run, merged["font_body"], body_size, color="#94A3B8")


def _build_content_page(doc, data: dict, merged: dict):
    _add_heading(doc, "课程内容详解", merged, level=1, page_break=True)

    items = data["content_items"]
    if not items:
        _add_body(doc, "本课内容暂未生成。", merged, shaded=True)
        return

    for item in items:
        if not isinstance(item, dict):
            continue
        kp = str(item.get("kp", "") or "").strip()
        text = str(item.get("text", "") or "").strip()
        if kp:
            _add_heading(doc, kp, merged, level=2)
        if text:
            _add_body(doc, text, merged, shaded=True, keep_with_next=False)


def _add_code_block(doc, code: str, merged: dict, content_width_mm: float):
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(tbl, "#D9DEE8")
    _set_table_width(tbl, content_width_mm, [content_width_mm])

    cell = tbl.cell(0, 0)
    _set_cell_shading(cell, "#F7F8FA")
    _set_cell_margins(cell, 120, 120, 160, 160)
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.line_spacing = 1.0
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)

    lines = code.splitlines() or [code]
    code_size = max(8.0, float(merged["font_size_body"]) - 2.5)
    for index, line in enumerate(lines):
        run = p.add_run(line if line else " ")
        _set_run_font(run, "Courier New", code_size, ascii_name="Courier New")
        if index < len(lines) - 1:
            run.add_break()


def _build_code_page(doc, data: dict, merged: dict):
    content_width = _content_width_mm(merged)
    body_size = float(merged["font_size_body"])

    # 代码展示
    _add_heading(doc, "代码展示", merged, level=1, page_break=True)
    if data["code_images"]:
        _add_image_grid(
            doc, data["code_images"], content_width,
            max_h_mm=70,
            cols=1 if len(data["code_images"]) == 1 else 2,
            alt_prefix="代码截图",
        )
    elif data["code_excerpt"]:
        _add_code_block(doc, data["code_excerpt"], merged, content_width)
    else:
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt

        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(10)
        run = p.add_run("代码截图位置（可在 Word 中直接插入图片）")
        _set_run_font(run, merged["font_body"], body_size, color="#94A3B8")

    # 核心词汇
    vocab = data["vocabulary"]
    if isinstance(vocab, dict) and vocab.get("word"):
        from docx.enum.table import WD_TABLE_ALIGNMENT
        from docx.shared import Pt

        _add_heading(doc, "核心词汇", merged, level=1)
        tbl = doc.add_table(rows=3, cols=2)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.style = "Table Grid"
        _set_table_borders(tbl, "#D9DEE8")
        label_w = 26.0
        _set_table_width(tbl, content_width, [label_w, content_width - label_w])
        _prevent_row_split(tbl)

        rows = (
            ("单词", f"{vocab.get('word', '')}  {vocab.get('phonetic', '')}".strip()),
            ("释义", str(vocab.get("meaning", "") or "")),
            ("例句", str(vocab.get("example", "") or "")),
        )
        for row_index, (label, value) in enumerate(rows):
            label_cell = tbl.cell(row_index, 0)
            value_cell = tbl.cell(row_index, 1)
            _set_cell_shading(label_cell, merged["secondary_color"])
            _set_cell_margins(label_cell, 60, 60, 100, 100)
            _set_cell_margins(value_cell, 60, 60, 100, 100)
            label_p = label_cell.paragraphs[0]
            label_p.paragraph_format.space_after = Pt(0)
            label_run = label_p.add_run(label)
            _set_run_font(label_run, merged["font_title"], body_size, bold=True,
                          color=merged["primary_color"])
            value_p = value_cell.paragraphs[0]
            value_p.paragraph_format.space_after = Pt(0)
            value_run = value_p.add_run(value)
            _set_run_font(value_run, merged["font_body"], body_size)

    # 能力提升
    _add_heading(doc, "能力提升", merged, level=1)
    ability = data["ability_improvement"] or "本节课能力提升内容暂未生成。"
    _add_body(doc, ability, merged, shaded=True)


def _build_homework_page(doc, data: dict, merged: dict):
    content_width = _content_width_mm(merged)
    body_size = float(merged["font_size_body"])
    homework = data["homework"]

    has_homework = bool(
        isinstance(homework, dict)
        and (homework.get("goal") or homework.get("questions") or homework.get("hints"))
    )

    if has_homework:
        from docx.shared import Pt

        _add_heading(doc, "课后作业", merged, level=1, page_break=True)

        questions = homework.get("questions")
        questions = questions if isinstance(questions, list) else []

        if questions:
            for index, question in enumerate(questions, start=1):
                if not isinstance(question, dict):
                    continue
                goal = str(question.get("goal", "") or "").strip()
                hint = question.get("hint") or ""
                if not hint:
                    hints = question.get("hints")
                    if isinstance(hints, list) and hints:
                        hint = hints[0]

                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(2)
                p.paragraph_format.space_after = Pt(3)
                p.paragraph_format.keep_with_next = True
                label = p.add_run(f"第 {index} 题：")
                _set_run_font(label, merged["font_title"], body_size, bold=True,
                              color=merged["primary_color"])
                goal_run = p.add_run(goal or "—")
                _set_run_font(goal_run, merged["font_body"], body_size)

                if hint:
                    hp = doc.add_paragraph()
                    hp.paragraph_format.left_indent = Pt(8)
                    hp.paragraph_format.space_before = Pt(1)
                    hp.paragraph_format.space_after = Pt(3)
                    _set_paragraph_shading(hp, "#FFFBEB")
                    _set_paragraph_border(hp, "left", "#F59E0B", size=12, space=4)
                    hint_label = hp.add_run("提示：")
                    _set_run_font(hint_label, merged["font_title"], body_size, bold=True,
                                  color="#B45309")
                    hint_run = hp.add_run(str(hint))
                    _set_run_font(hint_run, merged["font_body"], body_size, color="#475569")
        else:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(3)
            label = p.add_run("目标：")
            _set_run_font(label, merged["font_title"], body_size, bold=True,
                          color=merged["primary_color"])
            goal_run = p.add_run(str(homework.get("goal", "") or "—"))
            _set_run_font(goal_run, merged["font_body"], body_size)

        if data["homework_images"]:
            _add_heading(doc, "作业截图", merged, level=2)
            _add_image_grid(
                doc, data["homework_images"], content_width,
                max_h_mm=48,
                cols=1 if len(data["homework_images"]) == 1 else 2,
                alt_prefix="作业截图",
            )

    _add_heading(
        doc, "学生评价", merged, level=1,
        page_break=not has_homework,
    )
    evaluation = data["evaluation"] or "暂无评价。"
    _add_body(doc, evaluation, merged, first_line_indent=True)



# =========================
# Classic：PDF 风格 Word 版式
# =========================


def _lighten_hex(hex_color: str, ratio: float = 0.6) -> str:
    """把颜色向白色混合，得到浅色边框/分隔线。"""
    try:
        color = (hex_color or "").lstrip("#")
        if len(color) != 6:
            return "#E2E8F0"
        channels = [int(color[i:i + 2], 16) for i in (0, 2, 4)]
        mixed = [round(c + (255 - c) * ratio) for c in channels]
        return "#" + "".join(f"{c:02X}" for c in mixed)
    except (ValueError, IndexError):
        return "#E2E8F0"


def _resolve_classic_background(template_config: dict | None) -> str | None:
    theme = (template_config or {}).get("theme", {}) or {}
    bg = theme.get("background_image")
    if not isinstance(bg, str) or not bg:
        return None
    return _url_to_fs_path(bg)


def _add_fullpage_background(header, image_path: str):
    """把 A4 背景图作为浮于文字下方的锚定图片放进页眉，所有页面自动复用。"""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls
    from docx.shared import Cm, Pt

    p = header.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.0

    run = p.add_run()
    background = _background_stream(image_path)
    if background is not None:
        inline_shape = run.add_picture(background, width=Cm(21.0), height=Cm(29.7))
    else:
        inline_shape = run.add_picture(image_path, width=Cm(21.0), height=Cm(29.7))
    inline = inline_shape._inline
    cx = inline.extent.cx
    cy = inline.extent.cy
    doc_pr = inline.docPr
    graphic = inline.graphic

    anchor_xml = f"""
    <wp:anchor {nsdecls("wp", "a", "pic", "r")} distT="0" distB="0" distL="0" distR="0"
               simplePos="0" relativeHeight="0" behindDoc="1" locked="0" layoutInCell="1" allowOverlap="1">
        <wp:simplePos x="0" y="0"/>
        <wp:positionH relativeFrom="page"><wp:posOffset>0</wp:posOffset></wp:positionH>
        <wp:positionV relativeFrom="page"><wp:posOffset>0</wp:posOffset></wp:positionV>
        <wp:extent cx="{cx}" cy="{cy}"/>
        <wp:effectExtent l="0" t="0" r="0" b="0"/>
        <wp:wrapNone/>
        <wp:docPr id="{doc_pr.get('id')}" name="{doc_pr.get('name')}"/>
        <wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>
    </wp:anchor>
    """
    anchor = parse_xml(anchor_xml)
    anchor.append(graphic)
    drawing = inline.getparent()
    drawing.remove(inline)
    drawing.append(anchor)


def _add_classic_logo(doc, logo_path: str | None, logo_cfg: dict, page_break: bool = False):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    if not logo_path:
        return
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(2)
    if page_break:
        p.paragraph_format.page_break_before = True
    _add_inline_image(p, logo_path, 36, 12, "Logo", preserve_alpha=True)
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT


def _add_classic_heading(
    doc,
    text: str,
    merged: dict,
    level: int | None = 1,
    page_break: bool = False,
    center: bool = False,
    left_bar: bool = True,
    bottom_border: bool = True,
    size: float | None = None,
    compact: bool = False,
):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    style = f"Heading {level}" if level else None
    p = doc.add_paragraph(style=style) if style else doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.line_spacing = 1.2
    if page_break:
        p.paragraph_format.page_break_before = True

    primary = merged["primary_color"]
    light = _lighten_hex(primary, 0.6)
    title_font = merged["font_title"]
    body_size = float(merged["font_size_body"])

    if compact:
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run(text)
        _set_run_font(run, title_font, max(8, body_size - 2), bold=False, color="#8A94A6")
        return p

    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(8)
    heading_fill = merged.get("heading_fill")
    if left_bar and heading_fill:
        _set_paragraph_shading(p, heading_fill)
    if left_bar:
        _set_paragraph_border(p, "left", primary, size=24, space=12)
    if bottom_border:
        _set_paragraph_border(p, "bottom", light, size=8, space=4)

    run = p.add_run(text)
    _set_run_font(
        run, title_font,
        size if size is not None else max(13, body_size + 2),
        bold=True, color=primary,
    )
    return p


def _add_classic_title(doc, topic: str, merged: dict):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(14)
    p.paragraph_format.line_spacing = 1.0
    run = p.add_run(topic or "课程报告")
    _set_run_font(run, merged["font_title"], 24, bold=True, color=merged["primary_color"])


def _add_classic_student_pill(doc, student_name: str, course_date: str, merged: dict):
    from docx.shared import Mm, Pt

    content_width = _content_width_mm(merged)
    pill_width = min(92.0, content_width)
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(10)
    p.paragraph_format.line_spacing = 1.3
    p.paragraph_format.right_indent = Mm(max(0.0, content_width - pill_width))
    _set_paragraph_shading(p, merged.get("card_fill") or merged["secondary_color"])
    light = _lighten_hex(merged["primary_color"], 0.68)
    for side in ("top", "bottom", "left", "right"):
        _set_paragraph_border(p, side, light, size=4, space=4)

    label1 = p.add_run("学生姓名：")
    _set_run_font(label1, merged["font_body"], 9, color="#64748B")
    name = p.add_run(student_name or "—")
    _set_run_font(name, merged["font_title"], 11, bold=True, color="#1E293B")
    sep = p.add_run("  ｜  ")
    _set_run_font(sep, merged["font_body"], 9, color="#94A3B8")
    label2 = p.add_run("上课时间：")
    _set_run_font(label2, merged["font_body"], 9, color="#64748B")
    date = p.add_run(course_date or "—")
    _set_run_font(date, merged["font_title"], 11, bold=True, color="#1E293B")


def _make_classic_card(
    doc,
    merged: dict,
    fill: str,
    left_color: str | None = None,
    border_color: str | None = None,
    margins: tuple[int, int, int, int] = (150, 150, 220, 200),
):
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.shared import Mm

    width = _content_width_mm(merged)
    border = border_color or _lighten_hex(merged["primary_color"], 0.78)
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(tbl, None)
    _set_table_width(tbl, width, [width])
    cell = tbl.cell(0, 0)
    cell.width = Mm(width)
    _set_cell_shading(cell, fill)
    _set_cell_margins(cell, *margins)
    _set_cell_borders_sides(cell, {
        "top": (border, 4),
        "bottom": (border, 4),
        "right": (border, 4),
        "left": (left_color, 24) if left_color else (border, 4),
    })
    return cell


def _add_classic_knowledge_cards(doc, points: list, merged: dict):
    from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Mm, Pt

    points = [str(p).strip() for p in (points or []) if str(p).strip()]
    content_width = _content_width_mm(merged)
    if not points:
        cell = _make_classic_card(doc, merged, merged.get("card_fill") or merged["secondary_color"])
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("本节课暂无知识点记录。")
        _set_run_font(run, merged["font_body"], 10.5, color="#64748B")
        return

    gap = 4.0
    card_w = max(20.0, (content_width - gap * 2) / 3)
    total = card_w * 3 + gap * 2
    border = _lighten_hex(merged["primary_color"], 0.78)

    for start in range(0, len(points), 3):
        row_points = points[start:start + 3]
        tbl = doc.add_table(rows=1, cols=5)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        _set_table_borders(tbl, None)
        _set_table_width(tbl, total, [card_w, gap, card_w, gap, card_w])
        for card_index, text in zip((0, 2, 4), row_points, strict=False):
            cell = tbl.cell(0, card_index)
            cell.width = Mm(card_w)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            _set_cell_shading(cell, merged.get("card_fill") or merged["secondary_color"])
            _set_cell_margins(cell, 130, 130, 100, 100)
            _set_cell_borders_sides(cell, {
                "top": (border, 6), "bottom": (border, 6),
                "left": (border, 6), "right": (border, 6),
            })
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(text)
            _set_run_font(run, merged["font_body"], 10.5, color="#1E293B")
        for spacer_index in (1, 3):
            cell = tbl.cell(0, spacer_index)
            cell.width = Mm(gap)
            _set_cell_margins(cell, 0, 0, 0, 0)
            _set_cell_borders_sides(cell, None)

        gap_p = doc.add_paragraph()
        gap_p.paragraph_format.space_before = Pt(0)
        gap_p.paragraph_format.space_after = Pt(4)


def _add_classic_image_grid(
    doc,
    paths: list[str],
    merged: dict,
    cell_width_mm: float,
    max_h_mm: float,
    cols: int = 1,
    alt_prefix: str = "图片",
):
    from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    paths = [p for p in (paths or []) if p]
    if not paths:
        return

    content_width = _content_width_mm(merged)
    cols = max(1, min(cols, len(paths)))
    if cols > 1:
        cell_width_mm = min(cell_width_mm, (content_width - 4) / cols)
    rows = math.ceil(len(paths) / cols)

    tbl = doc.add_table(rows=rows, cols=cols)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(tbl, None)
    gap = 4.0
    total = cell_width_mm * cols + gap * (cols - 1)
    _set_table_width(tbl, total, [cell_width_mm] * cols)
    _prevent_row_split(tbl)

    for cell in tbl._cells:
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        _set_cell_margins(cell, 40, 40, 40, 40)
        _set_cell_borders_sides(cell, None)

    for index, path in enumerate(paths):
        row, col = divmod(index, cols)
        cell = tbl.cell(row, col)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        _add_inline_image(p, path, max(10.0, cell_width_mm - 2), max_h_mm, f"{alt_prefix} {index + 1}")


def _add_classic_content_card(doc, title: str, body: str, merged: dict):
    from docx.shared import Pt

    cell = _make_classic_card(
        doc, merged, merged.get("card_fill") or merged["secondary_color"],
        left_color=merged["primary_color"],
    )
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.35
    title_run = p.add_run(f"{title}：")
    _set_run_font(title_run, merged["font_title"], 12, bold=True, color=merged["primary_color"])
    if body:
        title_run.add_break()
        body_run = p.add_run(body)
        _set_run_font(body_run, merged["font_body"], 10.5, color="#334155")

    gap_p = doc.add_paragraph()
    gap_p.paragraph_format.space_before = Pt(0)
    gap_p.paragraph_format.space_after = Pt(6)


def _add_classic_vocab_card(doc, vocab: dict, merged: dict):
    from docx.shared import Pt

    cell = _make_classic_card(doc, merged, merged.get("card_fill") or merged["secondary_color"])
    p1 = cell.paragraphs[0]
    p1.paragraph_format.space_before = Pt(0)
    p1.paragraph_format.space_after = Pt(5)
    label = p1.add_run("单词：")
    _set_run_font(label, merged["font_body"], 9, color="#64748B")
    word = p1.add_run(str(vocab.get("word", "") or ""))
    _set_run_font(word, merged["font_title"], 13, bold=True, color=merged["primary_color"])
    phonetic = str(vocab.get("phonetic", "") or "")
    if phonetic:
        ph = p1.add_run("  " + phonetic)
        _set_run_font(ph, merged["font_body"], 11, italic=True, color="#64748B")

    for label_text, key in (("释义：", "meaning"), ("例句：", "example")):
        value = str(vocab.get(key, "") or "")
        if not value:
            continue
        p = cell.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(4)
        label_run = p.add_run(label_text)
        _set_run_font(label_run, merged["font_body"], 10.5, bold=True, color="#475569")
        value_run = p.add_run(value)
        _set_run_font(value_run, merged["font_body"], 10.5, color="#334155")


def _add_classic_body_card(doc, text: str, merged: dict, fill: str = "#F8FAFC", indent: bool = False):
    from docx.shared import Pt

    cell = _make_classic_card(doc, merged, fill, left_color=merged["primary_color"])
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.45
    if indent:
        p.paragraph_format.first_line_indent = Pt(22)
    run = p.add_run(text)
    _set_run_font(run, merged["font_body"], 10.5, color="#334155")


def _add_classic_hint_card(doc, hint: str, merged: dict):
    from docx.shared import Pt

    cell = _make_classic_card(
        doc, merged, "#FEFCE8", left_color="#F59E0B", border_color="#FEF08A",
        margins=(130, 130, 220, 200),
    )
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    label = p.add_run("提示：")
    _set_run_font(label, merged["font_title"], 10.5, bold=True, color="#B45309")
    run = p.add_run(hint)
    _set_run_font(run, merged["font_body"], 10.5, italic=True, color="#475569")


def _add_classic_hint_label(doc, merged: dict):
    from docx.shared import Pt

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    run = p.add_run("思路提示")
    _set_run_font(run, merged["font_title"], 11, bold=True, color=merged["primary_color"])


def _add_page_border(section, color: str = "#D9E1E8", size: int = 4, space: int = 24):
    """给 Word 页面加一圈很细的页边框（打印时少量线条，不铺底色）。"""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    sect_pr = section._sectPr
    borders = sect_pr.find(qn("w:pgBorders"))
    if borders is None:
        borders = OxmlElement("w:pgBorders")
        sect_pr.insert_element_before(
            borders,
            "w:lnNumType", "w:pgNumType", "w:cols", "w:formProt", "w:vAlign",
            "w:noEndnote", "w:titlePg", "w:textDirection", "w:bidi",
            "w:rtlGutter", "w:docGrid", "w:printerSettings",
        )
    borders.set(qn("w:offsetFrom"), "page")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:space"), str(space))
        el.set(qn("w:color"), (color or "#D9E1E8").lstrip("#").upper())
        borders.append(el)


def _build_classic_document(
    doc,
    data: dict,
    student_name: str,
    merged: dict,
    template_config: dict | None,
):
    """Classic 模板的 PDF 风格 Word 版式：整页背景 + 卡片化内容。"""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    section = doc.sections[0]
    section.header_distance = Cm(0)
    section.footer_distance = Cm(0)
    section.different_first_page_header_footer = False

    theme = (template_config or {}).get("theme", {}) or {}
    page_border = theme.get("page_border")
    if page_border:
        try:
            _add_page_border(section, page_border)
        except Exception as e:
            log.warning("Word 页边框添加失败: %s", e)

    background = _resolve_classic_background(template_config)
    if background:
        try:
            _add_fullpage_background(section.header, background)
        except Exception as e:
            log.warning("Word 整页背景图添加失败: %s", e)

    logo_path, logo_cfg = _resolve_logo(template_config, data.get("logo_config"))
    show_logo_all = logo_cfg.get("show_on_all_pages", True)

    def start_page(first: bool = False) -> bool:
        """开始新页；有 Logo 时把分页符放在 Logo 段落上，避免 Logo 跑到上一页底部。"""
        if not logo_path:
            return False
        if not first and not show_logo_all:
            return False
        _add_classic_logo(doc, logo_path, logo_cfg, page_break=not first)
        return True

    # ===== 第 1 页 =====
    start_page(first=True)
    _add_classic_title(doc, data["course_topic"], merged)
    _add_classic_student_pill(doc, student_name, data["course_date"], merged)

    _add_classic_heading(doc, "本节课知识点", merged, level=1)
    _add_classic_knowledge_cards(doc, data["knowledge_points"], merged)

    _add_classic_heading(doc, "项目运行效果", merged, level=1)
    if data["effect_images"]:
        count = len(data["effect_images"])
        _add_classic_image_grid(
            doc, data["effect_images"], merged,
            cell_width_mm=82 if count <= 2 else 78,
            max_h_mm=80 if count <= 2 else 52,
            cols=1 if count == 1 else 2,
            alt_prefix="项目运行效果",
        )
    else:
        cell = _make_classic_card(doc, merged, "#F8FAFC")
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("运行截图位置（可在 Word 中直接插入图片）")
        _set_run_font(run, merged["font_body"], 10.5, color="#94A3B8")

    # ===== 第 2 页 =====
    has_logo = start_page()
    _add_classic_heading(
        doc, "课程内容详解", merged, level=1, page_break=not has_logo,
        center=True, left_bar=False, size=16,
    )
    items = data["content_items"]
    if items:
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("kp", "") or "").strip()
            body = str(item.get("text", "") or "").strip()
            if not title and not body:
                continue
            _add_classic_content_card(doc, title or "本课内容", body, merged)
    else:
        _add_classic_content_card(doc, "本课内容", "本课内容暂未生成。", merged)

    # ===== 第 3 页 =====
    has_logo = start_page()
    _add_classic_heading(
        doc, "代码展示 & 单词学习", merged, level=1, page_break=not has_logo,
        center=True, left_bar=False, size=16,
    )
    _add_classic_heading(doc, "本节课代码展示", merged, level=None)

    if data["code_images"]:
        _add_classic_image_grid(
            doc, data["code_images"], merged,
            cell_width_mm=148 if len(data["code_images"]) == 1 else 74,
            max_h_mm=85 if len(data["code_images"]) == 1 else 65,
            cols=1 if len(data["code_images"]) == 1 else 2,
            alt_prefix="代码截图",
        )
    elif data["code_excerpt"]:
        _add_code_block(doc, data["code_excerpt"], merged, _content_width_mm(merged))
    else:
        cell = _make_classic_card(doc, merged, "#F8FAFC")
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("代码截图位置（可在 Word 中直接插入图片）")
        _set_run_font(run, merged["font_body"], 10.5, color="#94A3B8")

    vocab = data["vocabulary"]
    if isinstance(vocab, dict) and vocab.get("word"):
        _add_classic_heading(doc, "核心词汇", merged, level=1)
        _add_classic_vocab_card(doc, vocab, merged)

    _add_classic_heading(doc, "能力提升", merged, level=1)
    _add_classic_body_card(
        doc,
        data["ability_improvement"] or "本节课能力提升内容暂未生成。",
        merged,
    )

    # ===== 第 4 页 =====
    homework = data["homework"] if isinstance(data["homework"], dict) else {}
    questions = homework.get("questions") if isinstance(homework.get("questions"), list) else []
    has_homework = bool(homework.get("goal") or questions)

    has_logo = start_page()
    if has_homework:
        _add_classic_heading(doc, "课后作业", merged, level=1, page_break=not has_logo)
        if questions:
            for index, question in enumerate(questions, start=1):
                if not isinstance(question, dict):
                    continue
                goal = str(question.get("goal", "") or "").strip()
                hint = question.get("hint") or ""
                if not hint:
                    hints = question.get("hints")
                    if isinstance(hints, list) and hints:
                        hint = hints[0]

                cell = _make_classic_card(
                    doc, merged, "#F8FAFC", left_color=merged["primary_color"],
                )
                p = cell.paragraphs[0]
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.4
                label = p.add_run(f"第 {index} 题：")
                _set_run_font(label, merged["font_title"], 11, bold=True, color=merged["primary_color"])
                goal_run = p.add_run(goal or "—")
                _set_run_font(goal_run, merged["font_body"], 11, color="#334155")

                if hint:
                    _add_classic_hint_label(doc, merged)
                    _add_classic_hint_card(doc, str(hint), merged)
                gap_p = doc.add_paragraph()
                gap_p.paragraph_format.space_before = Pt(0)
                gap_p.paragraph_format.space_after = Pt(6)
        elif homework.get("goal"):
            cell = _make_classic_card(
                doc, merged, "#F8FAFC", left_color=merged["primary_color"],
            )
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            label = p.add_run("目标：")
            _set_run_font(label, merged["font_title"], 11, bold=True, color=merged["primary_color"])
            goal_run = p.add_run(str(homework.get("goal")))
            _set_run_font(goal_run, merged["font_body"], 11, color="#334155")
            hint = homework.get("hint") or ""
            if not hint:
                hints = homework.get("hints")
                if isinstance(hints, list) and hints:
                    hint = hints[0]
            if hint:
                _add_classic_hint_label(doc, merged)
                _add_classic_hint_card(doc, str(hint), merged)

        if data["homework_images"]:
            _add_classic_heading(doc, "作业截图", merged, level=None)
            _add_classic_image_grid(
                doc, data["homework_images"], merged,
                cell_width_mm=78, max_h_mm=55,
                cols=1 if len(data["homework_images"]) == 1 else 2,
                alt_prefix="作业截图",
            )

    _add_classic_heading(
        doc, "学生评价", merged, level=1,
        page_break=(not has_homework) and (not has_logo),
    )
    cell = _make_classic_card(doc, merged, "#F8FAFC")
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.55
    p.paragraph_format.first_line_indent = Pt(22)
    run = p.add_run(data["evaluation"] or "暂无评价。")
    _set_run_font(run, merged["font_body"], 11, color="#334155")


def _build_document(
    record,
    student_name: str = "",
    template_config: dict | None = None,
    layout_config: dict | None = None,
) -> bytes:
    from docx import Document

    merged = merge_layout_with_theme(template_config, layout_config)
    data = _collect_data(record)

    doc = Document()
    _setup_page(doc, merged)
    _setup_styles(doc, merged)

    template_id = (template_config or {}).get("id")
    if template_id in ("classic", "minimal"):
        # Classic 模板：PDF 风格版式（整页背景 + 卡片）
        _build_classic_document(doc, data, student_name, merged, template_config)
    else:
        _setup_header_footer(doc, template_config, merged, data.get("logo_config"))
        _build_cover(doc, data, student_name, merged)
        _build_content_page(doc, data, merged)
        _build_code_page(doc, data, merged)
        _build_homework_page(doc, data, merged)

    # 文档属性（不影响排版，方便识别）
    try:
        doc.core_properties.title = data["course_topic"] or "课程报告"
        doc.core_properties.author = "课程报告生成器"
        doc.core_properties.comments = "A4 打印版；所有文字可直接编辑，所有图片可右键替换"
    except Exception:
        pass

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


# =========================
# 入口
# =========================


def generate(
    record,
    student_name: str = "",
    template_config: dict | None = None,
    layout_config: dict | None = None,
) -> bytes:
    """生成 A4 Word 文档字节流。

    原生 python-docx 生成：文字可编辑、图片可替换、打印无需二次排版。
    """
    try:
        return _build_document(record, student_name, template_config, layout_config)
    except DocxGenerationError:
        raise
    except Exception as e:
        log.exception("Word 生成失败: %s", e)
        raise DocxGenerationError(f"Word 生成失败: {e}", original=e) from e
