"""通用 OpenAI 兼容协议 Provider（支持多家）。"""
from __future__ import annotations

from langchain_openai import ChatOpenAI

from backend.config import LLMConfig
from backend.llm.base import LLMProvider


class OpenAICompatProvider(LLMProvider):
    """
    通用 OpenAI 兼容协议 Provider。

    适用于：
    - minimax（MiniMax 模型，OpenAI 兼容协议）
    - qwen（通义千问，DashScope 兼容模式）
    - glm（智谱 AI）
    - 其他 OpenAI 兼容 API
    """

    def __init__(self, config: LLMConfig, name: str, base_url: str):
        super().__init__(config)
        self.name = name
        self._base_url = base_url

    def get_chat_model(self, temperature: float = 0.5) -> ChatOpenAI:
        return ChatOpenAI(
            model=self.config.default_model,
            api_key=self.config.api_key,
            base_url=self.config.base_url or self._base_url,
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
