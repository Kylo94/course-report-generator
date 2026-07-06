"""AI 生成 API 路由。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_session
from backend.llm.base import get_provider
from backend.schemas.ai_generation import (
    AIGeneratedContent,
    AIGenerateRequest,
    AIGenerateResponse,
    AIRegenerateRequest,
    ContentItemSchema,
    HomeworkSchema,
    VocabularySchema,
)
from backend.schemas.project import ProjectMetaSchema
from backend.schemas.student import StudentRead
from backend.services import students as student_svc
from backend.services.ai_orchestrator import STEP_FIELDS, AIOrchestrator
from backend.utils.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _result_to_content(result_dict: dict) -> AIGeneratedContent:
    """将 orchestrator 字典结果转为 Pydantic schema。"""
    content_items = [
        ContentItemSchema(**item)
        for item in result_dict.get("content_items", [])
    ]
    homework_raw = result_dict.get("homework", {})
    homework = HomeworkSchema(
        goal=homework_raw.get("goal", ""),
        hints=homework_raw.get("hints", []),
        criteria=homework_raw.get("criteria", []),
    )
    vocab_raw = result_dict.get("vocabulary", {})
    vocabulary = VocabularySchema(
        word=vocab_raw.get("word", ""),
        phonetic=vocab_raw.get("phonetic", ""),
        meaning=vocab_raw.get("meaning", ""),
        example=vocab_raw.get("example", ""),
    )
    return AIGeneratedContent(
        knowledge_points=result_dict.get("knowledge_points", []),
        ability_improvement=result_dict.get("ability_improvement", ""),
        content_items=content_items,
        homework=homework,
        vocabulary=vocabulary,
        evaluation=result_dict.get("evaluation", ""),
    )


@router.post(
    "/generate",
    response_model=AIGenerateResponse,
    summary="一键生成报告全部 AI 内容",
)
async def generate_report(
    req: AIGenerateRequest, session: AsyncSession = Depends(get_session)
) -> AIGenerateResponse:
    try:
        # 1. 取学生
        student = await student_svc.get_student(session, req.student_id)
        student_read = StudentRead.model_validate(student)

        # 2. 构造 project_meta
        project = ProjectMetaSchema(**req.project)

        # 3. 编排生成
        orch = AIOrchestrator()
        result = await orch.generate_all(
            project, student_read, req.teacher_observation,
            existing_content=req.existing_content,
        )

        content = _result_to_content(result.to_dict())
        return AIGenerateResponse(
            student_id=req.student_id,
            content=content,
            errors=result.errors,
        )
    except student_svc.StudentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.exception("AI 生成失败: %s", e)
        raise HTTPException(status_code=500, detail=f"AI 生成失败: {e}")


@router.post(
    "/regenerate",
    response_model=dict,
    summary="重新生成单个字段",
)
async def regenerate_field(
    req: AIRegenerateRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    if req.field not in STEP_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"未知字段: {req.field}，可选: {STEP_FIELDS}",
        )
    try:
        student = await student_svc.get_student(session, req.student_id)
        student_read = StudentRead.model_validate(student)
        project = ProjectMetaSchema(**req.project)
        orch = AIOrchestrator()
        result = await orch.regenerate_one(
            req.field,
            project,
            student_read,
            knowledge_points=req.knowledge_points,
            teacher_observation=req.teacher_observation,
        )
        return {"field": req.field, "value": result}
    except student_svc.StudentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.exception("重新生成失败: %s", e)
        raise HTTPException(status_code=500, detail=f"重新生成失败: {e}")


@router.get("/providers", response_model=list[str], summary="支持的 LLM 供应商列表")
async def list_providers() -> list[str]:
    return ["deepseek", "minimax", "qwen", "glm", "openai", "claude"]


@router.post("/test-connection", summary="测试当前 LLM 配置连通性")
async def test_connection() -> dict:
    try:
        provider = get_provider()
        ok, msg = provider.test_connection()
        return {
            "provider": provider.name,
            "success": ok,
            "message": msg,
        }
    except Exception as e:
        return {
            "provider": None,
            "success": False,
            "message": str(e),
        }


# =========================
# WebSocket 流式生成
# =========================
@router.websocket("/ws/generate")
async def websocket_generate(websocket: WebSocket) -> None:
    """
    WebSocket 流式 AI 生成。

    协议：
      Client → Server: {"project": {...}, "student_id": 1, "field": "evaluation"}
      Server → Client: {"type": "start", "field": "evaluation"}
                       {"type": "chunk", "field": "evaluation", "content": "..."}
                       {"type": "done", "field": "evaluation"}
                       {"type": "error", "field": "evaluation", "message": "..."}
    """
    await websocket.accept()
    log.info("WebSocket 连接已建立")
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                field = payload.get("field")
                if field not in STEP_FIELDS:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"未知字段: {field}",
                    })
                    continue

                await websocket.send_json({"type": "start", "field": field})

                # 流式调用
                from backend.services.ai_chains import build_streaming_chains
                provider = get_provider()
                chains = build_streaming_chains(provider)
                chain = chains[field]

                # 准备输入（简化：仅支持 evaluation，其他字段需要复杂输入）
                inputs = _build_stream_inputs(field, payload)

                # 累积内容
                accumulated = ""
                async for chunk in chain.astream(inputs):
                    accumulated += chunk
                    await websocket.send_json({
                        "type": "chunk",
                        "field": field,
                        "content": chunk,
                    })

                await websocket.send_json({
                    "type": "done",
                    "field": field,
                    "total_content": accumulated,
                })
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "JSON 解析失败",
                })
            except Exception as e:
                log.exception("流式生成失败: %s", e)
                await websocket.send_json({
                    "type": "error",
                    "field": payload.get("field"),
                    "message": str(e),
                })
    except WebSocketDisconnect:
        log.info("WebSocket 断开")


def _build_stream_inputs(field: str, payload: dict) -> dict:
    """构造流式输入（简化版，仅支持 evaluation）。"""
    if field == "evaluation":
        return {
            "student_name": payload.get("student_name", "学生"),
            "student_age": payload.get("student_age", "未知"),
            "student_level": payload.get("student_level", "入门"),
            "student_characteristics": payload.get(
                "student_characteristics", "无特别记录"
            ),
            "course_topic": payload.get("course_topic", "本节课程"),
            "knowledge_points": payload.get("knowledge_points", ""),
            "teacher_observation": payload.get("teacher_observation", "（无）"),
        }
    raise NotImplementedError(f"暂不支持流式字段: {field}")
