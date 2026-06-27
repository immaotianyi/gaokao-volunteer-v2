"""
AI 志愿顾问服务 (方案 C)

基于雪峰知识库 16 模块 + career_knowledge 结构化数据 + Tavily 动态搜索，
提供多轮对话式志愿咨询。

设计原则:
  - 专业中立调性（不套用雪峰毒舌东北味人设）
  - 复用 career_knowledge.py 结构化知识库
  - 复用 live_search.py Tavily 动态搜索
  - 复用 leakage_radar.py 录取数据查询
  - 支持多轮上下文记忆
  - 数据可信度 T1-T4 标注
  - 无 API Key 时降级为纯知识库模式

API:
  POST /api/advisor          — 同步聊天
  GET  /api/advisor/stream   — SSE 流式聊天
"""
from __future__ import annotations

import os
import json
import asyncio
from typing import Optional, AsyncGenerator

import httpx

from .career_knowledge import (
    get_major_recommendation,
    get_ai_impact_risk,
    get_university_alliance,
    get_employer_recognition,
    get_stable_career_for_major,
    is_high_salary_major,
    is_civil_service_friendly,
    RECOMMENDED_MAJORS,
    NOT_RECOMMENDED_MAJORS,
    UNIVERSITY_ALLIANCES,
    INDUSTRY_SCHOOLS,
    STABLE_CAREER_PATHS,
    AI_IMPACT_RISK,
    HIGH_SALARY_MAJORS,
    CIVIL_SERVICE_MAJORS,
    MAJOR_RESTRUCTURING_2024,
)


# ════════════════════════════════════════════════════════════════
# API 配置
# ════════════════════════════════════════════════════════════════

_DEEPSEEK_API_KEY = os.getenv("LLM_API_KEY", "") or os.getenv("DEEPSEEK_API_KEY", "")
_LLM_API_URL = os.getenv("LLM_API_URL", "") or os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
_LLM_MODEL = os.getenv("LLM_MODEL", "") or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


# ════════════════════════════════════════════════════════════════
# System Prompt 构建
# ════════════════════════════════════════════════════════════════

def build_advisor_system_prompt(user_profile: dict | None = None) -> str:
    """
    构建 AI 顾问的 system prompt。

    包含:
    - 顾问身份与调性（专业中立）
    - 知识库精华（从 career_knowledge 动态注入）
    - 咨询方法论（灵魂追问法 + 冲稳保规则）
    - 数据可信度原则
    - 输出格式要求
    """
    profile_section = ""
    if user_profile:
        profile_lines = []
        if user_profile.get("province"):
            profile_lines.append(f"- 省份: {user_profile['province']}")
        if user_profile.get("score"):
            profile_lines.append(f"- 总分: {user_profile['score']}")
        if user_profile.get("rank"):
            profile_lines.append(f"- 位次: {user_profile['rank']}")
        if user_profile.get("subjects"):
            profile_lines.append(f"- 选科: {user_profile['subjects']}")
        if user_profile.get("english_score"):
            profile_lines.append(f"- 英语: {user_profile['english_score']}")
        if user_profile.get("math_score"):
            profile_lines.append(f"- 数学: {user_profile['math_score']}")
        if user_profile.get("vision_status") and user_profile["vision_status"] != "正常":
            profile_lines.append(f"- 视力: {user_profile['vision_status']}")
        if profile_lines:
            profile_section = f"\n【考生档案】\n" + "\n".join(profile_lines) + "\n"

    # 知识库精华（精简版，避免 token 爆炸）
    kb_summary = _build_kb_summary()

    return f"""你是一位资深的高考志愿填报顾问，拥有 15 年咨询经验。

【身份与调性】
- 专业、中立、务实
- 用数据和事实说话，不夸大不恐吓
- 对普通家庭给出接地气的建议，不灌鸡汤
- 回答要有干货，避免空泛的"要看具体情况"

{profile_section}
【知识库精华】
{kb_summary}

【咨询方法论】
1. 灵魂追问法 — 信息不全时主动追问（省份/分数/位次/选科/家庭背景/就业诉求）
2. 就业倒推法 — 从"什么能找到好工作"倒推专业选择
3. 冲稳保梯度 — 位次法为核心，参考近 1-2 年录取位次
4. 家庭背景匹配 — 有行业资源优先继承，普通家庭优先技术类专业

【数据可信度原则】
- T1 官方数据（考试院/高校招生网）→ 给出具体数字
- T2 高校官方数据 → 可引用
- T3 经验规律/方法论 → 加"基于往年趋势"
- T4 推测/趋势 → 加"建议查询最新官方公告核实"
- 回答末尾标注本次回答的数据可信度级别

【输出要求】
- 直接回答问题，不要寒暄
- 涉及具体专业/院校时，引用知识库数据
- 如果不确定最新数据，明确说明并建议联网查询
- 回答控制在 300-500 字，重点突出
- 末尾给出 1-2 个可追问的方向（帮助用户深入咨询）

【禁忌】
- 不编造具体录取分数线/位次（知识库中没有的数字不要瞎编）
- 不对政治敏感话题发表意见
- 不推荐具体某所院校的某个专业组（除非用户明确询问）
"""


