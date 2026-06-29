"""报告编辑 API 集成测试。"""
from __future__ import annotations

import io

import pytest

pytestmark = pytest.mark.asyncio


async def _create_student(api_client) -> int:
    """快捷创建学生返回 ID。"""
    resp = await api_client.post("/api/students", json={"name": "测试学生"})
    assert resp.status_code == 201
    return resp.json()["id"]


class TestCreateRecord:
    async def test_create_minimal(self, api_client) -> None:
        student_id = await _create_student(api_client)
        resp = await api_client.post(
            "/api/reports",
            json={"student_id": student_id},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["student_id"] == student_id
        assert data["status"] == "draft"
        assert data["id"] > 0
        assert data["knowledge_points"] == []

    async def test_create_with_content(self, api_client) -> None:
        student_id = await _create_student(api_client)
        resp = await api_client.post(
            "/api/reports",
            json={
                "student_id": student_id,
                "course_date": "2026-06-29",
                "course_topic": "测试课",
                "knowledge_points": ["print", "if"],
                "ability_improvement": "逻辑思维提升",
                "evaluation": "表现很好",
                "homework": {
                    "goal": "练习 if",
                    "hints": ["提示1"],
                    "criteria": ["能运行"],
                },
                "vocabulary": {
                    "word": "Branch",
                    "phonetic": "/bræntʃ/",
                    "meaning": "分支",
                    "example": "if branch:",
                },
                "content_items": [
                    {"kp": "print", "text": "x" * 60},
                ],
                "screenshot_paths": ["/img/a.png"],
                "status": "draft",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["course_topic"] == "测试课"
        assert len(data["knowledge_points"]) == 2
        assert data["homework"]["goal"] == "练习 if"
        assert data["vocabulary"]["word"] == "Branch"
        assert len(data["content_items"]) == 1

    async def test_create_missing_student_id(self, api_client) -> None:
        resp = await api_client.post("/api/reports", json={})
        assert resp.status_code == 422


class TestGetRecord:
    async def test_get_by_id(self, api_client) -> None:
        student_id = await _create_student(api_client)
        create_resp = await api_client.post(
            "/api/reports", json={"student_id": student_id}
        )
        record_id = create_resp.json()["id"]

        resp = await api_client.get(f"/api/reports/{record_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == record_id
        assert data["student_id"] == student_id

    async def test_get_not_found(self, api_client) -> None:
        resp = await api_client.get("/api/reports/99999")
        assert resp.status_code == 404

    async def test_get_invalid_id(self, api_client) -> None:
        resp = await api_client.get("/api/reports/abc")
        assert resp.status_code == 422


class TestListRecords:
    async def test_list_empty(self, api_client) -> None:
        resp = await api_client.get("/api/reports")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 0
        assert "items" in data

    async def test_list_pagination(self, api_client) -> None:
        student_id = await _create_student(api_client)
        for i in range(3):
            await api_client.post(
                "/api/reports",
                json={
                    "student_id": student_id,
                    "course_topic": f"课程{i}",
                },
            )
        resp = await api_client.get("/api/reports?page=1&page_size=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] >= 3

    async def test_list_filter_by_status(self, api_client) -> None:
        student_id = await _create_student(api_client)
        r1 = await api_client.post(
            "/api/reports", json={"student_id": student_id}
        )
        rid1 = r1.json()["id"]
        await api_client.patch(f"/api/reports/{rid1}/status", json={"status": "finalized"})

        resp = await api_client.get("/api/reports?status=finalized")
        assert resp.status_code == 200

    async def test_list_filter_by_keyword(self, api_client) -> None:
        student_id = await _create_student(api_client)
        await api_client.post(
            "/api/reports",
            json={"student_id": student_id, "course_topic": "Python入门"},
        )
        resp = await api_client.get("/api/reports?keyword=Python")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1


class TestUpdateRecord:
    async def test_full_update(self, api_client) -> None:
        student_id = await _create_student(api_client)
        cr = await api_client.post(
            "/api/reports", json={"student_id": student_id}
        )
        record_id = cr.json()["id"]

        resp = await api_client.put(
            f"/api/reports/{record_id}",
            json={
                "course_topic": "新主题",
                "evaluation": "新的评价内容，长度足够180字测试数据测试数据测试数据测试数据",
                "knowledge_points": ["新知识点"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["course_topic"] == "新主题"
        assert len(data["knowledge_points"]) == 1

    async def test_patch_partial(self, api_client) -> None:
        student_id = await _create_student(api_client)
        cr = await api_client.post(
            "/api/reports",
            json={
                "student_id": student_id,
                "course_topic": "原主题",
            },
        )
        record_id = cr.json()["id"]

        resp = await api_client.patch(
            f"/api/reports/{record_id}",
            json={"evaluation": "仅更新评价"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["course_topic"] == "原主题"  # 未变
        assert "仅更新评价" in data["evaluation"]

    async def test_update_not_found(self, api_client) -> None:
        resp = await api_client.put(
            "/api/reports/99999",
            json={"course_topic": "x"},
        )
        assert resp.status_code == 404


class TestStatusTransition:
    async def test_draft_to_finalized(self, api_client) -> None:
        student_id = await _create_student(api_client)
        cr = await api_client.post(
            "/api/reports", json={"student_id": student_id}
        )
        record_id = cr.json()["id"]
        assert cr.json()["status"] == "draft"

        resp = await api_client.patch(
            f"/api/reports/{record_id}/status",
            json={"status": "finalized"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "finalized"

    async def test_invalid_status(self, api_client) -> None:
        student_id = await _create_student(api_client)
        cr = await api_client.post(
            "/api/reports", json={"student_id": student_id}
        )
        record_id = cr.json()["id"]

        resp = await api_client.patch(
            f"/api/reports/{record_id}/status",
            json={"status": "invalid"},
        )
        assert resp.status_code == 422


class TestDeleteRecord:
    async def test_delete_ok(self, api_client) -> None:
        student_id = await _create_student(api_client)
        cr = await api_client.post(
            "/api/reports", json={"student_id": student_id}
        )
        record_id = cr.json()["id"]

        resp = await api_client.delete(f"/api/reports/{record_id}")
        assert resp.status_code == 204

        # 验证已删除
        get_resp = await api_client.get(f"/api/reports/{record_id}")
        assert get_resp.status_code == 404

    async def test_delete_not_found(self, api_client) -> None:
        resp = await api_client.delete("/api/reports/99999")
        assert resp.status_code == 404


class TestScreenshotUpload:
    async def test_upload_screenshot(self, api_client) -> None:
        """上传 PNG 截图。"""
        img_data = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        resp = await api_client.post(
            "/api/assets/screenshot",
            files={"file": ("test.png", img_data, "image/png")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["path"].startswith("/api/assets/screenshots/")
        assert data["mime_type"] == "image/png"

    async def test_upload_invalid_type(self, api_client) -> None:
        resp = await api_client.post(
            "/api/assets/screenshot",
            files={"file": ("test.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 400


class TestLogoUpload:
    async def test_upload_logo(self, api_client) -> None:
        img_data = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        resp = await api_client.post(
            "/api/assets/logo",
            files={"file": ("logo.png", img_data, "image/png")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "path" in data
        assert data["mime_type"] == "image/png"

    async def test_get_logo_info(self, api_client) -> None:
        resp = await api_client.get("/api/assets/logo")
        assert resp.status_code == 200
        data = resp.json()
        assert "exists" in data

    async def test_logo_invalid_type(self, api_client) -> None:
        resp = await api_client.post(
            "/api/assets/logo",
            files={"file": ("logo.txt", b"test", "text/plain")},
        )
        assert resp.status_code == 400


class TestSerializationRoundtrip:
    """验证所有字段通过 API 能正确序列化/反序列化。"""

    async def test_full_content_roundtrip(self, api_client) -> None:
        student_id = await _create_student(api_client)

        # 创建含完整内容的记录
        create_payload = {
            "student_id": student_id,
            "course_date": "2026-06-29",
            "course_topic": "完整测试",
            "knowledge_points": ["var", "if", "loop", "func", "class"],
            "ability_improvement": "综合编程能力提升",
            "content_items": [
                {"kp": "var", "text": "变量用于存储数据"},
                {"kp": "if", "text": "条件判断"},
            ],
            "homework": {
                "goal": "完成一个综合练习",
                "hints": ["先画流程图", "从简单开始"],
                "criteria": ["代码可运行", "包含至少一个函数"],
            },
            "vocabulary": {
                "word": "Function",
                "phonetic": "/ˈfʌŋkʃn/",
                "meaning": "函数",
                "example": "def hello():",
            },
            "evaluation": "本节课学生表现非常出色，能独立完成所有练习。",
            "screenshot_paths": ["/img/1.png", "/img/2.png"],
        }

        create_resp = await api_client.post("/api/reports", json=create_payload)
        assert create_resp.status_code == 201
        data = create_resp.json()

        assert len(data["knowledge_points"]) == 5
        assert len(data["content_items"]) == 2
        assert data["homework"]["goal"] == "完成一个综合练习"
        assert len(data["homework"]["hints"]) == 2
        assert data["vocabulary"]["word"] == "Function"
        assert len(data["screenshot_paths"]) == 2

        # 读取验证
        get_resp = await api_client.get(f"/api/reports/{data['id']}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["course_topic"] == "完整测试"
        assert get_data["evaluation"] == create_payload["evaluation"]

        # 部分更新
        patch_resp = await api_client.patch(
            f"/api/reports/{data['id']}",
            json={"evaluation": "修改后的评价"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["evaluation"] == "修改后的评价"
        assert patch_resp.json()["course_topic"] == "完整测试"  # 未变


class TestTemplateAPI:
    """模板 API 集成测试。"""

    async def test_list_templates(self, api_client) -> None:
        """GET /api/templates 返回内置模板列表。"""
        resp = await api_client.get("/api/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 3
        ids = [t["id"] for t in data]
        assert "classic" in ids
        assert "cartoon" in ids
        assert "academic" in ids
        t0 = data[0]
        assert "name" in t0
        assert "description" in t0
        assert "page_size" in t0
        assert t0["page_size"] == "A4"


class TestExportPDF:
    """PDF 导出集成测试。"""

    async def test_export_success(self, api_client) -> None:
        """POST /api/reports/{id}/export 返回 PDF 信息。"""
        student_id = await _create_student(api_client)
        cr = await api_client.post(
            "/api/reports",
            json={
                "student_id": student_id,
                "course_topic": "导出测试",
                "course_date": "2026-06-29",
                "knowledge_points": ["变量", "循环"],
                "ability_improvement": "逻辑思维提升",
                "content_items": [
                    {"kp": "变量", "text": "学习变量基本概念和用法"},
                ],
                "homework": {
                    "goal": "完成课后练习",
                    "hints": ["先思考"],
                    "criteria": ["代码正确"],
                },
                "vocabulary": {
                    "word": "Variable",
                    "phonetic": "/v/",
                    "meaning": "变量",
                    "example": "x=1",
                },
                "evaluation": "表现良好",
            },
        )
        record_id = cr.json()["id"]

        resp = await api_client.post(
            f"/api/reports/{record_id}/export",
            json={"template_id": "classic"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "pdf_path" in data
        assert data["pdf_path"].endswith(".pdf")
        assert data["pdf_path"].startswith("/api/reports/pdf/")
        assert data["template_id"] == "classic"
        assert data["page_size"] == "A4"

    async def test_export_not_found(self, api_client) -> None:
        """不存在的 record_id 返回 404。"""
        resp = await api_client.post(
            "/api/reports/99999/export",
            json={"template_id": "classic"},
        )
        assert resp.status_code == 404

    async def test_export_with_invalid_template(self, api_client) -> None:
        """不存在的模板 ID 返回 400。"""
        student_id = await _create_student(api_client)
        cr = await api_client.post(
            "/api/reports", json={"student_id": student_id}
        )
        record_id = cr.json()["id"]

        resp = await api_client.post(
            f"/api/reports/{record_id}/export",
            json={"template_id": "nonexistent_template"},
        )
        assert resp.status_code == 400

    async def test_export_default_template(self, api_client) -> None:
        """不指定 template_id 时使用 classic。"""
        student_id = await _create_student(api_client)
        cr = await api_client.post(
            "/api/reports",
            json={
                "student_id": student_id,
                "course_topic": "默认模板导出",
            },
        )
        record_id = cr.json()["id"]

        resp = await api_client.post(
            f"/api/reports/{record_id}/export",
            json={},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["template_id"] == "classic"

    async def test_export_all_templates(self, api_client) -> None:
        """所有内置模板导出都不出错。"""
        student_id = await _create_student(api_client)
        cr = await api_client.post(
            "/api/reports",
            json={
                "student_id": student_id,
                "course_topic": "多模板测试",
            },
        )
        record_id = cr.json()["id"]

        for tid in ("classic", "cartoon", "academic"):
            resp = await api_client.post(
                f"/api/reports/{record_id}/export",
                json={"template_id": tid},
            )
            assert resp.status_code == 200, f"模板 {tid} 导出失败: {resp.text}"
            assert resp.json()["template_id"] == tid

    async def test_export_updates_status(self, api_client) -> None:
        """导出后草稿状态变为 finalized。"""
        student_id = await _create_student(api_client)
        cr = await api_client.post(
            "/api/reports",
            json={"student_id": student_id, "course_topic": "状态测试"},
        )
        record_id = cr.json()["id"]
        assert cr.json()["status"] == "draft"

        await api_client.post(
            f"/api/reports/{record_id}/export",
            json={"template_id": "classic"},
        )

        get_resp = await api_client.get(f"/api/reports/{record_id}")
        assert get_resp.json()["status"] == "finalized"
