"""
高考志愿知识库 — 从雪峰 agent 16 模块知识库中提取的 4 个高价值模块结构化数据

来源: xuefeng-agent/knowledge_base.md (MIT 许可证)
提取模块:
  - 模块十: 推荐/不推荐专业清单
  - 模块十一: 行业名校分类
  - 模块十三: 稳定就业路径
  - 模块十六: 2025-2026 AI 冲击趋势

设计原则:
  - 结构化为机器可查数据 (list[dict])，避免塞 markdown 全文进 prompt
  - 保留关键事实和判断逻辑，剔除人设/语录/表达风格
  - 可被探雷器和捡漏雷达共同复用
"""

from __future__ import annotations
import json
from pathlib import Path
from functools import lru_cache


# ════════════════════════════════════════════════════════════════
# 模块十: 推荐/不推荐专业清单
# ════════════════════════════════════════════════════════════════

# 强烈推荐专业 (普通家庭) — 每条含关键词列表和推荐理由
RECOMMENDED_MAJORS: list[dict] = [
    {
        "category": "计算机类",
        "keywords": ["计算机科学与技术", "软件工程", "网络工程", "信息安全", "物联网工程", "人工智能"],
        "reason": "进大厂/考公/大数据，就业面广",
        "employment_risk": "medium",  # 2025 后就业质量下降但高端稀缺
    },
    {
        "category": "电子信息类",
        "keywords": ["电子信息工程", "电子科学与技术", "通信工程", "微电子"],
        "reason": "国家芯片战略，研发芯片，进大厂/央企",
        "employment_risk": "low",
    },
    {
        "category": "电气工程",
        "keywords": ["电气工程及其自动化"],
        "reason": "进国家电网，稳定；新能源汽车/光伏/风电风口",
        "employment_risk": "low",
    },
    {
        "category": "数学/统计",
        "keywords": ["数学与应用数学", "统计学"],
        "reason": "考公统计局，转计算机/金融/精算，可为各行各业赋能",
        "employment_risk": "low",
    },
    {
        "category": "能源动力",
        "keywords": ["能源与动力工程"],
        "reason": "电网、新能源汽车、光伏、风电",
        "employment_risk": "low",
    },
    {
        "category": "生物医学工程",
        "keywords": ["生物医学工程"],
        "reason": "研发医疗器械（注意跟生物专业不一样）",
        "employment_risk": "low",
    },
    {
        "category": "航空航天",
        "keywords": ["航空航天"],
        "reason": "有情怀，稳定，钱不多但体面",
        "employment_risk": "low",
    },
    {
        "category": "法学",
        "keywords": ["法学"],
        "reason": "考公（公检法），律所，资源可传代。但学校档次要高",
        "employment_risk": "medium",  # 基础法律服务被 AI 冲击
    },
    {
        "category": "财会",
        "keywords": ["会计学", "财务管理", "审计学"],
        "reason": "专业性强，考公考编有优势，社会需求大。必须考 CPA",
        "employment_risk": "medium",  # 基础会计被替代，高端需求旺
    },
    {
        "category": "汉语言文学",
        "keywords": ["汉语言文学"],
        "reason": "考公大户，教师",
        "employment_risk": "low",
    },
]

# 不推荐专业 (普通家庭) — 每条含关键词和劝退理由
NOT_RECOMMENDED_MAJORS: list[dict] = [
    {
        "category": "土木",
        "keywords": ["土木工程", "土木"],
        "reason": "985 也要去工地，成绩差的反而可以学（先解决生存）",
        "employment_risk": "high",
    },
    {
        "category": "建筑",
        "keywords": ["建筑学", "建筑"],
        "reason": "市场不景气",
        "employment_risk": "high",
    },
    {
        "category": "生化环材/农/地质",
        "keywords": ["化学工程", "生物工程", "生物技术", "应用化学", "环境工程", "材料科学", "材料工程", "高分子", "冶金工程", "农学", "地质工程", "石油工程"],
        "reason": "四大天坑，本科就业难，需读到博士，工资不高",
        "employment_risk": "high",
    },
    {
        "category": "新闻学",
        "keywords": ["新闻学", "传播学", "新闻传播"],
        "reason": "传统媒体减少，自媒体无门槛，非专业人士也能干",
        "employment_risk": "high",
    },
    {
        "category": "英语",
        "keywords": ["英语"],
        "reason": "除非北外/上外，不利于考公，无专业壁垒；被 AI 翻译严重冲击",
        "employment_risk": "high",
    },
    {
        "category": "工商管理/行政管理",
        "keywords": ["工商管理", "行政管理"],
        "reason": "家里没企业不要选，不学也能干",
        "employment_risk": "high",
    },
    {
        "category": "哲学",
        "keywords": ["哲学", "宗教学", "伦理学"],
        "reason": "可以当兴趣不能当饭吃",
        "employment_risk": "high",
    },
    {
        "category": "教育学",
        "keywords": ["教育学"],
        "reason": "不如选具体师范专业",
        "employment_risk": "medium",
    },
    {
        "category": "金融",
        "keywords": ["金融学", "金融"],
        "reason": "吃学校和人脉，至少得有一样，数学/英语不行别报",
        "employment_risk": "medium",
    },
    {
        "category": "市场营销",
        "keywords": ["市场营销"],
        "reason": "没有任何壁垒，是个人都能做销售",
        "employment_risk": "high",
    },
    {
        "category": "设计类",
        "keywords": ["视觉传达", "环境设计", "产品设计", "艺术设计"],
        "reason": "熬夜加班，工资还低",
        "employment_risk": "medium",
    },
]

