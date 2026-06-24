"""
AI 志愿顾问 API 路由 (方案 C)

基于雪峰知识库 16 模块 + Tavily 联网搜索的多轮对话咨询。

接口:
  POST /api/advisor          — 同步聊天
  GET  /api/advisor/stream   — SSE 流式聊天
"""
import json
import time
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from schemas import AdvisorRequest, AdvisorResponse

router = APIRouter(prefix="/api/advisor", tags=["advisor"])


def _sse_line(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("", response_model=AdvisorResponse)
async def chat(payload: AdvisorRequest):
    """
    AI 顾问同步聊天。

    支持多轮对话（传入 history）和考生档案（传入 profile）。
    无 LLM API Key 时自动降级为纯知识库模式。
    """
    from services.advisor import chat as advisor_chat

    result = await advisor_chat(
        message=payload.message,
        history=[m.model_dump() for m in payload.history] if payload.history else None,
        user_profile=payload.profile.model_dump() if payload.profile else None,
    )

    return AdvisorResponse(
        reply=result["reply"],
        sources=result.get("sources"),
        data_trust_level=result.get("data_trust_level"),
        suggestions=result.get("suggestions"),
    )


@router.get("/stream")
async def chat_stream(
    message: str = Query(..., min_length=1, max_length=2000, description="用户提问"),
    history_json: str = Query("[]", description="对话历史 JSON"),
    profile_json: str = Query("{}", description="考生档案 JSON（可选）"),
):
    """
    AI 顾问流式聊天（SSE）。

    前端 EventSource 消费:
      data: {"type":"knowledge","data":"..."}   — 检索到的知识
      data: {"type":"live","data":"..."}         — 联网搜索结果
      data: {"type":"token","data":"..."}        — LLM 输出 token
      data: {"type":"done","data":{...}}         — 完成
    """
    from services.advisor import chat_stream as advisor_stream

    try:
        history = json.loads(history_json) if history_json else []
    except json.JSONDecodeError:
        history = []

    try:
        profile = json.loads(profile_json) if profile_json and profile_json != "{}" else None
    except json.JSONDecodeError:
        profile = None

    async def generator() -> AsyncGenerator[str, None]:
        try:
            async for event in advisor_stream(
                message=message,
                history=history,
                user_profile=profile,
            ):
                yield _sse_line(event)
        except Exception as e:
            yield _sse_line({"type": "error", "data": str(e)})

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
