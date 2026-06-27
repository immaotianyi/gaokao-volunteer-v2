"""
实时热度追踪服务 — 记录用户对捡漏机会的查看/收藏/解锁行为

数据结构（Redis）:
  heat:view:{unique_key}     — 累计查看次数
  heat:fav:{unique_key}      — 收藏次数
  heat:unlock:{unique_key}   — 解锁次数
  heat:daily:{date}:{unique_key} — 每日查看次数（用于"今日N人查看"）
  heat:users:{unique_key}    — 查看过的用户集合（去重，用于"N人在盯"）

Redis 不可用时 fallback 到内存计数器（开发环境）。
"""
import hashlib
from datetime import datetime, date
from typing import Optional

from database import get_redis, is_redis_available


# ── 内存 fallback（Redis 不可用时） ──────────────────────────
_mem_heat: dict[str, dict] = {}  # {unique_key: {view, fav, unlock, daily:{date:count}, users:set}}


def _build_key(university: str, major: str, province: str = "") -> str:
    """构建热度追踪的唯一 key。"""
    raw = f"{university}|{major}|{province}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


async def track_event(
    unique_key: str,
    event_type: str,
    user_id: str = "anonymous",
) -> dict:
    """
    记录一次用户行为。

    event_type: "view" | "fav" | "unlock" | "unfav"
    """
    redis = await get_redis()

    if redis is not None:
        # ── Redis 模式 ──
        pipe = redis.pipeline()
        view_key = f"heat:view:{unique_key}"
        fav_key = f"heat:fav:{unique_key}"
        unlock_key = f"heat:unlock:{unique_key}"
        daily_key = f"heat:daily:{date.today().isoformat()}:{unique_key}"
        users_key = f"heat:users:{unique_key}"

        if event_type == "view":
            pipe.incr(view_key)
            pipe.incr(daily_key)
            pipe.expire(daily_key, 86400 * 7)  # 保留7天
            pipe.sadd(users_key, user_id)
            pipe.expire(users_key, 86400 * 30)
        elif event_type == "fav":
            pipe.incr(fav_key)
        elif event_type == "unfav":
            # 用 Lua 脚本保证收藏数不为负（与内存路径 max(0,...) 行为一致）
            UNFAV_LUA = """
            local cur = tonumber(redis.call('GET', KEYS[1]) or '0')
            if cur > 0 then
                return redis.call('DECR', KEYS[1])
            else
                return 0
            end
            """
            pipe.eval(UNFAV_LUA, 1, fav_key)
        elif event_type == "unlock":
            pipe.incr(unlock_key)

        pipe.expire(view_key, 86400 * 30)
        pipe.expire(fav_key, 86400 * 30)
        pipe.expire(unlock_key, 86400 * 30)

        await pipe.execute()

        # 返回最新热度
        return await get_heat(unique_key)

    # ── 内存 fallback ──
    if unique_key not in _mem_heat:
        _mem_heat[unique_key] = {
            "view": 0, "fav": 0, "unlock": 0,
            "daily": {}, "users": set(),
        }
    h = _mem_heat[unique_key]

    today = date.today().isoformat()
    if event_type == "view":
        h["view"] += 1
        h["daily"][today] = h["daily"].get(today, 0) + 1
        h["users"].add(user_id)
    elif event_type == "fav":
        h["fav"] += 1
    elif event_type == "unfav":
        h["fav"] = max(0, h["fav"] - 1)
    elif event_type == "unlock":
        h["unlock"] += 1

    return _format_heat(unique_key, h)


async def get_heat(unique_key: str) -> dict:
    """查询某个机会的热度。"""
    redis = await get_redis()

    if redis is not None:
        view_key = f"heat:view:{unique_key}"
        fav_key = f"heat:fav:{unique_key}"
        unlock_key = f"heat:unlock:{unique_key}"
        daily_key = f"heat:daily:{date.today().isoformat()}:{unique_key}"
        users_key = f"heat:users:{unique_key}"

        pipe = redis.pipeline()
        pipe.get(view_key)
        pipe.get(fav_key)
        pipe.get(unlock_key)
        pipe.get(daily_key)
        pipe.scard(users_key)
        results = await pipe.execute()

        return {
            "unique_key": unique_key,
            "view_count": int(results[0] or 0),
            "fav_count": int(results[1] or 0),
            "unlock_count": int(results[2] or 0),
            "today_view": int(results[3] or 0),
            "watcher_count": int(results[4] or 0),
        }

    # 内存 fallback
    h = _mem_heat.get(unique_key, {
        "view": 0, "fav": 0, "unlock": 0,
        "daily": {}, "users": set(),
    })
    return _format_heat(unique_key, h)


def _format_heat(unique_key: str, h: dict) -> dict:
    today = date.today().isoformat()
    return {
        "unique_key": unique_key,
        "view_count": h["view"],
        "fav_count": h["fav"],
        "unlock_count": h["unlock"],
        "today_view": h["daily"].get(today, 0),
        "watcher_count": len(h["users"]),
    }


async def batch_get_heat(unique_keys: list[str]) -> dict[str, dict]:
    """批量查询多个机会的热度。"""
    redis = await get_redis()

    if redis is not None:
        pipe = redis.pipeline()
        for uk in unique_keys:
            pipe.get(f"heat:view:{uk}")
            pipe.get(f"heat:fav:{uk}")
            pipe.get(f"heat:unlock:{uk}")
            pipe.get(f"heat:daily:{date.today().isoformat()}:{uk}")
            pipe.scard(f"heat:users:{uk}")
        results = await pipe.execute()

        output = {}
        for i, uk in enumerate(unique_keys):
            base = i * 5
            output[uk] = {
                "unique_key": uk,
                "view_count": int(results[base] or 0),
                "fav_count": int(results[base + 1] or 0),
                "unlock_count": int(results[base + 2] or 0),
                "today_view": int(results[base + 3] or 0),
                "watcher_count": int(results[base + 4] or 0),
            }
        return output

    # 内存 fallback
    return {uk: _format_heat(uk, _mem_heat.get(uk, {
        "view": 0, "fav": 0, "unlock": 0, "daily": {}, "users": set()
    })) for uk in unique_keys}


def get_heat_level(view_count: int, watcher_count: int) -> str:
    """
    根据热度返回等级标签（用于前端展示）。
    - 冷门：< 10 查看
    - 普通：10-50 查看
    - 热门：50-200 查看
    - 爆款：> 200 查看
    """
    score = view_count + watcher_count * 3
    if score < 10:
        return "cold"
    elif score < 50:
        return "normal"
    elif score < 200:
        return "hot"
    else:
        return "viral"


def get_heat_label(level: str) -> str:
    """热度等级对应的中文标签。"""
    labels = {
        "cold": "少人关注",
        "normal": "正常关注",
        "hot": "热门机会",
        "viral": "爆款机会",
    }
    return labels.get(level, "正常关注")
