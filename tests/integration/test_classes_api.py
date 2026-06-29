"""班级 API 集成测试。"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


class TestClassCRUD:
    async def test_create_class(self, api_client) -> None:
        resp = await api_client.post(
            "/api/classes",
            json={"name": "周三班", "schedule_day": "周三"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "周三班"
        assert data["student_count"] == 0

    async def test_list_classes(self, api_client) -> None:
        await api_client.post("/api/classes", json={"name": "A班"})
        await api_client.post("/api/classes", json={"name": "B班"})

        resp = await api_client.get("/api/classes")
        data = resp.json()
        assert data["total"] == 2

    async def test_get_class(self, api_client) -> None:
        create = await api_client.post(
            "/api/classes", json={"name": "测试班"}
        )
        class_id = create.json()["id"]

        resp = await api_client.get(f"/api/classes/{class_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "测试班"

    async def test_update_class(self, api_client) -> None:
        create = await api_client.post(
            "/api/classes", json={"name": "原名"}
        )
        class_id = create.json()["id"]

        resp = await api_client.patch(
            f"/api/classes/{class_id}",
            json={"name": "新名", "schedule_time": "10:00-12:00"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "新名"
        assert data["schedule_time"] == "10:00-12:00"

    async def test_delete_class(self, api_client) -> None:
        create = await api_client.post(
            "/api/classes", json={"name": "待删"}
        )
        class_id = create.json()["id"]

        resp = await api_client.delete(f"/api/classes/{class_id}")
        assert resp.status_code == 204

        resp = await api_client.get(f"/api/classes/{class_id}")
        assert resp.status_code == 404


class TestClassStudentCount:
    async def test_student_count_updated(self, api_client) -> None:
        # 建班
        class_resp = await api_client.post(
            "/api/classes", json={"name": "测试班"}
        )
        class_id = class_resp.json()["id"]

        # 加 3 个学生
        for i in range(3):
            await api_client.post(
                "/api/students",
                json={"name": f"学生{i}", "class_id": class_id},
            )

        # 查班级人数
        resp = await api_client.get(f"/api/classes/{class_id}")
        assert resp.json()["student_count"] == 3

    async def test_delete_class_sets_student_class_id_null(
        self, api_client
    ) -> None:
        """删除班级后，学生的 class_id 应被置为 None。"""
        class_resp = await api_client.post(
            "/api/classes", json={"name": "测试班"}
        )
        class_id = class_resp.json()["id"]

        student_resp = await api_client.post(
            "/api/students",
            json={"name": "张三", "class_id": class_id},
        )
        student_id = student_resp.json()["id"]

        # 删班级
        await api_client.delete(f"/api/classes/{class_id}")

        # 学生还在，但 class_id 为 None
        resp = await api_client.get(f"/api/students/{student_id}")
        assert resp.status_code == 200
        assert resp.json()["class_id"] is None
