"""系统设置 API 路由。

用户在设置页读取和修改配置项：路径、图片转换、编辑器、AI 服务、默认模板。
数据持久化到 data/user_settings.json；API Key 由 secret_store 加密保存，
接口只返回配置状态与脱敏尾号。
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.config import (
    LLMConfig,
    get_settings,
    get_user_settings_dict,
    update_and_save_user_settings,
)
from backend.utils.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

Provider = Literal["deepseek", "minimax", "qwen", "glm", "openai", "claude"]


class SettingsUpdate(BaseModel):
    """设置更新请求体；未传入的字段保持不变。"""

    model_config = ConfigDict(extra="forbid")

    custom_output_dir: str | None = None
    default_project_dir: str | None = None
    image_dpi: int | None = Field(default=None, ge=10, le=600)
    image_quality: int | None = Field(default=None, ge=1, le=100)
    image_enabled: bool | None = None
    auto_save_interval_seconds: int | None = Field(default=None, ge=5, le=600)
    default_template_id: str | None = Field(default=None, max_length=100)

    llm_provider: Provider | None = None
    llm_api_key: str | None = Field(default=None, max_length=500)
    llm_base_url: str | None = Field(default=None, max_length=300)
    llm_default_model: str | None = Field(default=None, max_length=100)
    llm_max_tokens: int | None = Field(default=None, ge=1, le=1_000_000)
    llm_timeout: int | None = Field(default=None, ge=1, le=600)
    llm_max_retries: int | None = Field(default=None, ge=0, le=10)
    llm_temperature: dict[str, float] | None = None

    @field_validator("llm_temperature")
    @classmethod
    def _check_temperature(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        if value is None:
            return None
        allowed = set(LLMConfig().temperature)
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"不支持的温度字段: {', '.join(sorted(unknown))}")
        for key, temperature in value.items():
            if not 0.0 <= temperature <= 2.0:
                raise ValueError(f"{key} 的温度必须在 0~2 之间")
        return value


@router.get(
    "",
    response_model=dict,
    summary="获取系统设置",
)
async def get_settings_endpoint() -> dict:
    """返回当前用户设置；API Key 只返回配置状态与脱敏尾号。"""
    return get_user_settings_dict(get_settings())


@router.put(
    "",
    response_model=dict,
    summary="更新系统设置",
)
async def update_settings_endpoint(body: SettingsUpdate) -> dict:
    """更新用户可修改的设置；只更新请求体中出现的字段。

    llm_api_key 约定：
    - 不传或传空字符串：保持已有 Key 不变；
    - 传字符串：覆盖保存；
    - 传 null：清除已保存的 Key。
    """
    try:
        overrides = body.model_dump(exclude_unset=True)
        result = update_and_save_user_settings(overrides)
        # 只记录字段名，避免把 API Key 写进日志。
        log.info("系统设置已更新: %s", sorted(overrides))
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        log.exception("保存设置失败: %s", e)
        raise HTTPException(status_code=500, detail=f"保存设置失败: {e}") from e