def _build_kb_summary() -> str:
    """构建知识库精华摘要（约 1.5KB）"""
    lines = []

    # 1. 推荐专业
    lines.append("■ 强推专业(普通家庭): " + " / ".join(
        m["category"] for m in RECOMMENDED_MAJORS
    ))

    # 2. 不推荐专业
    lines.append("■ 不推荐专业: " + " / ".join(
        m["category"] for m in NOT_RECOMMENDED_MAJORS
    ))

    # 3. AI 风险
    high_ai = [k for k, v in AI_IMPACT_RISK.items() if v["risk"] == "high"]
    med_ai = [k for k, v in AI_IMPACT_RISK.items() if v["risk"] == "medium"]
    lines.append(f"■ AI替代高风险: {', '.join(high_ai)}")
    lines.append(f"■ AI替代中风险(需走高端): {', '.join(med_ai)}")

    # 4. 稳定就业路径
    lines.append("■ 稳定就业路径: " + " / ".join(
        p["path"] for p in STABLE_CAREER_PATHS
    ))

    # 5. 名校联盟
    lines.append("■ 顶尖联盟: " + " / ".join(UNIVERSITY_ALLIANCES.keys()))

    # 6. 行业对口强校
    lines.append("■ 行业对口方向: " + " / ".join(INDUSTRY_SCHOOLS.keys()))

    # 7. 钱途专业
    lines.append("■ 钱途20大: " + " / ".join(HIGH_SALARY_MAJORS[:10]) + " 等")

    # 8. 考公专业
    lines.append("■ 考公友好: " + " / ".join(CIVIL_SERVICE_MAJORS))

    # 9. 2024 专业洗牌
    lines.append(f"■ 2024专业洗牌: 撤销{MAJOR_RESTRUCTURING_2024['撤销专业点']}个/停招{MAJOR_RESTRUCTURING_2024['停招专业点']}个/新增{MAJOR_RESTRUCTURING_2024['新增专业点']}个")
    lines.append(f"  过剩预警: {', '.join(MAJOR_RESTRUCTURING_2024['过剩预警专业'])}")

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════
# 知识库检索（轻量 RAG）
# ════════════════════════════════════════════════════════════════

def retrieve_relevant_knowledge(query: str) -> str:
    """
    根据用户问题检索相关知识（轻量 RAG）。

    检测 query 中的关键词，返回相关知识库条目。
    """
    snippets = []
    query_lower = query.lower()

    # 检测专业名
    all_majors = []
    for m in RECOMMENDED_MAJORS + NOT_RECOMMENDED_MAJORS:
        all_majors.extend(m["keywords"])
    for kw in all_majors:
        if kw.lower() in query_lower:
            rec = get_major_recommendation(kw)
            if rec:
                snippets.append(f"[{kw}] 推荐:{rec['level']} 风险:{rec['employment_risk']} — {rec['reason']}")
            ai = get_ai_impact_risk(kw)
            if ai:
                snippets.append(f"[{kw}] AI风险:{ai['risk']} — {ai['detail']}")
            stable = get_stable_career_for_major(kw)
            if stable:
                snippets.append(f"[{kw}] 稳定就业: {[p['path'] for p in stable]}")

    # 检测院校名
    for alliance, members in UNIVERSITY_ALLIANCES.items():
        for member in members:
            if member[:2] in query or member[:3] in query:  # 简称匹配
                snippets.append(f"[{member}] 联盟: {alliance}")
                star = get_employer_recognition(member)
                if star:
                    snippets.append(f"[{member}] 认可度: {star}")
                break

    # 检测主题关键词
    theme_map = {
        "考公": "考公友好专业: " + " / ".join(CIVIL_SERVICE_MAJORS),
        "公务员": "考公友好专业: " + " / ".join(CIVIL_SERVICE_MAJORS),
        "电网": "电网对口: 电气工程及其自动化 → 华北电力大学等",
        "医生": "医学路径: 临床医学(5年)+规培(3年)，三甲要求博士",
        "教师": "教师路径: 公费师范生包分配，普通师范需考编",
        "军校": "普通家庭可考虑军校/警校（包分配）",
        "考研": "考研建议: 看学校层次+学科评估，非名校慎选经管",
        "专科": "专科策略: 选双高计划院校，重行业壁垒专业",
        "AI": f"AI冲击: 高风险{[k for k,v in AI_IMPACT_RISK.items() if v['risk']=='high']}",
        "人工智能": f"AI专业建议: 非名校不要选AI/大数据（要点4）",
    }
    for keyword, info in theme_map.items():
        if keyword.lower() in query_lower:
            snippets.append(info)

    if snippets:
        return "\n".join(snippets[:10])  # 最多 10 条，控制 token
    return ""


