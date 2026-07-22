"""
对话式 AI 生成（带记忆）

用 LangChain 消息历史做"记忆"，一次读完代码后所有步骤共享同一段对话上下文。

架构：
  第一轮：AI 读代码 → 记住所有函数和行号
  后续轮：每一步都是基于记忆的新提问，不再传原始代码
  重生成：基于已有记忆重新提问，不重复读盘

优势：
  - 每一轮 LLM 都保有完整代码上下文，不会信息丢失
  - 不会因为 _format_analysis() 的摘要遗漏而编造函数
  - 所有生成内容全部围绕真实代码
"""
from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from backend.llm.base import LLMProvider
from backend.utils.logger import get_logger

log = get_logger(__name__)


def _strip_think_blocks(text: str) -> str:
    """去掉推理模型输出的 <think>...</think> 块，返回剩余文本。"""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json(text: str) -> Any:
    """从 LLM 响应中提取 JSON（容错）。

    兼容：
    - 推理模型的 <think>...</think> 思考块（去掉后再解析）
    - ```json ... ``` markdown 包装
    - 前后有多余文本
    """
    # 1. 去掉 <think>...</think> 思考块
    text = _strip_think_blocks(text)
    if not text:
        raise ValueError("LLM 响应只有思考块，没有实际内容")
    if not text:
        raise ValueError("LLM 响应只有思考块，没有实际内容")
    # 2. 去掉 markdown ```json / ``` 包装
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start < 0:
            continue
        end = text.rfind(closer)
        if end <= start:
            continue
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"无法从 LLM 响应解析 JSON: {text[:200]}")


def _empty_analysis(course_topic: str = "") -> dict:
    return {
        "course_topic": course_topic,
        "main_objectives": [],
        "key_functions": [],
        "python_techniques": [],
    }


# =========================
# 各步骤的温度配置
# =========================
TEMPS = {
    "read_code": 0.2,
    "knowledge_points": 0.3,
    "content_summary": 0.5,
    "homework_vocab": 0.5,
    "evaluation": 0.9,
    "code_excerpt": 0.2,
}


