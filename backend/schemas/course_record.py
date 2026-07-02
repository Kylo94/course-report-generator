"""课程记录（报告草稿）Pydantic schemas。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.template import LayoutConfigSchema


class ContentItemSchema(BaseModel):
    """单个知识点内容描述（复用于兼容 ai_generation）。"""
    kp: str = Field(..., description="知识点名称")
    text: str = Field(..., description="60-100字描述")


class HomeworkSchema(BaseModel):
    """课后作业结构。"""
    goal: str = ""
    hints: list[str] = Field(default_factory=list)
    criteria: list[str] = Field(default_factory=list)


class VocabularySchema(BaseModel):
    """单词学习卡。"""
    word: str = ""
    phonetic: str = ""
    meaning: str = ""
    example: str = ""


class LogoConfigSchema(BaseModel):
    """Logo 配置。"""
    enabled: bool = False
    position: str = "top-right"  # top-left / top-right / top-center / bottom-left / bottom-right / bottom-center
    size: str = "medium"  # small / medium / large
    show_on_all_pages: bool = True
    margin: int = 0  # Logo 距页面边缘距离(mm)，控制 --logo-offset-* CSS 变量


class AiMetaSchema(BaseModel):
    """AI 生成元信息。"""
    provider: str = ""
    model: str = ""
    steps_completed: list[str] = Field(default_factory=list)


# =========================
# CRUD Schemas
# =========================

class CourseRecordCreate(BaseModel):
    """创建课程记录请求。"""
    student_id: int = Field(..., description="学生 ID")
    course_date: str = Field(default="", description="上课日期 YYYY-MM-DD")
    course_topic: str = Field(default="", max_length=64, description="课程主题")
    project_folder: str = Field(default="", description="项目文件夹路径")
    project_meta: dict | None = Field(default=None, description="扫描结果快照")

    # 内容字段（AI 生成后可填入）
    knowledge_points: list[str] | None = Field(default=None, description="知识点列表")
    ability_improvement: str = Field(default="", description="能力提升")
    content_items: list[ContentItemSchema] | None = Field(default=None, description="内容概述")
    homework: HomeworkSchema | None = Field(default=None, description="课后作业")
    vocabulary: VocabularySchema | None = Field(default=None, description="单词学习")
    evaluation: str = Field(default="", description="学生评价")

    # 资源
    screenshot_paths: list[str] | None = Field(default=None, description="截图路径列表")
    logo_config: LogoConfigSchema | None = Field(default=None, description="Logo 配置")

    # 布局设置
    layout_config: LayoutConfigSchema | None = Field(default=None, description="布局设置")

    # 状态
    status: str = Field(default="draft", pattern="^(draft|finalized|archived)$")
    template_id: str = Field(default="classic_default", description="模板 ID")

    # AI 元信息
    ai_meta: AiMetaSchema | None = Field(default=None, description="AI 元信息")


class CourseRecordUpdate(BaseModel):
    """更新课程记录请求（所有字段可选）。"""
    course_date: str | None = Field(default=None, description="上课日期")
    course_topic: str | None = Field(default=None, max_length=64, description="课程主题")
    project_folder: str | None = Field(default=None, description="项目文件夹")
    project_meta: dict | None = Field(default=None, description="扫描结果快照")

    knowledge_points: list[str] | None = Field(default=None, description="知识点列表")
    ability_improvement: str | None = Field(default=None, description="能力提升")
    content_items: list[ContentItemSchema] | None = Field(default=None, description="内容概述")
    homework: HomeworkSchema | None = Field(default=None, description="课后作业")
    vocabulary: VocabularySchema | None = Field(default=None, description="单词学习")
    evaluation: str | None = Field(default=None, description="学生评价")

    screenshot_paths: list[str] | None = Field(default=None, description="截图路径列表")
    logo_config: LogoConfigSchema | None = Field(default=None, description="Logo 配置")

    # 布局设置
    layout_config: LayoutConfigSchema | None = Field(default=None, description="布局设置")

    status: str | None = Field(default=None, pattern="^(draft|finalized|archived)$")
    template_id: str | None = Field(default=None, description="模板 ID")

    ai_meta: AiMetaSchema | None = Field(default=None, description="AI 元信息")


class CourseRecordRead(BaseModel):
    """课程记录详情响应。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    course_date: str
    course_topic: str
    project_folder: str
    project_meta: dict | None = None

    # 布局设置
    layout_config: LayoutConfigSchema | None = Field(default=None, description="布局设置")

    knowledge_points: list[str] = Field(default_factory=list)
    ability_improvement: str = ""
    content_items: list[ContentItemSchema] = Field(default_factory=list)
    homework: HomeworkSchema = Field(default_factory=HomeworkSchema)
    vocabulary: VocabularySchema = Field(default_factory=VocabularySchema)
    evaluation: str = ""

    screenshot_paths: list[str] = Field(default_factory=list)
    logo_config: LogoConfigSchema = Field(default_factory=LogoConfigSchema)

    status: str = "draft"
    template_id: str = "classic_default"

    ai_meta: AiMetaSchema = Field(default_factory=AiMetaSchema)

    last_auto_saved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CourseRecordListItem(BaseModel):
    """课程记录列表项（不含大字段内容）。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    course_date: str
    course_topic: str
    status: str
    template_id: str
    created_at: datetime
    updated_at: datetime


class CourseRecordList(BaseModel):
    """课程记录列表响应（分页）。"""
    items: list[CourseRecordListItem]
    total: int
    page: int = 1
    page_size: int = 50


class StatusUpdate(BaseModel):
    """状态变更请求。"""
    status: str = Field(..., pattern="^(draft|finalized|archived)$")
