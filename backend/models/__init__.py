"""
Models 模块

注意：`class` 是 Python 关键字，因此 ORM 模型 Class 在 klass.py 中定义。
"""
from backend.models.klass import Class
from backend.models.student import Student

__all__ = ["Class", "Student"]
