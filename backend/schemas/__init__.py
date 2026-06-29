"""
Schemas 模块

注意：`class` 是 Python 关键字，班级 schemas 在 klass.py 中定义。
"""
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
    "ClassCreate",
    "ClassList",
    "ClassRead",
    "ClassUpdate",
    "FileInfoSchema",
    "ProjectMetaSchema",
    "ProjectScanRequest",
    "PyStructureSchema",
    "StudentCreate",
    "StudentList",
    "StudentRead",
    "StudentUpdate",
]
