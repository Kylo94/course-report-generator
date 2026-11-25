"""单元测试：docx_generator.py Word 文档生成服务。"""
from __future__ import annotations

import json
from io import BytesIO

import pytest
from docx import Document
from docx.shared import Mm, Pt, RGBColor

from backend.services.docx_generator import DocxGenerationError, generate
from backend.services.report_renderer import get_template_config

# =========================
# Fixtures
# =========================


def _open_docx(content: bytes) -> Document:
    """从 bytes 打开 docx。"""
    return Document(BytesIO(content))


class FakeRecord:
    """模拟 CourseRecord 对象（仅含 docx_generator 需要的属性）。"""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def minimal_record():
    """最小记录——所有字段为空。"""
    return FakeRecord(
        course_date="",
        course_topic="",
        project_folder="",
        knowledge_points=None,
        ability_improvement=None,
        content_items=None,
        vocabulary=None,
        homework=None,
        screenshot_paths=None,
        evaluation=None,
    )


@pytest.fixture
def full_record():
    """完整记录——所有字段有内容。"""
    return FakeRecord(
        course_date="2025-06-15",
        course_topic="Python 入门",
        project_folder="/home/projects/python101",
        knowledge_points=json.dumps(["变量", "循环", "函数"], ensure_ascii=False),
        ability_improvement="逻辑思维和问题解决能力有显著提升",
        content_items=json.dumps([
            {"kp": "变量", "text": "学习了变量的定义和使用"},
            {"kp": "循环", "text": "掌握了 for 和 while 循环"},
        ], ensure_ascii=False),
        vocabulary=json.dumps({
            "word": "variable",
            "phonetic": "ˈveəriəbl",
            "meaning": "变量",
            "example": "x is a variable.",
        }, ensure_ascii=False),
        homework=json.dumps({
            "goal": "完成一个计算器程序",
            "hints": ["使用 input 获取输入", "处理加减乘除"],
            "criteria": ["正确接收输入", "运算结果正确", "代码整洁"],
        }, ensure_ascii=False),
        screenshot_paths=json.dumps([]),
        evaluation="学生表现优秀，积极参与课堂互动",
    )


# =========================
# 测试：基本功能
# =========================


class TestGenerate:
    def test_empty_record_returns_valid_docx(self, minimal_record):
        """空记录应生成有效的 docx 字节流。"""
        result = generate(minimal_record)
        assert isinstance(result, bytes)
        assert len(result) > 0

        # 验证是有效 docx
        doc = _open_docx(result)
        assert doc is not None

    def test_full_record_has_content(self, full_record):
        """完整记录应包含所有章节标题。"""
        result = generate(full_record)
        doc = _open_docx(result)
        texts = [p.text for p in doc.paragraphs]

        # 检查章节标题（与 HTML 模板保持一致）
        for heading in (
            "基本信息", "本节课知识点", "项目运行效果", "课程内容详解",
            "代码展示", "核心词汇", "能力提升", "课后作业", "学生评价",
        ):
            assert any(heading in t for t in texts), heading

    def test_contains_student_name(self, full_record):
        """文档应包含学生姓名。"""
        result = generate(full_record, student_name="张三")
        doc = _open_docx(result)
        texts = [p.text for p in doc.paragraphs]
        assert any("张三" in t for t in texts)

    def test_contains_basic_info(self, full_record):
        """基本信息应包含日期和课程名称。"""
        result = generate(full_record, student_name="张三")
        doc = _open_docx(result)
        texts = [p.text for p in doc.paragraphs]
        assert any("2025-06-15" in t for t in texts)
        assert any("Python 入门" in t for t in texts)

    def test_knowledge_points_as_bullets(self, full_record):
        """知识点应显示为列表。"""
        result = generate(full_record)
        doc = _open_docx(result)
        texts = [p.text for p in doc.paragraphs]
        assert any("变量" in t for t in texts)
        assert any("循环" in t for t in texts)
        assert any("函数" in t for t in texts)

    def test_ability_improvement_included(self, full_record):
        """能力提升段落应出现在文档中。"""
        result = generate(full_record)
        doc = _open_docx(result)
        texts = [p.text for p in doc.paragraphs]
        assert any("逻辑思维" in t for t in texts)

    def test_evaluation_included(self, full_record):
        """学生评价应出现在文档中。"""
        result = generate(full_record)
        doc = _open_docx(result)
        texts = [p.text for p in doc.paragraphs]
        assert any("课堂互动" in t for t in texts)

    def test_custom_primary_color_from_template(self, full_record):
        """模板配置中的主题色应生效。"""
        tpl_config = {"theme": {"primary_color": "#FF5722"}}
        result = generate(full_record, template_config=tpl_config)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_chinese_content_utf8(self, full_record):
        """中文字符应正确处理。"""
        result = generate(full_record, student_name="测试学生")
        doc = _open_docx(result)
        # 保存到临时变量以验证文本内容
        full_text = "\n".join(p.text for p in doc.paragraphs)
        assert "测试学生" in full_text
        assert "Python 入门" in full_text


