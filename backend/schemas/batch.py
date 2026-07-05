"""批量报告生成 Schema。"""
from __future__ import annotations

from pydantic import BaseModel


class BatchGenerateRequest(BaseModel):
    """批量生成请求。"""
    class_id: int
    course_date: str = ""
    course_topic: str = ""
    project_folder: str = ""
    teacher_observation: str = ""  # 全局观察（兜底）
    observations: dict[int, str] = {}  # 逐学生观察，key=student_id
    template_id: str = "classic"
    output_dir: str | None = None
    auto_export: bool = False
    screenshot_paths: list[str] = []
    # === 截图分类（save/ 目录扫描后填充） ===
    code_screenshots: list[str] = []      # 代码截图 URL（save/代码*.png）
    homework_screenshots: list[str] = []  # 作业截图 URL（save/作业*.png）
    # === AI 步骤开关 ===
    create_vocabulary: bool = True  # 是否生成单词卡
    skip_code_analysis: bool = False  # 是否有代码截图 → 跳过程序解析
    skip_homework_gen: bool = False  # 是否有作业截图 → 跳过作业生成


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
