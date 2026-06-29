"""项目扫描 API 路由。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from backend.schemas.project import (
    FileInfoSchema,
    ProjectMetaSchema,
    ProjectScanRequest,
    PyStructureSchema,
)
from backend.services import code_analyzer
from backend.utils.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])

# 常用项目起始目录
_DEFAULT_BROWSER_ROOTS = ["~", "~/Desktop", "~/Documents"]


@router.post(
    "/list-dir",
    summary="列出指定路径下的子目录（用于前端文件夹浏览器）",
    response_model=dict,
)
async def list_directory(
    body: dict = Body(default={"path": ""}),
) -> dict:
    """列出指定路径的子目录，返回目录树供前端浏览器使用。

    如果 path 为空，返回常用起始目录（桌面、文稿等）。
    """
    path_str = (body.get("path") or "").strip()

    if not path_str:
        # 默认起始页：列出常用根目录
        items = []
        for d in _DEFAULT_BROWSER_ROOTS:
            p = Path(d).expanduser().resolve()
            if p.exists():
                items.append({
                    "name": "📁 " + p.name,
                    "path": str(p),
                    "is_parent": False,
                    "is_root": True,
                })
        return {"path": "", "items": items, "is_root": True, "error": None}

    target = Path(path_str).expanduser().resolve()
    if not target.exists():
        return {"path": path_str, "items": [], "is_root": False, "error": "目录不存在"}
    if not target.is_dir():
        return {"path": path_str, "items": [], "is_root": False, "error": "不是目录"}

    items = []
    # 返回上级
    parent = target.parent
    if parent != target and parent.exists():
        items.append({
            "name": ".. 返回上级",
            "path": str(parent),
            "is_parent": True,
            "is_root": False,
        })

    try:
        for child in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name)):
            if child.is_dir() and not child.name.startswith("."):
                items.append({
                    "name": "📁 " + child.name,
                    "path": str(child.resolve()),
                    "is_parent": False,
                    "is_root": False,
                })
    except PermissionError:
        pass

    return {"path": str(target), "items": items, "is_root": False, "error": None}


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
