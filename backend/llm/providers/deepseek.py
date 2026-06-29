"""DeepSeek Provider（OpenAI 兼容协议）。"""
from __future__ import annotations

from langchain_openai import ChatOpenAI

from backend.llm.base import LLMProvider


class DeepSeekProvider(LLMProvider):
    """DeepSeek 官方 API（OpenAI 兼容）。"""

    name = "deepseek"

    DEFAULT_BASE_URL = "https://api.deepseek.com/v1"

    def get_chat_model(self, temperature: float = 0.5) -> ChatOpenAI:
        return ChatOpenAI(
            model=self.config.default_model,
            api_key=self.config.api_key,
            base_url=self.config.base_url or self.DEFAULT_BASE_URL,
            temperature=temperature,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
        )

    def test_connection(self) -> tuple[bool, str]:
        if not self.config.api_key:
            return False, "API Key 未设置"
        try:
            chat = self.get_chat_model(temperature=0)
            chat.invoke("ping")
            return True, ""
        except Exception as e:
            return False, str(e)
