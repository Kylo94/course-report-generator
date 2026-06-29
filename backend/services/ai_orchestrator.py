"""
AI Orchestrator（顶层编排）

设计原则（按策划书 4.2.1）：
- 不使用 LangChain Chain/LCEL 串联
- 顶层用业务代码控制：单步可重试 + 断点续跑
- 每步结果可独立 invoke，失败不影响其他字段
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from langchain_core.runnables import Runnable

from backend.llm.base import LLMProvider, get_provider
from backend.schemas.project import ProjectMetaSchema
from backend.schemas.student import StudentRead
from backend.services.ai_chains import build_chains
from backend.utils.logger import get_logger

log = get_logger(__name__)


# =========================
# 步骤定义
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
    AI 编排器。

    使用：
        orch = AIOrchestrator()
        result = await orch.generate_all(project_meta, student)
        # 或单步：
        kp = await orch.regenerate_one("knowledge_points", context)
    """

    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or get_provider()
        self.chains: dict[str, Runnable] = build_chains(self.provider)

    # =========================
    # 全量生成
    # =========================
    async def generate_all(
        self,
        project: ProjectMetaSchema,
        student: StudentRead,
        teacher_observation: str = "",
    ) -> GenerationResult:
        """
        4 步链式生成全部 9 项内容。

        任意步骤失败不中断，记录到 result.errors。
        """
        log.info(
            "开始生成报告: course=%s student=%s",
            project.course_title,
            student.name,
        )

        # 提取项目代码（启动文件全文 + 其他 .py 文件名）
        code_content = self._build_code_content(project)

        result = GenerationResult()

        # Step 1: 知识点
        try:
            result.knowledge_points = await self._run_kp(
                project, code_content
            )
            log.info("Step 1 完成: %d 个知识点", len(result.knowledge_points))
        except Exception as e:
            log.exception("Step 1 失败: %s", e)
            result.errors["knowledge_points"] = str(e)
            return result  # 后续步骤依赖知识点，提前返回

        # Step 2: 内容概述 + 能力提升
        try:
            cs = await self._run_content_summary(
                project, code_content, result.knowledge_points
            )
            result.content_items = cs.get("content_items", [])
            result.ability_improvement = cs.get("ability_improvement", "")
            log.info(
                "Step 2 完成: %d 个内容块, 能力提升 %d 字",
                len(result.content_items),
                len(result.ability_improvement),
            )
        except Exception as e:
            log.exception("Step 2 失败: %s", e)
            result.errors["content_summary"] = str(e)
            return result

        # Step 3: 作业 + 单词
        try:
            hv = await self._run_homework_vocab(
                project, result.knowledge_points, student
            )
            result.homework = hv.get("homework", {})
            result.vocabulary = hv.get("vocabulary", {})
            log.info("Step 3 完成: 作业 %d 提示点", len(result.homework.get("hints", [])))
        except Exception as e:
            log.exception("Step 3 失败: %s", e)
            result.errors["homework_vocab"] = str(e)

        # Step 4: 学生评价
        try:
            result.evaluation = await self._run_evaluation(
                project, student, teacher_observation
            )
            log.info("Step 4 完成: 评价 %d 字", len(result.evaluation))
        except Exception as e:
            log.exception("Step 4 失败: %s", e)
            result.errors["evaluation"] = str(e)

        return result

    # =========================
    # 单步重试
    # =========================
    async def regenerate_one(
        self,
        field_name: str,
        project: ProjectMetaSchema,
        student: StudentRead,
        knowledge_points: list[str] | None = None,
        teacher_observation: str = "",
    ) -> Any:
        """
        重新生成单个字段。

        field_name 可选：
          - knowledge_points
          - content_summary
          - homework_vocab
          - evaluation
        """
        if field_name not in STEP_FIELDS:
            raise ValueError(f"未知字段: {field_name}")

        log.info("重新生成字段: %s", field_name)
        code_content = self._build_code_content(project)

        if field_name == "knowledge_points":
            return await self._run_kp(project, code_content)
        if field_name == "content_summary":
            kp = knowledge_points or await self._run_kp(project, code_content)
            return await self._run_content_summary(project, code_content, kp)
        if field_name == "homework_vocab":
            kp = knowledge_points or await self._run_kp(project, code_content)
            return await self._run_homework_vocab(project, kp, student)
        if field_name == "evaluation":
            return await self._run_evaluation(
                project, student, teacher_observation
            )
        raise RuntimeError("unreachable")  # pragma: no cover

    # =========================
    # 内部：4 步实际调用
    # =========================
    async def _run_kp(
        self, project: ProjectMetaSchema, code_content: str
    ) -> list[str]:
        chain = self.chains["knowledge_points"]
        result = await asyncio.to_thread(
            chain.invoke,
            {
                "code_content": code_content[:3000],  # 截断避免超 token
                "course_topic": project.course_title or "未指定",
                "project_type": project.project_type,
            },
        )
        # 标准化为 list[str]
        if isinstance(result, list):
            return [str(x).strip() for x in result if str(x).strip()][:5]
        raise ValueError(f"知识点结果不是列表: {type(result)}")

    async def _run_content_summary(
        self, project: ProjectMetaSchema, code_content: str, kp: list[str]
    ) -> dict:
        chain = self.chains["content_summary"]
        result = await asyncio.to_thread(
            chain.invoke,
            {
                "knowledge_points": "、".join(kp),
                "code_content": code_content[:3000],
                "project_type": project.project_type,
            },
        )
        if not isinstance(result, dict):
            raise ValueError("内容概述结果不是 dict")
        return result

    async def _run_homework_vocab(
        self, project: ProjectMetaSchema, kp: list[str], student: StudentRead
    ) -> dict:
        chain = self.chains["homework_vocab"]
        result = await asyncio.to_thread(
            chain.invoke,
            {
                "knowledge_points": "、".join(kp),
                "project_type": project.project_type,
                "student_level": student.base_level,
            },
        )
        if not isinstance(result, dict):
            raise ValueError("作业/单词结果不是 dict")
        return result

    async def _run_evaluation(
        self,
        project: ProjectMetaSchema,
        student: StudentRead,
        teacher_observation: str,
    ) -> str:
        chain = self.chains["evaluation"]
        result = await asyncio.to_thread(
            chain.invoke,
            {
                "student_name": student.name,
                "student_age": student.age or "未知",
                "student_level": student.base_level,
                "student_characteristics": (
                    "、".join(student.characteristics) or "无特别记录"
                ),
                "course_topic": project.course_title or "本节课程",
                "knowledge_points": "、".join(
                    getattr(project, "_kp_for_eval", []) or []
                ) or "见上方知识点",
                "teacher_observation": teacher_observation or "（无补充）",
            },
        )
        return result.strip()

    # =========================
    # 工具
    # =========================
    def _build_code_content(self, project: ProjectMetaSchema) -> str:
        """拼接项目代码（启动文件全文 + 其他 .py 列表）。"""
        parts: list[str] = []
        for f in project.py_files:
            if f.path == project.entry_file:
                # 启动文件：尝试读全文
                parts.append(f"# === {f.path} ===\n{f.top_comment or ''}")
            else:
                # 其他文件：只列结构
                parts.append(
                    f"# === {f.path} ===\n"
                    f"imports: {f.imports}\n"
                    f"functions: {f.function_names}\n"
                    f"classes: {f.class_names}"
                )
        return "\n\n".join(parts)
