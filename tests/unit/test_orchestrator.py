"""AI Orchestrator 单元测试。"""
from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from backend.config import LLMConfig
from backend.llm.base import LLMProvider
from backend.schemas.project import (
    FileInfoSchema,
    ProjectMetaSchema,
    PyStructureSchema,
)
from backend.schemas.student import StudentRead
from backend.services.ai_orchestrator import (
    STEP_FIELDS,
    AIOrchestrator,
    GenerationResult,
)


# =========================
# Scripted Mock Provider
# =========================
def _make_scripted_runnable(scripts: dict[str, str]) -> RunnableLambda:
    """
    创建一个 Runnable Lambda，根据输入内容的关键字返回不同响应。

    输入通常是 ChatPromptValue（含 str 形式），转换为字符串后做关键字匹配。
    """
    state = {"calls": []}

    def _fn(payload: Any) -> AIMessage:
        state["calls"].append(payload)
        text = str(payload)
        for keyword, response in scripts.items():
            if keyword in text:
                return AIMessage(content=response)
        return AIMessage(content="{}")

    runnable = RunnableLambda(_fn)
    runnable._state = state  # type: ignore[attr-defined]
    return runnable


class _ScriptedProvider(LLMProvider):
    """根据 prompt 关键字返回不同响应的 Provider。"""

    def __init__(self, scripts: dict[str, str]):
        cfg = LLMConfig(api_key="test", default_model="mock")
        super().__init__(cfg)
        self.scripts = scripts
        self._models: list[RunnableLambda] = []
        self.name = "mock"

    def get_chat_model(self, temperature: float = 0.5) -> RunnableLambda:
        model = _make_scripted_runnable(self.scripts)
        self._models.append(model)
        return model

    def test_connection(self) -> tuple[bool, str]:
        return True, ""


def _make_project(course_title: str = "测试课") -> ProjectMetaSchema:
    return ProjectMetaSchema(
        folder="/tmp/proj",
        entry_file="main.py",
        project_type="pygame",
        course_title=course_title,
        all_files=[
            FileInfoSchema(
                path="main.py", name="main.py", is_python=True, size_bytes=100
            )
        ],
        py_files=[
            PyStructureSchema(
                path="main.py",
                imports=["pygame"],
                from_imports=[],
                function_names=["main"],
                class_names=["Bird"],
                decorators=[],
                top_comment="# Course: 测试课",
                course_title="测试课",
                line_count=10,
            )
        ],
        all_imports=["pygame"],
        total_lines=10,
        warnings=[],
    )


def _make_student(name: str = "小明") -> StudentRead:
    return StudentRead(
        id=1,
        name=name,
        age=10,
        gender="男",
        grade="三年级",
        base_level="入门",
        characteristics=["内向"],
        parent_contact=None,
        note=None,
        class_id=None,
        created_at="2026-06-29T00:00:00",
        updated_at="2026-06-29T00:00:00",
    )


# =========================
# 测试
# =========================
@pytest.mark.asyncio
class TestGenerateAll:
    async def test_success_all_steps(self) -> None:
        provider = _ScriptedProvider({
            "学生能力提升": json.dumps(
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
        })
        orch = AIOrchestrator(provider)
        result = await orch.generate_all(_make_project(), _make_student())
        assert isinstance(result, GenerationResult)
        assert len(result.knowledge_points) == 5  # 不足 5 条时补齐
        assert len(result.content_items) == 2
        assert result.ability_improvement == "逻辑思维提升"
        assert "小明" in result.evaluation
        assert result.errors == {}

    async def test_step1_failure_recorded(self) -> None:
        provider = _ScriptedProvider({})  # 空响应 → 解析失败
        orch = AIOrchestrator(provider)
        result = await orch.generate_all(_make_project(), _make_student())
        assert result.knowledge_points == []
        assert "knowledge_points" in result.errors

    async def test_step_continues_after_step3_failure(self) -> None:
        """Step 3 失败不应阻止 Step 4 执行。"""
        provider = _ScriptedProvider({
            "学生能力提升": json.dumps(
                ["print 使用"], ensure_ascii=False
            ),
            "为家长写一段课程内容概述": json.dumps({
                "content_items": [{"kp": "print", "text": "x" * 70}],
                "ability_improvement": "x",
            }, ensure_ascii=False),
            "为该学生写": "评价成功",
        })
        orch = AIOrchestrator(provider)
        result = await orch.generate_all(_make_project(), _make_student())
        # 即使 step3（homework_vocab）脚本里没有，evaluation 应成功
        assert "评价成功" in result.evaluation
        # step3 应有错误（因为没有匹配的脚本）
        assert "homework_vocab" in result.errors or result.homework == {}


@pytest.mark.asyncio
class TestRegenerateOne:
    async def test_knowledge_points(self) -> None:
        provider = _ScriptedProvider({
            "学生能力提升": json.dumps(
                ["新知识点1", "新知识点2"], ensure_ascii=False
            ),
        })
        orch = AIOrchestrator(provider)
        result = await orch.regenerate_one(
            "knowledge_points", _make_project(), _make_student()
        )
        assert result == ["新知识点1", "新知识点2", "for 循环强化重复思维", "函数定义培养分解能力", "调试代码提升排查技能"]

    async def test_evaluation(self) -> None:
        provider = _ScriptedProvider({
            "为该学生写": "新的评价内容，180字以上...",
        })
        orch = AIOrchestrator(provider)
        result = await orch.regenerate_one(
            "evaluation", _make_project(), _make_student()
        )
        assert "评价内容" in result

    async def test_invalid_field_raises(self) -> None:
        provider = _ScriptedProvider({})
        orch = AIOrchestrator(provider)
        with pytest.raises(ValueError, match="未知字段"):
            await orch.regenerate_one(
                "invalid_field", _make_project(), _make_student()
            )


class TestStepFields:
    def test_step_fields_constant(self) -> None:
        assert STEP_FIELDS == [
            "knowledge_points",
            "content_summary",
            "homework_vocab",
            "evaluation",
        ]


class TestBuildCodeContent:
    def test_includes_entry_and_others(self) -> None:
        provider = _ScriptedProvider({})
        orch = AIOrchestrator(provider)
        project = _make_project()
        content = orch._build_code_content(project)
        # entry file 的注释应被包含
        assert "测试课" in content or "imports:" in content
