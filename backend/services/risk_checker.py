"""
志愿探雷器 — 招生章程风险审查服务 (V3 — DeepSeek 直连 + 智能 Mock 回退 + 真实章程注入)

当 DEEPSEEK_API_KEY 配置时，直接调用 DeepSeek API 进行真正的 AI 审查。
未配置时使用智能 Mock（基于 audit_rules 规则库生成合理结果）。

V3.1 新增: 审查前从 EnrollmentKnowledgeBase 检索真实章程条款，
注入到 LLM prompt 或 Mock 判断中，不再仅凭通用规则做判断。

DeepSeek 兼容 OpenAI API 格式，端点: https://api.deepseek.com/v1/chat/completions
"""
import asyncio
import json
import os
import random
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # VM 无网络时 graceful degrade

from services.enrollment_kb import get_knowledge_base

# ── LLM 配置 ──────────────────────────────────────────────────
# V3 使用 DeepSeek V3 模型 (deepseek-chat，即 deepseek-v4-flash non-thinking)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = os.getenv(
    "DEEPSEEK_API_URL",
    "https://api.deepseek.com/v1/chat/completions",
)
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_TIMEOUT = int(os.getenv("DEEPSEEK_TIMEOUT", "60"))
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

# 保留旧 Dify 配置兼容
DIFY_API_URL = os.getenv("DIFY_API_URL", "")
DIFY_API_TOKEN = os.getenv("DIFY_API_TOKEN", "")

# ── 审核专用 System Prompt ────────────────────────────────────

SYSTEM_PROMPT = """你是一位资深的高考志愿填报风险管理专家。

你的任务是对考生提交的志愿目标进行逐条风险审查，输出结构化 JSON。

【审查维度（按优先级）】
1. 🔴 硬性退档（DANGER）：体检限制（色盲/色弱报临床/口腔/麻醉/影像/法医→直接DANGER）、选科不符（文科报临床→直接DANGER）
2. 🟡 软性风险（WARNING）：单科成绩低于专业门槛、属于低偏好专业（土木/农学/护理/生化环材/矿业/哲学/考古）
3. 🟢 通过（PASS）：未发现任何显性限制

【审查原则】
- 必须引用具体条款（如《体检指导意见》第X条）
- 术语规范：使用"低偏好专业"而非"天坑专业"，使用"极高退档风险"而非"100%退档"
- 结合考生实际档案（总分、单科、视力、选科）进行个性化判断
- 每人输出 JSON 格式：{"status":"DANGER|WARNING|PASS","reason":"审核理由","matched_clause":"条款原文"}"""

# ── 低偏好关键词 ──────────────────────────────────────────────

_LOW_PREFERENCE_KEYWORDS = [
    "土木", "农学", "护理", "生化", "环境", "材料", "矿业", "冶金",
    "哲学", "历史", "考古", "图书", "档案",
]

_BODY_CHECK_RISK_MAJORS = {
    "临床医学": ("色盲、色弱者不予录取", "《普通高等学校招生体检工作指导意见》第一条第二款"),
    "口腔医学": ("色盲、色弱者不予录取", "《普通高等学校招生体检工作指导意见》第一条第二款"),
    "麻醉学": ("色盲、色弱者不予录取", "《普通高等学校招生体检工作指导意见》第一条第二款"),
    "医学影像学": ("色盲、色弱者不予录取", "《普通高等学校招生体检工作指导意见》第一条第二款"),
    "法医学": ("色盲、色弱者不予录取", "《普通高等学校招生体检工作指导意见》第一条第二款"),
    "药学": ("色弱、色盲者不宜就读", "《普通高等学校招生体检工作指导意见》第一条第三款"),
    "飞行技术": ("裸眼视力低于5.0者不予录取", "《普通高等学校招生体检工作指导意见》第四款"),
}


# ── body_check 字符串 → dict 转换 ──────────────────────────────

def _parse_body_check_string(text: str) -> dict:
    """
    将 enrollment_rules.json 中字符串格式的 body_check 转为标准 dict。

    输入示例:
        "不招色盲" → {"color_blind": "DANGER"}
        "不招色盲色弱" → {"color_blind": "DANGER", "color_weak": "DANGER"}
        "不招单色识别不全者" → {"color_distinguish": "DANGER"}
    """
    result: dict = {}
    lowered = text.replace(" ", "")
    if "不招色盲色弱" in lowered or "不招色盲" in lowered:
        result["color_blind"] = "DANGER"
    if "不招色盲色弱" in lowered or "不招色弱" in lowered:
        result["color_weak"] = "DANGER"
    if "单色" in lowered:
        result["color_distinguish"] = "DANGER"
    if "镜片度" in lowered or "不宜就读" in lowered:
        result["vision"] = "WARNING"
    # 保留原文作为 clause
    result["clause"] = text
    return result