class AIConversation:
    """一次对话式 AI 生成会话。

    用法:
        conv = AIConversation(provider)
        analysis = await conv.step_read_code(code, comment, ...)
        kp = await conv.step_knowledge_points(...)
        items, ability = await conv.step_content_summary(...)
        hw, vocab = await conv.step_homework_vocab(...)
        evaluation = await conv.step_evaluation(...)
        excerpts = await conv.step_code_excerpt(...)

    "记忆" = self.messages（list[BaseMessage]），每次 _call 追加一对 Human/AI。
    """

    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self.messages: list = []
        self.outputs: dict[str, Any] = {}
        self._code_refs: str = ""

    @staticmethod
    def _extract_code_refs(code: str) -> str:
        """从源码中提取实际调用的函数、API、方法和属性，用于约束 AI 后续步骤不编造。

        提取三类内容：
        1. 函数/API 调用：xxx(
        2. 方法调用和属性赋值：.yyy(  / .zzz =
        3. def 函数定义和 class 类定义
        """
        # 函数调用名 — 一个 ASCII word 后接左括号（排除 Python 关键字和内建函数）
        KEYWORDS_BUILTINS = {
            'if', 'elif', 'else', 'while', 'for', 'def', 'class',
            'return', 'import', 'from', 'as', 'in', 'not', 'and',
            'or', 'is', 'with', 'try', 'except', 'finally', 'raise',
            'print', 'range', 'len', 'int', 'str', 'float', 'list',
            'dict', 'set', 'tuple', 'bool', 'max', 'min', 'abs', 'sum',
            'super', 'isinstance', 'hasattr', 'getattr', 'setattr',
            'open', 'read', 'write', 'input', 'type', 'id', 'dir',
            'sorted', 'reversed', 'enumerate', 'zip', 'map', 'filter',
            'any', 'all', 'True', 'False', 'None',
            'self', 'cls', 'time', 'random', 'os', 'sys', 'math',
            'json', 're', 'Path', 'object', 'property', 'staticmethod',
            'classmethod', 'ValueError', 'TypeError', 'KeyError',
            'Exception', 'BaseException', 'AssertionError',
            'append', 'extend', 'insert', 'pop', 'remove', 'clear',
            'copy', 'count', 'index', 'sort', 'reverse',
            'keys', 'values', 'items', 'get', 'update', 'setdefault',
            'split', 'join', 'strip', 'replace', 'find', 'format',
            'startswith', 'endswith', 'upper', 'lower',
            'format', 'isdigit', 'isalpha', 'isalnum',
        }
        calls = set()
        for m in re.finditer(r'(?a)(?<!["\'])(\w+)\s*\(', code):
            name = m.group(1)
            if name not in KEYWORDS_BUILTINS:
                calls.add(name)

        # 方法/属性调用：.xxx( 或 .xxx =
        attrs = set()
        for m in re.finditer(r'(?a)\.(\w+)\s*\(', code):
            attrs.add(m.group(1))
        for m in re.finditer(r'(?a)\.(\w+)\s*=', code):
            attrs.add(m.group(1))

        # def 函数定义名
        defs = set()
        for m in re.finditer(r'(?a)def\s+(\w+)\s*\(', code):
            defs.add(m.group(1))

        # class 定义名
        classes = set()
        for m in re.finditer(r'(?a)class\s+(\w+)', code):
            classes.add(m.group(1))

        # 从 import 提取的模块/类
        imports = set()
        for m in re.finditer(r'(?a)from\s+(\w+(?:\.\w+)*)\s+import', code):
            imports.add(m.group(1))
        for m in re.finditer(r'(?a)import\s+(\w+(?:\.\w+)*)', code):
            imports.add(m.group(1))
        imports.difference_update(
            {'os', 'sys', 'json', 're', 'math', 'random', 'time',
             'Path', 'typing', 'collections', 'dataclass'}
        )

        parts = []
        if defs:
            parts.append("用户自定义函数: " + ", ".join(sorted(defs)))
        if classes:
            parts.append("用户自定义类: " + ", ".join(sorted(classes)))
        if calls:
            parts.append("实际调用的 API/函数: " + ", ".join(sorted(calls)))
        if attrs:
            parts.append("调用的方法/属性: " + ", ".join(sorted(attrs)))
        if imports:
            parts.append("导入的模块: " + ", ".join(sorted(imports)))

        return "\n".join(parts)

    # ------------ 底层调用 ------------

    async def _call(self, prompt: str, temperature: float = 0.3) -> str:
        """追加一轮对话并调用 LLM。"""
        llm = self.provider.get_chat_model(temperature=temperature)
        self.messages.append(HumanMessage(content=prompt))
        response = await llm.ainvoke(self.messages)
        content = response.content if hasattr(response, "content") else str(response)
        self.messages.append(AIMessage(content=content))
        return content

    def _output(self, key: str, value: Any) -> None:
        """缓存本轮输出。"""
        self.outputs[key] = value

    # ------------ 步骤 0：读代码 ------------

    async def step_read_code(
        self,
        code_content: str,
        entry_comment: str,
        course_topic: str,
        project_type: str,
    ) -> dict:
        """读取并记住全部项目代码，输出结构化分析。

        这是 LLM 唯一一次接触原始代码。后续所有步骤依靠记忆。
        """
        # 代码太长时截断，留足 token 给输出
        # 由于入口注释中提到的文件已被优先排列，即使截断也能保证重点文件被 AI 看到
        code = code_content[:10000]

        # 提取代码中实际调用的函数/API/方法名，用于后续步骤约束 AI 不编造
        self._code_refs = self._extract_code_refs(code)
        log.debug("提取的代码引用清单:\n%s", self._code_refs)

        # 检测代码风格：扫描代码中是否有 def 函数定义或 class 定义
        # 如果有，优先识别为函数；如果没有(或极少)，则将逻辑块/API调用视为函数
        has_defs = len(re.findall(r'(?a)\bdef\s+\w+|class\s+\w+', code)) >= 3

        if not has_defs:
            func_desc = """注意：本代码是脚本风格（主要使用框架 API 调用如 key_pressed、goto 等），
没有或极少有显式的 def 函数定义。请将 main_objectives 对应的**主要逻辑块**列在 key_functions 中，
用逻辑块的核心 API 调用作为名称（如 key_just_pressed、play_snd、goto），
start_line/end_line 填写该逻辑块在代码中的起始和结束行号。"""
        else:
            func_desc = """key_functions **只包含直接服务于 main_objectives 的函数**，每个必须关联至少一个目标。
纯辅助函数（如初始化、工具函数）不要放进来。
必须从源码中确定 start_line / end_line。"""

        prompt = f"""你是少儿 Python 编程教学助手。请仔细阅读以下项目代码并**记住所有代码和逻辑**。

【入口文件顶部注释（说明本节课目标和主题）】
{entry_comment}

【课程主题】
{course_topic}

【项目类型】
{project_type}

【项目所有代码（实际项目源码）】
{code}

阅读完成后，输出 JSON 格式的结构化分析。严格按照以下 JSON 结构，不要添加无关字段：

{{
  "course_topic": "{course_topic}",
  "main_objectives": ["从入口注释提取的课程主要目标，如实现双人按键配置"],
  "key_functions": [
    {{
      "name": "函数名或核心逻辑块名，如 set_keys",
      "purpose": "作用描述，20-40字",
      "technique": "核心 Python 技术点",
      "file_path": "文件名",
      "start_line": 起始行号,
      "end_line": 结束行号,
      "related_objectives": [0]
    }}
  ],
  "python_techniques": ["代码中实际用到的 Python 技术点，如条件判断、列表操作、循环、字符串操作等"]
}}

【重要】
- **入口注释中提到的文件名（如 tools.py、sun.py）是本课的核心学习文件，必须重点关注这些文件中的函数或逻辑**
- {func_desc}
- **禁止编造代码中不存在的内容**。如果代码中没有 def 函数定义，请把关键逻辑块当作函数来分析
- 只输出 JSON，不要额外解释"""

        result_text = await self._call(prompt, TEMPS["read_code"])
        result = _extract_json(result_text)
        if not isinstance(result, dict):
            log.warning("代码分析结果不是 dict，使用空分析: %s", type(result))
            result = _empty_analysis(course_topic)
        log.info(
            "读代码完成: %d 个目标, %d 个关键函数",
            len(result.get("main_objectives", [])),
            len(result.get("key_functions", [])),
        )
        self._output("code_analysis", result)
        return result

    # ------------ 步骤 1：知识点 ------------

    async def step_knowledge_points(
        self,
        course_topic: str,
        project_type: str,
        entry_comment: str,
    ) -> list[str]:
        """基于记忆生成 5 个知识点。"""
        prompt = f"""基于你刚才阅读的代码，生成恰好 5 个本节课的知识点。

课程主题：{course_topic}
项目类型：{project_type}
入口注释：{entry_comment}

【代码中实际存在的函数/API/方法清单（只能引用以下名称，禁止编造）】
{self._code_refs}

要求：
- **每个知识点必须对应代码中实际存在的函数、类、方法或 API 调用**
- **只能引用上方清单中列出的代码元素，禁止编造清单外的函数名或 API**
- **优先从入口注释中提到的文件中提取知识点**，入口注释中出现的文件（如 tools.py、sun.py）是本课的核心学习文件
- **禁止编造代码中没有的函数或技术点**
- 格式「具体技术点 + 训练能力」，如：
  "if-else 训练条件判断逻辑"
  "字典配置训练数据组织能力"
  "碰撞检测训练空间判断能力"
- 每条 ≤15 个中文字符
- 输出严格 JSON 列表，如：
["if-else训练条件判断", "字典配置训练数据组织", "碰撞检测训练空间判断", "函数定义培养分解能力", "属性操作训练封装思维"]
- 只输出 JSON，不要解释"""

        result_text = await self._call(prompt, TEMPS["knowledge_points"])
        result = _extract_json(result_text)
        # 兼容 LLM 返回对象包装（如 {"knowledge_points": [...]}）
        if isinstance(result, dict):
            for key in ("knowledge_points", "items", "list", "data"):
                if key in result and isinstance(result[key], list):
                    result = result[key]
                    break
            else:
                result = []
        if not isinstance(result, list):
            result = []
        result = [str(x).strip() for x in result if str(x).strip()][:5]
        # 兜底补齐
        fallbacks = [
            "变量赋值建立抽象概念",
            "if-else 训练条件判断逻辑",
            "for 循环强化重复执行思维",
            "函数定义培养分解能力",
            "调试代码提升排查技能",
        ]
        while len(result) < 5:
            result.append(fallbacks[len(result)])
        self._output("knowledge_points", result)
        return result

    # ------------ 步骤 2：内容概述 + 能力提升 ------------

    async def step_content_summary(
        self,
        knowledge_points: list[str],
        entry_comment: str,
        project_type: str,
    ) -> tuple[list[dict], str]:
        """基于记忆生成内容概述和能提。"""
        kp_str = "、".join(knowledge_points)

        prompt = f"""基于你阅读的代码和以下知识点，生成课程内容概述。

知识点：{kp_str}
项目类型：{project_type}
入口注释：{entry_comment}

【代码中实际存在的函数/API/方法清单（只能引用以下名称，禁止编造）】
{self._code_refs}

要求：
1. 每个知识点写一段 **40-60 字**的描述，格式：
   - 做了什么（引用代码中**实际存在的函数、类、方法或 API 调用**）
   - 核心逻辑
   - 锻炼了什么思维
2. **禁止引用代码中不存在的内容**。只引用上方清单中列出的真实代码元素。
3. 直接陈述技术内容。不要写"家长可以让孩子""家长可以问孩子"等指导语。
4. 最后写一段 **40-100 字**的"能力提升"，围绕每个知识点逐条展开。

输出 JSON：
{{
  "content_items": [
    {{"kp": "知识点1", "text": "40-60字描述（引用具体函数名或 API）"}},
    {{"kp": "知识点2", "text": "40-60字描述（引用具体函数名或 API）"}}
  ],
  "ability_improvement": "40-100字能力提升总结，逐条展开"
}}
只输出 JSON，不要解释。"""

        result_text = await self._call(prompt, TEMPS["content_summary"])
        result = _extract_json(result_text)
        items = result.get("content_items", []) if isinstance(result, dict) else []
        ability = result.get("ability_improvement", "") if isinstance(result, dict) else ""
        self._output("content_items", items)
        self._output("ability_improvement", ability)
        return items, ability

    # ------------ 步骤 3：作业 + 单词 ------------

    async def step_homework_vocab(
        self,
        knowledge_points: list[str],
        student_level: str,
        entry_comment: str,
        project_type: str,
        homework_guidance: str = "",
    ) -> tuple[dict, dict]:
        """基于记忆生成作业和英文单词。

        优先使用用户写在入口注释中的作业描述，AI 应该将其直接作为作业内容。
        只有当入口注释和作业引导均为空时，才由 AI 自行生成作业。
        """
        kp_str = "、".join(knowledge_points)
        guidance_section = (
            f"\n【作业引导——这是用户写的作业描述，请将其内容直接作为作业出题，不要自己编造新的】\n{homework_guidance}\n"
            if homework_guidance
            else ""
        )

        # 判断入口注释是否包含作业描述（行内包含"作业"字样的都会被识别）
        has_hw_in_entry = any("作业" in line for line in entry_comment.splitlines()) if entry_comment else False

        if homework_guidance or has_hw_in_entry:
            # 用户有写作业描述 → AI 直接使用，不做修改
            prompt = f"""根据下方"入口注释"或"作业引导"中的作业描述，直接将其作为课后作业内容输出。
如果作业描述已经足够完整，原样输出即可，不需要修改或增删。
如果作业描述过于简略（只有一句话），可以适当补充为完整的题目格式。

学生水平：{student_level}
项目类型：{project_type}
入口注释：{entry_comment}{guidance_section}

【代码中实际存在的函数/API/方法清单（供作业引用的代码元素）】
{self._code_refs}

【作业——优先使用上方入口注释或作业引导中的描述，直接作为作业内容】
- 如果入口注释或作业引导中已有作业描述，直接使用，**不要自行编造新的作业**
- 如果描述中提到的代码元素不存在于上方清单中，可以保留但标注"（参考题）"
- 每题 30-50 字
- 提示 2-3 条
- 即使作业描述很短，也要保持学生的语言水平合适（{student_level}）

输出 JSON：
{{
  "homework": {{
    "questions": [
      {{
        "goal": "直接使用用户作业描述中的第1题",
        "hints": ["提示1", "提示2"]
      }},
      {{
        "goal": "直接使用用户作业描述中的第2题...",
        "hints": [...]
      }}
    ]
  }},
  "vocabulary": {{
    "word": "代码中的术语或函数名",
    "phonetic": "/音标/",
    "meaning": "中文释义",
    "example": "代码中的使用示例"
  }}
}}
只输出 JSON，不要解释。"""
        else:
            # 用户没写作业描述 → AI 自行基于代码生成
            prompt = f"""根据你阅读的代码和知识点（{kp_str}），生成课后作业（多题）和英文单词。

学生水平：{student_level}
项目类型：{project_type}
入口注释：{entry_comment}{guidance_section}

【代码中实际存在的函数/API/方法清单（只能引用以下名称，禁止编造）】
{self._code_refs}

【作业——只基于代码中实际出现的函数、类方法或 API 调用出题，生成 1-3 道题】
- 根据课程内容决定题型：
  · 概念/逻辑类 → 问答题（"请描述 XX() 的执行流程"）
  · 参数/配置类 → 修改题（"请修改 XX() 中的配置"）
  · 代码/模仿类 → 填空题或补全题
- **只能引用上方清单中实际存在的代码元素，禁止编造**
- 每题 30-50 字
- 难度适中
- 题型在 goal 中明确体现
- 提示 2-3 条

【单词——来自代码中实际出现的术语、函数名或 API 函数名】
- 音标、中文释义、代码语境例句

输出 JSON：
{{
  "homework": {{
    "questions": [
      {{
        "goal": "题1（含题型动词，引用代码中的函数名或 API）",
        "hints": ["提示1", "提示2"]
      }},
      {{
        "goal": "题2...",
        "hints": [...]
      }}
    ]
  }},
  "vocabulary": {{
    "word": "代码中的术语或函数名",
    "phonetic": "/音标/",
    "meaning": "中文释义",
    "example": "代码中的使用示例"
  }}
}}
只输出 JSON，不要解释。"""

        result_text = await self._call(prompt, TEMPS["homework_vocab"])
        result = _extract_json(result_text)
        hw = result.get("homework", {}) if isinstance(result, dict) else {}
        vocab = result.get("vocabulary", {}) if isinstance(result, dict) else {}
        # 兼容老 LLM 响应：单题也包成 questions 列表
        if "questions" not in hw and hw.get("goal"):
            hw = {
                "questions": [{
                    "goal": hw.get("goal", ""),
                    "hints": hw.get("hints", []),
                }],
                "goal": hw.get("goal", ""),
                "hints": hw.get("hints", []),
            }
        # 顶层 goal/hints 保留为 questions[0] 的同步，方便老渲染逻辑
        if hw.get("questions"):
            first = hw["questions"][0]
            hw.setdefault("goal", first.get("goal", ""))
            hw.setdefault("hints", first.get("hints", []))
        self._output("homework", hw)
        self._output("vocabulary", vocab)
        return hw, vocab

    # ------------ 步骤 4：学生评价 ------------

    async def step_evaluation(
        self,
        student_name: str,
        student_age: str,
        student_gender: str,
        student_level: str,
        student_characteristics: str,
        knowledge_points: list[str],
        teacher_observation: str,
        entry_comment: str,
        homework_context: str = "",
        course_content_context: str = "",
    ) -> str:
        """基于记忆生成个性化学生评价。

        homework_context: 用户编写的课后作业内容，AI 应在评价中引用学生的完成情况。
        course_content_context: 用户编写的课程内容/笔记/目标，AI 应在评价中参考。
        """
        kp_str = "、".join(knowledge_points)
        pronoun = "他" if student_gender == "男" else "她"

        # 构建用户编写内容的上下文
        user_content_section = ""
        if course_content_context:
            user_content_section += f"\n【本节课内容/笔记——教师在报告中填写，评价时请参考】\n{course_content_context}\n"
        if homework_context:
            user_content_section += f"\n【课后作业——教师布置的作业，评价时请参考学生的完成情况】\n{homework_context}\n"

        prompt = f"""根据你阅读的代码和知识点，为该学生写学习评价。

【学生信息】
姓名：{student_name}，{student_age}岁，{student_level}水平
性格：{student_characteristics}
知识点：{kp_str}
课堂表现：{teacher_observation}
入口注释：{entry_comment}{user_content_section}

【代码中实际存在的函数/API/方法清单（只能引用以下名称，禁止编造）】
{self._code_refs}

【字数——这是最重要的约束】
全文必须控制在 **180-200 个中文字符**（含标点）。先写好草稿，然后逐字计数，
如果超过 200 就删减到 200 以内。超过 200 会被系统退回。

【内容要求】
- 只围绕【知识点】中的函数写，禁止提知识点外的技术点
- **只能引用上方清单中实际存在的函数/API 名，禁止编造**
- 自然一段话：学了什么（引用 1 个具体函数名）→ 做得怎么样 → 总结
- 如果有【课后作业】内容，评价中应提到作业完成情况（"作业中……做得很好/还需要注意……"）
- 如果有【本节课内容/笔记】，评价中可参考这些内容来描述学习表现
- 用「{pronoun}」指代学生
- 语气亲切自然、内容具体
- 避免"上课认真""积极举手""表现良好"等空话
        - 不要以"家长您好"开头
        - **只输出评价文本本身**，不要 JSON，不要用 {{}} 包裹，不要加 evaluation 字段
        """

        result_text = await self._call(prompt, TEMPS["evaluation"])
        # 推理模型会输出 <think>...</think> 块，需要剥掉再返回
        result = _strip_think_blocks(result_text).strip()
        self._output("evaluation", result)
        return result

    # ------------ 步骤 5：课程代码片段 ------------

    async def step_code_excerpt(
        self,
        knowledge_points: list[str],
    ) -> list[dict]:
        """基于记忆提取课程相关代码片段（含精确行号、原文）。"""
        kp_str = "、".join(knowledge_points)
        prompt = f"""基于你记忆中的代码，为知识点（{kp_str}）提取相关代码片段。

【代码中实际存在的函数/API/方法清单（只能引用以下名称，禁止编造）】
{self._code_refs}

要求：
- 每个知识点对应一段代码
- 从记忆中找到原始代码的 file_path、start_line、end_line
- code 字段填代码原文，不要修改
- 只包含与知识点直接相关的函数，无关的不要
- 总行数 ≤ 15 行

输出 JSON：
[
  {{"file_path": "main.py", "start_line": 10, "end_line": 25, "code": "原始代码原文"}}
]
只输出 JSON，不要解释。"""

        result_text = await self._call(prompt, TEMPS["code_excerpt"])
        result = _extract_json(result_text)
        if not isinstance(result, list):
            result = []
        self._output("code_excerpt", result)
        return result

    # ------------ 纯图文/无代码模式步骤（基于课程描述而非代码） ------------

    async def step_knowledge_points_no_code(
        self,
        course_topic: str,
        course_description: str,
    ) -> list[str]:
        """纯图文模式：基于课程主题和描述生成知识点（无代码上下文）。"""
        prompt = f"""你是一名少儿课程助教。请为以下课程生成恰好 5 个本节课的知识点。

课程主题：{course_topic}

【课程详细描述】
{course_description}

要求：
- **每个知识点必须对应课程描述中实际提到的内容**
- **禁止编造课程描述中没有的内容**
- 格式「具体技术点 + 训练能力」，如：
  "音符识别训练听力感知"
  "节奏训练培养音乐感"
  "色彩搭配训练审美能力"
- 每条 ≤15 个中文字符
- 输出严格 JSON 列表，如：
["音符识别训练听力感知", "节奏训练培养音乐感", "色彩搭配训练审美能力"]
- 只输出 JSON，不要解释"""

        result_text = await self._call(prompt, TEMPS["knowledge_points"])
        result = _extract_json(result_text)
        if isinstance(result, dict):
            for key in ("knowledge_points", "items", "list", "data"):
                if key in result and isinstance(result[key], list):
                    result = result[key]
                    break
            else:
                result = []
        if not isinstance(result, list):
            result = []
        result = [str(x).strip() for x in result if str(x).strip()][:5]
        fallbacks = [
            "概念认知建立基础思维",
            "观察比较训练分析能力",
            "动手操作培养实践能力",
            "创意表达激发想象力",
            "逻辑推理提升思考深度",
        ]
        while len(result) < 5:
            result.append(fallbacks[len(result)])
        self._output("knowledge_points", result)
        return result

    async def step_content_summary_no_code(
        self,
        knowledge_points: list[str],
        course_topic: str,
        course_description: str,
    ) -> tuple[list[dict], str]:
        """纯图文模式：基于课程描述生成内容概述和能力提升。"""
        kp_str = "、".join(knowledge_points)

        prompt = f"""根据以下课程信息生成内容概述。

课程主题：{course_topic}

【课程详细描述】
{course_description}

知识点：{kp_str}

要求：
1. 每个知识点写一段 **40-60 字**的描述，格式：
   - 这节课做了什么（引用课程描述中实际提到的内容）
   - 核心知识点
   - 锻炼了什么思维
2. **禁止编造课程描述中没有的内容**
3. 直接陈述技术内容。不要写"家长可以让孩子""家长可以问孩子"等指导语。
4. 最后写一段 **40-100 字**的"能力提升"，围绕每个知识点逐条展开。

输出 JSON：
{{
  "content_items": [
    {{"kp": "知识点1", "text": "40-60字描述（引用课程实际内容）"}},
    {{"kp": "知识点2", "text": "40-60字描述（引用课程实际内容）"}}
  ],
  "ability_improvement": "40-100字能力提升总结，逐条展开"
}}
只输出 JSON，不要解释。"""

        result_text = await self._call(prompt, TEMPS["content_summary"])
        result = _extract_json(result_text)
        items = result.get("content_items", []) if isinstance(result, dict) else []
        ability = result.get("ability_improvement", "") if isinstance(result, dict) else ""
        self._output("content_items", items)
        self._output("ability_improvement", ability)
        return items, ability

    async def step_homework_vocab_no_code(
        self,
        knowledge_points: list[str],
        student_level: str,
        course_topic: str,
        course_description: str,
        homework_guidance: str = "",
    ) -> tuple[dict, dict]:
        """纯图文模式：基于课程描述生成作业和单词。

        优先使用课程描述中的作业要求，AI 应将作业要求直接作为作业内容。
        只有当课程描述中不含作业要求时，才由 AI 自行生成。
        """
        kp_str = "、".join(knowledge_points)
        guidance_section = (
            f"\n【作业引导——这是用户写的作业描述，请将其内容直接作为作业出题，不要自己编造新的】\n{homework_guidance}\n"
            if homework_guidance
            else ""
        )

        has_hw_in_desc = any("作业" in line for line in course_description.splitlines()) if course_description else False

        if homework_guidance or has_hw_in_desc:
            prompt = f"""根据下方课程描述中的作业要求，直接将其作为课后作业内容输出。
如果作业要求已经足够完整，原样输出即可，不需要修改或增删。

课程主题：{course_topic}
学生水平：{student_level}

【课程详细描述（关注其中含"作业"字样的内容）】
{course_description}

知识点：{kp_str}{guidance_section}

【作业——优先使用课程描述中的作业要求，直接作为作业内容】
- 如果课程描述中已有作业要求，直接使用，**不要自行编造新的作业**
- 如果描述过于简略，可以适当补充为完整题目格式
- 每题 30-50 字
- 提示 2-3 条

输出 JSON：
{{
  "homework": {{
    "questions": [
      {{
        "goal": "直接使用课程描述中的作业要求",
        "hints": ["提示1", "提示2"]
      }}
    ]
  }},
  "vocabulary": {{
    "word": "课程中的术语或英文关键词",
    "phonetic": "/音标/",
    "meaning": "中文释义",
    "example": "语境例句"
  }}
}}
只输出 JSON，不要解释。"""
        else:
            prompt = f"""根据以下课程信息，生成课后作业（多题）和英文单词。

课程主题：{course_topic}
学生水平：{student_level}

【课程详细描述】
{course_description}

知识点：{kp_str}{guidance_section}

【作业——只基于课程描述中实际出现的内容出题，生成 1-3 道题】
- 根据课程内容决定题型：
  · 概念/逻辑类 → 问答题
  · 操作类 → 实践题
  · 模仿类 → 填空题或补全题
- **只能引用课程描述中实际存在的内容，禁止编造**
- 每题 30-50 字
- 难度适中
- 题型在 goal 中明确体现
- 提示 2-3 条

【单词——来自课程中涉及的术语或英文关键词】
- 音标、中文释义、语境例句

输出 JSON：
{{
  "homework": {{
    "questions": [
      {{
        "goal": "题1（含题型动词，引用课程中的实际内容）",
        "hints": ["提示1", "提示2"]
      }},
      {{
        "goal": "题2...",
        "hints": [...]
      }}
    ]
  }},
  "vocabulary": {{
    "word": "课程中的术语或英文关键词",
    "phonetic": "/音标/",
    "meaning": "中文释义",
    "example": "课程中的使用示例"
  }}
}}
只输出 JSON，不要解释。"""

        result_text = await self._call(prompt, TEMPS["homework_vocab"])
        result = _extract_json(result_text)
        hw = result.get("homework", {}) if isinstance(result, dict) else {}
        vocab = result.get("vocabulary", {}) if isinstance(result, dict) else {}
        if "questions" not in hw and hw.get("goal"):
            hw = {
                "questions": [{
                    "goal": hw.get("goal", ""),
                    "hints": hw.get("hints", []),
                }],
                "goal": hw.get("goal", ""),
                "hints": hw.get("hints", []),
            }
        if hw.get("questions"):
            first = hw["questions"][0]
            hw.setdefault("goal", first.get("goal", ""))
            hw.setdefault("hints", first.get("hints", []))
        self._output("homework", hw)
        self._output("vocabulary", vocab)
        return hw, vocab

    async def step_evaluation_no_code(
        self,
        student_name: str,
        student_age: str,
        student_gender: str,
        student_level: str,
        student_characteristics: str,
        knowledge_points: list[str],
        teacher_observation: str,
        course_topic: str,
        course_description: str,
        homework_context: str = "",
        course_content_context: str = "",
    ) -> str:
        """纯图文模式：基于课程描述生成个性化学生评价。"""
        kp_str = "、".join(knowledge_points)
        pronoun = "他" if student_gender == "男" else "她"

        user_content_section = ""
        if course_content_context:
            user_content_section += f"\n【本节课内容/笔记——教师在报告中填写，评价时请参考】\n{course_content_context}\n"
        if homework_context:
            user_content_section += f"\n【课后作业——教师布置的作业，评价时请参考学生的完成情况】\n{homework_context}\n"

        prompt = f"""根据以下课程信息，为该学生写学习评价。

【课程主题】
{course_topic}

【课程详细描述】
{course_description}

【学生信息】
姓名：{student_name}，{student_age}岁，{student_level}水平
性格：{student_characteristics}
知识点：{kp_str}
课堂表现：{teacher_observation}{user_content_section}

【字数——这是最重要的约束】
全文必须控制在 **180-200 个中文字符**（含标点）。先写好草稿，然后逐字计数，
如果超过 200 就删减到 200 以内。超过 200 会被系统退回。

【内容要求】
- 只围绕【知识点】中的内容写，禁止提知识点外的内容
- **只能引用课程描述中实际出现的内容，禁止编造**
- 自然一段话：学了什么 → 做得怎么样 → 总结
- 如果有【课后作业】内容，评价中应提到作业完成情况
- 如果有【本节课内容/笔记】，评价中可参考这些内容来描述学习表现
- 用「{pronoun}」指代学生
- 语气亲切自然、内容具体
- 避免"上课认真""积极举手""表现良好"等空话
- 不要以"家长您好"开头
- **只输出评价文本本身**，不要 JSON，不要用 {{}} 包裹，不要加 evaluation 字段
"""

        result_text = await self._call(prompt, TEMPS["evaluation"])
        result = _strip_think_blocks(result_text).strip()
        self._output("evaluation", result)
        return result

    # ------------ 缓存重放 ------------

    def copy_from(self, other: AIConversation) -> None:
        """从另一个会话复制消息历史和输出缓存（用于批量模式子会话）。"""
        self.messages = other.messages.copy()
        self.outputs = other.outputs.copy()
        self._code_refs = other._code_refs

    @classmethod
    def from_shared(cls, provider: LLMProvider, shared: AIConversation) -> AIConversation:
        """从共享会话创建新会话（复制记忆）。"""
        conv = cls(provider)
        conv.copy_from(shared)
        return conv
