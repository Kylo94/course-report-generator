"""系统设置 API 路由。

允许用户在运行时读取和修改配置项（持久化到 data/user_settings.json）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.config import (
    get_settings,
    get_user_settings_dict,
    update_and_save_user_settings,
)
from backend.utils.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get(
    "",
    response_model=dict,
    summary="获取系统设置",
)
async def get_settings_endpoint() -> dict:
    """返回当前系统设置中用户可修改的部分。"""
    settings = get_settings()
    return get_user_settings_dict(settings)


@router.put(
    "",
    response_model=dict,
    summary="更新系统设置",
)
async def update_settings_endpoint(body: dict) -> dict:
    """更新用户可修改的设置，持久化到 user_settings.json。

    POST body 示例:
    {
        "custom_output_dir": "/path/to/output",
        "default_project_dir": "/path/to/projects",
        "image_dpi": 200,
        "image_quality": 90,
        "image_enabled": true,
        "auto_save_interval_seconds": 60
    }

    只更新传入的字段，未传入的字段保持不变。
    """
    if not body:
        raise HTTPException(status_code=400, detail="请求体不能为空")

    valid_keys = {
        "custom_output_dir",
        "default_project_dir",
        "image_dpi",
        "image_quality",
        "image_enabled",
        "auto_save_interval_seconds",
    }
    unknown = set(body.keys()) - valid_keys
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的设置字段: {', '.join(sorted(unknown))}",
        )

    try:
        result = update_and_save_user_settings(body)
        log.info("系统设置已更新: %s", body)
        return result
    except Exception as e:
        log.exception("保存设置失败: %s", e)
        raise HTTPException(status_code=500, detail=f"保存设置失败: {e}")