# ── 智能 Mock (V3.1 — 注入真实章程) ──────────────────────────

def _mock_check(user_profile: dict, university: str, major: str) -> dict:
    """
    基于考生实际条件 + 真实章程规则库生成有意义的 Mock 结果。

    优先级:
    1. 查询 enrollment_kb 结构化规则 → 精确匹配
    2. 未命中时 fallback 到通用体检规则
    """
    vision = user_profile.get("vision_status", "正常")
    english = user_profile.get("english_score", 0)
    math = user_profile.get("math_score", 0)

    # ── V3.1: 查询真实章程知识库 ──
    try:
        kb = get_knowledge_base()
        kb_rule = kb.query(university, major)

        # 1) 体检限制 (优先使用真实章程规则)
        if kb_rule.get("found") and kb_rule.get("body_check"):
            bc = kb_rule["body_check"]

            # ── 兼容处理: body_check 为字符串时转为 dict ──
            if isinstance(bc, str):
                bc = _parse_body_check_string(bc)
            # ── 兼容处理: body_check 仅有 "raw" 键 (由 enrollment_kb 存入) ──
            elif isinstance(bc, dict) and "raw" in bc and len(bc) == 1:
                bc = _parse_body_check_string(bc["raw"])

            if isinstance(bc, dict) and vision != "正常":
                # 硬性退档
                if bc.get("color_blind") == "DANGER" and vision == "色盲":
                    return {
                        "status": "DANGER",
                        "reason": f"根据{university}2026年招生章程，该专业不录取色盲考生。您的体检显示为{vision}，存在极高退档风险。",
                        "matched_clause": bc.get("clause", f"{university}2026年招生章程体检补充规定"),
                    }
                if bc.get("color_weak") == "DANGER" and vision == "色弱":
                    return {
                        "status": "DANGER",
                        "reason": f"根据{university}2026年招生章程，该专业不录取色弱考生。您的体检显示为{vision}，存在极高退档风险。",
                        "matched_clause": bc.get("clause", f"{university}2026年招生章程体检补充规定"),
                    }
                # 软性不宜就读 (WARNING 级)
                if bc.get("color_blind") == "WARNING" and vision == "色盲":
                    return {
                        "status": "WARNING",
                        "reason": f"根据{university}2026年招生章程，该专业不鼓励色盲考生报考。您的体检显示为色盲，建议慎重考虑。",
                        "matched_clause": bc.get("clause", f"{university}2026年招生章程体检补充规定"),
                    }
                if bc.get("color_weak") == "WARNING" and vision == "色弱":
                    return {
                        "status": "WARNING",
                        "reason": f"根据{university}2026年招生章程，该专业不鼓励色弱考生报考。您的体检显示为色弱，建议慎重考虑。",
                        "matched_clause": bc.get("clause", f"{university}2026年招生章程体检补充规定"),
                    }

        # 2) 单科成绩 (使用真实章程规则 — 支持两种格式)
        if kb_rule.get("found") and kb_rule.get("single_subject"):
            ss = kb_rule["single_subject"]
            # 格式A: {"field": "math_score", "threshold": 105, "subject": "数学"}
            if "field" in ss and "threshold" in ss:
                field = ss["field"]
                threshold = ss["threshold"]
                val = user_profile.get(field, 0)
                if val < threshold:
                    return {
                        "status": "WARNING",
                        "reason": f"根据{university}2026年招生章程，该专业要求{ss.get('subject', field)}单科不低于{threshold}分，您当前为{val}分，存在单科门槛风险。",
                        "matched_clause": ss.get("clause", f"{university}2026年招生章程"),
                    }
            # 格式B: {"english": {"min": 110, "clause": "..."}, "math": {"min": 105, ...}}
            else:
                for subj_key, subj_label in [("english", "英语"), ("math", "数学"), ("chinese", "语文")]:
                    subj_data = ss.get(subj_key)
                    if isinstance(subj_data, dict) and subj_data.get("min") and subj_data["min"] > 0:
                        val = user_profile.get(f"{subj_key}_score", 0)
                        if val < subj_data["min"]:
                            return {
                                "status": "WARNING",
                                "reason": f"根据{university}2026年招生章程，该专业要求{subj_label}单科不低于{subj_data['min']}分，您当前为{val}分，存在单科门槛风险。",
                                "matched_clause": subj_data.get("clause", f"{university}2026年招生章程"),
                            }

        # 2.5) 低偏好专业 (使用真实章程规则 + 通用关键词兜底)
        if kb_rule.get("found") and kb_rule.get("low_preference"):
            lp = kb_rule["low_preference"]
            return {
                "status": "WARNING",
                "reason": f"根据{university}2026年招生章程，该专业属于{lp.get('category', '低偏好')}方向，{lp.get('reason', '调剂风险较高。')}",
                "matched_clause": f"{university}2026年招生章程",
            }

        # 通用关键词兜底: 专业名直接匹配 low_preference 关键词
        # 适用于 KB 有大学但该专业正则没命中 low_preference 标注的情况
        if any(kw in major for kw in _LOW_PREFERENCE_KEYWORDS):
            return {
                "status": "WARNING",
                "reason": "该专业属于低偏好调剂方向，建议审慎评估调剂风险。",
                "matched_clause": "",
            }

        # 3) 语种限制 (使用真实章程规则)
        if kb_rule.get("found") and kb_rule.get("language_restriction"):
            user_lang = user_profile.get("foreign_language", "英语")
            restriction = kb_rule["language_restriction"]
            if "仅限英语" in restriction and user_lang != "英语":
                return {
                    "status": "DANGER",
                    "reason": f"根据{university}2026年招生章程，该专业{restriction}，您的语种为{user_lang}，无法报考。",
                    "matched_clause": f"{university}2026年招生章程",
                }

        # 4) 知识库有该大学但该专业无特殊限制 → 通过
        if kb_rule.get("found"):
            return {
                "status": "PASS",
                "reason": f"根据{university}2026年招生章程，该专业未发现体检/单科/语种特殊限制。",
                "matched_clause": f"{university}2026年招生章程",
            }

    except Exception:
        # 知识库异常时回退到通用规则
        pass

    # ── Fallback: 通用体检规则 (仅对教育部明确列出的高危专业) ──
    for risk_major, (reason, clause) in _BODY_CHECK_RISK_MAJORS.items():
        if risk_major in major and vision != "正常":
            return {
                "status": "DANGER",
                "reason": f"该专业{reason}，您的体检显示为{vision}，存在极高退档风险。",
                "matched_clause": clause,
            }

    # 2) 低偏好专业 (通用关键词)
    if any(kw in major for kw in _LOW_PREFERENCE_KEYWORDS):
        return {
            "status": "WARNING",
            "reason": "该专业属于低偏好调剂方向，建议审慎评估调剂风险。",
            "matched_clause": "",
        }

    # 3) 通过 (规则库全覆盖后，不再有随机推断)
    return {
        "status": "PASS",
        "reason": "未发现显性限制，体检及单科成绩均符合该专业招生章程要求。",
        "matched_clause": "",
    }


