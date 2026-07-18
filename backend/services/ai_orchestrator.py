"""
AI Orchestrator（顶层编排）

v3 — 对话记忆架构（2025-06）

设计变更：
  废除旧的"Phase 1 代码分析 → _format_analysis() → Phase 2 碎片化链调用"模式。
  改为 AIConversation 对话式流程：
    第一轮：LLM 读全部代码 → 记住所有函数行号
    后续轮：每一步都是基于记忆的新提问，不再传递摘要文本
    批量模式：共享会话的记忆通过 copy_from() 复制给每个学生

优势：
  - 每一轮 LLM 都保有完整代码上下文，不会因摘要丢失信息
  - 天然约束：LLM 引用函数时必定来自记忆中的真实代码
  - 重生成基于同一段记忆，不重复读盘
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.llm.base import LLMProvider, get_provider
from backend.schemas.project import ProjectMetaSchema
from backend.schemas.student import StudentRead
from backend.services.ai_conversation import AIConversation
from backend.utils.logger import get_logger

log = get_logger(__name__)


# =========================
# 步骤定义（保持兼容）
# =========================
STEP_FIELDS: list[str] = [
    "knowledge_points",
    "content_summary",
    "homework_vocab",
    "evaluation",
]


@dataclass
class GenerationResult:
    """单次生成的完整结果。"""
    knowledge_points: list[str] = field(default_factory=list)
    content_items: list[dict] = field(default_factory=list)
    ability_improvement: str = ""
    homework: dict = field(default_factory=dict)
    vocabulary: dict = field(default_factory=dict)
    evaluation: str = ""
    analysis: dict = field(default_factory=dict)  # 代码分析结果
    errors: dict[str, str] = field(default_factory=dict)  # 字段名 → 错误信息

    def to_dict(self) -> dict:
        return {
            "knowledge_points": self.knowledge_points,
            "content_items": self.content_items,
            "ability_improvement": self.ability_improvement,
            "homework": self.homework,
            "vocabulary": self.vocabulary,
            "evaluation": self.evaluation,
            "errors": self.errors,
        }


# =========================
# Orchestrator
# =========================
class AIOrchestrator:
    """
    AI 编排器（v3 — 对话记忆架构）。

    使用：
        orch = AIOrchestrator()
        result = await orch.generate_all(project_meta, student)
    """

    def __init__(self, provider: LLMProvider | None = None):
        if provider is None:
            from backend.config import get_settings
            provider = get_provider(get_settings().llm)
        self.provider = provider
        self._code_cache: str | None = None     # 代码内容缓存（避免重复读盘）
        self._shared_conv: AIConversation | None = None  # 批量共享会话

    # =========================
    # 单篇生成
    # =========================

    async def generate_all(
        self,
        project: ProjectMetaSchema,
        student: StudentRead,
        teacher_observation: str = "",
        existing_content: dict | None = None,
    ) -> GenerationResult:
        """完整生成：读代码 → 知识点 → 内容概述 → 作业/单词 → 评价。

        existing_content: 用户已填写的字段（如 homework/knowledge_points 等），
                          AI 跳过这些字段的生成，直接使用用户提供的值。
        """
        log.info("开始生成报告: course=%s student=%s", project.course_title, student.name)
        existing_content = existing_content or {}

        conv = AIConversation(self.provider)
        code_content = self._build_code_content(project)
        entry_comment = self._get_entry_comment(project)
        course_topic = project.course_title or "未指定"
        project_type = project.project_type

        result = GenerationResult()

        # Step 0: 读代码（始终需要——评价依赖记忆）
        try:
            analysis = await conv.step_read_code(
                code_content, entry_comment, course_topic, project_type,
            )
            result.analysis = analysis
        except Exception as e:
            log.exception("读代码失败: %s", e)
            result.errors["code_analysis"] = str(e)
            return result

        # Step 1: 知识点（用户已填则跳过 AI）
        try:
            if existing_content.get("knowledge_points"):
                result.knowledge_points = existing_content["knowledge_points"]
                log.info("知识点: 使用用户已填内容 (%d 条)", len(result.knowledge_points))
            else:
                result.knowledge_points = await conv.step_knowledge_points(
                    course_topic, project_type, entry_comment,
                )
                log.info("知识点完成: %d 条", len(result.knowledge_points))
        except Exception as e:
            log.exception("知识点失败: %s", e)
            result.errors["knowledge_points"] = str(e)
            return result

        # Step 2: 内容概述 + 能力提升（用户已填则跳过 AI）
        try:
            if existing_content.get("content_items"):
                result.content_items = existing_content["content_items"]
                result.ability_improvement = existing_content.get("ability_improvement", "")
                log.info("内容概述: 使用用户已填内容 (%d 条)", len(result.content_items))
            else:
                items, ability = await conv.step_content_summary(
                    result.knowledge_points, entry_comment, project_type,
                )
                result.content_items = items
                result.ability_improvement = ability
                log.info("内容概述完成: %d 条", len(result.content_items))
        except Exception as e:
            log.exception("内容概述失败: %s", e)
            result.errors["content_summary"] = str(e)
            return result

        # Step 3: 作业 + 单词（用户已填则跳过 AI）
        try:
            if existing_content.get("homework"):
                result.homework = existing_content["homework"]
                result.vocabulary = existing_content.get("vocabulary", {})
                log.info("作业/单词: 使用用户已填内容")
            else:
                homework_guidance = self._get_homework_guidance(project)
                hw, vocab = await conv.step_homework_vocab(
                    result.knowledge_points, student.base_level,
                    entry_comment, project_type, homework_guidance,
                )
                result.homework = hw
                result.vocabulary = vocab
                log.info("作业/单词完成")
        except Exception as e:
            log.exception("作业/单词失败: %s", e)
            result.errors["homework_vocab"] = str(e)

        # Step 4: 评价（始终生成，基于用户已填内容或 AI 生成内容）
        try:
            # 构造课程内容/作业上下文供评价参考
            _hw = result.homework or {}
            _hw_str_lines = []
            if _hw.get("goal"):
                _hw_str_lines.append(f"目标：{_hw['goal']}")
            for q in (_hw.get("questions") or []):
                _hw_str_lines.append(f"题目：{q.get('goal', '')}")
            _hw_str = "\n".join(_hw_str_lines)

            _content_str_lines = []
            for item in (result.content_items or []):
                if isinstance(item, dict):
                    _content_str_lines.append(f"{item.get('kp', '')}: {item.get('text', '')}")
            _content_str = "\n".join(_content_str_lines)

            result.evaluation = await conv.step_evaluation(
                student_name=student.name,
                student_age=student.age or "未知",
                student_gender=student.gender or "未知",
                student_level=student.base_level,
                student_characteristics="、".join(student.characteristics) or "无特别记录",
                knowledge_points=result.knowledge_points,
                teacher_observation=teacher_observation,
                entry_comment=entry_comment,
                homework_context=_hw_str,
                course_content_context=_content_str,
            )
            log.info("评价完成: %d 字", len(result.evaluation))
        except Exception as e:
            log.exception("评价失败: %s", e)
            result.errors["evaluation"] = str(e)

        return result

    # =========================
    # 批量生成
    # =========================

    async def generate_shared(
        self,
        project: ProjectMetaSchema,
        default_student: StudentRead,
        teacher_observation: str = "",
        code_screenshots: list[str] | None = None,
        homework_screenshots: list[str] | None = None,
        create_vocabulary: bool = True,
        skip_code_analysis: bool = False,
        skip_homework_gen: bool = False,
        existing_content: dict | None = None,
    ) -> dict:
        """批量模式：所有学生共享的内容（Steps 0-3）。

        参数：
        - code_screenshots: 代码/运行截图 URL 列表（截图/run.png, code*.png 扫描得到）
        - homework_screenshots: 作业截图 URL 列表（截图/homework*.png 扫描得到）
        - create_vocabulary: 是否生成单词卡（默认 True）
        - skip_code_analysis: 是否有代码截图，跳过代码 AI 解析
        - skip_homework_gen: 是否有作业截图，跳过作业 AI 生成
        - existing_content: 用户已填写的共享字段（如 homework/knowledge_points 等），
                            AI 跳过这些字段的生成，直接使用用户提供的值
        """
        log.info(
            "批量共享生成: course=%s code_imgs=%d hw_imgs=%d vocab=%s skip_code=%s skip_hw=%s",
            project.course_title,
            len(code_screenshots or []),
            len(homework_screenshots or []),
            create_vocabulary,
            skip_code_analysis,
            skip_homework_gen,
        )
        existing_content = existing_content or {}

        conv = AIConversation(self.provider)
        code_content = self._build_code_content(project)
        entry_comment = self._get_entry_comment(project)
        course_topic = project.course_title or "未指定"
        project_type = project.project_type

        # Step 0: 读代码
        if skip_code_analysis:
            log.info("跳过代码 AI 解析（使用代码截图 %d 张）", len(code_screenshots or []))
            # 即使跳过 AI 解析，也要提取代码中的实际函数/API 名，用于约束后续步骤不编造
            code_snippet = code_content[:10000]
            conv._code_refs = AIConversation._extract_code_refs(code_snippet)
            log.debug("提取的代码引用清单（跳过模式）:\n%s", conv._code_refs)
            analysis = {
                "course_topic": course_topic,
                "main_objectives": [],
                "key_functions": [],
                "python_techniques": [],
                "code_screenshots": list(code_screenshots or []),
                "skipped": True,
            }
        else:
            analysis = await conv.step_read_code(
                code_content, entry_comment, course_topic, project_type,
            )

        # Step 1: 知识点（用户已填则跳过 AI）
        if existing_content.get("knowledge_points"):
            kp = existing_content["knowledge_points"]
            log.info("共享知识点: 使用用户已填内容 (%d 条)", len(kp))
        else:
            kp = await conv.step_knowledge_points(course_topic, project_type, entry_comment)
            log.info("共享知识点: %d 条", len(kp))

        # Step 2: 内容概述（用户已填则跳过 AI）
        if existing_content.get("content_items"):
            items = existing_content["content_items"]
            ability = existing_content.get("ability_improvement", "")
            log.info("共享内容概述: 使用用户已填内容 (%d 条)", len(items))
        else:
            items, ability = await conv.step_content_summary(kp, entry_comment, project_type)
            log.info("共享内容概述: %d 条", len(items))

        # Step 3: 作业 + 单词（用户已填则跳过 AI）
        if existing_content.get("homework"):
            hw = existing_content["homework"]
            vocab = existing_content.get("vocabulary", {})
            log.info("共享作业/单词: 使用用户已填内容")
        elif skip_homework_gen:
            log.info("跳过作业 AI 生成（使用作业截图 %d 张）", len(homework_screenshots or []))
            hw = {
                "goal": "（基于作业截图，详见下方图片）",
                "hints": [],
                "criteria": [],
                "questions": [],
                "screenshots": list(homework_screenshots or []),
                "skipped": True,
            }
            vocab = {"word": "", "phonetic": "", "meaning": "", "example": ""} if create_vocabulary else {}
        else:
            homework_guidance = self._get_homework_guidance(project)
            hw, vocab = await conv.step_homework_vocab(
                kp, default_student.base_level, entry_comment, project_type,
                homework_guidance,
            )
            # 如果不需要单词，清空
            if not create_vocabulary:
                vocab = {"word": "", "phonetic": "", "meaning": "", "example": ""}

        log.info("共享作业/单词完成 (vocab=%s)", "是" if create_vocabulary else "否")

        # 保存共享会话，供 generate_evaluations 使用
        self._shared_conv = conv

        return {
            "knowledge_points": kp,
            "content_items": items,
            "ability_improvement": ability,
            "homework": hw,
            "vocabulary": vocab,
            "code_analysis": analysis,
            "code_screenshots": list(code_screenshots or []),
            "homework_screenshots": list(homework_screenshots or []),
        }

    # =========================
    # 纯图文/无代码模式共享生成
    # =========================

    async def _generate_no_code_shared(
        self,
        course_topic: str,
        course_description: str,
        default_student: StudentRead,
        code_screenshots: list[str] | None = None,
        homework_screenshots: list[str] | None = None,
        create_vocabulary: bool = True,
        skip_homework_gen: bool = False,
        existing_content: dict | None = None,
    ) -> dict:
        """纯图文模式的共享内容生成（无代码分析，基于课程描述）。"""
        log.info(
            "纯图文共享生成: topic=%s desc_len=%d code_imgs=%d hw_imgs=%d",
            course_topic,
            len(course_description),
            len(code_screenshots or []),
            len(homework_screenshots or []),
        )
        existing_content = existing_content or {}

        conv = AIConversation(self.provider)

        # Step 1: 知识点（用户已填则跳过 AI）
        if existing_content.get("knowledge_points"):
            kp = existing_content["knowledge_points"]
            log.info("知识点: 使用用户已填内容 (%d 条)", len(kp))
        else:
            kp = await conv.step_knowledge_points_no_code(course_topic, course_description)
            log.info("纯图文知识点: %d 条", len(kp))

        # Step 2: 内容概述（用户已填则跳过 AI）
        if existing_content.get("content_items"):
            items = existing_content["content_items"]
            ability = existing_content.get("ability_improvement", "")
            log.info("内容概述: 使用用户已填内容 (%d 条)", len(items))
        else:
            items, ability = await conv.step_content_summary_no_code(
                kp, course_topic, course_description,
            )
            log.info("纯图文内容概述: %d 条", len(items))

        # Step 3: 作业 + 单词（用户已填则跳过 AI）
        if existing_content.get("homework"):
            hw = existing_content["homework"]
            vocab = existing_content.get("vocabulary", {})
            log.info("作业/单词: 使用用户已填内容")
        elif skip_homework_gen:
            log.info("跳过作业 AI 生成（使用作业截图 %d 张）", len(homework_screenshots or []))
            hw = {
                "goal": "（基于作业截图，详见下方图片）",
                "hints": [], "criteria": [],
                "questions": [],
                "screenshots": list(homework_screenshots or []),
                "skipped": True,
            }
            vocab = {"word": "", "phonetic": "", "meaning": "", "example": ""} if create_vocabulary else {}
        else:
            hw, vocab = await conv.step_homework_vocab_no_code(
                kp, default_student.base_level, course_topic, course_description,
            )
            if not create_vocabulary:
                vocab = {"word": "", "phonetic": "", "meaning": "", "example": ""}

        log.info("纯图文作业/单词完成 (vocab=%s)", "是" if create_vocabulary else "否")

        self._shared_conv = conv

        analysis = {
            "course_topic": course_topic,
            "main_objectives": [],
            "key_functions": [],
            "python_techniques": [],
            "code_screenshots": list(code_screenshots or []),
            "skipped": True,
            "no_code": True,
        }

        return {
            "knowledge_points": kp,
            "content_items": items,
            "ability_improvement": ability,
            "homework": hw,
            "vocabulary": vocab,
            "code_analysis": analysis,
            "code_screenshots": list(code_screenshots or []),
            "homework_screenshots": list(homework_screenshots or []),
        }

    async def generate_evaluations(
        self,
        project: ProjectMetaSchema,
        students: list[StudentRead],
        shared_content: dict,
        teacher_observation: str = "",
        observations: dict[int, str] | None = None,
        course_description: str = "",
    ) -> list:
        """批量模式：为每个学生生成个性化评价（基于共享会话的记忆）。

        无代码模式（course_description 非空）时使用 step_evaluation_no_code。
        observations: 逐学生观察 dict（key=student_id）。未填则用 teacher_observation 全局值。
        """
        log.info("批量评价: %d 名学生 (含 %d 条逐学生观察)", len(students), len(observations or {}))
        kp = shared_content.get("knowledge_points", [])
        is_no_code = bool(course_description)
        if not is_no_code:
            entry_comment = self._get_entry_comment(project)
        else:
            entry_comment = ""
        observations = observations or {}

        # 构造课程内容/作业上下文供评价参考
        _hw = shared_content.get("homework", {}) or {}
        _hw_str_lines = []
        if _hw.get("goal"):
            _hw_str_lines.append(f"目标：{_hw['goal']}")
        for q in (_hw.get("questions") or []):
            _hw_str_lines.append(f"题目：{q.get('goal', '')}")
        _hw_str = "\n".join(_hw_str_lines)

        _content_str_lines = []
        for item in (shared_content.get("content_items") or []):
            if isinstance(item, dict):
                _content_str_lines.append(f"{item.get('kp', '')}: {item.get('text', '')}")
        _content_str = "\n".join(_content_str_lines)

        async def _eval_one(student: StudentRead) -> str:
            # 优先用逐学生观察，回退到全局观察
            per_student_obs = observations.get(student.id) or teacher_observation
            # 从共享会话创建子会话（复制全部记忆，不重复调用 LLM）
            conv = AIConversation.from_shared(self.provider, self._shared_conv)
            if is_no_code:
                return await conv.step_evaluation_no_code(
                    student_name=student.name,
                    student_age=student.age or "未知",
                    student_gender=student.gender or "未知",
                    student_level=student.base_level,
                    student_characteristics="、".join(student.characteristics) or "无特别记录",
                    knowledge_points=kp,
                    teacher_observation=per_student_obs,
                    course_topic=project.course_title or "未指定",
                    course_description=course_description,
                    homework_context=_hw_str,
                    course_content_context=_content_str,
                )
            return await conv.step_evaluation(
                student_name=student.name,
                student_age=student.age or "未知",
                student_gender=student.gender or "未知",
                student_level=student.base_level,
                student_characteristics="、".join(student.characteristics) or "无特别记录",
                knowledge_points=kp,
                teacher_observation=per_student_obs,
                entry_comment=entry_comment,
                homework_context=_hw_str,
                course_content_context=_content_str,
            )

        tasks = [_eval_one(s) for s in students]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

    # =========================
    # 单步重生成
    # =========================

    async def regenerate_one(
        self,
        field_name: str,
        project: ProjectMetaSchema,
        student: StudentRead,
        knowledge_points: list[str] | None = None,
        teacher_observation: str = "",
    ) -> Any:
        """重新生成单个字段（基于新的对话，但读代码阶段用缓存避免重复 LLM）。"""
        if field_name not in STEP_FIELDS:
            raise ValueError(f"未知字段: {field_name}")

        log.info("重生成字段: %s", field_name)

        conv = AIConversation(self.provider)
        code_content = self._build_code_content(project)
        entry_comment = self._get_entry_comment(project)
        course_topic = project.course_title or "未指定"
        project_type = project.project_type

        # 读代码（使用 code_content 缓存，或新对话中 LLM 重新读）
        await conv.step_read_code(code_content, entry_comment, course_topic, project_type)

        # 知识点重生成
        if field_name == "knowledge_points":
            return await conv.step_knowledge_points(course_topic, project_type, entry_comment)

        # 其他字段需要先有知识点
        kp = knowledge_points or await conv.step_knowledge_points(course_topic, project_type, entry_comment)

        # 内容概述重生成
        if field_name == "content_summary":
            items, ability = await conv.step_content_summary(kp, entry_comment, project_type)
            return {"content_items": items, "ability_improvement": ability}

        # 作业/单词重生成
        if field_name == "homework_vocab":
            await conv.step_content_summary(kp, entry_comment, project_type)
            homework_guidance = self._get_homework_guidance(project)
            hw, vocab = await conv.step_homework_vocab(
                kp, student.base_level, entry_comment, project_type,
                homework_guidance,
            )
            return {"homework": hw, "vocabulary": vocab}

        # 评价重生成
        if field_name == "evaluation":
            return await conv.step_evaluation(
                student_name=student.name,
                student_age=student.age or "未知",
                student_gender=student.gender or "未知",
                student_level=student.base_level,
                student_characteristics="、".join(student.characteristics) or "无特别记录",
                knowledge_points=kp,
                teacher_observation=teacher_observation,
                entry_comment=entry_comment,
            )

        raise RuntimeError("unreachable")

    async def get_analysis_text(self, project: ProjectMetaSchema) -> str:
        """兼容旧接口：获取格式化分析文本（用于旧版 reports.py 调用）。

        新版不再依赖 analysis_text，保留此方法避免导入错误。
        实际调用时会创建对话读代码，浪费 token，所以应尽快移除调用方。
        """
        conv = AIConversation(self.provider)
        code_content = self._build_code_content(project)
        entry_comment = self._get_entry_comment(project)
        course_topic = project.course_title or "未指定"
        analysis = await conv.step_read_code(
            code_content, entry_comment, course_topic, project.project_type,
        )
        # 模拟旧版 _format_analysis 简化输出
        lines = [f"课程主题：{analysis.get('course_topic', '')}"]
        for f in analysis.get("key_functions", []):
            if not f.get("related_objectives"):
                continue
            fp = f.get("file_path", "")
            sl, el = f.get("start_line"), f.get("end_line")
            loc = f" [{fp}:{sl}-{el}]" if fp and sl and el else ""
            lines.append(f"  - {f.get('name', '?')}{loc}")
            lines.append(f"    用途：{f.get('purpose', '')}")
            lines.append(f"    技术点：{f.get('technique', '')}")
        return "\n".join(lines)

    # =========================
    # 工具方法
    # =========================

    def _get_entry_comment(self, project: ProjectMetaSchema) -> str:
        """提取入口文件的完整顶部注释。"""
        if not project.entry_file:
            return ""
        for f in project.py_files:
            if f.path == project.entry_file:
                return f.top_comment or ""
        return ""

    def _get_homework_guidance(self, project: ProjectMetaSchema) -> str:
        """提取入口文件的作业引导。"""
        if not project.entry_file:
            return ""
        for f in project.py_files:
            if f.path == project.entry_file:
                return f.homework_guidance or ""
        return ""

    def _extract_referenced_files(self, entry_comment: str) -> set[str]:
        """从入口注释中提取被引用的 .py 文件名，如 tools.py、sun.py。

        用户写课程目标时习惯注明文件名：
        - "学习字符串分割函数split, 文件tools.py"
        - "加入定时任务类 Task, 文件tools.py"
        - "文件: sun.py"
        这些文件是本节课的重点学习对象，应优先提供给 AI。
        """
        if not entry_comment:
            return set()
        refs = re.findall(r'\b([\w-]+\.py)\b', entry_comment)
        return set(refs)

    def _build_code_content(self, project: ProjectMetaSchema) -> str:
        """拼接项目代码，从磁盘读取实际源码。

        策略：
        1. 入口文件（含课程标题注释）总在最前，读完整源码
        2. 从入口注释中提取引用的 .py 文件名（如 tools.py、sun.py），
           这些文件优先排在其余文件之前，且全部读完整源码（不论行数）
        3. 其余文件按行数从小到大排序，小文件（≤80行）读完整源码
        4. 大文件只列结构信息
        5. 结果在实例内缓存，同一次请求不重复读盘
        """
        if self._code_cache is not None:
            return self._code_cache

        project_root = Path(project.folder)
        entry = None
        others = []

        for f in project.py_files:
            if f.path == project.entry_file:
                entry = f
            else:
                others.append(f)

        # 提取入口注释中引用的文件名
        entry_comment = self._get_entry_comment(project)
        referenced_files = self._extract_referenced_files(entry_comment)
        if referenced_files:
            log.info("入口注释中引用的文件: %s", referenced_files)

        parts: list[str] = []

        if entry:
            file_path = (project_root / entry.path).resolve()
            try:
                source = file_path.read_text(encoding='utf-8')
                parts.append(f"# === {entry.path}（启动文件）===\n{source}")
            except (OSError, IOError):
                parts.append(f"# === {entry.path}（启动文件）===\n# (文件无法读取)")

        # 重点文件：入口注释中提到的文件，按行数排序后排在前面（全部读完整源码）
        referenced_list = []
        non_referenced_list = []
        for f in others:
            if f.path in referenced_files:
                referenced_list.append(f)
            else:
                non_referenced_list.append(f)

        referenced_list.sort(key=lambda f: f.line_count if f.line_count else 9999)
        non_referenced_list.sort(key=lambda f: f.line_count if f.line_count else 9999)

        # 重点文件全部读完整源码（不论行数）
        for f in referenced_list:
            file_path = (project_root / f.path).resolve()
            try:
                source = file_path.read_text(encoding='utf-8')
                parts.append(f"# === {f.path}（重点文件 - 入口注释引用）===\n{source}")
            except (OSError, IOError):
                parts.append(
                    f"# === {f.path}（重点文件 - 入口注释引用）===\n"
                    f"imports: {f.imports}\n"
                    f"functions: {f.function_names}\n"
                    f"classes: {f.class_names}"
                )

        # 其余文件按行数排序，小文件（≤80行）读完整源码
        for f in non_referenced_list:
            file_path = (project_root / f.path).resolve()
            if f.line_count and f.line_count <= 80:
                try:
                    source = file_path.read_text(encoding='utf-8')
                    parts.append(f"# === {f.path} ===\n{source}")
                except (OSError, IOError):
                    parts.append(
                        f"# === {f.path} ===\n"
                        f"imports: {f.imports}\n"
                        f"functions: {f.function_names}\n"
                        f"classes: {f.class_names}"
                    )
            else:
                parts.append(
                    f"# === {f.path} ===\n"
                    f"imports: {f.imports}\n"
                    f"functions: {f.function_names}\n"
                    f"classes: {f.class_names}"
                )

        result = "\n\n".join(parts)
        self._code_cache = result
        return result
