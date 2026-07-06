"""批量报告 ORM 模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class BatchReport(Base):
    """
    批量报告表。

    存储一次批量生成的所有内容（共享内容 + 所有学生的评价），
    取代逐个创建 CourseRecord 的做法。
    """
    __tablename__ = "batch_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    class_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    class_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    course_date: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    course_topic: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    project_folder: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # AI 共享内容（JSON 字符串）
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

    # 所有学生的评价（JSON dict: student_id → {name, evaluation}）
    evaluations: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # 模板
    template_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="classic"
    )

    # 截图
    screenshot_paths: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON list
    run_screenshots: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON list
    code_screenshots: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON list
    homework_screenshots: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON list

    # 配置
    logo_config: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON {enabled, position, ...}
    teacher_observation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    observations: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON dict: student_id → str
    ai_meta: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )  # JSON {provider, model, ...}

    # 状态
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", index=True
    )  # draft / finalized

    # 时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<BatchReport id={self.id} class_id={self.class_id}"
            f" topic={self.course_topic!r} status={self.status!r}>"
        )
