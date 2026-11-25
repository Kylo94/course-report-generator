"""
应用配置模块

使用 pydantic-settings 加载 config/app.yaml 和环境变量。

约定：
- 应用层配置（app、database、server、report、draft、logo）来自 config/app.yaml
- 用户设置（含 LLM 配置、默认模板）来自 data/user_settings.json，由设置页面维护
- API Key 由 backend.utils.secret_store 加密保存，不写入 user_settings.json
- 旧 config/llm.yaml 仅在首次升级时做一次性迁移，不再作为运行时配置源
- 环境变量以 CRG_ 开头可覆盖任意字段（最高优先级）

优先级：环境变量 > 用户设置 > YAML > 默认值
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（兼容 PyInstaller 打包模式）
from backend.paths import (
    _is_frozen,
    get_app_root,
    get_data_root,
    get_user_config_dir,
)
from backend.utils import secret_store
from backend.utils.logger import get_logger
from backend.version import __version__ as APP_VERSION

PROJECT_ROOT = get_app_root()
log = get_logger("config")

# 应用版本号唯一来源：backend/version.py

# 环境变量前缀
ENV_PREFIX = "CRG_"
ENV_DELIM = "__"


def _env(section: str, key: str) -> str | None:
    """读取形如 CRG_SECTION__KEY 的环境变量。"""
    return os.getenv(f"{ENV_PREFIX}{section}{ENV_DELIM}{key}")


# =========================
# 子模型
# =========================
class AppMeta(BaseModel):
    name: str = "课程报告生成工具"
    version: str = APP_VERSION
    debug: bool = True
    log_level: str = "INFO"


class DatabaseConfig(BaseModel):
    url: str = "sqlite+aiosqlite:///./data/app.db"
    echo: bool = False


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    reload: bool = True


class ImageConvertConfig(BaseModel):
    """PDF→图片转换参数"""
    dpi: int = 150
    quality: int = 95
    enabled: bool = True


class ReportConfig(BaseModel):
    default_template: str = "classic"
    output_dir: str = "./data/reports"
    screenshot_dir: str = "./data/screenshots"
    asset_dir: str = "./data/assets"
    custom_output_dir: str = ""
    default_project_dir: str = ""


class DraftConfig(BaseModel):
    auto_save_interval_seconds: int = 30


class LogoConfig(BaseModel):
    enabled: bool = False
    position: str = "top-right"
    size: str = "medium"
    show_on_all_pages: bool = True


class LLMConfig(BaseModel):
    """LLM 供应商配置（由设置页面维护，持久化到 user_settings.json）。"""
    provider: str = "deepseek"
    api_key: str = ""
    base_url: str | None = None
    default_model: str = "deepseek-chat"
    max_tokens: int = 8192
    timeout: int = 60
    max_retries: int = 2
    temperature: dict[str, float] = Field(default_factory=lambda: {
        "knowledge_points": 0.3,
        "content_summary": 0.5,
        "homework": 0.5,
        "vocabulary": 0.5,
        "ability_improvement": 0.5,
        "evaluation": 0.9,
    })


# =========================
# 主配置
# =========================
class Settings(BaseSettings):
    """全局应用配置。"""
    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_nested_delimiter=ENV_DELIM,
        extra="ignore",
    )

    app: AppMeta = Field(default_factory=AppMeta)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
    draft: DraftConfig = Field(default_factory=DraftConfig)
    logo: LogoConfig = Field(default_factory=LogoConfig)
    image: ImageConvertConfig = Field(default_factory=ImageConvertConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)

    @classmethod
    def from_yaml(cls, yaml_path: Path | str) -> Settings:
        """
        从 YAML 文件加载配置。

        优先级：环境变量 (CRG_SECTION__KEY) > YAML > 默认值

        实现说明：pydantic-settings 对嵌套 BaseModel 子类的 env 解析
        在某些版本下不够稳定，因此采用"读取 env 显式覆盖"的方式。
        """
        path = Path(yaml_path)
        if not path.exists():
            return cls()

        with path.open("r", encoding="utf-8") as f:
            yaml_data: dict[str, Any] = yaml.safe_load(f) or {}

        # 1. 用 YAML 数据初始化（作为 base）
        instance = cls(**yaml_data)

        # 2. 用 env 覆盖（最高优先级）
        for section in ("app", "database", "server", "report", "draft", "logo"):
            current = getattr(instance, section, None)
            if current is None:
                continue
            for field_name in type(current).model_fields:
                env_value = _env(section.upper(), field_name.upper())
                if env_value is not None:
                    # 转换类型
                    field = type(current).model_fields[field_name]
                    try:
                        coerced = field.annotation(env_value)  # type: ignore[arg-type]
                        setattr(current, field_name, coerced)
                    except (ValueError, TypeError):
                        # 转换失败保留 yaml 值
                        pass
        return instance

    def reload_llm(self) -> None:
        """从用户设置重新加载 LLM 配置（设置页面保存后调用）。"""
        apply_user_settings(self, _load_user_settings())
        env_key = _env("LLM", "API_KEY")
        self.llm.api_key = env_key if env_key is not None else secret_store.load_secret()
        _apply_env_overrides(self)


def _init_user_config() -> Path:
    """打包模式下，将默认配置从 bundled 目录复制到 exe 同级的 config/ 目录。

    返回用户配置目录。
    """
    user_cfg = get_user_config_dir()
    if not _is_frozen():
        return user_cfg  # 开发模式直接用项目目录

    # 首次运行：复制默认配置到 exe 同级
    if not user_cfg.exists():
        user_cfg.mkdir(parents=True, exist_ok=True)
        bundled = PROJECT_ROOT / "config"
        for fname in ("app.yaml", "llm.yaml.example"):
            src = bundled / fname
            if src.exists():
                dst = user_cfg / fname
                if not dst.exists():
                    dst.write_bytes(src.read_bytes())
                    log.info("已复制默认配置到 %s", dst)

        # AI 配置与 API Key 统一在「设置」页面维护，不再生成 llm.yaml。
        # 首次运行引导文档（exe 同级目录，方便用户一眼看到）
        _write_first_run_guide(user_cfg.parent)

    return user_cfg


# 首次使用说明模板（UTF-8，{version} / {config_rel} 由调用方填充）
_FIRST_RUN_GUIDE_TEMPLATE = """\
课程报告生成工具 v{version} — 首次使用说明
================================================================

