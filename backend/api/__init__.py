"""API 路由模块。"""
from fastapi import APIRouter

from backend.api import classes, import_export, projects, students

api_router = APIRouter()
api_router.include_router(students.router)
api_router.include_router(classes.router)
api_router.include_router(import_export.router)
api_router.include_router(projects.router)

__all__ = ["api_router"]
