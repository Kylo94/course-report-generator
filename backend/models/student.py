"""学生 ORM 模型。"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base

if TYPE_CHECKING:
    from backend.models.klass import Class


class Student(Base):
    """
    学生表。

    字段说明：
    - name: 姓名（必填）
    - age: 年龄
    - gender: 性别（男/女/其他）
    - grade: 年级（如"三年级"）
    - base_level: 基础水平（入门/初级/中级）
    - characteristics: 性格特点（JSON 数组，如 ["内向", "喜欢挑战"]）
    - parent_contact: 家长联系方式
    - note: 备注
    - class_id: 所属班级
    """
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(8), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(32), nullable=True)
    base_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="入门"
    )
    characteristics: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    parent_contact: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    class_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("classes.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # 关系
    klass: Mapped[Class | None] = relationship(
        "Class", back_populates="students", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Student id={self.id} name={self.name!r} level={self.base_level}>"
