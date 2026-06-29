"""布局合并函数单元测试。

测试 merge_layout_with_theme() 在 report_renderer 和 docx_generator 中的行为。
两个模块各自定义了自己的 merge 函数（逻辑相同），分别测试。
"""
from __future__ import annotations

import pytest

from backend.services.report_renderer import merge_layout_with_theme as renderer_merge
from backend.services.docx_generator import merge_layout_with_theme as docx_merge


SAMPLE_THEME = {
    "theme": {
        "primary_color": "#FF5722",
        "secondary_color": "#FFF3E0",
        "font_title": "KaiTi",
        "font_body": "FangSong",
        "font_size_title": 28,
        "font_size_body": 12,
    }
}


class TestMergeLayoutWithTheme:
    """merge_layout_with_theme 函数测试。"""

    @pytest.mark.parametrize("merge_fn", [renderer_merge, docx_merge])
    def test_empty_layout_uses_theme_defaults(self, merge_fn):
        """没有 layout 覆盖时使用模板主题默认值。"""
        result = merge_fn(SAMPLE_THEME, None)
        assert result["primary_color"] == "#FF5722"
        assert result["secondary_color"] == "#FFF3E0"
        assert result["font_title"] == "KaiTi"
        assert result["font_body"] == "FangSong"
        assert result["font_size_title"] == 28
        assert result["font_size_body"] == 12

    @pytest.mark.parametrize("merge_fn", [renderer_merge, docx_merge])
    def test_no_template_falls_back_to_hardcoded(self, merge_fn):
        """没有模板配置时使用硬编码默认值。"""
        result = merge_fn(None, None)
        assert result["primary_color"] == "#3B7DDD"
        assert result["font_title"] == "Heiti SC"
        assert result["font_size_title"] == 24

    @pytest.mark.parametrize("merge_fn", [renderer_merge, docx_merge])
    def test_partial_layout_overrides_theme(self, merge_fn):
        """部分 layout 覆盖正确合并。"""
        layout = {"primary_color": "#E91E63", "font_size_body": 14}
        result = merge_fn(SAMPLE_THEME, layout)
        assert result["primary_color"] == "#E91E63"  # 覆盖
        assert result["secondary_color"] == "#FFF3E0"  # 保留主题值
        assert result["font_title"] == "KaiTi"  # 保留主题值
        assert result["font_size_body"] == 14  # 覆盖
        assert result["font_size_title"] == 28  # 保留主题值

    @pytest.mark.parametrize("merge_fn", [renderer_merge, docx_merge])
    def test_null_values_dont_override(self, merge_fn):
        """layout 中的 null/None 值不覆盖模板值。"""
        layout = {"primary_color": None, "font_title": None, "font_size_body": None}
        result = merge_fn(SAMPLE_THEME, layout)
        assert result["primary_color"] == "#FF5722"  # 没被 None 覆盖
        assert result["font_title"] == "KaiTi"
        assert result["font_size_body"] == 12

    @pytest.mark.parametrize("merge_fn", [renderer_merge, docx_merge])
    def test_full_layout_overrides_everything(self, merge_fn):
        """完整 layout 覆盖所有可配置项。"""
        layout = {
            "primary_color": "#4CAF50",
            "secondary_color": "#E8F5E9",
            "font_title": "SimSun",
            "font_body": "SimHei",
            "font_size_title": 20,
            "font_size_body": 10,
        }
        result = merge_fn(SAMPLE_THEME, layout)
        for k, v in layout.items():
            assert result[k] == v

    @pytest.mark.parametrize("merge_fn", [renderer_merge, docx_merge])
    def test_edge_margin_has_defaults(self, merge_fn):
        """边距字段有合理的默认值。"""
        result = merge_fn(None, None)
        assert result["page_margin_top"] == 20
        assert result["page_margin_bottom"] == 18
        assert result["page_margin_left"] == 18
        assert result["page_margin_right"] == 18

    @pytest.mark.parametrize("merge_fn", [renderer_merge, docx_merge])
    def test_empty_dict_layout(self, merge_fn):
        """空字典的 layout 不覆盖任何值。"""
        result = merge_fn(SAMPLE_THEME, {})
        assert result["primary_color"] == "#FF5722"
        assert result["font_size_body"] == 12

    @pytest.mark.parametrize("merge_fn", [renderer_merge, docx_merge])
    def test_unknown_keys_ignored(self, merge_fn):
        """layout 中不识别的键被忽略。"""
        layout = {"primary_color": "#123456", "nonexistent_key": "should_be_ignored"}
        result = merge_fn(SAMPLE_THEME, layout)
        assert result["primary_color"] == "#123456"
        assert "nonexistent_key" not in result
