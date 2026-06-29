"""Pydantic schemas 单元测试。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.schemas.klass import ClassCreate
from backend.schemas.student import StudentCreate, StudentUpdate


class TestStudentCreate:
    def test_minimal(self) -> None:
        s = StudentCreate(name="张三")
        assert s.name == "张三"
        assert s.base_level == "入门"
        assert s.characteristics == []
        assert s.age is None
        assert s.class_id is None

    def test_full(self) -> None:
        s = StudentCreate(
            name="李四",
            age=10,
            gender="男",
            grade="三年级",
            base_level="初级",
            characteristics=["内向", "喜欢挑战"],
            parent_contact="13800001111",
            note="转介绍",
            class_id=1,
        )
        assert s.age == 10
        assert s.characteristics == ["内向", "喜欢挑战"]

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StudentCreate(name="")

    def test_invalid_level_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StudentCreate(name="张三", base_level="高级")

    def test_age_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            StudentCreate(name="张三", age=200)
        with pytest.raises(ValidationError):
            StudentCreate(name="张三", age=0)

    def test_name_too_long(self) -> None:
        with pytest.raises(ValidationError):
            StudentCreate(name="x" * 100)


class TestStudentUpdate:
    def test_partial(self) -> None:
        u = StudentUpdate(name="新名")
        assert u.name == "新名"
        assert u.age is None
        assert u.base_level is None

    def test_empty(self) -> None:
        u = StudentUpdate()
        assert u.name is None


class TestClassCreate:
    def test_minimal(self) -> None:
        c = ClassCreate(name="周三班")
        assert c.name == "周三班"
        assert c.schedule_day is None

    def test_full(self) -> None:
        c = ClassCreate(
            name="周六上午班",
            schedule_day="周六",
            schedule_time="09:00-11:00",
        )
        assert c.schedule_day == "周六"
        assert c.schedule_time == "09:00-11:00"

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClassCreate(name="")
