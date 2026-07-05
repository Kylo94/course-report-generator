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

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（兼容 PyInstaller 打包模式）
from backend.paths import get_app_root, get_user_config_dir, _is_frozen
from backend.utils.logger import get_logger

PROJECT_ROOT = get_app_root()
log = get_logger("config")

# 应用版本号（与 build.spec / pyproject.toml 保持一致）
APP_VERSION = "1.0.0"

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


class ImageConvertConfig(BaseModel):
    """PDF→图片转换参数"""
    dpi: int = 150
    quality: int = 95
    enabled: bool = True


class ReportConfig(BaseModel):
    default_template: str = "classic_default"
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

        # 首次运行引导文档（exe 同级目录，方便用户一眼看到）
        _write_first_run_guide(user_cfg.parent)

    return user_cfg


# 首次使用说明模板（UTF-8，{version} / {config_rel} 由调用方填充）
_FIRST_RUN_GUIDE_TEMPLATE = """\
课程报告生成工具 v{version} — 首次使用说明
================================================================

感谢使用！本工具需要配置 AI 服务的 API Key 才能生成报告内容。

────────────────────────────────────────────────────────────────
步骤 1：找到配置文件
────────────────────────────────────────────────────────────────
本目录下应有 {config_rel}/ 文件夹，内含：

  • app.yaml            应用配置（端口、数据库、日志等，一般无需修改）
  • llm.yaml            ⭐ AI 配置（需要你编辑填入 API Key）
  • llm.yaml.example    配置模板（参考用，不要直接编辑）

────────────────────────────────────────────────────────────────
步骤 2：编辑 llm.yaml
────────────────────────────────────────────────────────────────
用记事本、VSCode 或任意文本编辑器打开 llm.yaml，
找到 api_key 这一行：

    api_key: YOUR_API_KEY_HERE

替换成你从 AI 供应商网站申请到的真实 API Key，例如：

    api_key: sk-abc123def456xxxxxxxxxx

────────────────────────────────────────────────────────────────
步骤 3：选择 AI 供应商（可选）
────────────────────────────────────────────────────────────────
llm.yaml 顶部的 provider 字段决定使用哪家 AI 服务：

  ┌───────────┬──────────────────┬──────────────────────────┐
  │ provider  │ 供应商           │ 推荐模型                 │
  ├───────────┼──────────────────┼──────────────────────────┤
  │ deepseek  │ DeepSeek         │ deepseek-chat            │
  │ qwen      │ 通义千问（阿里） │ qwen-plus                │
  │ glm       │ 智谱 AI          │ glm-4                    │
  │ openai    │ OpenAI           │ gpt-4o-mini              │
  │ claude    │ Anthropic Claude │ claude-sonnet-4-6        │
  └───────────┴──────────────────┴──────────────────────────┘

切换供应商 = 改 provider 字段 + 填对应供应商的 api_key + 改 default_model。

────────────────────────────────────────────────────────────────
步骤 4：重启应用
────────────────────────────────────────────────────────────────
保存 llm.yaml 后，关闭本程序再双击启动，新配置生效。
（也可以在前端「设置」页面运行时重载。）

────────────────────────────────────────────────────────────────
常见问题
────────────────────────────────────────────────────────────────
Q：浏览器没有自动弹出？
A：手动访问 http://127.0.0.1:8765

Q：8765 端口被占用？
A：编辑 app.yaml，把 server.port 改成其它端口（如 8766）

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

    # 环境变量覆盖 LLM 配置（最高优先级，支持 CRG_LLM__API_KEY 等）
    for field_name in type(settings.llm).model_fields:
        env_value = _env("LLM", field_name.upper())
        if env_value is not None:
            field = type(settings.llm).model_fields[field_name]
            try:
                coerced = field.annotation(env_value)  # type: ignore[arg-type]
                setattr(settings.llm, field_name, coerced)
            except (ValueError, TypeError):
                pass

    # 加载用户持久化设置（覆盖 YAML 中的值）
    user_data = _load_user_settings()
    if user_data:
        apply_user_settings(settings, user_data)
        log.info("已加载用户设置: %s", user_data)

    return settings


def reset_settings_cache() -> None:
    """重置配置缓存（用于测试）。"""
    get_settings.cache_clear()


# =========================
# 用户可设置配置（持久化到 JSON）
# =========================

def _get_user_settings_path() -> Path:
    """获取用户设置持久化文件路径。"""
    return PROJECT_ROOT / "data" / "user_settings.json"


def _load_user_settings() -> dict[str, Any]:
    """从 user_settings.json 加载用户设置。"""
    path = _get_user_settings_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log.warning("用户设置文件损坏，将使用默认值")
    return {}


def _save_user_settings(data: dict[str, Any]) -> None:
    """保存用户设置到 user_settings.json。"""
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
    if "image_dpi" in user_data:
        settings.image.dpi = user_data["image_dpi"]
    if "image_quality" in user_data:
        settings.image.quality = user_data["image_quality"]
    if "image_enabled" in user_data:
        settings.image.enabled = user_data["image_enabled"]
    if "auto_save_interval_seconds" in user_data:
        settings.draft.auto_save_interval_seconds = user_data["auto_save_interval_seconds"]


def get_user_settings_dict(settings: Settings) -> dict[str, Any]:
    """从 Settings 对象提取可用户设置的字段。"""
    return {
        "custom_output_dir": settings.report.custom_output_dir or "",
        "default_project_dir": settings.report.default_project_dir or "",
        "image_dpi": settings.image.dpi,
        "image_quality": settings.image.quality,
        "image_enabled": settings.image.enabled,
        "auto_save_interval_seconds": settings.draft.auto_save_interval_seconds,
    }


def update_and_save_user_settings(overrides: dict[str, Any]) -> dict[str, Any]:
    """更新运行时设置并持久化到 user_settings.json。"""
    settings = get_settings()
    apply_user_settings(settings, overrides)
    current = get_user_settings_dict(settings)
    _save_user_settings(current)
    return current
