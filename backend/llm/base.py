"""
LLM Provider 抽象基类

设计要点：
1. 屏蔽多家供应商差异
2. 返回 LangChain BaseChatModel 实例
3. 支持温度参数、连接测试
4. 便于单测时 mock

使用流程：
    provider = get_provider(config.llm)
    chat = provider.get_chat_model(temperature=0.5)
    response = chat.invoke([...])
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from langchain_core.language_models import BaseChatModel

from backend.config import LLMConfig
from backend.utils.logger import get_logger

log = get_logger(__name__)


class LLMProvider(ABC):
    """LLM 供应商抽象基类。"""

    name: str

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    def get_chat_model(self, temperature: float = 0.5) -> BaseChatModel:
        """
        返回一个 LangChain BaseChatModel 实例。

        调用方可直接使用 LangChain 的 invoke/stream/batch 等接口。
        """
        ...

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """
        测试 API 连通性。

        Returns:
            (success, message) - 成功时 message 为空，失败时为错误信息
        """
        ...


class LLMProviderError(Exception):
    """LLM Provider 错误。"""

    def __init__(self, message: str, provider: str | None = None):
        self.provider = provider
        super().__init__(message)


# 各供应商的默认 base_url（用户可在 llm.yaml 覆盖）
DEFAULT_BASE_URLS: dict[str, str] = {
    "minimax": "https://api.minimax.chat/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4",
    "openai": "https://api.openai.com/v1",
}


def get_provider(config: LLMConfig) -> LLMProvider:
    """
    Provider 工厂：基于 config.provider 选择具体实现。

    支持：
      - deepseek：DeepSeek 官方（独立实现）
      - minimax：MiniMax（OpenAI 兼容）
      - openai / qwen / glm：OpenAI 兼容协议
      - claude：Anthropic 官方
    """
    from backend.llm.providers.claude import ClaudeProvider
    from backend.llm.providers.deepseek import DeepSeekProvider
    from backend.llm.providers.openai_compat import OpenAICompatProvider

    name = config.provider.lower()
    log.info("创建 LLM Provider: %s model=%s", name, config.default_model)

    if name == "deepseek":
        return DeepSeekProvider(config)

    if name == "claude":
        return ClaudeProvider(config)

    # OpenAI 兼容族
    if name in DEFAULT_BASE_URLS:
        return OpenAICompatProvider(
            config,
            name=name,
            base_url=config.base_url or DEFAULT_BASE_URLS[name],
        )

    raise LLMProviderError(f"不支持的 LLM 供应商: {name}", provider=name)
