"""
AI 子链定义（LangChain Runnable）

设计要点：
- 每个子能力是一个独立的 Runnable，可单独 invoke/stream
- 输入是字典，输出是字符串或解析后的 Python 对象
- 顶层 Orchestrator 负责串联，不在 chain 内部做编排
"""
from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from backend.llm.base import LLMProvider
from backend.llm.prompts import (
    CODE_ANALYSIS_PROMPT,
    CONTENT_SUMMARY_PROMPT,
    EVALUATION_PROMPT,
    HOMEWORK_VOCAB_PROMPT,
    KNOWLEDGE_POINTS_PROMPT,
)
from backend.utils.logger import get_logger

log = get_logger(__name__)


# =========================
# 工具：JSON 解析（容错）
# =========================
def _extract_json(text: str) -> Any:
    """
    从 LLM 响应中提取 JSON。
    容错策略：去掉 markdown 围栏 + 找首个 {/[ 到末个 }/] 的内容。
    """
    # 去掉 ```json ... ``` 围栏
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)

    # 尝试整体解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 提取首个 JSON 块
    for opener, closer in [("{", "}"), ("[", "]")]:
        start = text.find(opener)
        if start < 0:
            continue
        # 找匹配的末尾（粗略用末个 closer）
        end = text.rfind(closer)
        if end <= start:
            continue
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    raise ValueError(f"无法从 LLM 响应解析 JSON: {text[:200]}")


# =========================
# 工厂：按字段名获取 Runnable
# =========================
def build_chains(provider: LLMProvider) -> dict[str, Runnable]:
    """
    构建 5 个子链（代码分析 + 4 个生成链），返回 dict[field_name, Runnable]。

    每个 chain 是 prompt | llm | output_parser 的标准 LCEL 组合。
    """
    temps = provider.config.temperature

    # 代码分析链：输出 JSON 对象
    ca_prompt = ChatPromptTemplate.from_template(CODE_ANALYSIS_PROMPT)
    ca_chain = ca_prompt | provider.get_chat_model(
        temperature=temps.get("code_analysis", 0.2)
    ) | StrOutputParser() | _extract_json  # type: ignore[arg-type]

    # 知识点链：输出 JSON 列表
    kp_prompt = ChatPromptTemplate.from_template(KNOWLEDGE_POINTS_PROMPT)
    kp_chain = kp_prompt | provider.get_chat_model(
        temperature=temps.get("knowledge_points", 0.3)
    ) | StrOutputParser() | _extract_json  # type: ignore[arg-type]

    # 内容概述链：输出 JSON 对象
    cs_prompt = ChatPromptTemplate.from_template(CONTENT_SUMMARY_PROMPT)
    cs_chain = cs_prompt | provider.get_chat_model(
        temperature=temps.get("content_summary", 0.5)
    ) | StrOutputParser() | _extract_json  # type: ignore[arg-type]

    # 作业 + 单词链：输出 JSON 对象
    hw_prompt = ChatPromptTemplate.from_template(HOMEWORK_VOCAB_PROMPT)
    hw_chain = hw_prompt | provider.get_chat_model(
        temperature=temps.get("homework", 0.5)
    ) | StrOutputParser() | _extract_json  # type: ignore[arg-type]

    # 学生评价链：输出纯文本
    ev_prompt = ChatPromptTemplate.from_template(EVALUATION_PROMPT)
    ev_chain = ev_prompt | provider.get_chat_model(
        temperature=temps.get("evaluation", 0.9)
    ) | StrOutputParser()

    chains = {
        "code_analysis": ca_chain,
        "knowledge_points": kp_chain,
        "content_summary": cs_chain,
        "homework_vocab": hw_chain,
        "evaluation": ev_chain,
    }
    log.info("已构建 %d 个子链（代码分析 + 4 个生成链）", len(chains))
    return chains


# =========================
# 流式版本（用于 WebSocket 推送）
# =========================
def build_streaming_chains(provider: LLMProvider) -> dict[str, Runnable]:
    """
    构建流式子链（不挂 OutputParser，直接返回 LLM token 流）。

    使用方法：
        for chunk in chain.stream({"...": "..."}):
            # chunk 是字符串片段
    """
    temps = provider.config.temperature

    kp_prompt = ChatPromptTemplate.from_template(KNOWLEDGE_POINTS_PROMPT)
    cs_prompt = ChatPromptTemplate.from_template(CONTENT_SUMMARY_PROMPT)
    hw_prompt = ChatPromptTemplate.from_template(HOMEWORK_VOCAB_PROMPT)
    ev_prompt = ChatPromptTemplate.from_template(EVALUATION_PROMPT)

    return {
        "knowledge_points": kp_prompt | provider.get_chat_model(
            temperature=temps.get("knowledge_points", 0.3)
        ),
        "content_summary": cs_prompt | provider.get_chat_model(
            temperature=temps.get("content_summary", 0.5)
        ),
        "homework_vocab": hw_prompt | provider.get_chat_model(
            temperature=temps.get("homework", 0.5)
        ),
        "evaluation": ev_prompt | provider.get_chat_model(
            temperature=temps.get("evaluation", 0.9)
        ),
    }