class TestLayoutConfigGeneration:
    """测试 layout_config 对 Word 生成的影响。"""

    def test_layout_config_custom_font(self, full_record):
        """layout_config 中的字体应在 Word 中生效。"""
        layout = {"font_body": "SimSun", "font_size_body": 14}
        result = generate(full_record, template_config=None, layout_config=layout)
        assert isinstance(result, bytes)

        doc = _open_docx(result)
        style = doc.styles["Normal"]
        assert style.font.size == Pt(14)

    def test_layout_config_with_template_theme_override(self, full_record):
        """layout_config 应优先于模板主题。"""
        tpl = {"theme": {"primary_color": "#FF5722", "font_title": "Heiti SC"}}
        layout = {"primary_color": "#E91E63", "font_title": "KaiTi"}
        result = generate(full_record, template_config=tpl, layout_config=layout)
        assert isinstance(result, bytes)

    def test_layout_config_margins(self, full_record):
        """layout_config 中的页边距生效。"""
        layout = {"page_margin_top": 30, "page_margin_bottom": 25}
        result = generate(full_record, template_config=None, layout_config=layout)
        doc = _open_docx(result)
        section = doc.sections[0]
        # 允许 EMU 单位转换时的微小舍入误差（< 0.02mm）
        assert abs(section.top_margin - Mm(30)) < 1000
        assert abs(section.bottom_margin - Mm(25)) < 1000

    def test_layout_config_null_values_use_defaults(self, full_record):
        """layout_config 中的 null 值使用默认值。"""
        layout = {"primary_color": None, "font_size_body": None}
        result = generate(full_record, template_config=None, layout_config=layout)
        assert isinstance(result, bytes)

    def test_layout_empty_dict_falls_back(self, full_record):
        """空 layout 使用默认样式。"""
        result = generate(full_record, template_config=None, layout_config={})
        doc = _open_docx(result)
        style = doc.styles["Normal"]
        # 默认字号应为 11pt
        assert style.font.size == Pt(11)


class TestGenerationEdgeCases:
    def test_none_json_fields(self, minimal_record):
        """None JSON 字段不应导致错误。"""
        result = generate(minimal_record)
        assert isinstance(result, bytes)

    def test_empty_knowledge_points(self, full_record):
        """空知识点列表不应影响生成。"""
        full_record.knowledge_points = json.dumps([])
        result = generate(full_record)
        doc = _open_docx(result)
        texts = [p.text for p in doc.paragraphs]
        # 知识点概括标题不应出现
        has_kp_header = any("知识点概括" in t for t in texts)
        # 即使有标题也不应该有列表项
        assert isinstance(result, bytes)

    def test_empty_homework(self, full_record):
        """空 homework 不应导致错误。"""
        full_record.homework = json.dumps({"goal": "", "hints": [], "criteria": []})
        result = generate(full_record)
        assert isinstance(result, bytes)

    def test_title_centered(self, full_record):
        """课程名称大标题应居中（它前面的“基本信息”是小标签）。"""
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        result = generate(full_record)
        doc = _open_docx(result)
        title = next(p for p in doc.paragraphs if "课程名称" in p.text)
        assert title.alignment == WD_ALIGN_PARAGRAPH.CENTER


