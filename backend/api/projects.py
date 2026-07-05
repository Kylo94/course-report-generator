"""项目扫描 API 路由。"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from backend.config import get_settings
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


@router.post(
    "/scan-screenshots",
    response_model=dict,
    summary="扫描项目 截图/ 文件夹中的截图并自动上传",
)
async def scan_save_screenshots(
    body: dict = Body(default={"folder": ""}),
) -> dict:
    """扫描项目文件夹下的 截图/ 目录，查找图片文件，
    自动将其复制到截图目录，返回 URL 路径列表供前端直接使用。

    按文件名分类：
    - run.png / 运行截图.*       → code_screenshots（程序运行结果截图）
    - code*.png / 代码*.png     → code_screenshots
    - homework*.png / 作业*.png → homework_screenshots
    - 其他                     → other_screenshots

    返回: {
      "code_screenshots": [...],
      "homework_screenshots": [...],
      "other_screenshots": [...],
    }
    """
    folder = (body.get("folder") or "").strip()
    if not folder:
        return {"code_screenshots": [], "homework_screenshots": [], "other_screenshots": []}

    target = Path(folder).expanduser().resolve()
    if not target.exists() or not target.is_dir():
        return {"code_screenshots": [], "homework_screenshots": [], "other_screenshots": []}

    save_dir = target / "截图"
    if not save_dir.exists() or not save_dir.is_dir():
        return {"code_screenshots": [], "homework_screenshots": [], "other_screenshots": []}

    settings = get_settings()
    screenshot_store = Path(settings.report.screenshot_dir)
    screenshot_store.mkdir(parents=True, exist_ok=True)

    code_imgs: list[dict] = []
    homework_imgs: list[dict] = []
    other_imgs: list[dict] = []

    for png_file in sorted(save_dir.iterdir()):
        if not png_file.is_file() or png_file.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            continue

        ext = png_file.suffix.lower()
        unique_name = f"screenshot_{uuid.uuid4().hex}{ext}"
        dest = screenshot_store / unique_name
        try:
            shutil.copy2(str(png_file), str(dest))
        except OSError as e:
            log.warning("复制截图失败 %s: %s", png_file.name, e)
            continue

        url_path = f"/api/assets/screenshots/{unique_name}"
        info = {"url": url_path, "filename": png_file.name}
        lower_name = png_file.name.lower()
        stem_lower = png_file.stem.lower()
        # 运行截图 run.* → code_screenshots
        if stem_lower == "run" or png_file.name.startswith("运行截图"):
            code_imgs.append(info)
        # 代码截图 code* / 代码* → code_screenshots
        elif png_file.name.startswith("代码") or lower_name.startswith("code"):
            code_imgs.append(info)
        # 作业截图 homework* / 作业* → homework_screenshots
        elif png_file.name.startswith("作业") or lower_name.startswith("homework"):
            homework_imgs.append(info)
        else:
            other_imgs.append(info)

    log.info(
        "截图/ 扫描: folder=%s code=%d homework=%d other=%d",
        folder, len(code_imgs), len(homework_imgs), len(other_imgs),
    )
    return {
        "code_screenshots": code_imgs,
        "homework_screenshots": homework_imgs,
        "other_screenshots": other_imgs,
    }