# ════════════════════════════════════════════════════════════════
# Tavily 动态搜索（需要时触发）
# ════════════════════════════════════════════════════════════════

async def maybe_live_search(query: str) -> str:
    """
    判断是否需要联网搜索，需要则执行。

    触发条件:
    - 提到具体院校的分数线/招生计划
    - 提到"最新""2026""今年"
    - 提到具体专业的就业薪资
    """
    trigger_keywords = ["最新", "2026", "今年", "分数线", "投档线", "招生计划", "薪资", "就业率", "扩招"]
    need_search = any(kw in query for kw in trigger_keywords)

    if not need_search:
        return ""

    try:
        from .live_search import tavily_search
        result = await asyncio.to_thread(tavily_search, query + " 高考志愿 2026", 3)
        if result and result.get("answer"):
            urls = result.get("urls", [])
            sources_str = " | ".join(urls[:3]) if urls else ""
            return f"[联网搜索结果] {result['answer']}\n[来源] {sources_str}"
    except Exception as e:
        print(f"[advisor] Tavily 搜索失败: {e}")

    return ""


# ════════════════════════════════════════════════════════════════
# LLM 调用
# ════════════════════════════════════════════════════════════════

async def call_llm(
    system_prompt: str,
    messages: list[dict],
    stream: bool = False,
) -> str | AsyncGenerator[str, None]:
    """
    调用 LLM（DeepSeek / OpenAI 兼容格式）。

    stream=True 时返回 async generator，逐 token 产出。
    """
    api_key = _DEEPSEEK_API_KEY
    if not api_key:
        # 降级：纯知识库模式
        return _fallback_response(messages[-1].get("content", ""))

    full_messages = [{"role": "system", "content": system_prompt}] + messages

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _LLM_MODEL,
        "messages": full_messages,
        "temperature": 0.3,
        "max_tokens": 1024,
        "stream": stream,
    }

    if stream:
        return _stream_llm(_LLM_API_URL, headers, payload)
    else:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(_LLM_API_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]


async def _stream_llm(url: str, headers: dict, payload: dict) -> AsyncGenerator[str, None]:
    """流式调用 LLM"""
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue


def _fallback_response(query: str) -> str:
    """无 API Key 时的降级回复（纯知识库）"""
    knowledge = retrieve_relevant_knowledge(query)
    if knowledge:
        return f"""我理解你想了解：{query}

根据知识库，相关信息如下：
{knowledge}

[数据可信度: T3 - 基于知识库方法论]

💡 提示: 当前为知识库模式（未配置 LLM API Key），回答较为简略。配置后可获得更个性化的深度分析。

可追问方向：
- 该专业的具体就业薪资数据？
- 有哪些对口院校推荐？
- 冲稳保梯度怎么安排？"""
    else:
        return f"""我理解你想了解：{query}

当前为知识库模式（未配置 LLM API Key），无法进行深度分析。

建议你提供以下信息，我可以给出更精准的回答：
- 省份 + 分数 + 位次 + 选科
- 感兴趣的专业方向
- 就业诉求（考公/高薪/稳定/深造）

或尝试问我：推荐专业、不推荐专业、考公专业、AI风险专业等。"""


# ════════════════════════════════════════════════════════════════
# 主入口
# ════════════════════════════════════════════════════════════════

