"""
联网搜索服务 V2 — 基于 Tavily API

策略:
1. 用 Tavily AI 搜索某大学招生章程页面（替换原 DuckDuckGo/Bing）
2. 抓取章程内容通过 DeepSeek LLM 即时提取规则
3. 结果标注 source='live'，与本地预加载(source='local')区分
4. Redis 缓存 24h，避免同一大学重复搜索

用法:
  from services.live_search import search_university_rules
  result = await search_university_rules("某某大学")

环境变量:
  TAVILY_API_KEY  — Tavily API Key (https://tavily.com, 免费 1000 次/月)
  DEEPSEEK_API_KEY — DeepSeek API Key (章程规则提取)
"""
import os
import re
import json
import time
import requests
from typing import Optional
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# ── API 配置 ──────────────────────────────────────────────────
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
TAVILY_API_URL = "https://api.tavily.com/search"

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


# ── Tavily 搜索 ───────────────────────────────────────────────

def tavily_search(query: str, max_results: int = 5) -> Optional[dict]:
    """
    调用 Tavily Search API。

    Returns:
        {
            "answer": str,           # Tavily AI 生成的摘要
            "urls": [str, ...],      # 搜索结果 URL 列表
            "results": [{...}, ...]  # 完整结果对象
        }
        失败返回 None
    """
    if not TAVILY_API_KEY:
        print("[live_search] ⚠ TAVILY_API_KEY 未配置，Tavily 搜索不可用")
        return None

    try:
        resp = requests.post(
            TAVILY_API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TAVILY_API_KEY}",
            },
            json={
                "query": query,
                "search_depth": "basic",
                "include_answer": True,
                "max_results": max_results,
                "topic": "general",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"[live_search] Tavily 返回 {resp.status_code}: {resp.text[:200]}")
            return None

        data = resp.json()
        answer = data.get("answer", "")
        results = data.get("results", [])
        urls = [r.get("url", "") for r in results if r.get("url")]

        return {
            "answer": answer,
            "urls": urls,
            "results": results,
        }
    except requests.Timeout:
        print("[live_search] Tavily 搜索超时 (15s)")
        return None
    except Exception as e:
        print(f"[live_search] Tavily 搜索异常: {e}")
        return None


def find_zhangcheng_url(university_name: str) -> Optional[str]:
    """
    用 Tavily 搜索某大学 2026 招生章程页面 URL。
    优先返回 .edu.cn 域名的结果。
    """
    query = f"{university_name} 2026年 招生章程"
    result = tavily_search(query, max_results=5)
    if not result:
        return None

    urls = result["urls"]

    # 优先 edu.cn 域名
    for u in urls:
        if ".edu.cn" in u:
            return u
    # 其次含招生相关关键词
    for u in urls:
        if any(k in u.lower() for k in ["zhaosheng", "zsb", "bkzs", "admission", "zhangcheng"]):
            return u
    # 兜底取第一个
    if urls:
        return urls[0]

    return None


# ── 网页抓取 ───────────────────────────────────────────────────

def fetch_page_text(url: str) -> Optional[str]:
    """抓取网页文本内容（保留原实现，Tavily 的 content 字段做兜底）。"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return None

        resp.encoding = resp.apparent_encoding or "utf-8"

        text = resp.text
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        text = re.sub(r'\s+', ' ', text)

        if len(text) < 200:
            return None

        # 找正文
        for marker in ["招生章程", "第一章", "第一条", "总则"]:
            idx = text.find(marker)
            if idx != -1:
                text = text[idx:]
                break

        return text[:10000]
    except Exception:
        return None


def fetch_zhangcheng_text(university_name: str, url: str = None) -> Optional[str]:
    """
    获取章程文本：优先直接抓网页，失败则用 Tavily 搜索结果的 content。
    """
    # 如果有 URL，直接抓
    if url:
        text = fetch_page_text(url)
        if text and len(text) >= 200:
            return text

    # 兜底：用 Tavily 搜索，取 content 字段
    query = f"{university_name} 招生章程 录取规则 体检"
    result = tavily_search(query, max_results=3)
    if not result:
        return None

    # 拼接所有结果的 content
    combined = ""
    for r in result["results"]:
        content = r.get("content", "")
        if content:
            combined += content + "\n\n"

    if len(combined) < 200:
        return None

    return combined[:10000]


# ── LLM 规则提取 ──────────────────────────────────────────────

def extract_rules_via_llm(chapter_text: str, university_name: str) -> Optional[dict]:
    """通过 DeepSeek LLM 即时提取规则（保留原实现）。"""
    if not DEEPSEEK_API_KEY:
        return None

    prompt = f"""你是一位高考招生政策分析专家。请从以下招生章程中快速提取关键录取限制条件。

章程全文（{university_name}）：
{chapter_text[:8000]}

请用JSON格式输出，包含以下字段：
{{
  "university": "{university_name}",
  "majors": [
    {{
      "major_pattern": ".*",
      "major_name": "全部专业",
      "body_check": {{"color_blind": null, "color_weak": null, "vision": null, "height": null, "clause": ""}},
      "single_subject": {{}},
      "language_restriction": null,
      "subject_election": null,
      "notes": ""
    }}
  ],
  "summary": "一句话总结主要限制"
}}

