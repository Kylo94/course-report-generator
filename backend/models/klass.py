"""班级 ORM 模型。"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base

if TYPE_CHECKING:
    from backend.models.student import Student


class Class(Base):
    """
    班级表。

    字段说明：
    - name: 班级名（如"周三下午少儿编程班"）
    - schedule_day: 上课日（如"周三"）
    - schedule_time: 上课时间（如"15:00-17:00"）
    """
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    schedule_day: Mapped[str | None] = mapped_column(String(16), nullable=True)
    schedule_time: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # 关系：一个班级多个学生
    students: Mapped[list["Student"]] = relationship(
        "Student", back_populates="klass", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Class id={self.id} name={self.name!r}>"