async def chat(
    message: str,
    history: list[dict] | None = None,
    user_profile: dict | None = None,
) -> dict:
    """
    同步聊天入口。

    Returns:
        {
            "reply": str,
            "sources": list[str] | None,
            "data_trust_level": str | None,
            "suggestions": list[str] | None,
        }
    """
    # 1. 构建 system prompt
    system_prompt = build_advisor_system_prompt(user_profile)

    # 2. 知识库检索
    knowledge = retrieve_relevant_knowledge(message)
    if knowledge:
        system_prompt += f"\n【本次检索到的相关知识】\n{knowledge}"

    # 3. Tavily 动态搜索（如需要）
    live_info = await maybe_live_search(message)

    # 4. 构建消息列表
    messages = []
    if history:
        for msg in history[-6:]:  # 保留最近 6 轮
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    if live_info:
        messages.append({"role": "system", "content": live_info})
    messages.append({"role": "user", "content": message})

    # 5. 调用 LLM
    reply = await call_llm(system_prompt, messages, stream=False)

    # 6. 判断数据可信度
    trust_level = "T3"
    if live_info:
        trust_level = "T1"
    elif any(kw in message for kw in ["推荐", "不推荐", "考公", "AI风险"]):
        trust_level = "T3"
    elif any(kw in message for kw in ["就业", "前景", "趋势"]):
        trust_level = "T4"

    # 7. 生成追问建议
    suggestions = _generate_suggestions(message, knowledge)

    return {
        "reply": reply if isinstance(reply, str) else str(reply),
        "sources": _extract_sources(live_info),
        "data_trust_level": trust_level,
        "suggestions": suggestions,
    }


async def chat_stream(
    message: str,
    history: list[dict] | None = None,
    user_profile: dict | None = None,
) -> AsyncGenerator[dict, None]:
    """
    流式聊天入口（SSE）。

    Yield 事件:
        {"type": "knowledge", "data": "..."}  — 检索到的知识
        {"type": "live", "data": "..."}       — 联网搜索结果
        {"type": "token", "data": "..."}      — LLM 输出 token
        {"type": "done", "data": {...}}       — 完成（含 sources/trust/suggestions）
    """
    # 1. 构建 system prompt
    system_prompt = build_advisor_system_prompt(user_profile)

    # 2. 知识库检索
    knowledge = retrieve_relevant_knowledge(message)
    if knowledge:
        system_prompt += f"\n【本次检索到的相关知识】\n{knowledge}"
        yield {"type": "knowledge", "data": knowledge}

    # 3. Tavily 动态搜索
    live_info = await maybe_live_search(message)
    if live_info:
        yield {"type": "live", "data": live_info}

    # 4. 构建消息列表
    messages = []
    if history:
        for msg in history[-6:]:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    if live_info:
        messages.append({"role": "system", "content": live_info})
    messages.append({"role": "user", "content": message})

    # 5. 流式调用 LLM
    result = await call_llm(system_prompt, messages, stream=True)

    if isinstance(result, str):
        # 降级模式，直接返回
        yield {"type": "token", "data": result}
    else:
        async for token in result:
            yield {"type": "token", "data": token}

    # 6. 完成事件
    trust_level = "T3"
    if live_info:
        trust_level = "T1"

    yield {
        "type": "done",
        "data": {
            "sources": _extract_sources(live_info),
            "data_trust_level": trust_level,
            "suggestions": _generate_suggestions(message, knowledge),
        },
    }


def _extract_sources(live_info: str) -> list[str] | None:
    """从联网搜索结果中提取来源 URL"""
    if not live_info:
        return None
    import re
    urls = re.findall(r'https?://[^\s|]+', live_info)
    return urls[:5] if urls else None


def _generate_suggestions(query: str, knowledge: str) -> list[str]:
    """根据用户问题和检索结果生成追问建议"""
    suggestions = []

    if "专业" in query or knowledge:
        suggestions.append("这个专业的就业薪资数据是多少？")
        suggestions.append("有哪些对口院校推荐？")
    elif "院校" in query or "大学" in query:
        suggestions.append("这所大学的王牌专业是什么？")
        suggestions.append("录取分数线大概是多少？")
    elif "考公" in query:
        suggestions.append("考公竞争比大概是多少？")
        suggestions.append("哪些专业考公岗位最多？")
    else:
        suggestions.append("我该选什么专业？")
        suggestions.append("冲稳保梯度怎么安排？")

    return suggestions[:2]
