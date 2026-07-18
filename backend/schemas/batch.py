"""批量报告生成 Schema。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BatchGenerateRequest(BaseModel):
    """批量生成请求。"""
    class_id: int
    course_date: str = ""
    course_topic: str = ""
    course_description: str = ""       # 纯图文模式的课程详细描述
    is_no_code: bool = False            # 是否为纯图文课程（无代码文件）
    project_folder: str = ""
    teacher_observation: str = ""  # 全局观察（兜底）
    observations: dict[int, str] = {}  # 逐学生观察，key=student_id
    template_id: str = "classic"
    output_dir: str | None = None
    auto_export: bool = False
    screenshot_paths: list[str] = []
    # === 截图分类（截图/ 目录扫描后填充） ===
    run_screenshots: list[str] = []       # 运行效果/项目截图 URL
    code_screenshots: list[str] = []      # 代码截图 URL
    homework_screenshots: list[str] = []  # 作业截图 URL
    # === 用户已填写的内容（AI 应以此为准，不再生成） ===
    existing_content: dict | None = None  # 含 knowledge_points, content_items, homework, vocabulary 等
    # === AI 步骤开关 ===
    create_vocabulary: bool = True  # 是否生成单词卡
    skip_code_analysis: bool = False  # 是否有代码截图 → 跳过程序解析
    skip_homework_gen: bool = False  # 是否有作业截图 → 跳过作业生成


class BatchStudentResult(BaseModel):
    """单个学生的批量生成结果（不再有逐学生 record_id，改为按班级整体保存）。"""
    student_id: int
    student_name: str
    evaluation: str = ""
    error: str | None = None


class BatchGenerateResponse(BaseModel):
    """批量生成响应。"""
    batch_id: int | None = None  # BatchReport 的 ID
    class_name: str = ""
    total: int = 0
    success: int = 0
    failed: int = 0
    results: list[BatchStudentResult] = []


class BatchReportRead(BaseModel):
    """BatchReport 读取响应。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    class_id: int
    class_name: str
    course_date: str
    course_topic: str
    course_description: str = ""
    project_folder: str
    template_id: str
    knowledge_points: list[str] = Field(default_factory=list)
    ability_improvement: str = ""
    content_items: list[dict] = Field(default_factory=list)
    homework: dict = Field(default_factory=dict)
    vocabulary: dict = Field(default_factory=dict)
    evaluations: dict = Field(default_factory=dict)  # student_id → {name, evaluation}
    screenshot_paths: list[str] = Field(default_factory=list)
    run_screenshots: list[str] = Field(default_factory=list)
    code_screenshots: list[str] = Field(default_factory=list)
    homework_screenshots: list[str] = Field(default_factory=list)
    logo_config: dict = Field(default_factory=dict)
    teacher_observation: str = ""
    observations: dict = Field(default_factory=dict)
    ai_meta: dict = Field(default_factory=dict)
    status: str = "draft"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BatchReportUpdate(BaseModel):
    """BatchReport 更新请求（所有字段可选）。"""
    evaluations: dict | None = None  # 更新 evaluations（批量保存评价时使用）
    status: str | None = None
    course_description: str | None = None
    # 共享内容（用户手动编辑后保存）
    knowledge_points: list[str] | None = None
    ability_improvement: str | None = None
    content_items: list[dict] | None = None
    homework: dict | None = None
    vocabulary: dict | None = None
    teacher_observation: str | None = None
    observations: dict | None = None
    template_id: str | None = None
    # 截图
    run_screenshots: list[str] | None = None
    code_screenshots: list[str] | None = None
    homework_screenshots: list[str] | None = None
    screenshot_paths: list[str] | None = None
