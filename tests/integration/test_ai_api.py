"""AI 生成 API 集成测试（用 mock 避免真实 API 调用）。"""
from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

pytestmark = pytest.mark.asyncio


# =========================
# Mock Provider 全局 patch
# =========================
def _make_mock_runnable_factory(scripts: dict[str, str]):
    """创建一个能根据 prompt 返回不同响应的 Provider 工厂。"""
    from backend.config import LLMConfig
    from backend.llm.base import LLMProvider

    class _MockProvider(LLMProvider):
        def __init__(self):
            cfg = LLMConfig(
                api_key="test",
                default_model="mock",
                temperature={
                    "knowledge_points": 0.3,
                    "content_summary": 0.5,
                    "homework": 0.5,
                    "evaluation": 0.9,
                },
            )
            super().__init__(cfg)
            self.name = "mock"

        def get_chat_model(self, temperature: float = 0.5):
            def _fn(payload: Any) -> AIMessage:
                text = str(payload)
                for keyword, response in scripts.items():
                    if keyword in text:
                        return AIMessage(content=response)
                return AIMessage(content="{}")

            return RunnableLambda(_fn)

        def test_connection(self):
            return True, ""

    return _MockProvider


@pytest.fixture
def mock_ai(monkeypatch: pytest.MonkeyPatch):
    """替换 get_provider 为 mock。"""
    from backend.api import ai as ai_api
    from backend.llm import base
    from backend.services import ai_orchestrator

    scripts = {
        "提取本节课涉及的": json.dumps(
            ["print 使用", "if 分支"], ensure_ascii=False
        ),
        "为家长写一段课程内容概述": json.dumps({
            "content_items": [
                {"kp": "print", "text": "x" * 70},
                {"kp": "if", "text": "y" * 70},
            ],
            "ability_improvement": "逻辑思维提升",
        }, ensure_ascii=False),
        "为该学生写": "小明今天在实现 print 函数时，能跟随老师的节奏...",
        "课后作业": json.dumps({
            "homework": {
                "goal": "练习 if",
                "hints": ["提示1", "提示2"],
                "criteria": ["能运行", "结果正确"],
            },
            "vocabulary": {
                "word": "Branch",
                "phonetic": "/bræntʃ/",
                "meaning": "分支",
                "example": "if branch:",
            },
        }, ensure_ascii=False),
    }
    factory = _make_mock_runnable_factory(scripts)

    def _get_provider(*args, **kwargs):
        return factory()

    monkeypatch.setattr(base, "get_provider", _get_provider)
    monkeypatch.setattr(ai_orchestrator, "get_provider", _get_provider)
    monkeypatch.setattr(ai_api, "get_provider", _get_provider)
    return scripts


def _make_project_dict() -> dict:
    return {
        "folder": "/tmp/proj",
        "entry_file": "main.py",
        "project_type": "pygame",
        "course_title": "测试课",
        "all_files": [
            {
                "path": "main.py",
                "name": "main.py",
                "is_python": True,
                "size_bytes": 100,
            }
        ],
        "py_files": [
            {
                "path": "main.py",
                "imports": ["pygame"],
                "from_imports": [],
                "function_names": ["main"],
                "class_names": ["Bird"],
                "decorators": [],
                "top_comment": "# Course: 测试课",
                "course_title": "测试课",
                "line_count": 10,
            }
        ],
        "all_imports": ["pygame"],
        "total_lines": 10,
        "warnings": [],
    }


class TestProviders:
    async def test_list_providers(self, api_client) -> None:
        resp = await api_client.get("/api/ai/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert "deepseek" in data
        assert "minimax" in data
        assert "claude" in data
        assert "qwen" in data
        assert "glm" in data
        assert "openai" in data

    async def test_test_connection_with_mock(
        self, api_client, mock_ai
    ) -> None:
        resp = await api_client.post("/api/ai/test-connection")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


class TestGenerate:
    async def test_generate_all(self, api_client, mock_ai) -> None:
        # 先建学生
        student_resp = await api_client.post(
            "/api/students", json={"name": "小明", "age": 10}
        )
        student_id = student_resp.json()["id"]

        resp = await api_client.post(
            "/api/ai/generate",
            json={
                "project": _make_project_dict(),
                "student_id": student_id,
                "teacher_observation": "表现良好",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["student_id"] == student_id
        assert data["errors"] == {}
        content = data["content"]
        assert len(content["knowledge_points"]) == 2
        assert "能力提升" in content["ability_improvement"] or "逻辑" in content["ability_improvement"]
        assert len(content["content_items"]) == 2
        assert content["homework"]["goal"] == "练习 if"
        assert content["vocabulary"]["word"] == "Branch"
        assert "小明" in content["evaluation"]

    async def test_generate_student_not_found(
        self, api_client, mock_ai
    ) -> None:
        resp = await api_client.post(
            "/api/ai/generate",
            json={
                "project": _make_project_dict(),
                "student_id": 9999,
            },
        )
        assert resp.status_code == 404

    async def test_generate_invalid_request(
        self, api_client, mock_ai
    ) -> None:
        # 缺 student_id 字段
        resp = await api_client.post(
            "/api/ai/generate", json={"project": _make_project_dict()}
        )
        assert resp.status_code == 422


class TestRegenerate:
    async def test_regenerate_kp(self, api_client, mock_ai) -> None:
        # 建学生
        student_resp = await api_client.post(
            "/api/students", json={"name": "小红"}
        )
        student_id = student_resp.json()["id"]

        resp = await api_client.post(
            "/api/ai/regenerate",
            json={
                "project": _make_project_dict(),
                "student_id": student_id,
                "field": "knowledge_points",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["field"] == "knowledge_points"
        assert isinstance(data["value"], list)
        assert len(data["value"]) == 2

    async def test_regenerate_invalid_field(
        self, api_client, mock_ai
    ) -> None:
        student_resp = await api_client.post(
            "/api/students", json={"name": "测试"}
        )
        student_id = student_resp.json()["id"]

        resp = await api_client.post(
            "/api/ai/regenerate",
            json={
                "project": _make_project_dict(),
                "student_id": student_id,
                "field": "invalid_field",
            },
        )
        assert resp.status_code == 400

    async def test_regenerate_evaluation(self, api_client, mock_ai) -> None:
        student_resp = await api_client.post(
            "/api/students", json={"name": "小红"}
        )
        student_id = student_resp.json()["id"]

        resp = await api_client.post(
            "/api/ai/regenerate",
            json={
                "project": _make_project_dict(),
                "student_id": student_id,
                "field": "evaluation",
                "teacher_observation": "今天很专注",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["field"] == "evaluation"
        assert "小明" in data["value"]  # mock 中返回的固定文本