# 钱途最好的 20 大专业
HIGH_SALARY_MAJORS: list[str] = [
    "信息安全", "软件工程", "网络工程", "信息工程", "物联网工程",
    "计算机科学与技术", "数字媒体技术", "电子科学与技术", "信息管理与信息系统", "通信工程",
    "电子信息工程", "微电子科学与工程", "数字媒体艺术", "自动化", "交通运输",
    "电子信息科学与技术", "信息与计算科学", "测控技术与仪器", "光电信息科学与工程", "工业工程",
]

# 公务员招录多的专业
CIVIL_SERVICE_MAJORS: list[str] = ["法学", "汉语言文学", "会计学", "财务管理", "审计学", "计算机科学与技术", "经济学"]


# ════════════════════════════════════════════════════════════════
# 模块十一: 行业名校分类
# ════════════════════════════════════════════════════════════════

# 顶尖高校联盟
UNIVERSITY_ALLIANCES: dict[str, list[str]] = {
    "C9联盟": ["北京大学", "清华大学", "复旦大学", "上海交通大学", "南京大学", "浙江大学", "中国科学技术大学", "哈尔滨工业大学", "西安交通大学"],
    "华东五校": ["复旦大学", "上海交通大学", "南京大学", "浙江大学", "中国科学技术大学"],
    "国防七子": ["北京理工大学", "北京航空航天大学", "哈尔滨工业大学", "南京航空航天大学", "南京理工大学", "西北工业大学", "哈尔滨工程大学"],
    "两电一邮": ["电子科技大学", "西安电子科技大学", "北京邮电大学"],
    "五院四系": ["中国政法大学", "西南政法大学", "华东政法大学", "西北政法大学", "中南财经政法大学", "北京大学法学院", "武汉大学法学院", "吉林大学法学院", "中国人民大学法学院"],
    "电气二龙四虎": ["华北电力大学", "武汉大学", "清华大学", "西安交通大学", "浙江大学", "华中科技大学"],
    "机械四小龙": ["合肥工业大学", "湖南大学", "吉林大学", "燕山大学"],
    "南北双药": ["中国药科大学", "沈阳药科大学"],
    "卓越大学联盟": ["北京理工大学", "哈尔滨工业大学", "西北工业大学", "重庆大学", "大连理工大学", "东南大学", "华南理工大学", "天津大学", "同济大学"],
}

# 行业对口强校 (专业方向 → 对口院校)
INDUSTRY_SCHOOLS: dict[str, list[str]] = {
    "电气/电网": ["华北电力大学", "东北电力大学", "上海电力大学", "三峡大学", "长沙理工大学"],
    "电子信息/通信": ["电子科技大学", "西安电子科技大学", "北京邮电大学", "南京邮电大学", "重庆邮电大学", "杭州电子科技大学"],
    "法学": ["中国政法大学", "西南政法大学", "华东政法大学", "西北政法大学", "中南财经政法大学", "北京大学", "武汉大学", "吉林大学", "中国人民大学"],
    "石油/化工": ["中国石油大学(华东)", "中国石油大学(北京)", "西南石油大学", "东北石油大学"],
    "铁路/交通": ["西南交通大学", "北京交通大学", "石家庄铁道大学", "大连交通大学", "兰州交通大学"],
    "航空航天/军工": ["北京航空航天大学", "北京理工大学", "哈尔滨工业大学", "西北工业大学", "南京航空航天大学", "南京理工大学", "哈尔滨工程大学"],
    "医学": ["北京协和医学院", "北京大学医学部", "上海交通大学医学院", "复旦大学上海医学院", "中山大学中山医学院", "四川大学华西医学中心"],
    "气象": ["南京信息工程大学"],
    "民航": ["中国民用航空飞行学院", "中国民航大学"],
    "海关": ["上海海关学院"],
    "烟草": ["郑州轻工业大学", "云南农业大学"],
}