感谢使用！本工具需要配置 AI 服务的 API Key 才能生成报告内容。

────────────────────────────────────────────────────────────────
步骤 1：打开设置页面
────────────────────────────────────────────────────────────────
启动程序后，访问 http://127.0.0.1:8765 ，进入左侧「设置」页面。

────────────────────────────────────────────────────────────────
步骤 2：配置 AI 服务
────────────────────────────────────────────────────────────────
在「AI 服务」卡片中：

  1. 选择供应商（DeepSeek / 通义千问 / 智谱 GLM / OpenAI / Claude / MiniMax）
  2. 填入该供应商的 API Key
  3. 确认或填写模型名称（可选：自定义 base_url）
  4. 点击「测试连接」验证，再点击「保存设置」

API Key 会加密保存在系统钥匙串或本地加密文件中，不会明文写入配置文件。
设置即时生效，无需重启。

────────────────────────────────────────────────────────────────
步骤 3：选择默认模板（可选）
────────────────────────────────────────────────────────────────
在「报告」卡片的「默认模板」下拉框中选择，保存后批量生成会默认使用它。
也可以在「模板管理」页面点「设为默认」。

────────────────────────────────────────────────────────────────
常见问题
────────────────────────────────────────────────────────────────
Q：浏览器没有自动弹出？
A：手动访问 http://127.0.0.1:8765

Q：8765 端口被占用？
A：编辑 {config_rel}/app.yaml，把 server.port 改成其它端口（如 8766）

Q：日志在哪？
A：logs/ 目录下的 .log 文件

Q：报告、截图存在哪？
A：data/ 目录（reports / screenshots / assets 子目录）

Q：怎么彻底卸载？
A：删除整个程序目录即可，无注册表项、无系统残留

