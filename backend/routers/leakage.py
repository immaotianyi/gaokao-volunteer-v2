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
from schemas import LeakageRadarRequest, LeakageRadarResponse, LeakageOpportunity

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
                    set(o.get("unique_key", o.get("university_name","") + o.get("major_name",""))
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
            uk = item.get("university_code", "") + "_" + item.get("group_code", "") + "_" + item.get("major_name", "")
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
