"""课程记录（报告草稿）单元测试。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.models import CourseRecord
from backend.schemas.course_record import (
    AiMetaSchema,
    ContentItemSchema,
    CourseRecordCreate,
    CourseRecordUpdate,
    HomeworkSchema,
    LogoConfigSchema,
    StatusUpdate,
    VocabularySchema,
)


class TestCourseRecordModel:
    """CourseRecord ORM 模型测试。"""

    async def test_create_record(self, db_session) -> None:
        record = CourseRecord(
            student_id=1,
            course_date="2026-06-29",
            course_topic="测试课",
            project_folder="/tmp/test",
            knowledge_points=json.dumps(["print", "if"], ensure_ascii=False),
            ability_improvement="逻辑思维提升",
            evaluation="表现良好",
        )
        db_session.add(record)
        await db_session.commit()
        await db_session.refresh(record)

        assert record.id is not None
        assert record.student_id == 1
        assert record.course_topic == "测试课"
        assert record.status == "draft"
        assert record.created_at is not None

    async def test_default_status(self, db_session) -> None:
        record = CourseRecord(student_id=2, course_date="2026-06-29")
        db_session.add(record)
        await db_session.commit()
        await db_session.refresh(record)
        assert record.status == "draft"

    async def test_timestamps_auto(self, db_session) -> None:
        record = CourseRecord(student_id=3, course_date="2026-06-29")
        db_session.add(record)
        await db_session.commit()
        await db_session.refresh(record)
        assert record.created_at is not None
        assert record.updated_at is not None

    async def test_json_fields_roundtrip(self, db_session) -> None:
        kp = json.dumps(["a", "b"], ensure_ascii=False)
        ci = json.dumps(
            [{"kp": "a", "text": "内容1"}, {"kp": "b", "text": "内容2"}],
            ensure_ascii=False,
        )
        hw = json.dumps(
            {"goal": "练习", "hints": ["hint1"], "criteria": ["c1"]},
            ensure_ascii=False,
        )
        vocab = json.dumps(
            {"word": "Branch", "phonetic": "/bræntʃ/", "meaning": "分支", "example": "if"},
            ensure_ascii=False,
        )

        record = CourseRecord(
            student_id=4,
            course_date="2026-06-29",
            knowledge_points=kp,
            content_items=ci,
            homework=hw,
            vocabulary=vocab,
        )
        db_session.add(record)
        await db_session.commit()
        await db_session.refresh(record)

        assert json.loads(record.knowledge_points) == ["a", "b"]
        assert len(json.loads(record.content_items)) == 2
        assert json.loads(record.homework)["goal"] == "练习"
        assert json.loads(record.vocabulary)["word"] == "Branch"

    async def test_last_auto_saved_at(self, db_session) -> None:
        record = CourseRecord(student_id=5, course_date="2026-06-29")
        db_session.add(record)
        await db_session.commit()

        now = datetime.now(timezone.utc)
        record.last_auto_saved_at = now
        await db_session.commit()
        await db_session.refresh(record)

        assert record.last_auto_saved_at is not None


class TestCourseRecordSchemas:
    """CourseRecord Pydantic schemas 测试。"""

    def test_create_schema_minimal(self) -> None:
        data = CourseRecordCreate(student_id=1)
        assert data.student_id == 1
        assert data.status == "draft"
        assert data.template_id == "classic_default"
        assert data.course_date == ""

    def test_create_schema_full(self) -> None:
        data = CourseRecordCreate(
            student_id=1,
            course_date="2026-06-29",
            course_topic="测试课",
            knowledge_points=["print", "if"],
            ability_improvement="逻辑提升",
            content_items=[ContentItemSchema(kp="print", text="x" * 60)],
            homework=HomeworkSchema(goal="练习if", hints=["h1"], criteria=["c1"]),
            vocabulary=VocabularySchema(word="If", phonetic="/ɪf/", meaning="如果", example="if x:"),
            evaluation="表现良好",
            status="draft",
            template_id="classic_default",
            logo_config=LogoConfigSchema(enabled=True, position="top-left", size="medium"),
        )
        assert len(data.knowledge_points) == 2
        assert data.homework.goal == "练习if"
        assert data.logo_config.position == "top-left"

    def test_update_schema_all_optional(self) -> None:
        data = CourseRecordUpdate()
        assert data.model_dump(exclude_unset=True) == {}

    def test_update_schema_partial(self) -> None:
        data = CourseRecordUpdate(course_topic="新主题", evaluation="新评价")
        dumped = data.model_dump(exclude_unset=True)
        assert "course_topic" in dumped
        assert "evaluation" in dumped
        assert "homework" not in dumped

    def test_status_update_valid(self) -> None:
        s = StatusUpdate(status="finalized")
        assert s.status == "finalized"

    def test_status_update_invalid(self) -> None:
        with pytest.raises(ValueError):
            StatusUpdate(status="invalid_status")

    def test_ai_meta_schema(self) -> None:
        meta = AiMetaSchema(provider="deepseek", model="deepseek-chat", steps_completed=["kp", "cs"])
        assert meta.provider == "deepseek"
        assert len(meta.steps_completed) == 2

    def test_logo_config_defaults(self) -> None:
        cfg = LogoConfigSchema()
        assert cfg.enabled is False
        assert cfg.position == "top-right"
        assert cfg.size == "medium"

    def test_homework_defaults(self) -> None:
        hw = HomeworkSchema()
        assert hw.goal == ""
        assert hw.hints == []
        assert hw.criteria == []

    def test_vocabulary_defaults(self) -> None:
        v = VocabularySchema()
        assert v.word == ""
        assert v.phonetic == ""


class TestCourseRecordCRUD:
    """CourseRecord 服务层 CRUD 测试。"""

    async def test_create_and_get(self, db_session) -> None:
        from backend.services.course_records import create_record, get_record

        data = CourseRecordCreate(
            student_id=1,
            course_date="2026-06-29",
            course_topic="测试课",
            knowledge_points=["print", "if"],
        )
        record = await create_record(db_session, data)
        assert record.id is not None
        assert record.student_id == 1

        fetched = await get_record(db_session, record.id)
        assert fetched.id == record.id
        assert fetched.course_topic == "测试课"

    async def test_get_not_found(self, db_session) -> None:
        from backend.services.course_records import RecordNotFoundError, get_record

        with pytest.raises(RecordNotFoundError):
            await get_record(db_session, 99999)

    async def test_update(self, db_session) -> None:
        from backend.services.course_records import create_record, update_record

        data = CourseRecordCreate(student_id=1, course_date="2026-06-29")
        record = await create_record(db_session, data)

        update = CourseRecordUpdate(course_topic="新标题", evaluation="写得好")
        updated = await update_record(db_session, record.id, update)
        assert updated.course_topic == "新标题"
        assert updated.evaluation == "写得好"

    async def test_update_status(self, db_session) -> None:
        from backend.services.course_records import (
            create_record,
            update_record_status,
        )

        data = CourseRecordCreate(student_id=1, course_date="2026-06-29")
        record = await create_record(db_session, data)
        assert record.status == "draft"

        updated = await update_record_status(db_session, record.id, "finalized")
        assert updated.status == "finalized"

    async def test_delete(self, db_session) -> None:
        from backend.services.course_records import (
            RecordNotFoundError,
            create_record,
            delete_record,
            get_record,
        )

        data = CourseRecordCreate(student_id=1, course_date="2026-06-29")
        record = await create_record(db_session, data)
        await delete_record(db_session, record.id)

        with pytest.raises(RecordNotFoundError):
            await get_record(db_session, record.id)

    async def test_list_empty(self, db_session) -> None:
        from backend.services.course_records import list_records

        items, total = await list_records(db_session)
        assert total == 0
        assert len(items) == 0

    async def test_list_with_data(self, db_session) -> None:
        from backend.services.course_records import create_record, list_records

        for i in range(3):
            await create_record(
                db_session,
                CourseRecordCreate(
                    student_id=1,
                    course_date="2026-06-29",
                    course_topic=f"课程{i}",
                    status="draft",
                ),
            )

        items, total = await list_records(db_session)
        assert total == 3
        assert len(items) == 3

    async def test_list_filter_by_status(self, db_session) -> None:
        from backend.services.course_records import (
            create_record,
            list_records,
            update_record_status,
        )

        r1 = await create_record(
            db_session, CourseRecordCreate(student_id=1, course_date="2026-06-29")
        )
        await create_record(
            db_session, CourseRecordCreate(student_id=2, course_date="2026-06-29")
        )
        await update_record_status(db_session, r1.id, "finalized")

        items, total = await list_records(db_session, status="finalized")
        assert total == 1

        items2, total2 = await list_records(db_session, status="draft")
        assert total2 == 1

    async def test_update_auto_save_timestamp(self, db_session) -> None:
        from backend.services.course_records import (
            create_record,
            update_auto_save_timestamp,
        )

        data = CourseRecordCreate(student_id=1, course_date="2026-06-29")
        record = await create_record(db_session, data)
        assert record.last_auto_saved_at is None

        updated = await update_auto_save_timestamp(db_session, record.id)
        assert updated.last_auto_saved_at is not None

    async def test_serialize_deserialize(self) -> None:
        from backend.services.course_records import (
            _deserialize_from_record,
            _serialize_for_db,
        )

        data = CourseRecordCreate(
            student_id=1,
            course_date="2026-06-29",
            course_topic="测试",
            knowledge_points=["a", "b"],
            ability_improvement="提升逻辑",
            content_items=[{"kp": "a", "text": "内容1"}],
            homework={"goal": "G", "hints": ["h"], "criteria": ["c"]},
            vocabulary={"word": "X", "phonetic": "/x/", "meaning": "x", "example": "x"},
            evaluation="好",
            status="draft",
            screenshot_paths=["/img/a.jpg"],
            logo_config={"enabled": True, "position": "top-left", "size": 30, "show_on_all_pages": True},
        )

        db_data = _serialize_for_db(data)
        assert isinstance(db_data["knowledge_points"], str)
        assert isinstance(db_data["content_items"], str)
        assert isinstance(db_data["homework"], str)

        # 模拟 ORM 对象（反序列化测试用字符串字段）
        class FakeRecord:
            pass

        record = FakeRecord()
        for k, v in db_data.items():
            setattr(record, k, v)
        record.id = 1
        record.status = "draft"
        record.template_id = "classic_default"
        record.last_auto_saved_at = None
        from datetime import datetime
        record.created_at = datetime.now()
        record.updated_at = datetime.now()

        result = _deserialize_from_record(record, include_content=True)
        assert isinstance(result["knowledge_points"], list)
        assert len(result["knowledge_points"]) == 2
        assert isinstance(result["content_items"], list)
        assert isinstance(result["homework"], dict)
        assert isinstance(result["screenshot_paths"], list)
