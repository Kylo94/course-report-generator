"""班级相关 Pydantic schemas。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ClassBase(BaseModel):
    """班级基础字段。"""
    name: str = Field(..., min_length=1, max_length=64, description="班级名")
    schedule_day: str | None = Field(None, max_length=16, description="上课日")
    schedule_time: str | None = Field(None, max_length=32, description="上课时间")


class ClassCreate(ClassBase):
    """创建班级请求。"""


class ClassUpdate(BaseModel):
    """更新班级请求。"""
    name: str | None = Field(None, min_length=1, max_length=64)
    schedule_day: str | None = Field(None, max_length=16)
    schedule_time: str | None = Field(None, max_length=32)


class ClassRead(ClassBase):
    """班级详情响应。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    sort_order: int = Field(default=0, description="排序值，越小越靠前")
    student_count: int = Field(default=0, description="学生人数")
    created_at: datetime
    updated_at: datetime


class ClassReorderItem(BaseModel):
    """排序项。"""
    id: int
    sort_order: int


class ClassReorderRequest(BaseModel):
    """批量重排请求。"""
    orders: list[ClassReorderItem]


class ClassList(BaseModel):
    """班级列表响应。"""
    items: list[ClassRead]
    total: int
