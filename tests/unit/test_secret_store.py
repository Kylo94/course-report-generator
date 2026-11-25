"""API Key 加密存储单测。"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.utils import secret_store

KEY = "sk-test-secret-1234"


@pytest.fixture
def file_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """强制使用本地加密文件后端，避免触发系统钥匙串。"""
    monkeypatch.setattr(secret_store, "_KEY_FILE", tmp_path / ".llm_secret.key")
    monkeypatch.setattr(secret_store, "_ENC_FILE", tmp_path / ".llm_secret.enc")
    monkeypatch.setattr(secret_store, "_keyring_module", lambda: None)


class TestSecretStore:
    def test_save_load_clear(self, file_store: None) -> None:
        assert secret_store.save_secret(KEY) is True
        assert secret_store.load_secret() == KEY
        assert secret_store.secret_hint() == "****1234"

        secret_store.clear_secret()
        assert secret_store.load_secret() == ""
        assert secret_store.secret_hint() == ""

    def test_secret_not_stored_in_plaintext(self, file_store: None) -> None:
        assert secret_store.save_secret(KEY) is True
        enc_path = Path(secret_store._ENC_FILE)
        assert enc_path.exists()
        assert KEY.encode() not in enc_path.read_bytes()

    def test_empty_value_is_ignored(self, file_store: None) -> None:
        assert secret_store.save_secret("   ") is False
        assert secret_store.load_secret() == ""
