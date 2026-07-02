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
    ) -> GenerationResult:
        """完整生成：读代码 → 知识点 → 内容概述 → 作业/单词 → 评价。"""
        log.info("开始生成报告: course=%s student=%s", project.course_title, student.name)

        conv = AIConversation(self.provider)
        code_content = self._build_code_content(project)
        entry_comment = self._get_entry_comment(project)
        course_topic = project.course_title or "未指定"
        project_type = project.project_type

        result = GenerationResult()

        # Step 0: 读代码
        try:
            analysis = await conv.step_read_code(
                code_content, entry_comment, course_topic, project_type,
            )
            result.analysis = analysis
        except Exception as e:
            log.exception("读代码失败: %s", e)
            result.errors["code_analysis"] = str(e)
            return result

        # Step 1: 知识点
        try:
            result.knowledge_points = await conv.step_knowledge_points(
                course_topic, project_type, entry_comment,
            )
            log.info("知识点完成: %d 条", len(result.knowledge_points))
        except Exception as e:
            log.exception("知识点失败: %s", e)
            result.errors["knowledge_points"] = str(e)
            return result

        # Step 2: 内容概述 + 能力提升
        try:
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

        # Step 3: 作业 + 单词
        try:
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

        # Step 4: 评价
        try:
            result.evaluation = await conv.step_evaluation(
                student_name=student.name,
                student_age=student.age or "未知",
                student_gender=student.gender or "未知",
                student_level=student.base_level,
                student_characteristics="、".join(student.characteristics) or "无特别记录",
                knowledge_points=result.knowledge_points,
                teacher_observation=teacher_observation,
                entry_comment=entry_comment,
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
    ) -> dict:
        """批量模式：所有学生共享的内容（Steps 0-3）。"""
        log.info("批量共享生成: course=%s", project.course_title)

        conv = AIConversation(self.provider)
        code_content = self._build_code_content(project)
        entry_comment = self._get_entry_comment(project)
        course_topic = project.course_title or "未指定"
        project_type = project.project_type

        # Step 0: 读代码
        analysis = await conv.step_read_code(
            code_content, entry_comment, course_topic, project_type,
        )

        # Step 1: 知识点
        kp = await conv.step_knowledge_points(course_topic, project_type, entry_comment)
        log.info("共享知识点: %d 条", len(kp))

        # Step 2: 内容概述
        items, ability = await conv.step_content_summary(kp, entry_comment, project_type)
        log.info("共享内容概述: %d 条", len(items))

        # Step 3: 作业 + 单词
        homework_guidance = self._get_homework_guidance(project)
        hw, vocab = await conv.step_homework_vocab(
            kp, default_student.base_level, entry_comment, project_type,
            homework_guidance,
        )
        log.info("共享作业/单词完成")

        # 保存共享会话，供 generate_evaluations 使用
        self._shared_conv = conv

        return {
            "knowledge_points": kp,
            "content_items": items,
            "ability_improvement": ability,
            "homework": hw,
            "vocabulary": vocab,
            "code_analysis": analysis,
        }

    async def generate_evaluations(
        self,
        project: ProjectMetaSchema,
        students: list[StudentRead],
        shared_content: dict,
        teacher_observation: str = "",
    ) -> list:
        """批量模式：为每个学生生成个性化评价（基于共享会话的记忆）。"""
        log.info("批量评价: %d 名学生", len(students))
        kp = shared_content.get("knowledge_points", [])
        entry_comment = self._get_entry_comment(project)

        async def _eval_one(student: StudentRead) -> str:
            # 从共享会话创建子会话（复制全部记忆，不重复调用 LLM）
            conv = AIConversation.from_shared(self.provider, self._shared_conv)
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

    def _build_code_content(self, project: ProjectMetaSchema) -> str:
        """拼接项目代码，从磁盘读取实际源码。

        策略：
        1. 入口文件（含课程标题注释）总在最前，读完整源码
        2. 其余文件按行数从小到大排序，小文件（≤80行）读完整源码
        3. 大文件只列结构信息
        4. 结果在实例内缓存，同一次请求不重复读盘
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

        parts: list[str] = []

        if entry:
            file_path = (project_root / entry.path).resolve()
            try:
                source = file_path.read_text(encoding='utf-8')
                parts.append(f"# === {entry.path}（启动文件）===\n{source}")
            except (OSError, IOError):
                parts.append(f"# === {entry.path}（启动文件）===\n# (文件无法读取)")

        others.sort(key=lambda f: f.line_count if f.line_count else 9999)
        for f in others:
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
