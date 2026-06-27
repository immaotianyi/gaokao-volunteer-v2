"""
捡漏雷达 API 路由 (V3 — 三层缓存 + 差异追踪)

- POST /api/leakage-radar  主接口，三层缓存策略
- 缓存层级:
  Layer 1: raw:plans:{year}:{province}:{subject_group} — 原始数据缓存（手动刷新）
  Layer 2: radar:{province}:{subject_group}:{filter_hash} — 算法结果缓存（24h TTL）
  Layer 3: user:radar:{user_id}:{query_hash} — 用户个性化缓存（1h TTL）

- 差异追踪: 对比当日与昨日结果，返回 new_since_yesterday 字段
"""
import json
import hashlib
import os
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from services.leakage_radar import find_leakage_opportunities, DEFAULT_NEW_CAMPUSES
from schemas import (
    LeakageRadarRequest, LeakageRadarResponse, LeakageOpportunity,
    CustomLeakageRequest, CustomLeakageResponse,
    CustomLeakageUnlockRequest, CustomLeakageUnlockResponse,
)

router = APIRouter(prefix="/api/leakage-radar", tags=["leakage-radar"])

CACHE_TTL_RADAR = 86400       # 24 小时 (Layer 2)
CACHE_TTL_USER = 3600         # 1 小时  (Layer 3)
CACHE_TTL_RAW = 0             # 永久     (Layer 1, 手动删除)

# 差异追踪 Key
DIFF_TRACK_KEY = "leakage:diff_track"


import math


def _safe_opportunity(item: dict) -> LeakageOpportunity:
    """安全构建 LeakageOpportunity，过滤掉 Pydantic 不接受的 nan/inf/None 值。"""
    clean = {}
    for k, v in item.items():
        if v is None:
            # bool 字段不能为 None，转为 False
            if k in ("is_sino_foreign", "is_high_tuition", "is_new_campus", "is_first_batch"):
                clean[k] = False
            else:
                clean[k] = None
        elif isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                clean[k] = None
            else:
                clean[k] = v
        else:
            clean[k] = v
    return LeakageOpportunity(**clean)


def _diff_key(university_name: str, major_name: str, group_code: str = "") -> str:
    """统一差异追踪 key 格式，确保缓存命中与新算两种路径可比。"""
    return f"{university_name}|{major_name}|{group_code}"


def _cache_key_from_params(
    province: str,
    subject_group: str,
    batch: str = "",
    school_types: str = "",
    min_score: str = "",
    max_score: str = "",
    user_score: str = "",
) -> str:
    """构建 Layer 2 缓存 Key（含全部过滤参数哈希）。"""
    filter_str = f"{batch}|{school_types}|{min_score}|{max_score}|{user_score}"
    filter_hash = hashlib.md5(filter_str.encode()).hexdigest()[:8] if filter_str != "||||" else "default"
    return f"radar:{province}:{subject_group}:{filter_hash}"


