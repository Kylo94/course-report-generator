"""Word 文档导入解析服务：.docx → 结构化字段。

解析策略：
1. 按 Heading 1 分节匹配字段名
2. AI 辅助兜底：未识别段落调用 LLM 分类（可选）
3. 返回结构化 dict + 置信度
"""
from __future__ import annotations

import json
import re
from io import BytesIO
from typing import Any

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT

from backend.utils.logger import get_logger

log = get_logger(__name__)


class DocxImportError(Exception):
    """Word 文档解析失败。"""

    def __init__(self, message: str, original: Exception | None = None):
        self.original = original
        super().__init__(message)


# 字段名 → 中文标题映射（用于匹配 Heading 1）
FIELD_HEADINGS: dict[str, list[str]] = {
    "course_date": ["上课时间", "上课日期", "日期", "课程日期"],
    "course_topic": ["课程名称", "课程主题", "课程名", "课程标题", "主题"],
    "knowledge_points": ["知识点概括", "知识点", "知识点摘要", "学习知识点"],
    "ability_improvement": ["能力提升", "能力培养", "能力成长", "提升"],
    "content_items": ["内容概述", "课程内容", "内容详解", "教学内容", "内容"],
    "vocabulary": ["单词学习", "核心词汇", "词汇学习", "英语单词", "单词"],
    "homework": ["课后作业", "作业", "家庭作业", "练习"],
    "evaluation": ["学生评价", "评价", "教师评价", "评语", "老师评语"],
}

_field_name_to_key = {
    "基本信息": None,  # 特殊处理
}


def _match_heading(text: str) -> str | None:
    """匹配标题文本对应的字段 key。"""
    text = text.strip().replace(" ", "").replace("　", "")
    for key, headings in FIELD_HEADINGS.items():
        for h in headings:
            if text == h or text.startswith(h):
                return key
    return None


def _parse_basic_info(paragraphs: list) -> dict[str, Any]:
    """解析基本信息（项目文件夹等）。"""
    fields: dict[str, Any] = {}
    for para in paragraphs:
        text = para.text.strip()
        if "：" in text:
            label, _, value = text.partition("：")
            value = value.strip()
            if "上课时间" in label or "课程日期" in label:
                # 尝试提取 YYYY-MM-DD
                m = re.search(r"\d{4}-\d{2}-\d{2}", value)
                if m:
                    fields["course_date"] = m.group()
                else:
                    fields["course_date"] = value
            elif "学生姓名" in label or "姓名" in label:
                fields["_student_name"] = value
            elif "课程名称" in label or "课程主题" in label or "课程名" in label:
                fields["course_topic"] = value
    return fields


def _parse_knowledge_points(paragraphs: list) -> list[str]:
    """解析知识点列表（bullet points）。"""
    points = []
    for para in paragraphs:
        text = para.text.strip()
        if text:
            # 去掉 bullet 前缀
            text = text.lstrip("•·-*●◆▶▸").strip()
            if text:
                points.append(text)
    return points


def _parse_key_value_blocks(paragraphs: list) -> dict[str, str]:
    """解析键值对段落（如单词学习、基本信息）。"""
    result: dict[str, str] = {}
    for para in paragraphs:
        text = para.text.strip()
        if "：" in text:
            label, _, value = text.partition("：")
            result[label.strip()] = value.strip()
    return result


def _parse_content_items(paragraphs: list) -> list[dict[str, str]]:
    """解析内容概述块 → [{kp, text}]。"""
    items: list[dict[str, str]] = []
    for para in paragraphs:
        text = para.text.strip()
        if "：" in text:
            kp, _, detail = text.partition("：")
            items.append({"kp": kp.strip(), "text": detail.strip()})
        elif text:
            # 尝试按第一个空格或 tab 分割
            parts = text.split(None, 1)
            if len(parts) == 2:
                items.append({"kp": parts[0], "text": parts[1]})
            else:
                items.append({"kp": text[:20], "text": text})
    return items


def _parse_list_section(paragraphs: list) -> list[str]:
    """解析列表段落（提示、评分点等）。"""
    items = []
    for para in paragraphs:
        text = para.text.strip()
        if text:
            text = text.lstrip("•·-*●◆▶▸#0123456789)）、。").strip()
            if text:
                items.append(text)
    return items


