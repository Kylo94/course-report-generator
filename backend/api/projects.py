"""项目扫描 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.schemas.project import (
    FileInfoSchema,
    ProjectMetaSchema,
    ProjectScanRequest,
    PyStructureSchema,
)
from backend.services import code_analyzer

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post(
    "/scan",
    response_model=ProjectMetaSchema,
    summary="扫描 Python 项目文件夹",
)
async def scan_project(req: ProjectScanRequest) -> ProjectMetaSchema:
    """
    扫描指定路径下的 Python 项目，返回：
    - 启动文件
    - 项目类型（pygame / turtle / web / algorithm 等）
    - 课程主题（从启动文件顶部注释解析）
    - 所有文件清单 + 每个 .py 的结构
    - 全部 import 列表
    - 警告（如未找到课程主题）
    """
    try:
        meta = code_analyzer.analyze_project(req.folder)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except NotADirectoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ProjectMetaSchema(
        folder=meta.folder,
        entry_file=meta.entry_file,
        project_type=meta.project_type,
        course_title=meta.course_title,
        all_files=[FileInfoSchema(**vars(f)) for f in meta.all_files],
        py_files=[
            PyStructureSchema(
                path=s.path,
                imports=s.imports,
                from_imports=[
                    {"module": m, "name": n} for m, n in s.from_imports
                ],
                function_names=s.function_names,
                class_names=s.class_names,
                decorators=s.decorators,
                top_comment=s.top_comment,
                course_title=s.course_title,
                line_count=s.line_count,
            )
            for s in meta.py_files
        ],
        all_imports=meta.all_imports,
        total_lines=meta.total_lines,
        warnings=meta.warnings,
    )
