"""
Schemas 模块

注意：`class` 是 Python 关键字，班级 schemas 在 klass.py 中定义。
"""
from backend.schemas.ai_generation import (
    AIGeneratedContent,
    AIGenerateRequest,
    AIGenerateResponse,
    AIRegenerateRequest,
    ContentItemSchema,
    HomeworkSchema,
    VocabularySchema,
)
from backend.schemas.template import (
    TemplateConfig,
    TemplateListItem,
    ThemeConfig,
)
from backend.schemas.course_record import (
    AiMetaSchema,
    CourseRecordCreate,
    CourseRecordList,
    CourseRecordListItem,
    CourseRecordRead,
    CourseRecordUpdate,
    LogoConfigSchema,
    StatusUpdate,
)
from backend.schemas.klass import (
    ClassCreate,
    ClassList,
    ClassRead,
    ClassUpdate,
)
from backend.schemas.project import (
    FileInfoSchema,
    ProjectMetaSchema,
    ProjectScanRequest,
    PyStructureSchema,
)
from backend.schemas.student import (
    StudentCreate,
    StudentList,
    StudentRead,
    StudentUpdate,
)

__all__ = [
    "AIGenerateRequest",
    "AIGenerateResponse",
    "AIGeneratedContent",
    "AIRegenerateRequest",
    "AiMetaSchema",
    "ClassCreate",
    "ClassList",
    "ClassRead",
    "ClassUpdate",
    "ContentItemSchema",
    "CourseRecordCreate",
    "CourseRecordListItem",
    "CourseRecordList",
    "CourseRecordRead",
    "CourseRecordUpdate",
    "FileInfoSchema",
    "HomeworkSchema",
    "LogoConfigSchema",
    "ProjectMetaSchema",
    "ProjectScanRequest",
    "PyStructureSchema",
    "StatusUpdate",
    "StudentCreate",
    "TemplateConfig",
    "TemplateListItem",
    "ThemeConfig",
    "StudentList",
    "StudentRead",
    "StudentUpdate",
    "VocabularySchema",
]
