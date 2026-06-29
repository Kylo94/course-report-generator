"""课程记录（报告草稿）ORM 模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class CourseRecord(Base):
    """
    课程记录表（报告草稿 / 已导出 / 已归档）。

    存储 AI 生成 + 人工编辑后的完整报告内容，支持草稿续编。
    状态流转：draft → finalized → archived
    """
    __tablename__ = "course_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_date: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    course_topic: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    project_folder: Mapped[str] = mapped_column(Text, nullable=False, default="")
    project_meta: Mapped[dict | None] = mapped_column(
        "project_meta", Text, nullable=True, default=None
    )  # JSON 字符串，扫描结果快照

    # AI 生成 + 人工编辑的 9 项内容
    knowledge_points: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON list
    ability_improvement: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_items: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON list of {kp, text}
    homework: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON {goal, hints, criteria}
    vocabulary: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON {word, phonetic, meaning, example}
    evaluation: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 资源
    screenshot_paths: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON list of paths
    logo_config: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON {enabled, position, size, show_on_all_pages}

    # 布局设置（用户自定义排版）
    layout_config: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON {primary_color, font_title, ...}

    # 状态
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", index=True
    )  # draft / finalized / archived
    template_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="classic_default"
    )

    # AI 元信息
    ai_meta: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON {provider, model, steps_completed}

    # 时间
    last_auto_saved_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<CourseRecord id={self.id} student_id={self.student_id}"
            f" topic={self.course_topic!r} status={self.status!r}>"
        )