# 用人单位认可度星级排名 (部分代表性院校)
EMPLOYER_RECOGNITION: dict[str, list[str]] = {
    "十星": ["清华大学", "北京大学"],
    "九星": ["复旦大学", "上海交通大学", "浙江大学", "南京大学", "中国科学技术大学", "中国人民大学"],
    "八星": ["北京航空航天大学", "同济大学", "上海财经大学", "中央财经大学", "对外经济贸易大学", "西安交通大学", "哈尔滨工业大学", "武汉大学", "东南大学", "天津大学", "中山大学", "南开大学", "北京师范大学", "华中科技大学", "北京理工大学"],
    "七星": ["电子科技大学", "华南理工大学", "西北工业大学", "北京邮电大学", "厦门大学", "华东师范大学", "中国政法大学"],
    "六星": ["山东大学", "四川大学", "吉林大学", "重庆大学", "湖南大学", "东北大学", "中南大学", "大连理工大学", "北京交通大学", "北京科技大学", "中国传媒大学"],
}

# 华为校招目标院校 (四非代表)
HUAWEI_TARGET_SCHOOLS_TOP: list[str] = [
    "深圳大学", "杭州电子科技大学", "重庆邮电大学",  # 四非但华为青睐
]


# ════════════════════════════════════════════════════════════════
# 模块十三: 稳定就业路径
# ════════════════════════════════════════════════════════════════

# 稳定就业路径 (每条含进入门槛、对口专业、对口院校、稳定性评级)
STABLE_CAREER_PATHS: list[dict] = [
    {
        "path": "教师",
        "stability": "high",
        "threshold": "公费师范生包分配有编；普通师范生需考编（笔试+面试）",
        "target_majors": ["汉语言文学", "数学与应用数学", "英语", "物理学", "化学", "生物科学", "历史学", "思想政治教育", "教育学"],
        "target_schools": ["北京师范大学", "华东师范大学", "华中师范大学", "东北师范大学", "陕西师范大学", "西南大学"],
        "pros": "寒暑假带薪、五险一金比例高、社会认可度高",
        "cons": "编制考试竞争激烈、基层待遇一般",
    },
    {
        "path": "医生",
        "stability": "high",
        "threshold": "必须通过执业医师资格考试；本科5年+规培3年；三甲要求博士",
        "target_majors": ["临床医学", "口腔医学", "麻醉学", "医学影像学", "儿科学"],
        "target_schools": ["北京协和医学院", "北京大学医学部", "上海交通大学医学院", "复旦大学上海医学院", "中山大学中山医学院", "四川大学华西医学中心"],
        "pros": "不可替代性强、持续稳定、社会地位高",
        "cons": "学制长（8-11年起）、35岁前基本不赚钱、工作强度大",
    },
    {
        "path": "公务员",
        "stability": "high",
        "threshold": "国考/省考笔试+面试；2024年国考竞争比约57:1；选调生要求党员+学生干部",
        "target_majors": ["法学", "汉语言文学", "会计学", "财务管理", "计算机科学与技术", "经济学"],
        "target_schools": ["不限，但选调生多要求双一流"],
        "pros": "稳定、离家近、发展空间可预期",
        "cons": "竞争极其激烈、基层工作压力大",
    },
    {
        "path": "国家电网",
        "stability": "high",
        "threshold": "校招为主，一本以上电气专业基本稳；县级以下更容易进",
        "target_majors": ["电气工程及其自动化", "能源与动力工程"],
        "target_schools": ["华北电力大学", "东北电力大学", "上海电力大学", "三峡大学", "长沙理工大学"],
        "pros": "稳定性高、待遇好",
        "cons": "大城市竞争激烈",
    },
    {
        "path": "铁路系统",
        "stability": "high",
        "threshold": "校招为主",
        "target_majors": ["交通运输", "土木工程", "机械工程", "电气工程"],
        "target_schools": ["西南交通大学", "北京交通大学", "石家庄铁道大学", "大连交通大学", "兰州交通大学"],
        "pros": "稳定性高、福利好",
        "cons": "工作地点可能偏远",
    },
    {
        "path": "石油系统",
        "stability": "medium",
        "threshold": "校招为主",
        "target_majors": ["石油工程", "地质工程", "化学工程", "机械工程"],
        "target_schools": ["中国石油大学(华东)", "中国石油大学(北京)", "西南石油大学", "东北石油大学"],
        "pros": "待遇好",
        "cons": "地点偏，常驻油田",
    },
    {
        "path": "航空航天/军工",
        "stability": "high",
        "threshold": "校招为主，部分涉及保密限制",
        "target_majors": ["航空航天类", "兵器类", "核工程类", "电子信息类"],
        "target_schools": ["哈尔滨工业大学", "北京航空航天大学", "北京理工大学", "西北工业大学", "南京航空航天大学", "南京理工大学", "哈尔滨工程大学"],
        "pros": "有情怀、稳定、待遇中上",
        "cons": "部分涉密限制",
    },
    {
        "path": "银行系统",
        "stability": "medium",
        "threshold": "校招为主，笔试+面试，对学校层次有要求",
        "target_majors": ["金融学", "经济学", "会计学", "计算机科学与技术"],
        "target_schools": ["不限，但偏好985/211"],
        "pros": "待遇中上",
        "cons": "基层工作压力大，有业绩考核",
    },
]


