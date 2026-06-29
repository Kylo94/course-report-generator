"""AI 组件单元测试（使用 Mock LLM 避免真实 API 调用）。"""
from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from backend.config import LLMConfig
from backend.llm.base import LLMProvider, LLMProviderError, get_provider
from backend.llm.providers.openai_compat import OpenAICompatProvider
from backend.services.ai_chains import _extract_json, build_chains


# =========================
# Mock Provider
# =========================
def _make_mock_runnable(responses: list[str]) -> RunnableLambda:
    """
    创建一个 Runnable Lambda，按顺序返回预设 AIMessage 响应。

    AIMessage 是 LangChain 标准 chat 输出，可被 StrOutputParser 正确解析。
    """
    state = {"responses": list(responses), "calls": []}

    def _fn(payload: Any) -> AIMessage:
        state["calls"].append(payload)
        if not state["responses"]:
            return AIMessage(content="{}")
        text = state["responses"].pop(0)
        return AIMessage(content=text)

    runnable = RunnableLambda(_fn)
    runnable._state = state  # type: ignore[attr-defined]
    return runnable


class MockProvider(LLMProvider):
    """测试用 Provider，返回 Runnable Lambda 作为 chat model。"""

    def __init__(self, responses: dict[str, str] | None = None):
        cfg = LLMConfig(api_key="test-fake-key", default_model="mock-model")
        super().__init__(cfg)
        self.responses = responses or {}
        self.created_models: list[RunnableLambda] = []

    def get_chat_model(self, temperature: float = 0.5) -> RunnableLambda:
        responses = list(self.responses.values())
        model = _make_mock_runnable(responses)
        self.created_models.append(model)
        return model

    def test_connection(self) -> tuple[bool, str]:
        return True, ""


# =========================
# _extract_json 测试
# =========================
class TestExtractJson:
    def test_plain_list(self) -> None:
        assert _extract_json('["a", "b"]') == ["a", "b"]

    def test_plain_dict(self) -> None:
        assert _extract_json('{"a": 1}') == {"a": 1}

    def test_markdown_wrapped(self) -> None:
        text = '```json\n["a", "b"]\n```'
        assert _extract_json(text) == ["a", "b"]

    def test_with_surrounding_text(self) -> None:
        text = '好的，结果如下：\n["a", "b"]\n希望对你有帮助'
        assert _extract_json(text) == ["a", "b"]

    def test_nested_dict(self) -> None:
        text = '{"homework": {"goal": "test", "hints": ["a", "b"]}}'
        result = _extract_json(text)
        assert result["homework"]["goal"] == "test"
        assert result["homework"]["hints"] == ["a", "b"]

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="无法从 LLM 响应解析 JSON"):
            _extract_json("not json at all")

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            _extract_json("")


# =========================
# get_provider 工厂测试
# =========================
class TestGetProvider:
    def test_deepseek(self) -> None:
        cfg = LLMConfig(provider="deepseek", api_key="test")
        p = get_provider(cfg)
        assert isinstance(p, OpenAICompatProvider) or p.name == "deepseek"

    def test_minimax(self) -> None:
        cfg = LLMConfig(provider="minimax", api_key="test")
        p = get_provider(cfg)
        assert p.name == "minimax"

    def test_qwen(self) -> None:
        cfg = LLMConfig(provider="qwen", api_key="test")
        p = get_provider(cfg)
        assert p.name == "qwen"

    def test_glm(self) -> None:
        cfg = LLMConfig(provider="glm", api_key="test")
        p = get_provider(cfg)
        assert p.name == "glm"

    def test_openai(self) -> None:
        cfg = LLMConfig(provider="openai", api_key="test")
        p = get_provider(cfg)
        assert p.name == "openai"

    def test_unknown_raises(self) -> None:
        cfg = LLMConfig(provider="unknown_xyz")
        with pytest.raises(LLMProviderError, match="不支持"):
            get_provider(cfg)

    def test_provider_name_case_insensitive(self) -> None:
        cfg = LLMConfig(provider="DeepSeek", api_key="test")
        p = get_provider(cfg)
        assert p.name == "deepseek"


