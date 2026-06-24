"""
志愿探雷器 API 路由 (V3 — 真实 SSE + 智能 Mock 回退 + 联网搜索)

接口:
  POST /api/check-risk        — 普通 JSON 请求
  GET  /api/check-risk/stream — SSE 流式推送
  POST /api/check-risk/live   — 联网实时检索非核心高校章程

SSE 日志现在包含真实考生数据（分数、省份、英语单科等），
逐目标展示审查过程，最后一步调用真正的 AI API 或智能 Mock。
"""
import asyncio
import json
import time
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from services.risk_checker import batch_check_risks, check_admission_risk
from services.enrollment_kb import get_knowledge_base
from schemas import CheckRiskRequest, CheckRiskResponse, RiskCheckItem, RiskTarget

router = APIRouter(prefix="/api/check-risk", tags=["risk-checker"])


def _sse_line(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _sse_event_generator(
    user_profile: dict,
    targets: list[dict[str, str]],
) -> AsyncGenerator[str, None]:
    """
    SSE 生成器：使用考生真实档案数据 + 志愿列表，
    逐目标推送审查日志，最后返回审查结果。
    """
    score = user_profile.get("score", "?")
    province = user_profile.get("province", "?")
    english = user_profile.get("english_score", "?")
    vision = user_profile.get("vision_status", "正常")
    rank = user_profile.get("rank", "?")

    # ── Step 1: 展示真实考生档案 ──────────────────────────
    ts = int(time.time())
    yield _sse_line({"type": "log", "text": "[INIT] 建立安全连接... 就绪", "ts": ts})
    await asyncio.sleep(0.2)

    yield _sse_line({"type": "log", "text": f"[PROFILE] 考生档案: 总分{score} | {province} | 英语{english} | 视力{vision} | 位次{rank}", "ts": ts})
    await asyncio.sleep(0.3)

    yield _sse_line({"type": "log", "text": f"[TARGETS] 本次审查 {len(targets)} 个志愿目标", "ts": ts})
    await asyncio.sleep(0.2)

    yield _sse_line({"type": "log", "text": "────────────────────────────────", "ts": ts})
    await asyncio.sleep(0.1)

    # ── Step 2: 逐目标真实审查 ────────────────────────────
    results = []

    for i, t in enumerate(targets):
        univ = t.get("university", "未知大学")
        major = t.get("major", "未知专业")

        ts = int(time.time())
        yield _sse_line({"type": "log", "text": f">>> [{i+1}/{len(targets)}] 审查: 【{univ}】{major}", "ts": ts})
        await asyncio.sleep(0.2)

        # ── V3.1: 真实知识库检索 ──
        kb_hit = False
        live_search_used = False
        try:
            kb = get_knowledge_base()
            kb_rule = kb.query(univ, major)
            if kb_rule.get("found"):
                kb_hit = True
                if kb_rule.get("body_check"):
                    ts = int(time.time())
                    yield _sse_line({"type": "log", "text": f"   [KB] ✓ 已检索 {univ} 章程条款: 体检限制={list(kb_rule['body_check'].keys())}", "ts": ts})
                else:
                    ts = int(time.time())
                    yield _sse_line({"type": "log", "text": f"   [KB] ✓ 已检索 {univ} 章程条款: 该专业无特殊限制", "ts": ts})
            else:
                full_len = len(kb.get_full_articles(univ))
                if full_len > 0:
                    ts = int(time.time())
                    yield _sse_line({"type": "log", "text": f"   [KB] ⚠ {univ} 未收录结构化规则，加载章程全文({full_len}字)", "ts": ts})
                else:
                    # ── 本地无数据，启动联网搜索 ──
                    ts = int(time.time())
                    yield _sse_line({"type": "log", "text": f"   [LIVE] 🌐 {univ} 未在本地数据库，启动联网检索...", "ts": ts})
                    await asyncio.sleep(0.5)

                    try:
                        from services.live_search import search_university_rules
                        live_result = await search_university_rules(univ)
                        if live_result.get("rules") and not live_result.get("error"):
                            live_search_used = True
                            url = live_result.get("url", "未知")
                            ts = int(time.time())
                            yield _sse_line({"type": "log", "text": f"   [LIVE] ✓ 联网检索成功: {url[:80]}", "ts": ts})
                            # 将联网结果注入知识库缓存
                            kb._inject_live_result(univ, live_result["rules"])
                        else:
                            ts = int(time.time())
                            yield _sse_line({"type": "log", "text": f"   [LIVE] ⚠ 联网检索未找到有效章程", "ts": ts})
                    except Exception as e:
                        ts = int(time.time())
                        yield _sse_line({"type": "log", "text": f"   [LIVE] ❌ 联网检索失败: {str(e)[:60]}", "ts": ts})
        except Exception:
            ts = int(time.time())
            yield _sse_line({"type": "log", "text": f"   [KB] ⚠ 知识库暂不可用，使用通用规则", "ts": ts})

        await asyncio.sleep(0.2)

        ts = int(time.time())
        yield _sse_line({"type": "log", "text": f"   [MATCH] 核对: 单科成绩 ≥ 门槛? 体检合格? 语种限制?", "ts": ts})
        await asyncio.sleep(0.3)

        # 实际调用 AI API（或智能 Mock）
        result = await check_admission_risk(
            user_profile=user_profile,
            target_university=univ,
            target_major=major,
        )

        # 将审查结果输出到 Terminal
        status_labels = {"DANGER": "⚠ 极高退档风险", "WARNING": "⚡ 需关注", "PASS": "✓ 规则通过", "UNKNOWN": "? 未确认"}
        label = status_labels.get(result.get("status", "UNKNOWN"), result.get("status", ""))
        ts = int(time.time())
        yield _sse_line({"type": "log", "text": f"   → {label}: {result.get('reason', '')[:80]}", "ts": ts})

        # 标记数据来源
        result["source"] = "live" if live_search_used else "local"
        results.append({**t, **result})

    # ── Step 3: 汇总 ─────────────────────────────────────
    await asyncio.sleep(0.2)
    ts = int(time.time())
    yield _sse_line({"type": "log", "text": "────────────────────────────────", "ts": ts})

    danger_count = sum(1 for r in results if r.get("status") == "DANGER")
    warn_count = sum(1 for r in results if r.get("status") == "WARNING")
    pass_count = sum(1 for r in results if r.get("status") == "PASS")
    yield _sse_line({"type": "log", "text": f"[SUMMARY] 极高风险:{danger_count} | 需关注:{warn_count} | 通过:{pass_count}", "ts": int(time.time())})

    await asyncio.sleep(0.3)
    yield _sse_line({"type": "log", "text": "[COMPLETE] 审查完毕，生成诊断报告...", "ts": int(time.time())})
    await asyncio.sleep(0.3)

    # ── Step 4: 推送最终结果 JSON ─────────────────────────
    yield _sse_line({"type": "result", "data": results})
    yield _sse_line({"type": "done"})


# ── 路由 ────────────────────────────────────────────────────────

@router.post("", response_model=CheckRiskResponse)
async def run_risk_check(payload: CheckRiskRequest):
    """普通 JSON 请求。"""
    if not payload.targets:
        raise HTTPException(status_code=400, detail="审查目标列表不能为空")
    if len(payload.targets) > 50:
        raise HTTPException(status_code=400, detail="单次最多审查 50 个志愿组合")

    user_profile = payload.profile.model_dump()
    results = await batch_check_risks(
        user_profile=user_profile,
        targets=[t.model_dump() for t in payload.targets],
    )
    return CheckRiskResponse(total=len(results), results=[RiskCheckItem(**r) for r in results])


@router.get("/stream")
async def run_risk_check_stream(
    profile_json: str = Query(..., description="考生档案 JSON"),
    targets_json: str = Query(..., description="志愿列表 JSON"),
):
    """
    SSE 流式接口。

    前端通过 EventSource 消费:
      data: {"type":"log","text":"...","ts":...}
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

    return StreamingResponse(
        _sse_event_generator(user_profile, targets),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 联网搜索接口 ─────────────────────────────────────────────

@router.post("/live", response_model=dict)
async def check_risk_live(target: RiskTarget):
    """
    联网实时检索非核心高校的招生章程并提取规则。
    
    用于本地数据库未覆盖的高校，通过 DuckDuckGo 搜索 + DeepSeek 提取。
    结果标注 source='live'，提醒用户仔细甄别。
    """
    from services.live_search import search_university_rules
    from services.enrollment_kb import get_knowledge_base

    # 先检查是否在本地数据库中
    kb = get_knowledge_base()
    local_rules = kb.search_rules(target.university, target.major)
    if local_rules:
        return {
            "university": target.university,
            "major": target.major,
            "source": "local",
            "rules": local_rules,
            "message": "该高校已在本地数据库中，无需联网搜索",
        }

    # 本地没有，联网搜索
    result = await search_university_rules(target.university)

    # 追加专业信息
    result["major"] = target.major
    return result
