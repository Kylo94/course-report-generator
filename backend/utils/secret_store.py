"""敏感配置（LLM API Key）的安全存储。

优先级：系统钥匙串 > 本地加密文件。

- 系统钥匙串：macOS Keychain / Windows 凭据管理器 / Linux SecretService；
- 本地加密文件：使用 cryptography 的 Fernet 对称加密，密钥文件仅当前用户可读。

无论哪种方式，明文都不会写入 data/user_settings.json、日志或 API 响应。
"""
from __future__ import annotations

import os
from pathlib import Path

from backend.paths import get_data_root
from backend.utils.logger import get_logger

log = get_logger(__name__)

SERVICE_NAME = "course-report-generator"
KEY_NAME = "llm_api_key"

_DATA_DIR = get_data_root()
_KEY_FILE = _DATA_DIR / ".llm_secret.key"
_ENC_FILE = _DATA_DIR / ".llm_secret.enc"


def _keyring_module():
    """返回可用的 keyring 模块；不可用时返回 None。"""
    try:
        import keyring
    except Exception as e:
        log.debug("未安装 keyring，使用加密文件存储: %s", e)
        return None
    try:
        backend = keyring.get_keyring()
        if backend is None or "fail" in type(backend).__name__.lower():
            return None
        return keyring
    except Exception as e:
        log.debug("系统钥匙串不可用，使用加密文件存储: %s", e)
        return None


def _fernet():
    """获取 Fernet 实例（首次使用时生成密钥文件）。"""
    from cryptography.fernet import Fernet

    if not _KEY_FILE.exists():
        _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        _KEY_FILE.write_bytes(key)
        _restrict_permissions(_KEY_FILE)
    return Fernet(_KEY_FILE.read_bytes())


def _restrict_permissions(path: Path) -> None:
    """尽力将文件权限限制为仅当前用户可读写（Windows 上忽略）。"""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _clear_file_backup() -> None:
    for path in (_ENC_FILE, _KEY_FILE):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def load_secret() -> str:
    """读取已保存的 API Key；未配置或读取失败时返回空字符串。"""
    kr = _keyring_module()
    if kr is not None:
        try:
            value = kr.get_password(SERVICE_NAME, KEY_NAME)
            if value:
                return value
        except Exception as e:
            log.debug("从系统钥匙串读取 API Key 失败: %s", e)

    if _ENC_FILE.exists():
        try:
            return _fernet().decrypt(_ENC_FILE.read_bytes()).decode("utf-8")
        except Exception as e:
            log.warning("解密本地 API Key 失败（可能密钥文件已丢失）: %s", e)
    return ""


def save_secret(value: str, *, use_keyring: bool = True) -> bool:
    """保存 API Key，成功返回 True。

    use_keyring=False 用于启动迁移等无界面场景，避免钥匙串授权弹窗。
    """
    value = value.strip()
    if not value:
        return False

    kr = _keyring_module() if use_keyring else None
    if kr is not None:
        try:
            kr.set_password(SERVICE_NAME, KEY_NAME, value)
            if kr.get_password(SERVICE_NAME, KEY_NAME) == value:
                _clear_file_backup()
                return True
        except Exception as e:
            log.debug("系统钥匙串保存失败，改用加密文件: %s", e)

    try:
        _ENC_FILE.parent.mkdir(parents=True, exist_ok=True)
        _ENC_FILE.write_bytes(_fernet().encrypt(value.encode("utf-8")))
        _restrict_permissions(_ENC_FILE)
        return True
    except Exception as e:
        log.exception("加密保存 API Key 失败: %s", e)
        return False


def clear_secret() -> None:
    """清除所有位置保存的 API Key。"""
    kr = _keyring_module()
    if kr is not None:
        try:
            kr.delete_password(SERVICE_NAME, KEY_NAME)
        except Exception as e:
            log.debug("从系统钥匙串删除 API Key 失败: %s", e)
    _clear_file_backup()


def secret_hint() -> str:
    """返回用于界面展示的脱敏尾号，例如 ****1234。"""
    value = load_secret()
    if not value:
        return ""
    return "****" + value[-4:] if len(value) > 4 else "****"