def _load_new_campuses() -> list[dict]:
    """从 JSON 文件加载新校区字典。"""
    data_dir = Path(__file__).parent.parent / "data"
    campus_file = data_dir / "new_campuses.json"
    if campus_file.exists():
        try:
            with open(campus_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_NEW_CAMPUSES


async def _track_daily_diff(
    redis,
    province: str,
    subject_group: str,
    current_keys: set,
) -> int:
    """
    差异追踪：对比今天和昨天的 unique_key 集合，返回新增数量。

    存储结构：
    - leakage:diff_track:{province}:{subject_group}:{date} → set of unique_keys
    """
    if redis is None:
        return 0

    today_str = datetime.now().strftime("%Y-%m-%d")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    today_key = f"leakage:diff_track:{province}:{subject_group}:{today_str}"
    yesterday_key = f"leakage:diff_track:{province}:{subject_group}:{yesterday_str}"

    # 存储今天的 unique_keys
    if current_keys:
        await redis.delete(today_key)
        await redis.sadd(today_key, *list(current_keys)[:10000])  # 限制上限
        await redis.expire(today_key, 86400 * 7)  # 保留 7 天

    # 获取昨天的 keys
    yesterday_keys = await redis.smembers(yesterday_key)
    if yesterday_keys:
        yesterday_set = set(yesterday_keys)
        new_count = len(current_keys - yesterday_set)
        return new_count

    return 0


async def _get_last_updated(redis) -> str | None:
    """获取数据最后更新时间。"""
    if redis is None:
        return None
    ts = await redis.get("leakage:last_updated")
    return ts


@router.post("", response_model=LeakageRadarResponse)
async def run_leakage_radar(payload: LeakageRadarRequest, request: Request):
    """
    执行捡漏雷达分析（V3 三层缓存 + 差异追踪）。

    新增参数:
    - user_score: 用户分数（用于估分匹配和分数区间默认值）
    - user_subjects_detail: 具体选科（用于稀缺度计算）
    - score_tolerance: 分数容差（默认 ±30）

    响应新增:
    - last_updated: 数据最后更新时间
    - new_since_yesterday: 自昨天以来新增的捡漏机会数
    - top_pick: 评分最高的机会
    - 每条机会含 leakage_score, estimated_score, score_breakdown 等
    """
    from main import global_data
    from database import get_redis

    # 确定分数区间
    min_score = payload.min_score
    max_score = payload.max_score
    # 如果只传了 user_score 但没传 min/max → 不设区间（让 score_tolerance 在算法内处理）
    # 只有用户显式设了 min_score 或 max_score 时才启用精确过滤
    if payload.user_score is not None and payload.min_score is None and payload.max_score is None:
        min_score = None
        max_score = None

    # ── 尝试 Layer 3 用户缓存（1h TTL，同一用户重复查询直接返回）──
    user_id = request.query_params.get("user_id", "")
    redis = await get_redis()
    if redis is not None and user_id:
        user_query_hash = hashlib.md5(str(payload.model_dump()).encode()).hexdigest()[:8]
        user_cache_key = f"user:radar:{user_id}:{user_query_hash}"
        try:
            user_cached = await redis.get(user_cache_key)
            if user_cached:
                data = json.loads(user_cached)
                data["last_updated"] = await _get_last_updated(redis)
                return LeakageRadarResponse(**data)
        except Exception:
            pass

    # ── 尝试 Layer 2 缓存 ──
    redis = await get_redis()
    if redis is not None:
        key = _cache_key_from_params(
            payload.province,
            payload.subject_group,
            payload.batch or "",
            ",".join(sorted(payload.school_types)) if payload.school_types else "",
            str(min_score) if min_score is not None else "",
            str(max_score) if max_score is not None else "",
            str(payload.user_score) if payload.user_score is not None else "",
        )
        cached = await redis.get(key)
        if cached:
            data = json.loads(cached)
            # 补充差异追踪数据
            new_since = 0
            if redis:
                new_since = await _track_daily_diff(
                    redis,
                    payload.province,
                    payload.subject_group,
                    set(_diff_key(o.get("university_name",""), o.get("major_name",""), o.get("group_code",""))
                        for o in data.get("opportunities", [])),
                )
            data["new_since_yesterday"] = new_since
            data["last_updated"] = await _get_last_updated(redis)
            return LeakageRadarResponse(**data)

    # ── 缓存未命中 → 计算 ──
    df_2026 = global_data.get("plans_2026.csv")
    df_2025 = global_data.get("plans_2025.csv")
    df_history = global_data.get("admission_history.csv")

    if df_2026 is None or df_2025 is None:
        raise HTTPException(
            status_code=500,
            detail="招生计划数据未加载，请检查 data/ 目录",
        )

    # 加载新校区配置
    new_campuses = _load_new_campuses()

    try:
        results = find_leakage_opportunities(
            df_current_year=df_2026.copy(),
            df_last_year=df_2025.copy(),
            df_history=df_history.copy() if df_history is not None else None,
            new_campuses=new_campuses,
            user_province=payload.province,
            user_subject=payload.subject_group,
            user_score=payload.user_score,
            user_subjects_detail=payload.user_subjects_detail,
            batch=payload.batch,
            school_types=payload.school_types,
            min_score=min_score,
            max_score=max_score,
            score_tolerance=payload.score_tolerance,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 获取最后更新时间
    last_updated = await _get_last_updated(redis)

    # ── Tavily 动态信息层：为 Top 3 结果补充联网信息 ──
    # 仅对评分最高的 3 条机会调用 Tavily，避免 API 配额浪费
    if results and os.getenv("TAVILY_API_KEY"):
        from services.live_search import search_leakage_context
        import asyncio as _asyncio

        top_n = min(3, len(results))
        live_tasks = []
        for item in results[:top_n]:
            live_tasks.append(search_leakage_context(
                university_name=item.get("university_name", ""),
                major_name=item.get("major_name", ""),
                province=payload.province,
            ))

        live_results = await _asyncio.gather(*live_tasks, return_exceptions=True)

        for i, live_res in enumerate(live_results):
            if isinstance(live_res, Exception) or not isinstance(live_res, dict):
                continue
            if live_res.get("error"):
                continue
            results[i]["live_latest_score"] = live_res.get("latest_score")
            results[i]["live_employment"] = live_res.get("employment")
            results[i]["live_news"] = live_res.get("news")
            results[i]["live_sources"] = live_res.get("sources")

    # 确定 top_pick（含动态信息）
    top_pick = None
    if results:
        top_pick = _safe_opportunity(results[0])

    # 差异追踪
    new_since_yesterday = 0
    if redis is not None and results:
        current_keys = set()
        for item in results:
            uk = _diff_key(item.get("university_name",""), item.get("major_name",""), item.get("group_code",""))
            current_keys.add(uk)
        new_since_yesterday = await _track_daily_diff(
            redis,
            payload.province,
            payload.subject_group,
            current_keys,
        )

    response = LeakageRadarResponse(
        province=payload.province,
        subject_group=payload.subject_group,
        total=len(results),
        opportunities=[_safe_opportunity(item) for item in results],
        last_updated=last_updated,
        new_since_yesterday=new_since_yesterday,
        top_pick=top_pick,
    )

    # 为 top 5 结果附带实时热度信息
    if results:
        try:
            heat_items = [
                {"university": r.get("university_name", ""), "major": r.get("major_name", ""), "province": payload.province}
                for r in results[:5]
            ]
            heat_keys = [_build_key(i["university"], i["major"], i["province"]) for i in heat_items]
            heat_map = await batch_get_heat(heat_keys)
            for i, r in enumerate(results[:5]):
                uk = heat_keys[i]
                heat = heat_map.get(uk, {})
                r["heat_view_count"] = heat.get("view_count", 0)
                r["heat_watcher_count"] = heat.get("watcher_count", 0)
                r["heat_today_view"] = heat.get("today_view", 0)
                r["heat_level"] = get_heat_level(heat.get("view_count", 0), heat.get("watcher_count", 0))
                r["heat_label"] = get_heat_label(r["heat_level"])
            # 重建 response 以包含热度字段
            top_pick = _safe_opportunity(results[0]) if results else None
            response = LeakageRadarResponse(
                province=payload.province,
                subject_group=payload.subject_group,
                total=len(results),
                opportunities=[_safe_opportunity(item) for item in results],
                last_updated=last_updated,
                new_since_yesterday=new_since_yesterday,
                top_pick=top_pick,
            )
        except Exception:
            pass

    # 回写 Layer 2 缓存
    if redis is not None and results:
        try:
            key = _cache_key_from_params(
                payload.province,
                payload.subject_group,
                payload.batch or "",
                ",".join(sorted(payload.school_types)) if payload.school_types else "",
                str(min_score) if min_score is not None else "",
                str(max_score) if max_score is not None else "",
                str(payload.user_score) if payload.user_score is not None else "",
            )
            await redis.setex(
                key,
                CACHE_TTL_RADAR,
                response.model_dump_json(),
            )
            # 更新最后更新时间
            await redis.set(
                "leakage:last_updated",
                datetime.now().isoformat(),
            )
        except Exception:
            pass

    # 回写 Layer 3 用户缓存
    if redis is not None and results and user_id:
        try:
            user_query_hash = hashlib.md5(str(payload.model_dump()).encode()).hexdigest()[:8]
            user_cache_key = f"user:radar:{user_id}:{user_query_hash}"
            await redis.setex(user_cache_key, CACHE_TTL_USER, response.model_dump_json())
        except Exception:
            pass

    return response


@router.post("/refresh-cache", tags=["leakage-radar"])
async def refresh_cache(request: Request):
    """
    手动刷新 Layer 2 缓存（按省份+科类全部失效）。
    通常在 daily_update.py 执行后调用。
    """
    from database import get_redis

    redis = await get_redis()
    if redis is None:
        return {"status": "error", "detail": "Redis 不可用"}

    # 扫描并删除所有 radar:* 开头的 key
    deleted = 0
    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor, match="radar:*", count=100)
        if keys:
            await redis.delete(*keys)
            deleted += len(keys)
        if cursor == 0:
            break

    # 更新时间戳
    await redis.set("leakage:last_updated", datetime.now().isoformat())

    return {
        "status": "ok",
        "deleted_keys": deleted,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/cache-stats", tags=["leakage-radar"])
async def cache_stats(request: Request):
    """查看缓存统计信息。"""
    from database import get_redis

    redis = await get_redis()
    if redis is None:
        return {"status": "error", "detail": "Redis 不可用"}

    stats = {}
    for prefix in ["radar:", "leakage:diff_track:", "leakage:last_updated"]:
        count = 0
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor, match=f"{prefix}*", count=100)
            count += len(keys)
            if cursor == 0:
                break
        stats[prefix.rstrip(":")] = count

    last_updated = await redis.get("leakage:last_updated")
    stats["last_updated"] = last_updated

    return stats


@router.get("/notifications/{user_id}", tags=["leakage-radar"])
async def get_user_notifications(user_id: str):
    """获取用户的站内通知列表（含未读计数）。"""
    from services.notification import get_notifications, get_unread_count

    return {
        "user_id": user_id,
        "unread_count": get_unread_count(user_id),
        "notifications": get_notifications(user_id),
    }


@router.post("/notifications/{user_id}/read", tags=["leakage-radar"])
async def mark_notifications_read(user_id: str):
    """标记全部通知已读。"""
    from services.notification import mark_all_read

    count = mark_all_read(user_id)
    return {"status": "ok", "marked_read": count}


# ═══════════════════════════════════════════════════════════════
# 定制化捡漏雷达（付费功能） — 结合志愿草表生成针对性建议
# ═══════════════════════════════════════════════════════════════

import uuid as _uuid
import time as _time

# 内存缓存：{request_id: (results, expire_ts)}，生产环境替换为 Redis
_customize_cache: dict[str, tuple[list, float]] = {}
_CUSTOMIZE_CACHE_TTL = 3600  # 1小时


@router.post("/customize", response_model=CustomLeakageResponse)
async def customize_leakage_radar(payload: CustomLeakageRequest):
    """
    定制化捡漏雷达：结合考生档案 + 志愿草表生成针对性捡漏建议。

    流程：
    1. 提取考生档案（分数/省份/科类/单科/体检）
    2. 对志愿草表里每所大学，在捡漏雷达结果中匹配同校/同专业机会
    3. 用招生章程知识库过滤体检/单科不符的机会
    4. 免费预览前3条，完整报告需付费解锁（9.9元）
    """
    from main import global_data
    from services.enrollment_kb import get_knowledge_base

    df_2026 = global_data.get("plans_2026.csv")
    df_2025 = global_data.get("plans_2025.csv")
    df_history = global_data.get("admission_history.csv")
    if df_2026 is None or df_2025 is None:
        raise HTTPException(status_code=500, detail="招生计划数据未加载")

    profile = payload.profile
    user_score = profile.score
    province = profile.province
    subject_group = payload.subject_group
    targets = [{"university": t.university, "major": t.major} for t in payload.targets]

    # 1. 调用核心捡漏雷达获取全省所有机会
    new_campuses = _load_new_campuses()
    try:
        all_results = find_leakage_opportunities(
            df_current_year=df_2026.copy(),
            df_last_year=df_2025.copy(),
            df_history=df_history.copy() if df_history is not None else None,
            new_campuses=new_campuses,
            user_province=province,
            user_subject=subject_group,
            user_score=user_score,
            user_subjects_detail=profile.subjects,
            score_tolerance=payload.score_tolerance,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not all_results:
        return CustomLeakageResponse(
            total=0,
            preview=[],
            locked=False,
            locked_count=0,
            prompt_text="当前分数范围内暂未发现捡漏机会，建议调整志愿草表后重试。",
            target_summary=[],
        )

    # 2. 与志愿草表匹配：同校/同专业/同分段
    target_unis = {t["university"].strip() for t in targets}
    target_majors = {t["major"].strip() for t in targets}
    score_low = user_score - payload.score_tolerance
    score_high = user_score + 15

    matched = []
    for r in all_results:
        uni = str(r.get("university_name", "")).strip()
        major = str(r.get("major_name", "")).strip()
        ls = r.get("lowest_score_2025")

        # 相关度分级
        relevance = 0
        if uni in target_unis:
            relevance = 100  # 同校
            if major in target_majors:
                relevance = 200  # 同校同专业
        elif ls is not None and not _is_nan(ls) and score_low <= float(ls) <= score_high:
            relevance = 50  # 同分段可替代

        if relevance > 0:
            r["_relevance"] = relevance
            matched.append(r)

    # 3. 用招生章程过滤体检/单科不符的机会
    kb = get_knowledge_base()
    filtered = []
    for r in matched:
        uni = str(r.get("university_name", "")).strip()
        major = str(r.get("major_name", "")).strip()
        rule = kb.query(uni, major)

        # 体检限制过滤
        if rule.get("body_check") and profile.vision_status != "正常":
            bc = rule["body_check"]
            if isinstance(bc, dict):
                cb = bc.get("color_blind")
                cw = bc.get("color_weak")
                if (cb == "不录取" or cw == "不录取"):
                    continue  # 体检不符，排除

        # 单科成绩过滤
        ss = rule.get("single_subject")
        if ss and isinstance(ss, dict):
            eng = ss.get("english")
            if isinstance(eng, dict) and profile.english_score is not None:
                if profile.english_score < eng.get("min", 0):
                    continue  # 英语不达标
            math = ss.get("math")
            if isinstance(math, dict) and profile.math_score is not None:
                if profile.math_score < math.get("min", 0):
                    continue  # 数学不达标

        filtered.append(r)

    # 4. 按相关度+捡漏评分排序
    filtered.sort(key=lambda x: (x.get("_relevance", 0), x.get("leakage_score", 0)), reverse=True)

    # 5. 构建各志愿目标统计
    target_summary = []
    for t in targets:
        uni = t["university"].strip()
        major = t["major"].strip()
        uni_results = [r for r in filtered if str(r.get("university_name", "")).strip() == uni]
        opp_count = len(uni_results)
        best = max(uni_results, key=lambda x: x.get("leakage_score", 0)) if uni_results else None
        target_summary.append({
            "university": uni,
            "major": major,
            "opportunity_count": opp_count,
            "best_score": best.get("leakage_score") if best else None,
            "best_type": best.get("opportunity_type") if best else None,
        })

    # 6. 免费预览前3条 + 锁定剩余
    preview_count = min(3, len(filtered))
    preview = [_safe_opportunity(r) for r in filtered[:preview_count]]
    locked_count = max(0, len(filtered) - preview_count)

    # 7. 生成 request_id 并缓存完整结果
    request_id = str(_uuid.uuid4())
    _customize_cache[request_id] = (filtered, _time.time() + _CUSTOMIZE_CACHE_TTL)
    # 清理过期缓存
    _cleanup_customize_cache()

    # 8. 引导付费文案
    if locked_count > 0:
        prompt_text = (
            f"基于您的志愿草表（{len(targets)}个目标），"
            f"捡漏雷达共发现 {len(filtered)} 个定制化捡漏机会。"
            f"已为您预览前 {preview_count} 条，还有 {locked_count} 条高价值机会待解锁。"
            f"\n\n💡 解锁完整报告（仅需 ¥9.9），获取：\n"
            f"  • 全部 {len(filtered)} 个捡漏机会的详细分析\n"
            f"  • 每个机会的六维评分明细和报考建议\n"
            f"  • 针对您体检/单科成绩的个性化风险提示\n"
            f"  • 同档次可替代院校推荐"
        )
    else:
        prompt_text = f"基于您的志愿草表，共发现 {len(filtered)} 个捡漏机会，已全部展示。"
        locked_count = 0

    return CustomLeakageResponse(
        total=len(filtered),
        preview=preview,
        locked=locked_count > 0,
        locked_count=locked_count,
        request_id=request_id if locked_count > 0 else None,
        prompt_text=prompt_text,
        target_summary=target_summary,
    )


@router.post("/customize/unlock", response_model=CustomLeakageUnlockResponse)
async def unlock_custom_leakage(payload: CustomLeakageUnlockRequest):
    """
    付费解锁定制化捡漏报告完整版。

    比赛演示：直接返回完整结果（跳过真实支付）。
    生产环境：此处接入微信/支付宝支付回调验证。
    """
    request_id = payload.request_id
    if request_id not in _customize_cache:
        raise HTTPException(status_code=404, detail="报告已过期或不存在，请重新生成")

    results, expire_ts = _customize_cache[request_id]
    if _time.time() > expire_ts:
        del _customize_cache[request_id]
        raise HTTPException(status_code=410, detail="报告已过期，请重新生成")

    # 解锁后返回完整结果
    full_opportunities = [_safe_opportunity(r) for r in results]
    return CustomLeakageUnlockResponse(
        unlocked=True,
        total=len(full_opportunities),
        opportunities=full_opportunities,
    )


def _is_nan(val) -> bool:
    """安全检查 nan"""
    try:
        return val != val
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
# 实时热度追踪 — 记录用户对捡漏机会的查看/收藏/解锁行为
# ═══════════════════════════════════════════════════════════════

from services.heat_tracker import (
    track_event, get_heat, batch_get_heat,
    get_heat_level, get_heat_label, _build_key,
)
from pydantic import BaseModel as _BM


class HeatTrackRequest(_BM):
    """热度追踪请求"""
    university: str
    major: str
    province: str = ""
    event_type: str = "view"  # view | fav | unlock | unfav
    user_id: str = "anonymous"


class HeatBatchRequest(_BM):
    """批量热度查询请求"""
    items: list[dict]  # [{university, major, province}, ...]


@router.post("/heat/track", tags=["leakage-radar"])
async def track_heat(payload: HeatTrackRequest):
    """
    记录用户对某个捡漏机会的行为（查看/收藏/解锁）。

    前端在用户查看机会详情、收藏、解锁时调用此接口。
    """
    unique_key = _build_key(payload.university, payload.major, payload.province)
    result = await track_event(unique_key, payload.event_type, payload.user_id)

    # 同时持久化到 SQLite（行为日志，用于后续分析）
    try:
        from database import SessionLocal
        from models import UserBehavior
        with SessionLocal() as db:
            db.add(UserBehavior(
                user_id=payload.user_id,
                unique_key=unique_key,
                event_type=payload.event_type,
                university_name=payload.university,
                major_name=payload.major,
            ))
            db.commit()
    except Exception:
        pass  # 持久化失败不影响主流程

    level = get_heat_level(result["view_count"], result["watcher_count"])
    return {
        **result,
        "level": level,
        "label": get_heat_label(level),
    }


@router.get("/heat/{unique_key}", tags=["leakage-radar"])
async def get_opportunity_heat(unique_key: str):
    """查询单个机会的热度。"""
    result = await get_heat(unique_key)
    level = get_heat_level(result["view_count"], result["watcher_count"])
    return {**result, "level": level, "label": get_heat_label(level)}


@router.post("/heat/batch", tags=["leakage-radar"])
async def batch_get_opportunity_heat(payload: HeatBatchRequest):
    """
    批量查询多个机会的热度。

    前端在加载捡漏雷达结果列表时，一次性查询所有机会的热度。
    """
    unique_keys = []
    key_to_info = {}
    for item in payload.items:
        uk = _build_key(
            item.get("university", ""),
            item.get("major", ""),
            item.get("province", ""),
        )
        unique_keys.append(uk)
        key_to_info[uk] = item

    heat_map = await batch_get_heat(unique_keys)

    # 附加等级标签
    result = {}
    for uk, heat in heat_map.items():
        level = get_heat_level(heat["view_count"], heat["watcher_count"])
        result[uk] = {**heat, "level": level, "label": get_heat_label(level)}

    return {"heat_map": result}


@router.get("/heat/stats/overview", tags=["leakage-radar"])
async def heat_stats_overview():
    """热度统计概览（用于仪表盘）。"""
    from database import SessionLocal, is_redis_available
    from models import UserBehavior
    from sqlalchemy import func as sql_func

    # 从 SQLite 统计行为
    try:
        with SessionLocal() as db:
            total_views = db.query(sql_func.count(UserBehavior.id)).filter(
                UserBehavior.event_type == "view"
            ).scalar() or 0
            total_favs = db.query(sql_func.count(UserBehavior.id)).filter(
                UserBehavior.event_type == "fav"
            ).scalar() or 0
            total_unlocks = db.query(sql_func.count(UserBehavior.id)).filter(
                UserBehavior.event_type == "unlock"
            ).scalar() or 0
            unique_users = db.query(sql_func.count(sql_func.distinct(UserBehavior.user_id))).scalar() or 0
    except Exception:
        total_views = total_favs = total_unlocks = unique_users = 0

    return {
        "total_views": int(total_views),
        "total_favs": int(total_favs),
        "total_unlocks": int(total_unlocks),
        "unique_users": int(unique_users),
        "redis_available": is_redis_available(),
    }


def _cleanup_customize_cache():
    """清理过期缓存"""
    now = _time.time()
    expired = [k for k, (_, ts) in _customize_cache.items() if now > ts]
    for k in expired:
        del _customize_cache[k]