只提取明确写出的限制，没有的填null。"""

    try:
        resp = requests.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "你是一个高考招生政策分析专家。请严格按照JSON格式输出。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 2048,
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            content = re.sub(r'^```json\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
            return json.loads(content)
    except Exception:
        pass

    return None


# ── Redis 缓存 ────────────────────────────────────────────────

async def _get_cached(key: str) -> Optional[dict]:
    """从 Redis 读取缓存。"""
    try:
        from database import get_redis
        redis = await get_redis()
        if redis is None:
            return None
        cached = await redis.get(key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass
    return None


async def _set_cached(key: str, value: dict, ttl: int = 86400):
    """写入 Redis 缓存（默认 24h TTL）。"""
    try:
        from database import get_redis
        redis = await get_redis()
        if redis is None:
            return
        await redis.setex(key, ttl, json.dumps(value, ensure_ascii=False))
    except Exception:
        pass


# ── 主接口 ────────────────────────────────────────────────────

async def search_university_rules(university_name: str) -> dict:
    """
    联网搜索某大学的招生章程并提取规则（V2: Tavily + Redis 缓存）。

    Returns:
        {
            "university": str,
            "source": "live",
            "url": str,
            "rules": dict,
            "warning": str,
            "error": str | None,
            "cached": bool,          # 是否命中缓存
        }
    """
    cache_key = f"live_search:rules:{university_name}"

    # 1. 查缓存
    cached = await _get_cached(cache_key)
    if cached:
        cached["cached"] = True
        return cached

    result = {
        "university": university_name,
        "source": "live",
        "url": None,
        "rules": None,
        "warning": "此数据通过联网实时检索获取，非本地数据库预加载，请仔细甄别。",
        "error": None,
        "cached": False,
    }

    # 2. Tavily 搜索章程 URL
    url = find_zhangcheng_url(university_name)
    if url:
        result["url"] = url

    # 3. 获取章程文本
    text = fetch_zhangcheng_text(university_name, url)
    if not text:
        result["error"] = f"未找到 {university_name} 的招生章程内容"
        return result

    # 4. LLM 提取规则
    rules = extract_rules_via_llm(text, university_name)
    if not rules:
        if not DEEPSEEK_API_KEY:
            result["rules"] = {
                "university": university_name,
                "majors": [{
                    "major_pattern": ".*",
                    "major_name": "全部专业",
                    "notes": f"章程原文已获取 ({len(text)}字符)，但 DEEPSEEK_API_KEY 未配置，规则提取跳过。来源: {url or 'Tavily'}"
                }],
                "summary": "联网获取的章程原文，规则提取待配置 API Key",
            }
        else:
            result["rules"] = {
                "university": university_name,
                "majors": [{
                    "major_pattern": ".*",
                    "major_name": "全部专业",
                    "notes": f"章程原文已获取 ({len(text)}字符)，但自动规则提取未完成。请手动查看: {url}"
                }],
                "summary": "联网获取的章程原文，规则提取待完成",
            }
        return result

    result["rules"] = rules

    # 5. 写缓存（24h）
    await _set_cached(cache_key, result)

    return result


# ── 捡漏雷达动态信息层 ────────────────────────────────────────

async def search_leakage_context(
    university_name: str,
    major_name: str,
    province: str,
) -> dict:
    """
    为捡漏雷达搜索某校某专业的最新动态信息。

    搜索内容:
    - 2026 最新录取分数线/位次
    - 该专业就业前景/薪资
    - 该校扩招/缩招新闻

    Returns:
        {
            "university": str,
            "major": str,
            "latest_score": str | None,   # 最新分数线信息
            "employment": str | None,     # 就业前景信息
            "news": str | None,           # 相关新闻
            "sources": [str, ...],        # 来源 URL
            "error": str | None,
        }
    """
    cache_key = f"live_search:leakage:{university_name}:{major_name}:{province}"

    # 查缓存（1h TTL，动态信息更新更快）
    cached = await _get_cached(cache_key)
    if cached:
        return cached

    result = {
        "university": university_name,
        "major": major_name,
        "latest_score": None,
        "employment": None,
        "news": None,
        "sources": [],
        "error": None,
    }

    if not TAVILY_API_KEY:
        result["error"] = "TAVILY_API_KEY 未配置"
        return result

    # 并行 3 路搜索
    queries = {
        "latest_score": f"{university_name} {major_name} {province} 2025 2026 录取分数线 位次",
        "employment": f"{university_name} {major_name} 就业前景 薪资 2025",
        "news": f"{university_name} 2026 扩招 新增专业 招生计划",
    }

    for key, query in queries.items():
        tavily_result = tavily_search(query, max_results=3)
        if tavily_result:
            # 优先用 Tavily 的 AI answer，没有则拼接 content
            answer = tavily_result.get("answer", "")
            if answer:
                result[key] = answer[:500]
            else:
                contents = [r.get("content", "")[:200] for r in tavily_result.get("results", []) if r.get("content")]
                if contents:
                    result[key] = " | ".join(contents)[:500]
            # 收集来源 URL
            for u in tavily_result.get("urls", []):
                if u and u not in result["sources"]:
                    result["sources"].append(u)

    # 写缓存（1h）
    await _set_cached(cache_key, result, ttl=3600)

    return result
