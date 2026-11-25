"""测试配置模块。"""
from __future__ import annotations

from pathlib import Path

import pytest

import backend.config as config_module
from backend.config import (
    APP_VERSION,
    LLMConfig,
    LogoConfig,
    Settings,
    get_settings,
    reset_settings_cache,
)
from backend.utils import secret_store


class TestSettingsDefaults:
    """默认值测试。"""

    def test_default_app_meta(self) -> None:
        s = Settings()
        assert s.app.name == "课程报告生成工具"
        assert s.app.version == APP_VERSION

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
        assert s.app.version == APP_VERSION


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


class TestUserSettings:
    def test_collect_data_never_contains_api_key(self) -> None:
        s = Settings()
        s.llm.api_key = "sk-should-not-be-saved"
        s.report.default_template = "academic"

        data = config_module._collect_user_data(s)

        assert data["default_template_id"] == "academic"
        assert "llm_api_key" not in data
        assert "sk-should-not-be-saved" not in str(data)

    def test_apply_llm_and_template_settings(self) -> None:
        s = Settings()
        config_module.apply_user_settings(s, {
            "default_template_id": "cartoon",
            "llm_provider": "openai",
            "llm_default_model": "gpt-4o-mini",
            "llm_temperature": {"evaluation": 0.7},
        })
        assert s.report.default_template == "cartoon"
        assert s.llm.provider == "openai"
        assert s.llm.default_model == "gpt-4o-mini"
        assert s.llm.temperature["evaluation"] == 0.7

    def test_update_saves_api_key_encrypted(
        self, monkeypatch: pytest.MonkeyPatch, tmp_dir: Path
    ) -> None:
        settings = Settings()
        settings_path = tmp_dir / "user_settings.json"
        monkeypatch.setattr(config_module, "get_settings", lambda: settings)
        monkeypatch.setattr(config_module, "_get_user_settings_path", lambda: settings_path)
        monkeypatch.setattr(secret_store, "save_secret", lambda value, **kwargs: True)

        result = config_module.update_and_save_user_settings({
            "llm_api_key": "sk-secret-from-page",
            "default_template_id": "academic",
        })

        assert settings.llm.api_key == "sk-secret-from-page"
        assert result["api_key_configured"] is True
        stored = settings_path.read_text(encoding="utf-8")
        assert "sk-secret-from-page" not in stored
        assert "academic" in stored

    def test_migrate_legacy_llm_yaml_once(
        self, monkeypatch: pytest.MonkeyPatch, tmp_dir: Path
    ) -> None:
        legacy = tmp_dir / "llm.yaml"
        legacy.write_text(
            "provider: openai\napi_key: sk-legacy-key\ndefault_model: gpt-4o-mini\n",
            encoding="utf-8",
        )
        saved_keys: list[str] = []
        monkeypatch.setattr(config_module, "_get_user_settings_path", lambda: tmp_dir / "user_settings.json")
        monkeypatch.setattr(config_module, "_legacy_llm_path", lambda cfg_dir: legacy)
        monkeypatch.setattr(
            secret_store,
            "save_secret",
            lambda value, **kwargs: saved_keys.append(value) or True,
        )

        data = config_module._migrate_legacy_llm_yaml(tmp_dir, {})

        assert data["llm_provider"] == "openai"
        assert data["llm_default_model"] == "gpt-4o-mini"
        assert data["llm_migrated"] is True
        assert saved_keys == ["sk-legacy-key"]
        assert "sk-legacy-key" not in legacy.read_text(encoding="utf-8")
        assert "sk-legacy-key" not in (tmp_dir / "user_settings.json").read_text(encoding="utf-8")

        # 再次调用不会重复迁移
        assert config_module._migrate_legacy_llm_yaml(tmp_dir, data) is data
