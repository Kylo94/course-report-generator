"""测试配置模块。"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.config import (
    LLMConfig,
    LogoConfig,
    Settings,
    get_settings,
    reset_settings_cache,
)


class TestSettingsDefaults:
    """默认值测试。"""

    def test_default_app_meta(self) -> None:
        s = Settings()
        assert s.app.name == "课程报告生成工具"
        assert s.app.version == "0.1.0"

    def test_default_logo(self) -> None:
        s = Settings()
        assert s.logo.enabled is False
        assert s.logo.position == "top-right"
        assert s.logo.size == "medium"

    def test_default_draft_interval(self) -> None:
        s = Settings()
        assert s.draft.auto_save_interval_seconds == 30

    def test_default_llm_provider(self) -> None:
        s = Settings()
        assert s.llm.provider == "deepseek"
        assert s.llm.timeout == 60
        assert s.llm.max_retries == 2
        assert "evaluation" in s.llm.temperature
        assert s.llm.temperature["evaluation"] == 0.9


class TestSettingsFromYaml:
    """从 YAML 加载配置。"""

    def test_load_partial_yaml(self, tmp_dir: Path) -> None:
        yaml_path = tmp_dir / "test.yaml"
        yaml_path.write_text(
            """
app:
  name: 测试
  version: 9.9.9
logo:
  enabled: true
  position: bottom-left
""",
            encoding="utf-8",
        )
        s = Settings.from_yaml(yaml_path)
        assert s.app.name == "测试"
        assert s.app.version == "9.9.9"
        assert s.logo.enabled is True
        assert s.logo.position == "bottom-left"
        # 未指定的字段保持默认
        assert s.logo.size == "medium"

    def test_load_empty_yaml(self, tmp_dir: Path) -> None:
        yaml_path = tmp_dir / "empty.yaml"
        yaml_path.write_text("", encoding="utf-8")
        s = Settings.from_yaml(yaml_path)
        # 全部使用默认值
        assert s.app.name == "课程报告生成工具"

    def test_load_missing_file(self, tmp_dir: Path) -> None:
        s = Settings.from_yaml(tmp_dir / "nonexistent.yaml")
        # 文件不存在时返回默认值
        assert s.app.version == "0.1.0"


class TestGetSettingsSingleton:
    """get_settings 单例与缓存。"""

    def test_singleton_returns_same_instance(self) -> None:
        reset_settings_cache()
        a = get_settings()
        b = get_settings()
        assert a is b

    def test_reset_cache(self) -> None:
        reset_settings_cache()
        a = get_settings()
        reset_settings_cache()
        b = get_settings()
        # 重置后应该是新对象
        assert a is not b


class TestEnvOverride:
    """环境变量覆盖。"""

    def test_env_prefix_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CRG_APP__NAME", "环境变量覆盖名")
        reset_settings_cache()
        s = get_settings()
        assert s.app.name == "环境变量覆盖名"
        reset_settings_cache()


class TestLLMConfig:
    """LLMConfig 单独测试。"""

    def test_default_temperature_values(self) -> None:
        c = LLMConfig()
        assert 0.0 <= c.temperature["evaluation"] <= 1.0
        assert c.temperature["knowledge_points"] <= 0.5

    def test_logo_config_validation(self) -> None:
        c = LogoConfig()
        assert c.size in ("small", "medium", "large")