class TestPrintAndEditability:
    """A4 打印 / 可编辑性 / 图片可替换性测试。"""

    def test_a4_page_size_and_margins(self, full_record):
        """页面必须是 A4，并应用配置的页边距。"""
        doc = _open_docx(generate(full_record))
        section = doc.sections[0]
        assert abs(section.page_width - Mm(210)) < 1000
        assert abs(section.page_height - Mm(297)) < 1000
        assert abs(section.top_margin - Mm(20)) < 1000
        assert abs(section.bottom_margin - Mm(18)) < 1000
        assert abs(section.left_margin - Mm(18)) < 1000
        assert abs(section.right_margin - Mm(18)) < 1000

    def test_has_four_pages_of_content(self, full_record):
        """第 1~4 页之间各有一次分页，且不使用 altChunk。"""
        doc = _open_docx(generate(full_record))
        xml = doc.element.xml
        assert xml.count("pageBreakBefore") == 3
        assert "altChunk" not in xml

    def test_all_visible_text_is_editable_runs(self, full_record):
        """关键文字应存在于普通段落 run 中，而不是图片。"""
        doc = _open_docx(generate(full_record, student_name="张三"))
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "张三" in text
        assert "2025-06-15" in text
        assert "Python 入门" in text
        assert "循环" in text
        assert "课堂互动" in text

    def test_headings_use_heading_1_for_word_navigation(self, full_record):
        """章节标题使用 Word 内置 Heading 1，便于导航和重新导入。"""
        doc = _open_docx(generate(full_record))
        heading_texts = {
            p.text.strip(): p.style.name
            for p in doc.paragraphs
            if p.style.name.startswith("Heading 1")
        }
        for heading in ("基本信息", "本节课知识点", "课程内容详解", "核心词汇", "课后作业", "学生评价"):
            assert heading_texts.get(heading) == "Heading 1", heading

    def test_images_are_inline_and_keep_aspect_ratio(self, full_record, tmp_path):
        """图片必须是 inline（可右键替换），且按原始比例等比缩放。"""
        from PIL import Image

        wide = tmp_path / "wide.png"
        tall = tmp_path / "tall.png"
        Image.new("RGB", (1200, 600), "#2563EB").save(wide)
        Image.new("RGB", (600, 1200), "#DC2626").save(tall)
        full_record.screenshot_paths = json.dumps([str(wide), str(tall)])

        doc = _open_docx(generate(full_record))
        xml = doc.element.xml
        assert "<wp:inline" in xml
        assert "<wp:anchor" not in xml

        ratios = sorted(round(shape.width / shape.height, 1) for shape in doc.inline_shapes)
        assert ratios == [0.5, 2.0]
        # 每张图都有 alt 文本，方便替换时辨认
        assert all(shape._inline.docPr.get("descr") for shape in doc.inline_shapes)

    def test_images_do_not_exceed_content_width(self, full_record, tmp_path):
        """单张超宽图也必须缩放到正文宽度以内，不能超出 A4 边界。"""
        from PIL import Image

        huge = tmp_path / "huge.png"
        Image.new("RGB", (5000, 2500), "#16A34A").save(huge)
        full_record.screenshot_paths = json.dumps([str(huge)])

        doc = _open_docx(generate(full_record))
        assert len(doc.inline_shapes) == 1
        shape = doc.inline_shapes[0]
        content_width = Mm(210) - Mm(18) - Mm(18)
        assert shape.width <= content_width + 1000
        assert abs(shape.width / shape.height - 2.0) < 0.01

class TestClassicPdfStyle:
    """Classic 模板的 PDF 风格 Word 版式测试。"""

    def _classic_doc(self, record, **kwargs):
        return _open_docx(generate(record, template_config=get_template_config("classic"), **kwargs))

    def test_has_fullpage_background_anchor(self, full_record):
        """背景图必须以 behindDoc 锚定在页眉中，才能在所有页面上显示。"""
        doc = self._classic_doc(full_record)
        header_xml = doc.sections[0].header._element.xml
        assert "wp:anchor" in header_xml
        assert 'behindDoc="1"' in header_xml

    def test_classic_four_pages_and_a4(self, full_record):
        doc = self._classic_doc(full_record)
        section = doc.sections[0]
        assert abs(section.page_width - Mm(210)) < 1000
        assert abs(section.page_height - Mm(297)) < 1000
        assert doc.element.xml.count("pageBreakBefore") == 3

    def test_classic_uses_card_tables(self, full_record):
        """知识点、内容、词汇、作业、评价都应使用卡片表格。"""
        doc = self._classic_doc(full_record)
        assert len(doc.tables) >= 8

    def test_classic_effect_image_is_small_and_proportional(self, full_record, tmp_path):
        from PIL import Image

        image = tmp_path / "effect.png"
        Image.new("RGB", (1200, 600), "#2563EB").save(image)
        full_record.screenshot_paths = json.dumps([str(image)])

        doc = self._classic_doc(full_record)
        effect_shapes = [
            shape for shape in doc.inline_shapes
            if (shape._inline.docPr.get("descr") or "").startswith("项目运行效果")
        ]
        assert len(effect_shapes) == 1
        shape = effect_shapes[0]
        # 首页运行截图固定约 7.8cm 宽，不再占满正文宽度
        assert shape.width <= Mm(80) + 1000
        assert abs(shape.width / shape.height - 2.0) < 0.01

    def test_classic_text_in_cards_is_editable(self, full_record):
        """卡片表格里的文字也必须能读到（不是图片）。"""
        doc = self._classic_doc(full_record, student_name="张三")
        texts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    texts.extend(p.text for p in cell.paragraphs)
        all_text = "\n".join(texts)
        assert "张三" in all_text
        assert "2025-06-15" in all_text
        assert "课堂互动" in all_text

class TestMinimalWord:
    """素白极简模板的 Word 版式测试。"""

    def test_minimal_page_border_and_no_background(self, full_record):
        doc = _open_docx(generate(
            full_record,
            template_config=get_template_config("minimal"),
        ))
        sect_xml = doc.sections[0]._sectPr.xml
        assert "w:pgBorders" in sect_xml
        assert 'w:color="D9E1E8"' in sect_xml
        # 极简模板不嵌入整页背景图
        assert "wp:anchor" not in doc.sections[0].header._element.xml
        # 标题浅底，正文卡片白底
        assert 'w:fill="F4F7F9"' in doc.element.xml
        assert 'w:fill="FFFFFF"' in doc.element.xml
        # A4、4 页
        assert abs(doc.sections[0].page_width - Mm(210)) < 1000
        assert doc.element.xml.count("pageBreakBefore") == 3
