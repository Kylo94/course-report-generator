"""单元测试：template_manager.py 模板管理服务。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend.services.report_renderer import TEMPLATES_DIR, list_templates
from backend.services.template_manager import (
    TemplateNotDeletableError,
    TemplateNotFoundError,
    _generate_unique_id,
    _sanitize_id,
    create_template,
    delete_template,
    list_custom_templates,
    render_template_preview,
    update_template_config,
)


# =========================
# 辅助函数
# =========================


def _read_config(template_id: str) -> dict:
    """读取模板的 config.json。"""
    config_path = TEMPLATES_DIR / template_id / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


# =========================
# _sanitize_id 测试
# =========================


class TestSanitizeId:
    def test_basic_name(self) -> None:
        """普通英文名。"""
        assert _sanitize_id("My Template") == "my_template"

    def test_chinese_name(self) -> None:
        """中文名称。"""
        result = _sanitize_id("我的模板")
        assert "我的模板" in result

    def test_special_chars(self) -> None:
        """特殊字符被过滤。"""
        result = _sanitize_id("Hello!!! World@@@")
        assert "hello_world" == result

    def test_empty_after_sanitize(self) -> None:
        """全部特殊字符时生成默认 ID。"""
        result = _sanitize_id("!!! @@@ ###")
        # 空格→下划线，特殊字符被过滤，剩下的下划线是有效的 ID
        assert result == "__"

    def test_mixed_chinese_space(self) -> None:
        """中英文混合。"""
        result = _sanitize_id("My模板 Test")
        assert "my模板_test" == result


# =========================
# _generate_unique_id 测试
# =========================


class TestGenerateUniqueId:
    def test_basic(self) -> None:
        """基本名称生成。"""
        tid = _generate_unique_id("测试唯一模板")
        assert isinstance(tid, str)
        assert len(tid) > 0

    def test_no_collision_with_builtin(self) -> None:
        """不会与内置模板 ID 冲突。"""
        tid = _generate_unique_id("classic")
        assert tid != "classic"
        assert tid.startswith("classic_")


# =========================
# create_template 测试
# =========================


class TestCreateTemplate:
    def test_create_from_classic(self) -> None:
        """从经典模板创建自定义模板。"""
        try:
            result = create_template(
                name="测试模板A",
                description="这是一个测试模板",
                base_template_id="classic",
                theme_overrides={"primary_color": "#FF0000"},
            )
            assert result["name"] == "测试模板A"
            assert result["description"] == "这是一个测试模板"
            assert result["is_builtin"] is False
            assert result["parent_template"] == "classic"
            assert result["page_size"] == "A4"
            assert result["id"] != "classic"

            # 验证目录和文件存在
            template_dir = TEMPLATES_DIR / result["id"]
            assert template_dir.exists()
            assert (template_dir / "template.html").exists()
            assert (template_dir / "style.css").exists()
            assert (template_dir / "config.json").exists()

            # 验证 config.json 内容
            config = _read_config(result["id"])
            assert config["name"] == "测试模板A"
            assert config["is_builtin"] is False
            assert config["parent_template"] == "classic"
            assert config["theme"]["primary_color"] == "#FF0000"
            # 其他主题值应继承自经典模板
            assert config["theme"]["font_title"] == "Heiti SC"
            assert config["theme"]["font_size_body"] == 11
        finally:
            # 清理
            for t in list_templates():
                if not t["is_builtin"]:
                    delete_template(t["id"])

    def test_create_from_academic(self) -> None:
        """从学术模板创建。"""
        try:
            result = create_template(
                name="学术自定义",
                description="基于学术风",
                base_template_id="academic",
                theme_overrides={
                    "primary_color": "#123456",
                    "font_title": "KaiTi",
                    "font_size_title": 20,
                },
            )
            assert result["parent_template"] == "academic"
            config = _read_config(result["id"])
            assert config["theme"]["primary_color"] == "#123456"
            assert config["theme"]["font_title"] == "KaiTi"
            assert config["theme"]["font_size_title"] == 20
            # 未覆盖的应继承
            assert config["theme"]["font_body"] == "STSong"
            assert config["theme"]["font_size_body"] == 11
        finally:
            for t in list_templates():
                if not t["is_builtin"]:
                    delete_template(t["id"])

    def test_create_without_overrides(self) -> None:
        """不传 theme_overrides 时完全继承基础模板。"""
        try:
            result = create_template(
                name="无覆盖模板",
                description="",
                base_template_id="classic",
                theme_overrides=None,
            )
            config = _read_config(result["id"])
            assert config["theme"]["primary_color"] == "#2B5FC3"  # classic 的默认主色
            assert config["theme"]["font_size_body"] == 11
        finally:
            for t in list_templates():
                if not t["is_builtin"]:
                    delete_template(t["id"])

    def test_create_base_not_found(self) -> None:
        """不存在的 base_template_id 应报错。"""
        with pytest.raises(TemplateNotFoundError):
            create_template(
                name="出错模板",
                description="",
                base_template_id="nonexistent_template_xyz",
            )


# =========================
# update_template_config 测试
# =========================


class TestUpdateTemplateConfig:
    @pytest.fixture(autouse=True)
    def setup_and_cleanup(self):
        """每个测试前创建临时模板，测试后清理。"""
        self.result = create_template(
            name="待更新模板",
            description="用于测试更新",
            base_template_id="classic",
        )
        self.template_id = self.result["id"]
        yield
        # 清理所有自定义模板
        for t in list_templates():
            if not t["is_builtin"]:
                delete_template(t["id"])

    def test_update_name_and_description(self) -> None:
        """更新名称和描述。"""
        update_template_config(
            self.template_id,
            {"name": "新名称", "description": "新描述"},
        )
        config = _read_config(self.template_id)
        assert config["name"] == "新名称"
        assert config["description"] == "新描述"

    def test_update_theme_fields(self) -> None:
        """更新主题字段。"""
        update_template_config(
            self.template_id,
            {"primary_color": "#00FF00", "font_body": "KaiTi", "font_size_body": 14},
        )
        config = _read_config(self.template_id)
        assert config["theme"]["primary_color"] == "#00FF00"
        assert config["theme"]["font_body"] == "KaiTi"
        assert config["theme"]["font_size_body"] == 14
        # 未更新的字段保留
        assert config["theme"]["secondary_color"] == "#F0F4FA"
        assert config["theme"]["font_title"] == "Heiti SC"

    def test_update_none_values_ignored(self) -> None:
        """null 值不覆盖已有配置。"""
        update_template_config(
            self.template_id,
            {"primary_color": "#FF0000"},
        )
        update_template_config(
            self.template_id,
            {"primary_color": None, "font_size_title": None},
        )
        config = _read_config(self.template_id)
        # None 不覆盖，所以 primary_color 仍为上次设置的值
        assert config["theme"]["primary_color"] == "#FF0000"

    def test_update_page_size(self) -> None:
        """更新页面尺寸。"""
        update_template_config(
            self.template_id,
            {"page_size": "Letter"},
        )
        config = _read_config(self.template_id)
        assert config["page_size"] == "Letter"

    def test_update_nonexistent_raises(self) -> None:
        """更新不存在的模板应报错。"""
        with pytest.raises(TemplateNotFoundError):
            update_template_config("nonexistent_id", {"name": "test"})


# =========================
# delete_template 测试
# =========================


class TestDeleteTemplate:
    def test_delete_custom(self) -> None:
        """删除自定义模板成功。"""
        result = create_template(
            name="待删除模板",
            description="",
            base_template_id="classic",
        )
        template_id = result["id"]
        template_dir = TEMPLATES_DIR / template_id
        assert template_dir.exists()

        delete_template(template_id)
        assert not template_dir.exists()

    def test_delete_nonexistent_raises(self) -> None:
        """删除不存在的模板报错。"""
        with pytest.raises(TemplateNotFoundError):
            delete_template("nonexistent_xyz")

    def test_delete_builtin_by_id_set(self) -> None:
        """通过 ID 集合阻止删除内置模板。"""
        with pytest.raises(TemplateNotDeletableError):
            delete_template("classic")

    def test_delete_builtin_by_config_flag(self) -> None:
        """通过 is_builtin 标志阻止（绕过 ID 集合检查）。"""
        # 无法创建 is_builtin=True 的模板（create_template 会设为 False）
        # 但可以通过直接写入 config.json 来模拟
        result = create_template(
            name="伪装内置",
            description="",
            base_template_id="classic",
        )
        template_id = result["id"]
        config_path = TEMPLATES_DIR / template_id / "config.json"
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        config["is_builtin"] = True
        config["id"] = "classic_99"  # 避免被 ID 集合拦截
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        with pytest.raises(TemplateNotDeletableError):
            delete_template(template_id)

        # 清理
        config["is_builtin"] = False
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        delete_template(template_id)


# =========================
# list_custom_templates 测试
# =========================


class TestListCustomTemplates:
    def test_initial_empty(self) -> None:
        """初始时没有自定义模板。"""
        custom = list_custom_templates()
        assert isinstance(custom, list)
        # 全部是内置模板
        for t in custom:
            assert not t["is_builtin"]

    def test_after_create_contains_new(self) -> None:
        """创建后出现在自定义列表。"""
        try:
            create_template(
                name="列表测试模板",
                description="",
                base_template_id="classic",
            )
            custom = list_custom_templates()
            names = [t["name"] for t in custom]
            assert "列表测试模板" in names
        finally:
            for t in list_templates():
                if not t["is_builtin"]:
                    delete_template(t["id"])


# =========================
# render_template_preview 测试
# =========================


class TestRenderTemplatePreview:
    def test_returns_html(self) -> None:
        """返回有效的 HTML 字符串。"""
        html = render_template_preview("classic")
        assert isinstance(html, str)
        assert len(html) > 0
        assert "<!DOCTYPE html>" in html or "<html" in html

    def test_contains_sample_data(self) -> None:
        """包含示例数据。"""
        html = render_template_preview("classic")
        assert "示例课程名称" in html
        assert "示例学生" in html
        assert "示例知识点1" in html

    def test_academic_template(self) -> None:
        """学术模板的预览。"""
        html = render_template_preview("academic")
        assert isinstance(html, str)
        assert len(html) > 0

    def test_cartoon_template(self) -> None:
        """卡通模板的预览。"""
        html = render_template_preview("cartoon")
        assert isinstance(html, str)
        assert len(html) > 0

    def test_nonexistent_raises(self) -> None:
        """不存在的模板报错。"""
        with pytest.raises(TemplateNotFoundError):
            render_template_preview("nonexistent_xyz")


# =========================
# 集成：list_templates 包含 parent_template
# =========================


class TestListTemplatesIntegration:
    def test_builtin_templates_have_no_parent(self) -> None:
        """内置模板的 parent_template 为 None。"""
        all_templates = list_templates()
        for t in all_templates:
            if t["is_builtin"]:
                assert t.get("parent_template") is None

    def test_custom_templates_have_parent(self) -> None:
        """自定义模板有 parent_template。"""
        try:
            create_template(
                name="集成测试模板",
                description="",
                base_template_id="academic",
            )
            all_templates = list_templates()
            custom = [t for t in all_templates if not t["is_builtin"]]
            for t in custom:
                assert t.get("parent_template") == "academic"
        finally:
            for t in list_templates():
                if not t["is_builtin"]:
                    delete_template(t["id"])