────────────────────────────────────────────────────────────────
技术支持：参考 README.md 或提交 Issue
================================================================
"""


def _write_first_run_guide(exe_dir: Path) -> None:
    """在 exe 同级目录生成首次使用说明（仅打包模式、仅首次）。"""
    target = exe_dir / "首次使用说明.txt"
    if target.exists():
        return  # 已生成过就不覆盖，保留用户可能的手改
    try:
        content = _FIRST_RUN_GUIDE_TEMPLATE.format(
            version=APP_VERSION,
            config_rel="config",
        )
        target.write_text(content, encoding="utf-8")
        log.info("已生成首次使用说明: %s", target)
    except Exception as e:
        log.warning("生成首次使用说明失败: %s", e)


def _coerce_env_value(raw: str, annotation: Any) -> Any:
    """将环境变量字符串转换为字段类型。"""
    if annotation is bool:
        return raw.lower() in ("1", "true", "yes", "on")
    if annotation is int:
        return int(raw)
    if annotation is float:
        return float(raw)
    if str(annotation).startswith("dict"):
        return json.loads(raw)
    return raw


def _apply_env_overrides(settings: Settings) -> None:
    """用 CRG_SECTION__KEY 环境变量覆盖所有配置（最高优先级）。"""
    sections = ("app", "database", "server", "report", "draft", "logo", "image", "llm")
    for section in sections:
        current = getattr(settings, section, None)
        if current is None:
            continue
        for field_name, field in type(current).model_fields.items():
            env_value = _env(section.upper(), field_name.upper())
            if env_value is None:
                continue
            try:
                setattr(current, field_name, _coerce_env_value(env_value, field.annotation))
            except (ValueError, TypeError, json.JSONDecodeError):
                log.warning("环境变量 CRG_%s__%s 格式无效，已忽略", section.upper(), field_name.upper())


def _legacy_llm_path(cfg_dir: Path) -> Path:
    path = cfg_dir / "llm.yaml"
    if path.exists():
        return path
    return PROJECT_ROOT / "config" / "llm.yaml"


def _migrate_legacy_llm_yaml(cfg_dir: Path, user_data: dict[str, Any]) -> dict[str, Any]:
    """首次升级时从 llm.yaml 导入 AI 配置，之后该文件不再生效。"""
    if user_data.get("llm_migrated") or "llm_provider" in user_data:
        return user_data

    path = _legacy_llm_path(cfg_dir)
    if not path.exists():
        return user_data
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        log.warning("读取旧 llm.yaml 失败，已跳过迁移: %s", e)
        return user_data
    if not isinstance(data, dict):
        return user_data

    for key in (
        "provider", "base_url", "default_model", "max_tokens",
        "timeout", "max_retries", "temperature",
    ):
        if key in data:
            user_data[f"llm_{key}"] = data[key]

    api_key = str(data.get("api_key") or "").strip()
    if api_key and not api_key.upper().startswith("YOUR_") and not api_key.startswith("sk-your"):
        if secret_store.save_secret(api_key, use_keyring=False):
            log.info("已从 llm.yaml 迁移 API Key 到本地加密存储")

    user_data["llm_migrated"] = True
    _save_user_settings(user_data)
    # 迁移后清除旧文件中的明文 Key，避免继续以明文散落。
    try:
        path.write_text(
            "# 此文件中的 AI 配置已迁移到前端「设置」页面，本文件不再生效。\n",
            encoding="utf-8",
        )
    except OSError as e:
        log.warning("清理旧 llm.yaml 失败: %s", e)
    log.info("已从 llm.yaml 一次性迁移 AI 配置")
    return user_data


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    获取全局配置单例。

    加载顺序（优先级由低到高）：
      1. config/app.yaml
      2. data/user_settings.json（设置页面维护；首次升级时从 llm.yaml 迁移）
      3. 环境变量 CRG_*
    """
    cfg_dir = _init_user_config()

    app_yaml = cfg_dir / "app.yaml"
    if not app_yaml.exists():
        app_yaml = PROJECT_ROOT / "config" / "app.yaml"
    settings = Settings.from_yaml(app_yaml)

    user_data = _load_user_settings()
    user_data = _migrate_legacy_llm_yaml(cfg_dir, user_data)
    if user_data:
        apply_user_settings(settings, user_data)
        settings.llm.api_key = secret_store.load_secret()

    # 环境变量优先级最高，放在最后覆盖。
    _apply_env_overrides(settings)
    return settings


def reset_settings_cache() -> None:
    """重置配置缓存（用于测试）。"""
    get_settings.cache_clear()


# =========================
# 用户可设置配置（持久化到 JSON）
# =========================

