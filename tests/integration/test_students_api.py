"""学生 API 集成测试。"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


class TestStudentCRUD:
    async def test_create_student(self, api_client) -> None:
        resp = await api_client.post(
            "/api/students",
            json={"name": "张三", "age": 10, "gender": "男"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "张三"
        assert data["age"] == 10
        assert data["base_level"] == "入门"
        assert "id" in data
        assert "created_at" in data

    async def test_create_student_with_class(self, api_client) -> None:
        # 先建班级
        class_resp = await api_client.post(
            "/api/classes",
            json={"name": "周三班", "schedule_day": "周三"},
        )
        assert class_resp.status_code == 201
        class_id = class_resp.json()["id"]

        # 再建学生
        resp = await api_client.post(
            "/api/students",
            json={"name": "李四", "class_id": class_id},
        )
        assert resp.status_code == 201
        assert resp.json()["class_id"] == class_id

    async def test_create_student_invalid_class(self, api_client) -> None:
        resp = await api_client.post(
            "/api/students",
            json={"name": "测试", "class_id": 9999},
        )
        assert resp.status_code == 400

    async def test_get_student(self, api_client) -> None:
        create_resp = await api_client.post(
            "/api/students", json={"name": "王五"}
        )
        student_id = create_resp.json()["id"]

        resp = await api_client.get(f"/api/students/{student_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "王五"

    async def test_get_nonexistent_student(self, api_client) -> None:
        resp = await api_client.get("/api/students/9999")
        assert resp.status_code == 404

    async def test_list_students(self, api_client) -> None:
        for i in range(3):
            await api_client.post(
                "/api/students", json={"name": f"学生{i}"}
            )

        resp = await api_client.get("/api/students")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

    async def test_list_students_with_keyword(self, api_client) -> None:
        await api_client.post("/api/students", json={"name": "张三"})
        await api_client.post("/api/students", json={"name": "李四"})

        resp = await api_client.get("/api/students?keyword=张")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "张三"

    async def test_list_students_with_level(self, api_client) -> None:
        await api_client.post(
            "/api/students", json={"name": "A", "base_level": "入门"}
        )
        await api_client.post(
            "/api/students", json={"name": "B", "base_level": "初级"}
        )

        resp = await api_client.get("/api/students?base_level=初级")
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "B"

    async def test_update_student(self, api_client) -> None:
        create_resp = await api_client.post(
            "/api/students", json={"name": "原名"}
        )
        student_id = create_resp.json()["id"]

        resp = await api_client.patch(
            f"/api/students/{student_id}",
            json={"name": "新名", "age": 12},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "新名"
        assert data["age"] == 12

    async def test_delete_student(self, api_client) -> None:
        create_resp = await api_client.post(
            "/api/students", json={"name": "待删"}
        )
        student_id = create_resp.json()["id"]

        resp = await api_client.delete(f"/api/students/{student_id}")
        assert resp.status_code == 204

        # 再次获取应 404
        resp = await api_client.get(f"/api/students/{student_id}")
        assert resp.status_code == 404


class TestStudentBatch:
    async def test_batch_create(self, api_client) -> None:
        students_data = [
            {"name": f"学生{i}", "base_level": "入门"} for i in range(5)
        ]
        resp = await api_client.post("/api/students/batch", json=students_data)
        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 5

    async def test_batch_empty_rejected(self, api_client) -> None:
        resp = await api_client.post("/api/students/batch", json=[])
        assert resp.status_code == 400


class TestStudentValidation:
    async def test_empty_name_rejected(self, api_client) -> None:
        resp = await api_client.post("/api/students", json={"name": ""})
        assert resp.status_code == 422

    async def test_missing_name_rejected(self, api_client) -> None:
        resp = await api_client.post("/api/students", json={})
        assert resp.status_code == 422

    async def test_invalid_base_level(self, api_client) -> None:
        resp = await api_client.post(
            "/api/students", json={"name": "测试", "base_level": "高级"}
        )
        assert resp.status_code == 422