# =========================
# build_chains 测试（带 mock）
# =========================
class TestBuildChains:
    def test_builds_four_chains(self) -> None:
        provider = MockProvider()
        chains = build_chains(provider)
        assert len(chains) == 4
        assert "knowledge_points" in chains
        assert "content_summary" in chains
        assert "homework_vocab" in chains
        assert "evaluation" in chains

    def test_kp_chain_parses_list(self) -> None:
        provider = MockProvider(
            responses={
                "kp": '["print 使用", "if 分支", "for 循环"]',
            }
        )
        chains = build_chains(provider)
        result = chains["knowledge_points"].invoke({
            "code_content": "print('hi')",
            "course_topic": "test",
            "project_type": "cli",
        })
        assert result == ["print 使用", "if 分支", "for 循环"]

    def test_content_summary_chain_parses_dict(self) -> None:
        provider = MockProvider(
            responses={
                "cs": json.dumps({
                    "content_items": [
                        {"kp": "print", "text": "test1"},
                        {"kp": "if", "text": "test2"},
                    ],
                    "ability_improvement": "逻辑思维提升",
                }, ensure_ascii=False),
            }
        )
        chains = build_chains(provider)
        result = chains["content_summary"].invoke({
            "knowledge_points": "print, if",
            "code_content": "x = 1",
            "project_type": "cli",
        })
        assert "content_items" in result
        assert len(result["content_items"]) == 2
        assert result["ability_improvement"] == "逻辑思维提升"

    def test_homework_chain_parses_dict(self) -> None:
        provider = MockProvider(
            responses={
                "hw": json.dumps({
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
        )
        chains = build_chains(provider)
        result = chains["homework_vocab"].invoke({
            "knowledge_points": "if",
            "code_content": "print('hello')\nif x > 5:",
            "project_type": "cli",
            "student_level": "入门",
        })
        assert result["homework"]["goal"] == "练习 if"
        assert result["vocabulary"]["word"] == "Branch"

    def test_evaluation_chain_returns_text(self) -> None:
        provider = MockProvider(
            responses={
                "ev": "小明今天学习很认真，完成了所有练习。",
            }
        )
        chains = build_chains(provider)
        result = chains["evaluation"].invoke({
            "student_name": "小明",
            "student_age": 10,
            "student_level": "入门",
            "student_characteristics": "内向",
            "course_topic": "if 语句",
            "knowledge_points": "if, else",
            "code_content": "print('hello')\nif x > 5:",
            "teacher_observation": "（无）",
        })
        assert isinstance(result, str)
        assert "小明" in result


# =========================
# Prompt 模板测试
# =========================
class TestPrompts:
    def test_knowledge_points_has_placeholders(self) -> None:
        from backend.llm.prompts import KNOWLEDGE_POINTS_PROMPT
        assert "{code_content}" in KNOWLEDGE_POINTS_PROMPT
        assert "{course_topic}" in KNOWLEDGE_POINTS_PROMPT
        assert "{project_type}" in KNOWLEDGE_POINTS_PROMPT

    def test_content_summary_has_placeholders(self) -> None:
        from backend.llm.prompts import CONTENT_SUMMARY_PROMPT
        assert "{knowledge_points}" in CONTENT_SUMMARY_PROMPT
        assert "{ability_improvement}" in CONTENT_SUMMARY_PROMPT or "ability" in CONTENT_SUMMARY_PROMPT

    def test_homework_has_placeholders(self) -> None:
        from backend.llm.prompts import HOMEWORK_VOCAB_PROMPT
        assert "{student_level}" in HOMEWORK_VOCAB_PROMPT

    def test_evaluation_has_placeholders(self) -> None:
        from backend.llm.prompts import EVALUATION_PROMPT
        assert "{student_name}" in EVALUATION_PROMPT
        assert "{course_topic}" in EVALUATION_PROMPT

    def test_prompts_renderable(self) -> None:
        """所有 prompt 应能用 sample 输入正常渲染（不抛错）。"""
        from backend.llm.prompts import (
            CONTENT_SUMMARY_PROMPT,
            EVALUATION_PROMPT,
            HOMEWORK_VOCAB_PROMPT,
            KNOWLEDGE_POINTS_PROMPT,
        )
        KNOWLEDGE_POINTS_PROMPT.format(
            code_content="x = 1", course_topic="test", project_type="cli"
        )
        CONTENT_SUMMARY_PROMPT.format(
            knowledge_points="a, b", code_content="x = 1", project_type="cli"
        )
        HOMEWORK_VOCAB_PROMPT.format(
            knowledge_points="a",
            code_content="x = 1",
            project_type="cli",
            student_level="入门",
        )
        EVALUATION_PROMPT.format(
            student_name="x",
            student_age=10,
            student_level="入门",
            student_characteristics="",
            course_topic="test",
            knowledge_points="a, b",
            code_content="x = 1",
            teacher_observation="",
        )


# =========================
# 真实 Provider 类测试（不实际调用）
# =========================
class TestProviderClasses:
    def test_deepseek_test_no_api_key(self) -> None:
        from backend.llm.providers.deepseek import DeepSeekProvider
        cfg = LLMConfig(api_key="")
        p = DeepSeekProvider(cfg)
        ok, msg = p.test_connection()
        assert ok is False
        assert "API Key" in msg

    def test_openai_compat_test_no_api_key(self) -> None:
        cfg = LLMConfig(api_key="")
        p = OpenAICompatProvider(cfg, name="test", base_url="http://x")
        ok, msg = p.test_connection()
        assert ok is False

    def test_minimax_default_url(self) -> None:
        cfg = LLMConfig(provider="minimax", api_key="test")
        p = get_provider(cfg)
        assert "minimax" in p._base_url.lower()
