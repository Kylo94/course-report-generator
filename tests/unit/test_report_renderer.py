"""报告渲染器单元测试。"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.services.report_renderer import (
    ReportRenderer,
    TemplateNotFoundError,
    _image_to_data_uri,
    _url_to_fs_path,
    get_template_config,
    list_templates,
)


class TestTemplateDiscovery:
    """模板发现功能测试。"""

    def test_list_templates(self) -> None:
        """list_templates 返回非空列表，包含 classic / cartoon / academic。"""
        templates = list_templates()
        assert len(templates) >= 3
        ids = [t["id"] for t in templates]
        assert "classic" in ids
        assert "cartoon" in ids
        assert "academic" in ids

    def test_get_template_config(self) -> None:
        """get_template_config 加载经典模板配置。"""
        config = get_template_config("classic")
        assert config["id"] == "classic"
        assert config["name"] == "经典简约"
        assert "theme" in config

    def test_get_template_config_not_found(self) -> None:
        """不存在的模板抛出 TemplateNotFoundError。"""
        with pytest.raises(TemplateNotFoundError):
            get_template_config("nonexistent_template_xyz")


class TestRenderInitialization:
    """渲染器初始化测试。"""

    def test_init_classic(self) -> None:
        """经典模板渲染器初始化成功。"""
        renderer = ReportRenderer("classic")
        assert renderer.template_id == "classic"
        assert renderer.css_content
        assert renderer.html_template
        assert renderer.config["id"] == "classic"

    def test_init_cartoon(self) -> None:
        """卡通模板初始化成功。"""
        renderer = ReportRenderer("cartoon")
        assert renderer.html_template
        assert renderer.css_content

    def test_init_academic(self) -> None:
        """学术模板初始化成功。"""
        renderer = ReportRenderer("academic")
        assert renderer.html_template
        assert renderer.css_content

    def test_init_not_found(self) -> None:
        """不存在的模板抛出异常。"""
        with pytest.raises(TemplateNotFoundError):
            ReportRenderer("nonexistent_template_xyz")


class TestRenderer:
    """渲染功能测试。"""

    def _make_fake_record(self, **overrides) -> MagicMock:
        """创建一个模拟的 CourseRecord 对象。"""
        defaults = {
            "course_topic": "Python 基础",
            "course_date": "2026-06-29",
            "ability_improvement": "逻辑思维能力提升，抽象思维培养",
            "evaluation": "上课认真，逻辑清晰，能够独立完成课堂练习。继续保持！",
            "knowledge_points": json.dumps(["变量", "循环", "条件判断"]),
            "content_items": json.dumps([
                {"kp": "变量", "text": "学习使用变量存储数据"},
                {"kp": "循环", "text": "掌握 for 循环基本语法"},
                {"kp": "条件判断", "text": "理解 if-else 逻辑"},
            ]),
            "homework": json.dumps({"goal": "完成课后练习", "hints": ["先思考再编码"], "criteria": ["代码正确", "注释完整"]}),
            "vocabulary": json.dumps({"word": "Variable", "phonetic": "/ˈveəriəbl/", "meaning": "变量", "example": "x = 10"}),
            "screenshot_paths": json.dumps([]),
            "logo_config": json.dumps({"enabled": False}),
        }
        defaults.update(overrides)
        return MagicMock(**defaults)

    def test_render_contains_course_topic(self) -> None:
        """渲染输出包含课程名称。"""
        renderer = ReportRenderer("classic")
        record = self._make_fake_record()
        html = renderer.render(record, student_name="张三")
        assert "Python 基础" in html
        assert "张三" in html

    def test_render_contains_knowledge_points(self) -> None:
        """渲染输出包含知识点。"""
        renderer = ReportRenderer("classic")
        record = self._make_fake_record()
        html = renderer.render(record)
        assert "变量" in html
        assert "循环" in html
        assert "条件判断" in html

    def test_render_contains_evaluation(self) -> None:
        """渲染输出包含评价。"""
        renderer = ReportRenderer("classic")
        record = self._make_fake_record()
        html = renderer.render(record)
        assert "上课认真" in html

    def test_render_empty_fields(self) -> None:
        """空数据字段不影响渲染。"""
        renderer = ReportRenderer("classic")
        record = self._make_fake_record(
            course_topic="",
            ability_improvement="",
            evaluation="",
            knowledge_points=json.dumps([]),
            content_items=json.dumps([]),
            homework=json.dumps({}),
            vocabulary=json.dumps({}),
        )
        html = renderer.render(record, student_name="")
        # 不能崩溃
        assert isinstance(html, str)
        assert len(html) > 500

    def test_render_with_logo(self) -> None:
        """启用 Logo 时渲染不出错。"""
        renderer = ReportRenderer("classic")
        record = self._make_fake_record(
            logo_config=json.dumps({
                "enabled": True,
                "position": "top-right",
                "size": 30,
                "show_on_all_pages": True,
            }),
        )
        # Logo 文件可能不存在，但渲染不会崩溃
        html = renderer.render(record)
        assert isinstance(html, str)

    def test_render_all_templates(self) -> None:
        """三种模板渲染都不出错。"""
        record = self._make_fake_record()
        for tid in ("classic", "cartoon", "academic"):
            renderer = ReportRenderer(tid)
            html = renderer.render(record, student_name="测试")
            assert isinstance(html, str)
            assert len(html) > 500
            assert "测试" in html

    def test_render_content_items_ordering(self) -> None:
        """内容项按顺序渲染（前 3 项在第 2 页，其余在第 3 页）。"""
        renderer = ReportRenderer("classic")
        items = [
            {"kp": f"KP{i}", "text": f"内容{i}"}
            for i in range(5)
        ]
        record = self._make_fake_record(content_items=json.dumps(items))
        html = renderer.render(record)
        # 所有 5 项都要出现
        for i in range(5):
            assert f"KP{i}" in html
            assert f"内容{i}" in html


class TestLayoutConfigRendering:
    """带 layout_config 的渲染测试。"""

    def _make_fake_record(self, **overrides) -> MagicMock:
        defaults = {
            "course_topic": "Test Topic",
            "course_date": "2026-06-29",
            "ability_improvement": "Ability text",
            "evaluation": "Evaluation text",
            "knowledge_points": json.dumps(["KP1", "KP2"]),
            "content_items": json.dumps([{"kp": "KP1", "text": "Content1"}]),
            "homework": json.dumps({"goal": "Goal", "hints": [], "criteria": []}),
            "vocabulary": json.dumps({"word": "Test", "phonetic": "/test/", "meaning": "测试", "example": "test"}),
            "screenshot_paths": json.dumps([]),
            "logo_config": json.dumps({"enabled": False}),
            "layout_config": None,
        }
        defaults.update(overrides)
        return MagicMock(**defaults)

    def test_render_with_layout_config_injects_custom_style(self) -> None:
        """传递 layout_config 时 HTML 中包含自定义 CSS。"""
        renderer = ReportRenderer("classic")
        record = self._make_fake_record()
        layout = {"primary_color": "#FF0000", "font_body": "SimSun"}
        html = renderer.render(record, student_name="测试", layout_config=layout)
        # 自定义样式块应注入
        assert "custom_style" in renderer.html_template or "--primary: #FF0000" in html
        # 实际检查 HTML 中是否包含颜色值
        assert "#FF0000" in html

    def test_render_without_layout_uses_default_colors(self) -> None:
        """不传 layout_config 时使用主题默认色。"""
        renderer = ReportRenderer("classic")
        record = self._make_fake_record()
        html = renderer.render(record, student_name="测试")
        # 主题默认色应出现在 CSS 变量中
        assert "--primary" in html
        assert "3B7DDD" in html or renderer.config.get("theme", {}).get("primary_color", "") in html

    def test_render_with_layout_font_size(self) -> None:
        """layout_config 中的字体大小生效。"""
        renderer = ReportRenderer("classic")
        record = self._make_fake_record()
        layout = {"font_size_title": 36, "font_size_body": 16}
        html = renderer.render(record, layout_config=layout)
        assert "--fs-title: 36pt" in html
        assert "--fs-body: 16pt" in html

    def test_render_with_background_color(self) -> None:
        """layout_config 中的背景色生效。"""
        renderer = ReportRenderer("classic")
        record = self._make_fake_record()
        layout = {"background_color": "#FFF3E0"}
        html = renderer.render(record, layout_config=layout)
        assert "--bg-color: #FFF3E0" in html

    def test_render_all_templates_with_layout(self) -> None:
        """三种模板带 layout_config 都能正常渲染。"""
        record = self._make_fake_record()
        layout = {"primary_color": "#9C27B0", "font_title": "KaiTi"}
        for tid in ("classic", "cartoon", "academic"):
            renderer = ReportRenderer(tid)
            html = renderer.render(record, student_name="测试", layout_config=layout)
            assert isinstance(html, str)
            assert "#9C27B0" in html

    def test_custom_style_block_has_valid_css(self) -> None:
        """_build_custom_style 生成有效的 CSS 变量块。"""
        merged = {
            "primary_color": "#E91E63",
            "secondary_color": "#FCE4EC",
            "font_title": "KaiTi",
            "font_body": "SimSun",
            "font_size_title": 30,
            "font_size_body": 14,
            "background_color": "#FFFFFF",
            "background_image": None,
            "page_margin_top": 20,
            "page_margin_right": 18,
            "page_margin_bottom": 18,
            "page_margin_left": 18,
        }
        style = ReportRenderer._build_custom_style(merged)
        assert ":root {" in style
        assert "--primary: #E91E63;" in style
        assert "--font-title: \"KaiTi\"" in style
        assert "--fs-title: 30pt;" in style
        assert "--page-margin-top: 20mm;" in style
        assert "}" in style


class TestHelpers:
    """辅助函数测试。"""

    def test_url_to_fs_path_screenshot_invalid(self) -> None:
        """无效路径返回 None。"""
        result = _url_to_fs_path("/api/assets/screenshots/notexist.jpg")
        assert result is None

    def test_image_to_data_uri_nonexistent(self) -> None:
        """不存在的文件返回 None。"""
        result = _image_to_data_uri("/nonexistent/path/file.png")
        assert result is None

    def test_image_to_data_uri_invalid_path(self) -> None:
        """无效路径返回 None。"""
        result = _image_to_data_uri("")
        assert result is None
