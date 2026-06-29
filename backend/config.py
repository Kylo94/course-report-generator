"""
应用配置模块

使用 pydantic-settings 加载 config/app.yaml 和环境变量。

约定：
- 应用层配置（app、database、server、report、draft、logo）来自 config/app.yaml
- LLM 配置（api_key 等敏感信息）来自 config/llm.yaml，不入 git
- 环境变量以 CRG_ 开头可覆盖任意字段（最高优先级）

优先级：环境变量 > YAML > 默认值
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（兼容 PyInstaller 打包模式）
from backend.paths import get_app_root, get_user_config_dir, _is_frozen

PROJECT_ROOT = get_app_root()

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
    version: str = "0.1.0"
    debug: bool = True
    log_level: str = "INFO"


class DatabaseConfig(BaseModel):
    url: str = "sqlite+aiosqlite:///./data/app.db"
    echo: bool = False


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    reload: bool = True


class ReportConfig(BaseModel):
    default_template: str = "classic_default"
    output_dir: str = "./data/reports"
    screenshot_dir: str = "./data/screenshots"
    asset_dir: str = "./data/assets"
    custom_output_dir: str = ""


class DraftConfig(BaseModel):
    auto_save_interval_seconds: int = 30


class LogoConfig(BaseModel):
    enabled: bool = False
    position: str = "top-right"
    size: str = "medium"
    show_on_all_pages: bool = True


class LLMConfig(BaseModel):
    """LLM 供应商配置（从 llm.yaml 单独加载）。"""
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
        """重新加载 LLM 配置（用于运行时切换供应商）。"""
        # 优先从用户配置目录（打包模式下 exe 同级）加载
        llm_path = get_user_config_dir() / "llm.yaml"
        if not llm_path.exists():
            llm_path = PROJECT_ROOT / "config" / "llm.yaml"
        if llm_path.exists():
            with llm_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self.llm = LLMConfig(**data)


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

        # 生成 llm.yaml（如果还没有）
        llm_yaml = user_cfg / "llm.yaml"
        if not llm_yaml.exists():
            example = user_cfg / "llm.yaml.example"
            if example.exists():
                llm_yaml.write_bytes(example.read_bytes())
                log.info("已生成 %s（请编辑 API Key 后重启）", llm_yaml)
            else:
                # 兜底：生成基础模板
                _write_default_llm_yaml(llm_yaml)
                log.info("已生成默认 %s（请编辑 API Key 后重启）", llm_yaml)
    return user_cfg


def _write_default_llm_yaml(path: Path) -> None:
    content = """# LLM 供应商配置
# 首次使用请在此填入 API Key，然后重启应用

provider: deepseek
api_key: YOUR_API_KEY_HERE
default_model: deepseek-chat
timeout: 60
max_retries: 2
"""
    path.write_text(content, encoding="utf-8")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    获取全局配置单例。

    加载顺序：
      1. config/app.yaml（应用层，打包模式下从 exe 同级 config/ 目录读取）
      2. config/llm.yaml（LLM 供应商）
      3. 环境变量 CRG_* 覆盖
    """
    # 打包模式下确保 exe 同级有可编辑的配置文件
    cfg_dir = _init_user_config()

    app_yaml = cfg_dir / "app.yaml"
    if not app_yaml.exists():
        app_yaml = PROJECT_ROOT / "config" / "app.yaml"
    settings = Settings.from_yaml(app_yaml)

    # 单独加载 llm.yaml（如果存在）
    llm_yaml = cfg_dir / "llm.yaml"
    if not llm_yaml.exists():
        llm_yaml = PROJECT_ROOT / "config" / "llm.yaml"
    if llm_yaml.exists():
        with llm_yaml.open("r", encoding="utf-8") as f:
            llm_data = yaml.safe_load(f) or {}
        settings.llm = LLMConfig(**llm_data)

    return settings


def reset_settings_cache() -> None:
    """重置配置缓存（用于测试）。"""
    get_settings.cache_clear()