# ════════════════════════════════════════════════════════════════
# 模块十六: 2025-2026 AI 冲击趋势
# ════════════════════════════════════════════════════════════════

# AI 替代风险评级 (专业 → 风险等级 + 说明)
AI_IMPACT_RISK: dict[str, dict] = {
    "计算机科学与技术": {
        "risk": "medium",
        "detail": "就业质量下降但高端人才稀缺，不能只学基础，必须+AI/大数据方向",
        "data": "绿牌专业中计算机类: 2021年4个→2024年0个；月收入负增长(6863→6846元)",
    },
    "软件工程": {
        "risk": "medium",
        "detail": "初级码农过剩，架构师稀缺；名校+深造可选，普通院校慎选",
        "data": "40人毕业生仅1人拿到大厂offer（三四年前是30人）",
    },
    "电子信息": {
        "risk": "low",
        "detail": "国家战略重点，持续看好；芯片方向是最稳妥的硬科技",
        "data": None,
    },
    "集成电路": {
        "risk": "low",
        "detail": "国家战略重点，持续看好",
        "data": None,
    },
    "电气工程": {
        "risk": "low",
        "detail": "电网+新能源双驱动，稳定；进电网仍是很好的选择",
        "data": None,
    },
    "翻译": {
        "risk": "high",
        "detail": "被 AI 严重替代，除非北外/上外层次，否则不建议",
        "data": "翻译自动化覆盖率极高",
    },
    "英语": {
        "risk": "high",
        "detail": "被 AI 翻译严重替代，无专业壁垒",
        "data": None,
    },
    "会计学": {
        "risk": "medium",
        "detail": "基础会计被替代，高端需求旺；必须考 CPA/CMA，走高端路线",
        "data": "数据录入员自动化覆盖率67.1%",
    },
    "法学": {
        "risk": "medium",
        "detail": "基础法律服务被 AI 冲击；五院四系+法考，门槛更高了",
        "data": None,
    },
    "医学": {
        "risk": "low",
        "detail": "不可替代性强，持续稳定；仍是普通家庭好选择",
        "data": None,
    },
    "护理": {
        "risk": "low",
        "detail": "不可替代性强，持续稳定",
        "data": None,
    },
    "客服": {
        "risk": "high",
        "detail": "AI 自动化覆盖率70.1%",
        "data": None,
    },
    "数据录入": {
        "risk": "high",
        "detail": "AI 自动化覆盖率67.1%",
        "data": None,
    },
}

# 2024 年度高校专业大洗牌数据
MAJOR_RESTRUCTURING_2024: dict = {
    "撤销专业点": 1428,
    "停招专业点": 2220,
    "新增专业点": 1839,
    "过剩预警专业": ["计算机", "软件工程", "英语", "国际经济与贸易", "法学", "市场营销"],
    "新增方向": ["人工智能(569所院校)", "具身智能", "智能医学工程", "AI教育"],
    "note": "规模历史之最，多省发布过剩专业预警",
}


# ════════════════════════════════════════════════════════════════
# 查询函数 (供探雷器和捡漏雷达调用)
# ════════════════════════════════════════════════════════════════

