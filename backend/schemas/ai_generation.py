"""AI 生成相关 Pydantic schemas。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ContentItemSchema(BaseModel):
    """单个知识点的内容描述。"""
    kp: str = Field(..., description="知识点名称")
    text: str = Field(..., description="60-100字描述")


class HomeworkSchema(BaseModel):
    """课后作业结构。"""
    goal: str = Field(..., description="作业目标")
    hints: list[str] = Field(default_factory=list, description="提示列表")
    criteria: list[str] = Field(default_factory=list, description="评分点列表")


class VocabularySchema(BaseModel):
    """单词学习卡。"""
    word: str
    phonetic: str
    meaning: str
    example: str


class AIGeneratedContent(BaseModel):
    """AI 生成的完整 9 项内容。"""
    course_date: str | None = Field(None, description="上课时间 YYYY-MM-DD")
    course_name: str | None = Field(None, description="课程名称")
    knowledge_points: list[str] = Field(default_factory=list, max_length=5)
    ability_improvement: str = ""
    content_items: list[ContentItemSchema] = Field(default_factory=list)
    homework: HomeworkSchema = Field(default_factory=HomeworkSchema)
    vocabulary: VocabularySchema = Field(default_factory=VocabularySchema)
    evaluation: str = ""


class AIGenerateRequest(BaseModel):
    """AI 生成请求。"""
    project: dict = Field(..., description="项目元信息（来自 /api/projects/scan）")
    student_id: int = Field(..., description="学生 ID")
    teacher_observation: str = Field(
        default="", description="教师课堂观察补充"
    )
    fields: list[str] | None = Field(
        default=None,
        description="指定要生成的字段；None 表示全部",
    )
    existing_content: dict | None = Field(
        default=None,
        description="用户已填写的内容（knowledge_points/homework/vocabulary 等），AI 以此为准不再生成",
    )


class AIGenerateResponse(BaseModel):
    """AI 生成响应。"""
    student_id: int
    content: AIGeneratedContent
    errors: dict[str, str] = Field(default_factory=dict)


class AIRegenerateRequest(BaseModel):
    """单字段重新生成请求。"""
    project: dict
    student_id: int
    field: str = Field(..., description="字段名：knowledge_points 等")
    teacher_observation: str = ""
    knowledge_points: list[str] | None = None
