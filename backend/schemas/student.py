"""学生相关 Pydantic schemas。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StudentBase(BaseModel):
    """学生基础字段。"""
    name: str = Field(..., min_length=1, max_length=64, description="姓名")
    age: int | None = Field(None, ge=3, le=99, description="年龄")
    gender: str | None = Field(None, max_length=8, description="性别")
    grade: str | None = Field(None, max_length=32, description="年级")
    base_level: str = Field(
        default="入门", pattern="^(入门|初级|中级)$", description="基础水平"
    )
    characteristics: list[str] = Field(
        default_factory=list, description="性格特点列表"
    )
    parent_contact: str | None = Field(None, max_length=64, description="家长联系方式")
    note: str | None = Field(None, description="备注")
    class_id: int | None = Field(None, description="所属班级 ID")


class StudentCreate(StudentBase):
    """创建学生请求。"""


class StudentUpdate(BaseModel):
    """更新学生请求（所有字段可选）。"""
    name: str | None = Field(None, min_length=1, max_length=64)
    age: int | None = Field(None, ge=3, le=99)
    gender: str | None = Field(None, max_length=8)
    grade: str | None = Field(None, max_length=32)
    base_level: str | None = Field(None, pattern="^(入门|初级|中级)$")
    characteristics: list[str] | None = None
    parent_contact: str | None = Field(None, max_length=64)
    note: str | None = None
    class_id: int | None = None


class StudentRead(StudentBase):
    """学生详情响应。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class StudentList(BaseModel):
    """学生列表响应（分页）。"""
    items: list[StudentRead]
    total: int
    page: int = 1
    page_size: int = 50
