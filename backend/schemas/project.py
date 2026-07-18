"""项目扫描相关 Pydantic schemas。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class FileInfoSchema(BaseModel):
    """文件信息。"""
    path: str
    name: str
    is_python: bool
    size_bytes: int


class PyStructureSchema(BaseModel):
    """Python 文件结构。"""
    path: str
    imports: list[str] = Field(default_factory=list)
    from_imports: list[dict] = Field(default_factory=list)
    function_names: list[str] = Field(default_factory=list)
    class_names: list[str] = Field(default_factory=list)
    decorators: list[str] = Field(default_factory=list)
    top_comment: str | None = None
    course_title: str | None = None
    homework_guidance: str | None = None
    line_count: int = 0


class ProjectMetaSchema(BaseModel):
    """项目元信息响应。"""
    folder: str
    entry_file: str | None
    project_type: str
    course_title: str | None
    all_files: list[FileInfoSchema]
    py_files: list[PyStructureSchema]
    all_imports: list[str]
    total_lines: int
    warnings: list[str]

    @classmethod
    def no_code_stub(cls, course_topic: str = "") -> "ProjectMetaSchema":
        """创建纯图文课程的空白项目元信息（无代码文件）。"""
        return cls(
            folder="",
            entry_file="",
            project_type="图文",
            course_title=course_topic,
            all_files=[],
            py_files=[],
            all_imports=[],
            total_lines=0,
            warnings=["纯图文课程，无代码文件"],
        )


class ProjectScanRequest(BaseModel):
    """项目扫描请求。"""
    folder: str = Field(..., min_length=1, description="项目文件夹绝对路径")