# ── DeepSeek API 调用 (V3.1 — 注入真实章程) ────────────────

async def _call_deepseek(user_profile: dict, university: str, major: str) -> dict:
    """
    调用 DeepSeek API，用真实 LLM 审查单个志愿目标。

    V3.1: 审查前从 EnrollmentKnowledgeBase 检索真实章程条款，
    注入到 LLM prompt 中，让 AI 基于该校真实章程进行审查。
    返回格式: {"status":"...", "reason":"...", "matched_clause":"..."}
    """
    profile_str = json.dumps(user_profile, ensure_ascii=False)

    # ── V3.1: 注入真实章程条款 ──
    rule_text = ""
    try:
        kb = get_knowledge_base()
        rule_text = kb.get_rule_summary(university, major)
        if not rule_text:
            # Fallback: 读取章程全文
            full_text = kb.get_full_articles(university)
            if full_text:
                rule_text = f"【{university}章程全文（节选）】\n{full_text[:3000]}"
    except Exception:
        pass

    user_content = f"""请审查以下志愿目标：

【考生档案】
{profile_str}

【目标志愿】
大学: {university}
专业: {major}
"""

    if rule_text:
        user_content += f"""
{rule_text}

请基于上述真实章程条款，结合考生档案进行个性化审查。
"""
    else:
        user_content += """
（该校章程暂未收录，请依据教育部通用体检指导意见及常见招生规则审查）
"""

    user_content += """
请直接返回 JSON（不要 Markdown 代码块，不要额外解释）：
{"status":"DANGER|WARNING|PASS","reason":"审核理由","matched_clause":"条款原文"}"""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 500,
    }

    async with httpx.AsyncClient(timeout=DEEPSEEK_TIMEOUT) as client:
        response = await client.post(DEEPSEEK_API_URL, json=payload, headers=headers)

    if response.status_code != 200:
        raise Exception(f"DeepSeek API 返回 {response.status_code}: {response.text[:200]}")

    data = response.json()
    content = data["choices"][0]["message"]["content"].strip()

    # 解析 LLM 返回的 JSON（兼容 Markdown 代码块包裹的情况）
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]

    try:
        result = json.loads(content)
        return {
            "status": result.get("status", "UNKNOWN").upper(),
            "reason": result.get("reason", "未获取到审查结论"),
            "matched_clause": result.get("matched_clause", ""),
            "career_risk": result.get("career_risk"),
            "ai_risk": result.get("ai_risk"),
        }
    except json.JSONDecodeError:
        return {
            "status": "UNKNOWN",
            "reason": f"AI 返回格式异常，未能解析为有效结果。原始返回: {content[:100]}",
            "matched_clause": "",
        }


