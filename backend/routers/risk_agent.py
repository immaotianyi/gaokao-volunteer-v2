"""
志愿探雷器 API 路由 (V4 — AI Agent 流式推理)

Agent 模式 (独立 prefix，与 V3 规则引擎共存):
  GET  /api/check-risk/agent/stream — Agent 多轮推理 SSE 流
  POST /api/check-risk/agent         — Agent 同步审核

V3 规则引擎 (保持不变):
  GET  /api/check-risk/stream        — V3 SSE 流
  POST /api/check-risk               — V3 JSON

与 V3 的区别:
  - V3 是单次 AI 调用 + 规则引擎 fallback
  - V4 是 Agent 多轮推理：Agent 自主决定调用哪些知识工具，
    逐条验证体检、单科、选科、调剂风险，输出带条款引用的结构化报告。
"""
import asyncio
import json
import time
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from schemas import CheckRiskRequest, CheckRiskResponse, RiskCheckItem

router = APIRouter(prefix="/api/check-risk/agent", tags=["risk-checker-agent"])


# ── SSE 工具函数 ────────────────────────────────────────────────

def _sse_line(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── Agent 流式生成器 ───────────────────────────────────────────

async def _agent_sse_generator(
    user_profile: dict,
    targets: list[dict[str, str]],
    provider: str = "mock",
    prompt_mode: str = "default",
) -> AsyncGenerator[str, None]:
    """
    Agent SSE 生成器：
    - 实时推送 Agent 思考过程 (thinking)
    - 实时推送工具调用过程 (tool_call / tool_result)
    - 最终推送审核结论 (result)
    """
    from services.risk_agent import create_risk_agent, AgentEvent

    agent = create_risk_agent(provider=provider, prompt_mode=prompt_mode)

    score = user_profile.get("score", "?")
    province = user_profile.get("province", "?")
    english = user_profile.get("english_score", "?")
    vision = user_profile.get("vision_status", "正常")
    rank = user_profile.get("rank", "?")
    subjects = user_profile.get("subjects", "?")

    ts = int(time.time())

    # ── Phase 1: 初始化 ──────────────────────────
    yield _sse_line({"type": "log", "text": "[AGENT] 启动志愿审核 AI Agent...", "ts": ts})
    await asyncio.sleep(0.3)

    yield _sse_line({
        "type": "log",
        "text": f"[PROFILE] 考生档案: 总分{score} | {province} | {subjects} | 英语{english} | 视力{vision} | 位次{rank}",
        "ts": ts,
    })
    await asyncio.sleep(0.2)

    yield _sse_line({
        "type": "log",
        "text": f"[TARGETS] Agent 将逐条审查 {len(targets)} 个志愿目标",
        "ts": ts,
    })
    await asyncio.sleep(0.3)

    yield _sse_line({"type": "log", "text": "────────────────────────────────", "ts": ts})
    await asyncio.sleep(0.1)

    # ── Phase 2: Agent 流式推理 ────────────────────
    results = []
    tool_calls_log = []

    try:
        async for event in agent.audit_stream(
            user_profile=user_profile,
            targets=targets,
        ):
            ts = int(time.time())

            if event.type == "thinking":
                yield _sse_line({
                    "type": "log",
                    "text": f"[THINKING] {event.content}",
                    "ts": ts,
                })

            elif event.type == "tool_call":
                tool_name = event.data.get("tool", "") if event.data else ""
                tool_calls_log.append(tool_name)
                yield _sse_line({
                    "type": "log",
                    "text": f"[TOOL] 🔧 调用知识库工具: {tool_name}",
                    "ts": ts,
                })
                await asyncio.sleep(0.15)

            elif event.type == "tool_result":
                tool_data = event.data or {}
                if isinstance(tool_data, dict) and tool_data.get("error"):
                    yield _sse_line({
                        "type": "log",
                        "text": f"[TOOL] ⚠ 工具返回异常: {tool_data['error']}",
                        "ts": ts,
                    })
                else:
                    yield _sse_line({
                        "type": "log",
                        "text": f"[TOOL] ✓ 知识检索完成",
                        "ts": ts,
                    })
                await asyncio.sleep(0.1)

            elif event.type == "conclusion":
                data = event.data or {}
                if isinstance(data, dict):
                    # 从 Agent 返回中提取审核结果
                    agent_results = data.get("results", [])
                    if not agent_results and "result" in data:
                        agent_results = data["result"].get("results", [])

                    for r in agent_results:
                        results.append(r)
                        status = r.get("status", "UNKNOWN")
                        reason = r.get("reason", "")[:100]
                        label = {
                            "DANGER": "⚠ 极高退档风险",
                            "WARNING": "⚡ 需关注",
                            "PASS": "✓ 规则通过",
                            "UNKNOWN": "? 未确认",
                        }.get(status, status)

                        yield _sse_line({
                            "type": "log",
                            "text": f"   → {label}: {reason}",
                            "ts": ts,
                        })

                    # 输出总结
                    summary = data.get("summary", {})
                    if summary:
                        yield _sse_line({
                            "type": "log",
                            "text": f"[SUMMARY] 极高风险:{summary.get('danger',0)} | 需关注:{summary.get('warning',0)} | 通过:{summary.get('pass',0)}",
                            "ts": int(time.time()),
                        })

            elif event.type == "done":
                yield _sse_line({
                    "type": "log",
                    "text": f"[AGENT] 推理完成，共调用 {len(tool_calls_log)} 次知识工具",
                    "ts": ts,
                })

    except Exception as e:
        yield _sse_line({
            "type": "log",
            "text": f"[ERROR] Agent 推理异常: {str(e)}，回退到规则引擎...",
            "ts": int(time.time()),
        })
        # fallback 到旧版规则引擎
        from services.risk_checker import check_admission_risk
        for t in targets:
            result = await check_admission_risk(
                user_profile=user_profile,
                target_university=t.get("university", ""),
                target_major=t.get("major", ""),
            )
            results.append({**t, **result})

    # ── Phase 3: 最终结果推送 ──────────────────────
    await asyncio.sleep(0.3)
    yield _sse_line({"type": "log", "text": "────────────────────────────────", "ts": int(time.time())})
    yield _sse_line({"type": "log", "text": "[COMPLETE] Agent 审核完毕，生成诊断报告...", "ts": int(time.time())})
    await asyncio.sleep(0.3)

    yield _sse_line({"type": "result", "data": results})
    yield _sse_line({"type": "done"})


# ════════════════════════════════════════════════════════════════
# 路由
# ════════════════════════════════════════════════════════════════

@router.post("", response_model=CheckRiskResponse)
async def run_risk_check_agent(
    payload: CheckRiskRequest,
    provider: str = Query("openai", description="LLM provider: openai(默认DeepSeek)/mock/dify/deepseek"),
    prompt_mode: str = Query("default", description="审核模式: default/strict/quick/detail"),
):
    """Agent 同步审核（POST JSON）。默认使用真实 LLM (DeepSeek V4 Flash)，API Key 未配置时自动回退 Mock。"""
    if not payload.targets:
        raise HTTPException(status_code=400, detail="审查目标列表不能为空")
    if len(payload.targets) > 50:
        raise HTTPException(status_code=400, detail="单次最多审查 50 个志愿组合")

    import os as _os
    from services.risk_agent import create_risk_agent

    # 如果选 openai/deepseek 但 API Key 为空，自动回退 mock
    actual_provider = provider
    if provider in ("openai", "deepseek") and not (_os.getenv("LLM_API_KEY") or _os.getenv("DEEPSEEK_API_KEY")):
        actual_provider = "mock"

    agent = create_risk_agent(provider=actual_provider, prompt_mode=prompt_mode)
    user_profile = payload.profile.model_dump()
    result = await agent.audit(
        user_profile=user_profile,
        targets=[t.model_dump() for t in payload.targets],
    )

    agent_results = result.get("results", [])
    if not agent_results and "result" in result:
        agent_results = result["result"].get("results", [])

    return CheckRiskResponse(
        total=len(agent_results),
        results=[RiskCheckItem(**r) for r in agent_results],
    )


@router.get("/stream")
async def run_risk_check_agent_stream(
    profile_json: str = Query(..., description="考生档案 JSON"),
    targets_json: str = Query(..., description="志愿列表 JSON"),
    provider: str = Query("openai", description="LLM provider: openai(默认DeepSeek)/mock/dify/deepseek"),
    prompt_mode: str = Query("default", description="审核模式: default/strict/quick/detail"),
):
    """
    Agent 流式审核 SSE 接口。

    与 V3 /stream 的区别：
      - 展示 Agent 思考过程 (THINKING)
      - 展示工具调用过程 (TOOL)
      - 真实 LLM 多轮推理（API Key 已配置时），未配置时自动回退 Mock

    前端 EventSource 消费:
      data: {"type":"log","text":"[THINKING] ...","ts":...}
      data: {"type":"log","text":"[TOOL] ...","ts":...}
      data: {"type":"result","data":[...]}
      data: {"type":"done"}
    """
    try:
        user_profile = json.loads(profile_json)
        targets = json.loads(targets_json)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"JSON 解析失败: {e}")

    if not targets:
        raise HTTPException(status_code=400, detail="审查目标列表不能为空")
    if len(targets) > 50:
        raise HTTPException(status_code=400, detail="单次最多审查 50 个志愿组合")

    # 如果选 openai/deepseek 但 API Key 为空，自动回退 mock
    import os as _os
    actual_provider = provider
    if provider in ("openai", "deepseek") and not (_os.getenv("LLM_API_KEY") or _os.getenv("DEEPSEEK_API_KEY")):
        actual_provider = "mock"

    return StreamingResponse(
        _agent_sse_generator(user_profile, targets, provider=actual_provider, prompt_mode=prompt_mode),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
