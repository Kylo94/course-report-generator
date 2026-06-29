"""
AI Orchestrator（顶层编排）

设计原则（按策划书 4.2.1）：
- 不使用 LangChain Chain/LCEL 串联
- 顶层用业务代码控制：单步可重试 + 断点续跑
- 每步结果可独立 invoke，失败不影响其他字段

两阶段设计（v2）：
  Phase 1: _analyze_code() — 通读所有代码，输出结构化分析 JSON
  Phase 2: 4 个生成步骤 — 仅用分析结果，不再传原始代码
"""
from __future__ import annotations

import asyncio
import json
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
    AI 编排器（两阶段设计）。

    Phase 1 — 代码分析：通读项目所有代码，输出结构化的函数/技术点分析
    Phase 2 — 内容生成：基于分析结果（不带原始代码）生成各字段

    使用：
        orch = AIOrchestrator()
        result = await orch.generate_all(project_meta, student)
    """

    def __init__(self, provider: LLMProvider | None = None):
        if provider is None:
            from backend.config import get_settings
            provider = get_provider(get_settings().llm)
        self.provider = provider
        self.chains: dict[str, Runnable] = build_chains(self.provider)
        self._code_cache: str | None = None  # 缓存 code_content，避免重复读盘
        self._analysis_cache: dict | None = None  # 缓存分析结果

    # =========================
    # Phase 1: 代码分析
    # =========================

    async def _analyze_code(self, project: ProjectMetaSchema) -> dict:
        """Phase 1：通读项目全部代码，输出结构化分析。

        这是唯一一次传原始代码给 LLM 的步骤。
        返回 JSON：
        {
          "course_topic": "...",
          "main_objectives": ["目标1", "目标2"],
          "key_functions": [
            {"name": "func()", "purpose": "...", "technique": "...",
             "code_snippet": "...", "related_objectives": [0]}
          ],
          "python_techniques": ["技术点1", "技术点2"]
        }
        """
        if self._analysis_cache is not None:
            return self._analysis_cache

        code_content = self._build_code_content(project)
        entry_comment = self._get_entry_comment(project)

        chain = self.chains["code_analysis"]
        result = await asyncio.to_thread(
            chain.invoke,
            {
                "entry_comment": entry_comment,
                "course_topic": project.course_title or "未指定",
                "project_type": project.project_type,
                "code_content": code_content[:5000],  # 分析阶段给更多代码
            },
        )

        if not isinstance(result, dict):
            log.warning("代码分析结果不是 dict，使用空分析: %s", type(result))
            result = self._empty_analysis(project)

        self._analysis_cache = result
        log.info(
            "Phase 1 代码分析完成: %d 个目标, %d 个关键函数, %d 个技术点",
            len(result.get("main_objectives", [])),
            len(result.get("key_functions", [])),
            len(result.get("python_techniques", [])),
        )
        return result

    def _empty_analysis(self, project: ProjectMetaSchema) -> dict:
        """分析失败时的兜底空分析。"""
        return {
            "course_topic": project.course_title or "",
            "main_objectives": [],
            "key_functions": [],
            "python_techniques": [],
        }

    def _format_analysis(self, analysis: dict) -> str:
        """将结构化分析格式化为 readable 文本，传给后续生成步骤。

        这是替代原始 code_content 的产物——小得多、更聚焦。
        """
        lines = ["【代码分析结果】"]
        lines.append(f"课程主题：{analysis.get('course_topic', '')}")
        lines.append("")

        objectives = analysis.get("main_objectives", [])
        if objectives:
            lines.append("主要功能目标：")
            for i, obj in enumerate(objectives):
                lines.append(f"  {i + 1}. {obj}")
            lines.append("")

        functions = analysis.get("key_functions", [])
        if functions:
            lines.append("关键函数：")
            for f in functions:
                obj_refs = f.get("related_objectives", [])
                obj_str = ""
                if obj_refs and objectives:
                    parts = [f"目标 {i + 1}" for i in obj_refs if i < len(objectives)]
                    obj_str = f"（关联：{'、'.join(parts)}）" if parts else ""
                file_info = ""
                fp = f.get("file_path", "")
                sl = f.get("start_line")
                el = f.get("end_line")
                if fp and sl and el:
                    file_info = f" [{fp}:{sl}-{el}]"
                lines.append(f"  - {f.get('name', '?')}{file_info} {obj_str}")
                lines.append(f"    用途：{f.get('purpose', '')}")
                lines.append(f"    技术点：{f.get('technique', '')}")
                snippet = f.get("code_snippet", "")
                if snippet:
                    lines.append(f"    代码片段：{snippet[:200]}")
            lines.append("")

        techniques = analysis.get("python_techniques", [])
        if techniques:
            lines.append(f"Python 技术点：{'、'.join(techniques)}")
            lines.append("")

        return "\n".join(lines)

    # =========================
    # Phase 2: 全量生成
    # =========================
    async def generate_all(
        self,
        project: ProjectMetaSchema,
        student: StudentRead,
        teacher_observation: str = "",
    ) -> GenerationResult:
        """
        两阶段生成：
        Phase 1 — 代码分析（仅一次）
        Phase 2 — 4 步链式生成（基于分析结果，不带原始代码）

        任意步骤失败不中断，记录到 result.errors。
        """
        log.info(
            "开始生成报告: course=%s student=%s",
            project.course_title,
            student.name,
        )

        # Phase 1: 代码分析
        analysis = await self._analyze_code(project)
        analysis_text = self._format_analysis(analysis)

        result = GenerationResult(analysis=analysis)

        # Phase 2 - Step 1: 知识点
        try:
            result.knowledge_points = await self._run_kp(
                project, analysis_text, analysis
            )
            log.info("Step 1 完成: %d 个知识点", len(result.knowledge_points))
        except Exception as e:
            log.exception("Step 1 失败: %s", e)
            result.errors["knowledge_points"] = str(e)
            return result

        # Phase 2 - Step 2: 内容概述 + 能力提升
        try:
            cs = await self._run_content_summary(
                project, analysis_text, result.knowledge_points
            )
            result.content_items = cs.get("content_items", [])
            result.ability_improvement = cs.get("ability_improvement", "")
            log.info("Step 2 完成: %d 个内容块", len(result.content_items))
        except Exception as e:
            log.exception("Step 2 失败: %s", e)
            result.errors["content_summary"] = str(e)
            return result

        # Phase 2 - Step 3: 作业 + 单词
        try:
            hv = await self._run_homework_vocab(
                project, analysis_text, result.knowledge_points, student,
            )
            result.homework = hv.get("homework", {})
            result.vocabulary = hv.get("vocabulary", {})
            log.info("Step 3 完成: 作业 %d 提示点", len(result.homework.get("hints", [])))
        except Exception as e:
            log.exception("Step 3 失败: %s", e)
            result.errors["homework_vocab"] = str(e)

        # Phase 2 - Step 4: 学生评价
        try:
            result.evaluation = await self._run_evaluation(
                project, student, teacher_observation,
                knowledge_points=result.knowledge_points,
                analysis_text=analysis_text,
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

        # 先做代码分析（如果缓存则命中）
        analysis = await self._analyze_code(project)
        analysis_text = self._format_analysis(analysis)

        if field_name == "knowledge_points":
            return await self._run_kp(project, analysis_text, analysis)
        if field_name == "content_summary":
            kp = knowledge_points or await self._run_kp(project, analysis_text, analysis)
            return await self._run_content_summary(project, analysis_text, kp)
        if field_name == "homework_vocab":
            kp = knowledge_points or await self._run_kp(project, analysis_text, analysis)
            return await self._run_homework_vocab(
                project, analysis_text, kp, student,
            )
        if field_name == "evaluation":
            return await self._run_evaluation(
                project, student, teacher_observation,
                knowledge_points=knowledge_points or None,
                analysis_text=analysis_text,
            )
        raise RuntimeError("unreachable")

    async def get_analysis_text(self, project: ProjectMetaSchema) -> str:
        """获取格式化的代码分析文本（供外部调用，如 batch 端点的 evaluations）。"""
        analysis = await self._analyze_code(project)
        return self._format_analysis(analysis)

    # =========================
    # 批量生成（班级模式）
    # =========================

    async def generate_shared(
        self,
        project: ProjectMetaSchema,
        default_student: StudentRead,
        teacher_observation: str = "",
    ) -> dict:
        """批量模式：仅生成共享内容（Steps 1-3）。

        所有学生共享这部分内容，只需执行一次。
        """
        log.info("批量生成共享内容: course=%s", project.course_title)

        # Phase 1: 代码分析
        analysis = await self._analyze_code(project)
        analysis_text = self._format_analysis(analysis)

        # Phase 2 - Step 1: 知识点
        try:
            kp = await self._run_kp(project, analysis_text, analysis)
            log.info("共享 Step 1 完成: %d 个知识点", len(kp))
        except Exception as e:
            log.exception("批量 Step 1 失败: %s", e)
            raise

        # Phase 2 - Step 2: 内容概述
        try:
            cs = await self._run_content_summary(project, analysis_text, kp)
            log.info("共享 Step 2 完成: %d 个内容块", len(cs.get("content_items", [])))
        except Exception as e:
            log.exception("批量 Step 2 失败: %s", e)
            raise

        # Phase 2 - Step 3: 作业 + 单词
        try:
            hv = await self._run_homework_vocab(project, analysis_text, kp, default_student)
            log.info("共享 Step 3 完成")
        except Exception as e:
            log.exception("批量 Step 3 失败: %s", e)
            raise

        return {
            "knowledge_points": kp,
            "content_items": cs.get("content_items", []),
            "ability_improvement": cs.get("ability_improvement", ""),
            "homework": hv.get("homework", {}),
            "vocabulary": hv.get("vocabulary", {}),
            "code_analysis": analysis,  # 代码分析结果（含 key_functions 的 line range）
        }

    async def generate_evaluations(
        self,
        project: ProjectMetaSchema,
        students: list[StudentRead],
        shared_content: dict,
        teacher_observation: str = "",
        analysis_text: str = "",
    ) -> list:
        """批量模式：为多个学生并行生成评价（Step 4）。

        不再传原始代码——使用预先分析好的 analysis_text。
        """
        log.info("批量生成评价: %d 名学生", len(students))
        kp = shared_content.get("knowledge_points", [])

        async def _eval_one(student: StudentRead) -> str:
            return await self._run_evaluation(
                project, student, teacher_observation,
                knowledge_points=kp,
                analysis_text=analysis_text,
            )

        tasks = [_eval_one(s) for s in students]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

    # =========================
    # 内部：4 步生成调用（Phase 2）
    # 所有方法接收 analysis_text（格式化分析结果）而非原始 code_content
    # =========================

    def _get_entry_comment(self, project: ProjectMetaSchema) -> str:
        """提取入口文件的完整顶部注释（含课程目标描述）。"""
        if not project.entry_file:
            return ""
        for f in project.py_files:
            if f.path == project.entry_file:
                return f.top_comment or ""
        return ""

    def _format_techniques(self, analysis: dict) -> str:
        """从分析结果提取技术点列表字符串。"""
        techniques = analysis.get("python_techniques", [])
        if techniques:
            return "、".join(techniques)
        return ""

    async def _run_kp(
        self, project: ProjectMetaSchema, analysis_text: str, analysis: dict
    ) -> list[str]:
        chain = self.chains["knowledge_points"]
        result = await asyncio.to_thread(
            chain.invoke,
            {
                "analysis_text": analysis_text,
                "course_topic": project.course_title or "未指定",
                "project_type": project.project_type,
                "entry_comment": self._get_entry_comment(project),
                "python_techniques": self._format_techniques(analysis),
            },
        )
        if not isinstance(result, list):
            raise ValueError(f"知识点结果不是列表: {type(result)}")

        items = [str(x).strip() for x in result if str(x).strip()][:5]

        # 兜底补齐
        fallbacks = [
            "变量赋值建立抽象概念",
            "if-else 训练条件判断逻辑",
            "for 循环强化重复执行思维",
            "函数定义培养分解能力",
            "调试代码提升排查技能",
        ]
        while len(items) < 5:
            items.append(fallbacks[len(items)])

        return items[:5]

    async def _run_content_summary(
        self, project: ProjectMetaSchema, analysis_text: str, kp: list[str]
    ) -> dict:
        chain = self.chains["content_summary"]
        result = await asyncio.to_thread(
            chain.invoke,
            {
                "knowledge_points": "、".join(kp),
                "analysis_text": analysis_text,
                "project_type": project.project_type,
                "entry_comment": self._get_entry_comment(project),
            },
        )
        if not isinstance(result, dict):
            raise ValueError("内容概述结果不是 dict")
        return result

    async def _run_homework_vocab(
        self, project: ProjectMetaSchema, analysis_text: str, kp: list[str],
        student: StudentRead,
    ) -> dict:
        chain = self.chains["homework_vocab"]
        result = await asyncio.to_thread(
            chain.invoke,
            {
                "knowledge_points": "、".join(kp),
                "analysis_text": analysis_text,
                "project_type": project.project_type,
                "student_level": student.base_level,
                "entry_comment": self._get_entry_comment(project),
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
        knowledge_points: list[str] | None = None,
        analysis_text: str = "",
    ) -> str:
        kp_str = "、".join(knowledge_points) if knowledge_points else "（见上方知识点）"
        chain = self.chains["evaluation"]
        result = await asyncio.to_thread(
            chain.invoke,
            {
                "student_name": student.name,
                "student_age": student.age or "未知",
                "student_gender": student.gender or "未知",
                "student_level": student.base_level,
                "student_characteristics": (
                    "、".join(student.characteristics) or "无特别记录"
                ),
                "course_topic": project.course_title or "本节课程",
                "knowledge_points": kp_str,
                "analysis_text": analysis_text,
                "teacher_observation": teacher_observation or "（无补充）",
                "entry_comment": self._get_entry_comment(project),
            },
        )
        return result.strip()

    # =========================
    # 工具
    # =========================
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

        from pathlib import Path

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
