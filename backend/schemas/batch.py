"""批量报告生成 Schema。"""
from __future__ import annotations

from pydantic import BaseModel


class BatchGenerateRequest(BaseModel):
    """批量生成请求。"""
    class_id: int
    course_date: str = ""
    course_topic: str = ""
    project_folder: str = ""
    teacher_observation: str = ""
    template_id: str = "classic"
    output_dir: str | None = None
    auto_export: bool = False
    screenshot_paths: list[str] = []


class BatchStudentResult(BaseModel):
    """单个学生的批量生成结果。"""
    student_id: int
    student_name: str
    record_id: int | None = None
    evaluation: str = ""
    error: str | None = None


class BatchGenerateResponse(BaseModel):
    """批量生成响应。"""
    class_name: str = ""
    total: int = 0
    success: int = 0
    failed: int = 0
    results: list[BatchStudentResult] = []
