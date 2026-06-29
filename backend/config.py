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

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

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
    def from_yaml(cls, yaml_path: Path | str) -> "Settings":
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
        llm_path = PROJECT_ROOT / "config" / "llm.yaml"
        if llm_path.exists():
            with llm_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self.llm = LLMConfig(**data)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    获取全局配置单例。

    加载顺序：
      1. config/app.yaml（应用层）
      2. config/llm.yaml（LLM 供应商）
      3. 环境变量 CRG_* 覆盖
    """
    app_yaml = PROJECT_ROOT / "config" / "app.yaml"
    settings = Settings.from_yaml(app_yaml)

    # 单独加载 llm.yaml（如果存在）
    llm_yaml = PROJECT_ROOT / "config" / "llm.yaml"
    if llm_yaml.exists():
        with llm_yaml.open("r", encoding="utf-8") as f:
            llm_data = yaml.safe_load(f) or {}
        settings.llm = LLMConfig(**llm_data)

    return settings


def reset_settings_cache() -> None:
    """重置配置缓存（用于测试）。"""
    get_settings.cache_clear()
