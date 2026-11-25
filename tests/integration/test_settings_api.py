"""系统设置 API 集成测试（AI 配置脱敏 + 默认模板持久化）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend import config
from backend.config import reset_settings_cache
from backend.utils import secret_store


@pytest.fixture(autouse=True)
def isolated_user_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """隔离用户设置与密钥存储，避免污染真实 data 目录。"""
    monkeypatch.setattr(config, "_get_user_settings_path", lambda: tmp_path / "user_settings.json")
    monkeypatch.setattr(config, "_legacy_llm_path", lambda cfg_dir: tmp_path / "llm.yaml")
    monkeypatch.setattr(secret_store, "_KEY_FILE", tmp_path / ".llm_secret.key")
    monkeypatch.setattr(secret_store, "_ENC_FILE", tmp_path / ".llm_secret.enc")
    monkeypatch.setattr(secret_store, "_keyring_module", lambda: None)
    reset_settings_cache()
    yield
    reset_settings_cache()


class TestSettingsAPI:
    async def test_get_settings_masks_api_key(self, api_client) -> None:
        resp = await api_client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "api_key_configured" in data
        assert "api_key_hint" in data
        assert "api_key" not in data
        assert "llm_api_key" not in data

    async def test_update_persists_settings_without_plaintext_key(
        self, api_client, tmp_path: Path
    ) -> None:
        key = "sk-integration-secret"

        resp = await api_client.put("/api/settings", json={
            "llm_api_key": key,
            "llm_provider": "openai",
            "llm_default_model": "gpt-4o-mini",
            "llm_timeout": 30,
            "default_template_id": "academic",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["llm_provider"] == "openai"
        assert data["llm_timeout"] == 30
        assert data["default_template_id"] == "academic"
        assert data["api_key_configured"] is True
        assert key not in str(data)

        stored = (tmp_path / "user_settings.json").read_text(encoding="utf-8")
        assert key not in stored
        assert "academic" in stored

        follow_up = await api_client.get("/api/settings")
        assert follow_up.json()["default_template_id"] == "academic"
        assert follow_up.json()["api_key_hint"].startswith("****")

    async def test_clear_api_key(self, api_client) -> None:
        await api_client.put("/api/settings", json={"llm_api_key": "sk-clear-me"})
        resp = await api_client.put("/api/settings", json={"llm_api_key": None})
        assert resp.status_code == 200
        assert resp.json()["api_key_configured"] is False

    async def test_reject_invalid_payload(self, api_client) -> None:
        unknown = await api_client.put("/api/settings", json={"unknown_field": 1})
        assert unknown.status_code == 422

        provider = await api_client.put("/api/settings", json={"llm_provider": "bad"})
        assert provider.status_code == 422

        timeout = await api_client.put("/api/settings", json={"llm_timeout": 0})
        assert timeout.status_code == 422

        temperature = await api_client.put(
            "/api/settings", json={"llm_temperature": {"unknown_step": 0.5}}
        )
        assert temperature.status_code == 422