LLM_USER_FIELDS: dict[str, str] = {
    "llm_provider": "provider",
    "llm_base_url": "base_url",
    "llm_default_model": "default_model",
    "llm_max_tokens": "max_tokens",
    "llm_timeout": "timeout",
    "llm_max_retries": "max_retries",
}


def _get_user_settings_path() -> Path:
    """获取用户设置持久化文件路径（打包模式使用 exe 同级 data/）。"""
    return get_data_root() / "user_settings.json"


def _load_user_settings() -> dict[str, Any]:
    """从 user_settings.json 加载用户设置。"""
    path = _get_user_settings_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            log.warning("用户设置文件损坏，将使用默认值")
    return {}


def _save_user_settings(data: dict[str, Any]) -> None:
    """保存用户设置到 user_settings.json（不含明文 API Key）。"""
    path = _get_user_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def apply_user_settings(settings: Settings, user_data: dict[str, Any]) -> None:
    """将 user_settings.json 中的值应用到 Settings 对象。"""
    if "custom_output_dir" in user_data:
        settings.report.custom_output_dir = user_data["custom_output_dir"]
    if "default_project_dir" in user_data:
        settings.report.default_project_dir = user_data["default_project_dir"]
    if "default_template_id" in user_data:
        settings.report.default_template = user_data["default_template_id"]
    if "image_dpi" in user_data:
        settings.image.dpi = user_data["image_dpi"]
    if "image_quality" in user_data:
        settings.image.quality = user_data["image_quality"]
    if "image_enabled" in user_data:
        settings.image.enabled = user_data["image_enabled"]
    if "auto_save_interval_seconds" in user_data:
        settings.draft.auto_save_interval_seconds = user_data["auto_save_interval_seconds"]

    for key, attr in LLM_USER_FIELDS.items():
        if key in user_data:
            setattr(settings.llm, attr, user_data[key])
    temperature = user_data.get("llm_temperature")
    if isinstance(temperature, dict):
        settings.llm.temperature = {**settings.llm.temperature, **temperature}


def _collect_user_data(settings: Settings) -> dict[str, Any]:
    """收集可持久化的用户设置（绝不包含明文 API Key）。"""
    return {
        "custom_output_dir": settings.report.custom_output_dir or "",
        "default_project_dir": settings.report.default_project_dir or "",
        "default_template_id": settings.report.default_template or "",
        "image_dpi": settings.image.dpi,
        "image_quality": settings.image.quality,
        "image_enabled": settings.image.enabled,
        "auto_save_interval_seconds": settings.draft.auto_save_interval_seconds,
        "llm_provider": settings.llm.provider,
        "llm_base_url": settings.llm.base_url or "",
        "llm_default_model": settings.llm.default_model,
        "llm_max_tokens": settings.llm.max_tokens,
        "llm_timeout": settings.llm.timeout,
        "llm_max_retries": settings.llm.max_retries,
        "llm_temperature": dict(settings.llm.temperature),
    }


def _mask_key(value: str) -> str:
    return "****" + value[-4:] if len(value) > 4 else "****" if value else ""


def get_user_settings_dict(settings: Settings) -> dict[str, Any]:
    """返回前端设置页所需的配置（API Key 只给状态与脱敏尾号）。"""
    data = _collect_user_data(settings)
    effective_key = settings.llm.api_key or secret_store.load_secret()
    data["api_key_configured"] = bool(effective_key)
    data["api_key_hint"] = _mask_key(effective_key)
    return data


def update_and_save_user_settings(overrides: dict[str, Any]) -> dict[str, Any]:
    """更新运行时设置并持久化到 user_settings.json。"""
    settings = get_settings()
    overrides = dict(overrides)

    if "llm_api_key" in overrides:
        api_key = overrides.pop("llm_api_key")
        if api_key is None:
            secret_store.clear_secret()
            settings.llm.api_key = ""
        elif isinstance(api_key, str) and api_key.strip():
            api_key = api_key.strip()
            secret_store.save_secret(api_key)
            settings.llm.api_key = api_key
        # 空字符串表示保持不变

    apply_user_settings(settings, overrides)
    stored = _load_user_settings()
    stored.update(_collect_user_data(settings))
    _save_user_settings(stored)
    return get_user_settings_dict(settings)
