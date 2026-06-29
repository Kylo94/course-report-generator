"""
Prompt 模板集合

所有模板的输入变量都用 Python 字符串 format 风格，{var} 占位符。
每个模板只负责"提问 + 格式约束"，不依赖 LLM 类型。
"""
from backend.llm.prompts.content_summary import CONTENT_SUMMARY_PROMPT
from backend.llm.prompts.evaluation import EVALUATION_PROMPT
from backend.llm.prompts.homework import HOMEWORK_VOCAB_PROMPT
from backend.llm.prompts.knowledge_points import KNOWLEDGE_POINTS_PROMPT

__all__ = [
    "CONTENT_SUMMARY_PROMPT",
    "EVALUATION_PROMPT",
    "HOMEWORK_VOCAB_PROMPT",
    "KNOWLEDGE_POINTS_PROMPT",
]
