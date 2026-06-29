"""模板配置 Pydantic schemas。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ThemeConfig(BaseModel):
    """模板主题配色与字体配置。"""
    primary_color: str = Field(default="#3B7DDD", description="主色调（16 进制）")
    secondary_color: str = Field(default="#F5F5F5", description="辅色调")
    font_title: str = Field(default="Heiti SC", description="标题字体")
    font_body: str = Field(default="STSong", description="正文字体")
    font_size_title: int = Field(default=24, description="标题字号")
    font_size_body: int = Field(default=11, description="正文字号")


class TemplateConfig(BaseModel):
    """模板元信息。"""
    id: str = Field(..., description="模板唯一标识")
    name: str = Field(..., description="模板名称（中文）")
    version: str = Field(default="1.0", description="模板版本")
    is_builtin: bool = Field(default=True, description="是否内置模板")
    thumbnail: str = Field(default="", description="预览缩略图路径")
    description: str = Field(default="", description="模板描述")
    theme: ThemeConfig = Field(default_factory=ThemeConfig, description="主题配置")
    page_size: str = Field(default="A4", description="默认页面尺寸")


class TemplateListItem(BaseModel):
    """模板列表项（不含主题细节）。"""
    id: str
    name: str
    version: str
    is_builtin: bool
    thumbnail: str
    description: str
    page_size: str
