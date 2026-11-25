"""C/C++ 支持相关测试（代码分析 + AI 语言配置）。"""
from __future__ import annotations

from backend.services.ai_conversation import AIConversation


class TestCppAIConversation:
    def test_language_label(self) -> None:
        assert AIConversation(None, language="cpp").language_label == "C++"
        assert AIConversation(None, language="c").language_label == "C"
        assert AIConversation(None, language="python").language_label == "Python"

    def test_extract_cpp_code_refs(self) -> None:
        code = """
#include <iostream>
class Character {
public:
    void attack(int dmg) { hp -= dmg; }
    int hp = 100;
};
int add(int a, int b) { return a + b; }
int main() { std::cout << add(1, 2); return 0; }
"""
        refs = AIConversation._extract_code_refs(code)
        assert "add" in refs
        assert "Character" in refs
        assert "iostream" in refs
        assert "attack" in refs


class TestOrchestratorLanguage:
    def test_make_conversation_uses_project_language(self) -> None:
        from types import SimpleNamespace

        from backend.services.ai_orchestrator import AIOrchestrator

        orch = AIOrchestrator(provider=SimpleNamespace())
        cpp_conv = orch._make_conversation(SimpleNamespace(language="cpp"))
        py_conv = orch._make_conversation(SimpleNamespace(language="python"))
        assert cpp_conv.language_label == "C++"
        assert py_conv.language_label == "Python"