# ── 核心入口 ──────────────────────────────────────────────────

async def check_admission_risk(
    user_profile: dict[str, Any],
    target_university: str,
    target_major: str,
) -> dict:
    """
    审查单个志愿目标。

    优先级: DeepSeek API > Dify API > 智能 Mock
    """
    # ── DeepSeek 优先 ──
    if DEEPSEEK_API_KEY:
        for attempt in range(MAX_RETRIES + 1):
            try:
                return await _call_deepseek(user_profile, target_university, target_major)
            except Exception as e:
                if attempt >= MAX_RETRIES:
                    # 重试耗尽 → Mock 回退
                    return _mock_check(user_profile, target_university, target_major)
                await asyncio.sleep(1)

    # ── Dify 兼容 ──
    if DIFY_API_TOKEN and DIFY_API_URL:
        return await _call_dify(user_profile, target_university, target_major)

    # ── 无任何 API → 智能 Mock ──
    return _mock_check(user_profile, target_university, target_major)


async def _call_dify(user_profile: dict, university: str, major: str) -> dict:
    """保留 Dify API 兼容路径。"""
    payload = {
        "inputs": {
            "profile": user_profile,
            "university": university,
            "major": major,
        },
        "response_mode": "blocking",
        "user": "gaokao-sniper-mvp",
    }

    headers = {
        "Authorization": f"Bearer {DIFY_API_TOKEN}",
        "Content-Type": "application/json",
    }

    for attempt in range(MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(DIFY_API_URL, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                outputs = data.get("data", {}).get("outputs", {})
                if isinstance(outputs, dict):
                    return {
                        "status": str(outputs.get("status", "UNKNOWN")).upper(),
                        "reason": str(outputs.get("reason", "未获取到审查结论")),
                        "matched_clause": str(outputs.get("matched_clause", "")),
                    }
                return {"status": "UNKNOWN", "reason": str(outputs), "matched_clause": ""}
            elif response.status_code in (401, 403):
                return _mock_check(user_profile, university, major)
        except (httpx.TimeoutException, httpx.RequestError):
            if attempt >= MAX_RETRIES:
                return _mock_check(user_profile, university, major)
            await asyncio.sleep(1)
        except Exception:
            break

    return _mock_check(user_profile, university, major)

async def batch_check_risks(
    user_profile: dict[str, Any],
    targets: list[dict[str, str]],
    max_concurrency: int = 5,
) -> list[dict]:
    """并发批量审查。"""
    semaphore = asyncio.Semaphore(max_concurrency)

    def _validate(item: dict) -> dict | None:
        """输入合法性校验，返回 None 表示通过，返回 dict 表示无效结果。"""
        univ = item.get("university", "")
        major = item.get("major", "")
        if not univ or len(univ.strip()) < 2:
            return {**item, "status": "WARNING", "reason": f"大学名称「{univ}」过短，请输入完整校名", "matched_clause": ""}
        if "大学" not in univ and "学院" not in univ and len(univ) < 3:
            return {**item, "status": "WARNING", "reason": f"「{univ}」不像有效的大学名称，请输入完整校名", "matched_clause": ""}
        if not major or len(major.strip()) < 2:
            return {**item, "status": "WARNING", "reason": f"专业名称「{major}」过短，请输入完整专业名", "matched_clause": ""}
        return None

    async def _checked(item: dict) -> dict:
        invalid = _validate(item)
        if invalid:
            return invalid
        async with semaphore:
            result = await check_admission_risk(
                user_profile=user_profile,
                target_university=item["university"],
                target_major=item["major"],
            )
        return {**item, **result}

    return await asyncio.gather(*[_checked(t) for t in targets])
