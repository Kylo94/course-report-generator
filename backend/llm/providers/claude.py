"""Claude Provider（Anthropic）。"""
from __future__ import annotations

from langchain_anthropic import ChatAnthropic

from backend.llm.base import LLMProvider


class ClaudeProvider(LLMProvider):
    """Anthropic Claude 官方 API。"""

    name = "claude"

    def get_chat_model(self, temperature: float = 0.5) -> ChatAnthropic:
        return ChatAnthropic(
            model=self.config.default_model,
            api_key=self.config.api_key,
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