def _match_major(major_name: str, keywords: list[str]) -> bool:
    """模糊匹配专业名是否包含任一关键词"""
    if not major_name:
        return False
    major_lower = major_name.lower()
    for kw in keywords:
        if kw.lower() in major_lower:
            return True
    return False


def get_major_recommendation(major_name: str) -> dict | None:
    """
    查询专业推荐/不推荐评级

    返回:
        {
            "level": "recommended" | "not_recommended" | "neutral",
            "category": "分类",
            "reason": "理由",
            "employment_risk": "low" | "medium" | "high"
        }
    """
    for item in NOT_RECOMMENDED_MAJORS:
        if _match_major(major_name, item["keywords"]):
            return {
                "level": "not_recommended",
                "category": item["category"],
                "reason": item["reason"],
                "employment_risk": item["employment_risk"],
            }
    for item in RECOMMENDED_MAJORS:
        if _match_major(major_name, item["keywords"]):
            return {
                "level": "recommended",
                "category": item["category"],
                "reason": item["reason"],
                "employment_risk": item["employment_risk"],
            }
    return None


def get_ai_impact_risk(major_name: str) -> dict | None:
    """
    查询专业的 AI 替代风险

    返回:
        {
            "risk": "low" | "medium" | "high",
            "detail": "说明",
            "data": "数据支撑(可None)"
        }
    """
    for key, val in AI_IMPACT_RISK.items():
        if _match_major(major_name, [key]):
            return val
    return None


def get_university_alliance(university_name: str) -> list[str]:
    """查询院校所属的联盟列表"""
    alliances = []
    for alliance, members in UNIVERSITY_ALLIANCES.items():
        for member in members:
            if member in university_name or university_name in member:
                alliances.append(alliance)
                break
    return alliances


def get_employer_recognition(university_name: str) -> str | None:
    """查询用人单位认可度星级"""
    for star, schools in EMPLOYER_RECOGNITION.items():
        for school in schools:
            if school in university_name or university_name in school:
                return star
    return None


def get_stable_career_for_major(major_name: str) -> list[dict]:
    """查询该专业对应的稳定就业路径"""
    paths = []
    for path in STABLE_CAREER_PATHS:
        if _match_major(major_name, path["target_majors"]):
            paths.append({
                "path": path["path"],
                "stability": path["stability"],
                "threshold": path["threshold"],
                "pros": path["pros"],
                "cons": path["cons"],
            })
    return paths


def is_high_salary_major(major_name: str) -> bool:
    """是否属于钱途最好的20大专业"""
    return _match_major(major_name, HIGH_SALARY_MAJORS)


def is_civil_service_friendly(major_name: str) -> bool:
    """是否属于考公友好专业"""
    return _match_major(major_name, CIVIL_SERVICE_MAJORS)


# ════════════════════════════════════════════════════════════════
# 导出为 JSON (用于注入 prompt)
# ════════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def export_compact_kb() -> str:
    """
    导出精简版知识库 JSON (约 3-5KB)，用于注入探雷器 system prompt

    只保留最关键的事实数据，剔除冗长描述
    """
    compact = {
        "not_recommended_majors": [
            {"category": m["category"], "keywords": m["keywords"], "risk": m["employment_risk"]}
            for m in NOT_RECOMMENDED_MAJORS
        ],
        "recommended_majors": [
            {"category": m["category"], "keywords": m["keywords"], "risk": m["employment_risk"]}
            for m in RECOMMENDED_MAJORS
        ],
        "high_salary_majors": HIGH_SALARY_MAJORS,
        "civil_service_majors": CIVIL_SERVICE_MAJORS,
        "ai_impact_risk": {
            k: {"risk": v["risk"], "detail": v["detail"]}
            for k, v in AI_IMPACT_RISK.items()
        },
        "major_restructuring_2024": MAJOR_RESTRUCTURING_2024,
    }
    return json.dumps(compact, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    # 自测
    print("=" * 60)
    print("知识库自测")
    print("=" * 60)

    test_majors = ["计算机科学与技术", "土木工程", "法学", "英语", "护理学", "电气工程及其自动化", "新闻学"]
    for m in test_majors:
        print(f"\n【{m}】")
        rec = get_major_recommendation(m)
        print(f"  推荐: {rec}")
        ai = get_ai_impact_risk(m)
        print(f"  AI风险: {ai}")
        stable = get_stable_career_for_major(m)
        if stable:
            print(f"  稳定就业: {[p['path'] for p in stable]}")

    print("\n精简KB大小:", len(export_compact_kb()), "bytes")