def import_docx(docx_bytes: bytes, llm_provider=None) -> dict[str, Any]:
    """解析 docx 文件为结构化字段。

    Args:
        docx_bytes: .docx 文件二进制内容
        llm_provider: 可选的 LLMProvider 实例（用于 AI 辅助兜底）

    Returns:
        {
            "fields": { field_key: value },
            "unrecognized_sections": [section_text, ...],
            "confidence": 0.0-1.0
        }
    """
    try:
        buf = BytesIO(docx_bytes)
        doc = Document(buf)
    except Exception as e:
        raise DocxImportError(f"无法解析 docx 文件: {e}", original=e)

    fields: dict[str, Any] = {}
    unrecognized: list[str] = []
    total_sections = 0
    matched_sections = 0

    # 按 Heading 1 分节
    current_heading = None
    current_paras: list = []

    all_paragraphs = list(doc.paragraphs)

    def _flush_section():
        nonlocal current_heading, current_paras, total_sections, matched_sections
        if current_heading is None:
            current_paras = []
            return

        total_sections += 1
        heading_text = current_heading.text.strip()
        field_key = _match_heading(heading_text)

        if field_key is None and heading_text in ("基本信息",):
            # 基本信息 → 解析子字段
            info = _parse_basic_info(current_paras)
            for k, v in info.items():
                if k not in fields or v:
                    fields[k] = v
            matched_sections += 1
        elif field_key == "knowledge_points":
            vals = _parse_knowledge_points(current_paras)
            if vals:
                fields["knowledge_points"] = vals
            matched_sections += 1
        elif field_key == "content_items":
            vals = _parse_content_items(current_paras)
            if vals:
                fields["content_items"] = vals
            matched_sections += 1
        elif field_key == "vocabulary":
            kv = _parse_key_value_blocks(current_paras)
            vocab: dict[str, str] = {}
            for k, v in kv.items():
                if "单词" in k or "word" in k.lower() or "vocab" in k.lower():
                    vocab["word"] = v
                elif "音" in k or "phonetic" in k.lower() or "ph" in k.lower():
                    vocab["phonetic"] = v.strip("/")
                elif "释义" in k or "含义" in k or "意思" in k or "meaning" in k.lower():
                    vocab["meaning"] = v
                elif "例句" in k or "例子" in k or "example" in k.lower():
                    vocab["example"] = v
            if vocab:
                fields["vocabulary"] = vocab
            matched_sections += 1
        elif field_key == "homework":
            homework: dict[str, Any] = {"goal": "", "hints": [], "criteria": []}
            current_text = ""
            mode = None
            for para in current_paras:
                text = para.text.strip()
                if not text:
                    continue
                if text.startswith("目标") or text.startswith("goal") or "：" in text and text.split("：")[0] in ("目标", "Goal"):
                    label, _, val = text.partition("：")
                    homework["goal"] = val.strip()
                    mode = None
                elif text.startswith("提示") or "hint" in text.lower():
                    mode = "hints"
                elif text.startswith("评分") or "criteria" in text.lower() or "标准" in text:
                    mode = "criteria"
                elif mode == "hints":
                    homework["hints"].append(text.lstrip("•·-*●◆#0123456789)）、。").strip())
                elif mode == "criteria":
                    homework["criteria"].append(text.lstrip("•·-*●◆#0123456789)）、。").strip())
            if homework["goal"] or homework["hints"] or homework["criteria"]:
                fields["homework"] = homework
            matched_sections += 1
        elif field_key == "evaluation":
            evals = [p.text.strip() for p in current_paras if p.text.strip()]
            if evals:
                fields["evaluation"] = "\n".join(evals)
            matched_sections += 1
        elif field_key == "ability_improvement":
            texts = [p.text.strip() for p in current_paras if p.text.strip()]
            if texts:
                fields["ability_improvement"] = texts[0]
            matched_sections += 1
        else:
            # 未识别
            section_text = heading_text + "\n" + "\n".join(
                p.text.strip() for p in current_paras if p.text.strip()
            )
            unrecognized.append(section_text)

        current_paras = []

    for para in all_paragraphs:
        if para.style.name.startswith("Heading 1"):
            _flush_section()
            current_heading = para
        else:
            current_paras.append(para)
    _flush_section()

    # 计算置信度
    confidence = matched_sections / max(total_sections, 1)

    # AI 辅助兜底（可选）
    if llm_provider and unrecognized:
        try:
            ai_fields = _ai_assisted_parse(unrecognized, llm_provider)
            for k, v in ai_fields.items():
                if k not in fields or not fields.get(k):
                    fields[k] = v
            confidence = min(1.0, confidence + 0.1)
            unrecognized = []
        except Exception as e:
            log.warning("AI 辅助解析失败: %s", e)

    return {
        "fields": fields,
        "unrecognized_sections": unrecognized,
        "confidence": round(confidence, 2),
    }


def _ai_assisted_parse(
    unrecognized: list[str], llm_provider,
) -> dict[str, Any]:
    """使用 LLM 辅助解析未识别小节。"""
    prompt = {
        "role": "user",
        "content": (
            "以下是从课程报告 Word 文档中提取的未识别小节。"
            "请将它们映射到课程报告字段中（course_topic, course_date, knowledge_points, "
            "ability_improvement, content_items, vocabulary, homework, evaluation）。"
            "仅返回 JSON 对象。\n\n"
            + "\n---\n".join(unrecognized)
        ),
    }
    try:
        response = llm_provider.chat([prompt])
        # 尝试从响应中提取 JSON
        text = response.strip()
        # 查找 JSON 块
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    return {}
