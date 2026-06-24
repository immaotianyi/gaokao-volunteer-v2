"""
高考志愿审核规则配置 — 集中管理所有审核规则

设计理念:
  - 规则与代码分离，支持热更新
  - 每条规则有明确的触发条件、严重等级、引用条款
  - 可直接导入到 Agent 工具中使用
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class RiskSeverity(str, Enum):
    """风险严重等级"""
    DANGER = "DANGER"    # 硬性退档：一旦触发，该志愿作废
    WARNING = "WARNING"  # 软性风险：需要警示考生
    PASS = "PASS"        # 通过
    INFO = "INFO"        # 提示信息


@dataclass
class AuditRule:
    """单条审核规则"""
    id: str                                    # 规则唯一标识
    name: str                                  # 规则名称
    category: str                              # 分类: body_check / subject_score / major_preference / subject_election
    description: str                           # 规则描述
    severity: RiskSeverity                     # 风险等级
    clause: str                                # 引用的条款/文件
    clause_text: str                           # 条款原文
    trigger_keywords: list[str] = field(default_factory=list)  # 触发关键词（专业名）
    trigger_conditions: dict = field(default_factory=dict)      # 触发条件（如 {"vision_status": ["色盲", "色弱"]}）


# ════════════════════════════════════════════════════════════════
# 体检限制规则
# ════════════════════════════════════════════════════════════════

BODY_CHECK_RULES: list[AuditRule] = [
    AuditRule(
        id="BC-001",
        name="色觉异常—临床医学类",
        category="body_check",
        description="色弱/色盲/色觉异常Ⅱ度者，临床医学、口腔医学、麻醉学、医学影像学、法医学专业可不予录取",
        severity=RiskSeverity.DANGER,
        clause="《普通高等学校招生体检工作指导意见》第一条第二款",
        clause_text="轻度色觉异常（色弱）、色觉异常Ⅱ度（色盲）者，临床医学专业可不予录取。",
        trigger_keywords=["临床医学", "口腔医学", "麻醉学", "医学影像学", "法医学"],
        trigger_conditions={"vision_status": ["色盲", "色弱", "色觉异常", "色觉异常Ⅱ度"]},
    ),
    AuditRule(
        id="BC-002",
        name="色觉异常—理学类",
        category="body_check",
        description="色弱/色盲者，化学类、生物科学类、药学类、心理学、环境科学类专业不宜就读",
        severity=RiskSeverity.WARNING,
        clause="《普通高等学校招生体检工作指导意见》第一条第三款",
        clause_text="色弱、色盲者，化学类、生物科学类、药学类、心理学、环境科学类专业不宜就读（非强制性，但院校可能拒录）。",
        trigger_keywords=["化学", "生物科学", "生物技术", "药学", "心理学", "环境科学", "环境工程"],
        trigger_conditions={"vision_status": ["色盲", "色弱"]},
    ),
    AuditRule(
        id="BC-003",
        name="视力限制—飞行航海类",
        category="body_check",
        description="裸眼视力低于5.0或矫正度数过高者，飞行技术、航海技术专业不予录取",
        severity=RiskSeverity.DANGER,
        clause="《普通高等学校招生体检工作指导意见》第四款",
        clause_text="裸眼视力任何一眼低于5.0者，飞行技术专业不予录取；裸眼视力任何一眼低于4.8者，航海技术专业不予录取，色弱色盲者不予录取。",
        trigger_keywords=["飞行技术", "航海技术"],
        trigger_conditions={"vision_status": ["近视", "裸眼视力低于5.0", "裸眼视力低于4.8"]},
    ),
    AuditRule(
        id="BC-004",
        name="身高限制—体育护理类",
        category="body_check",
        description="部分院校体育教育、护理学专业有身高限制",
        severity=RiskSeverity.WARNING,
        clause="各院校招生章程（具体以目标院校章程为准）",
        clause_text="体育教育专业通常要求男生不低于1.70米、女生不低于1.60米；护理学专业部分院校要求不低于1.58米。",
        trigger_keywords=["体育教育", "护理学"],
        trigger_conditions={},
    ),
]

# ════════════════════════════════════════════════════════════════
# 单科成绩规则
# ════════════════════════════════════════════════════════════════

@dataclass
class SubjectScoreRule:
    """单科成绩要求规则"""
    id: str
    subject: str              # 科目名称
    score_field: str          # 对应的考生档案字段
    default_threshold: int    # 默认门槛分
    keywords: list[str]       # 触发专业关键词
    clause: str
    description: str


SUBJECT_SCORE_RULES: list[SubjectScoreRule] = [
    SubjectScoreRule(
        id="SS-001",
        subject="英语",
        score_field="english_score",
        default_threshold=110,
        keywords=["英语", "翻译", "商务英语", "国际经贸", "国际商务", "对外汉语", "外交学"],
        clause="各院校招生章程第三章",
        description="外语类及涉外类专业通常要求英语单科不低于110分（部分211/985院校要求120+）",
    ),
    SubjectScoreRule(
        id="SS-002",
        subject="数学",
        score_field="math_score",
        default_threshold=120,
        keywords=["数学与应用数学", "统计学", "金融数学", "信息与计算科学"],
        clause="各院校招生章程第三章",
        description="数学类专业通常要求数学单科不低于120分",
    ),
    SubjectScoreRule(
        id="SS-003",
        subject="数学",
        score_field="math_score",
        default_threshold=105,
        keywords=["计算机科学", "计算机", "软件工程", "人工智能", "数据科学", "大数据"],
        clause="各院校招生章程第三章",
        description="计算机类及数据科学专业通常要求数学单科不低于105分",
    ),
    SubjectScoreRule(
        id="SS-004",
        subject="语文",
        score_field="chinese_score",
        default_threshold=105,
        keywords=["法学", "新闻学", "传播学", "汉语言文学", "中文"],
        clause="各院校招生章程第三章",
        description="法学、新闻传播及中文类专业可能要求语文单科不低于105分",
    ),
]

# ════════════════════════════════════════════════════════════════
# 低偏好专业规则
# ════════════════════════════════════════════════════════════════

LOW_PREFERENCE_RULES: list[dict] = [
    {
        "category": "土木建筑类",
        "keywords": ["土木", "建筑工程", "给排水", "建筑环境"],
        "reason": "行业景气度下行，报考热度持续走低。该类专业所在专业组可能包含多个低偏好专业，存在调剂陷阱。",
    },
    {
        "category": "农学类",
        "keywords": ["农学", "园艺", "植物保护", "动物科学", "水产", "草业科学"],
        "reason": "属于传统冷门学科群，部分院校将其打包进大类招生，作为未录取考生的调剂去向。",
    },
    {
        "category": "护理类",
        "keywords": ["护理学", "助产学"],
        "reason": "报考意愿普遍较低，常被院校用于接收被调剂的考生。若非首选，填报该组需格外谨慎。",
    },
    {
        "category": "生化环材",
        "keywords": ["化学工程", "生物工程", "生物技术", "应用化学", "环境工程", "环境科学", "材料科学", "材料工程", "高分子", "冶金工程"],
        "reason": "属于传统'生化环材'范畴，部分方向就业市场供需失衡，报考热度低于其他工科专业。",
    },
    {
        "category": "矿业地质类",
        "keywords": ["采矿工程", "矿业", "地质工程", "石油工程", "矿物加工"],
        "reason": "工作环境相对艰苦，报考热度极低，常年出现在调剂名单中。",
    },
    {
        "category": "哲学历史类",
        "keywords": ["哲学", "宗教学", "伦理学", "历史学", "考古学", "文物与博物馆学"],
        "reason": "就业方向不明确或就业口径较窄，属于传统冷门人文方向。",
    },
    {
        "category": "图书档案类",
        "keywords": ["图书馆学", "档案学", "情报学", "信息资源管理"],
        "reason": "行业需求有限，毕业生多转行，报考热度低。",
    },
]

# ════════════════════════════════════════════════════════════════
# 选科要求规则
# ════════════════════════════════════════════════════════════════

SUBJECT_ELECTION_RULES: dict[str, str] = {
    "临床医学": "物理+化学+生物（或物理+化学），纯文科类考生不可报考",
    "口腔医学": "物理+化学+生物（或物理+化学），纯文科类考生不可报考",
    "麻醉学": "物理+化学+生物（或物理+化学），纯文科类考生不可报考",
    "医学影像学": "物理+化学+生物（或物理+化学），纯文科类考生不可报考",
    "药学": "物理+化学（或物理+化学+生物），部分院校接受化学+生物",
    "计算机": "物理（必选），部分顶尖院校要求物理+化学",
    "软件工程": "物理（必选）",
    "人工智能": "物理（必选），部分院校要求物理+化学",
    "数据科学": "物理（必选）",
    "电子信息": "物理（必选），部分院校要求物理+化学",
    "电气工程": "物理（必选）",
    "机械工程": "物理（必选）",
    "土木工程": "物理（必选）",
    "建筑学": "物理（或物理+化学），部分院校接受历史类考生",
    "法学": "通常不限选科，但部分院校要求选考政治",
    "汉语言文学": "通常不限选科，部分院校要求选考历史",
    "英语": "通常不限选科",
}


# ════════════════════════════════════════════════════════════════
# 冲-稳-保 梯度规则 (来源: 雪峰知识库模块二)
# ════════════════════════════════════════════════════════════════

@dataclass
class RushSteadyGuardRule:
    """冲稳保梯度规则"""
    mode: str               # 填报模式: "mode1"(一校一专业) / "mode2"(专业组) / "legacy"(老高考)
    mode_name: str          # 模式名称
    rush: str               # 冲: 位次/分数区间
    steady: str             # 稳: 位次/分数区间
    guard: str              # 保: 位次/分数区间
    adjust_advice: str      # 服从调剂建议


RUSH_STEADY_GUARD_RULES: list[RushSteadyGuardRule] = [
    RushSteadyGuardRule(
        mode="mode1",
        mode_name="新高考模式一（一校一专业：浙江/山东/河北/重庆/辽宁）",
        rush="上浮 15000 位次以内（高概率冲击：上浮 10000 位次）",
        steady="下浮 0~3000（第一阶梯）/ 3000~6000（第二阶梯）/ 6000~9000（第三阶梯）",
        guard="第一阶梯：+9000~15000 位 / 第二阶梯：+15000~30000 位",
        adjust_advice="冲击院校→谨慎服从（可能被调剂到冷门专业）；保底院校→必须服从",
    ),
    RushSteadyGuardRule(
        mode="mode2",
        mode_name="新高考模式二（专业组：江苏/北京/上海/湖北/湖南/广东/福建/天津/海南）",
        rush="上浮 15 分以内（用转换分，参考近1年分数）",
        steady="下浮 0~5 分（第一阶梯）/ 5~10 分（第二阶梯）",
        guard="下浮 15~30 分，至少 2-3 个",
        adjust_advice="冲击院校→谨慎服从；稳妥院校→酌情服从；保底院校→必须服从",
    ),
    RushSteadyGuardRule(
        mode="legacy",
        mode_name="老高考模式（各省具体规则）",
        rush="参考近 1-2 年录取位次，上浮适度",
        steady="位次法匹配，参考前 1-2 年同位录取情况",
        guard="保底学校至少 1-2 个",
        adjust_advice="冲击院校若有不满意专业，切忌冲击；不是所有人都需要冲击",
    ),
]

# 位次法核心技巧
RANK_METHOD_TIPS: list[str] = [
    "位次比分数更稳定（分数每年波动，位次是全省相对位置）",
    "重点参考前 1-2 年专业分数位次",
    "3 年位次变化看趋势，不只盯单年",
    "服从调剂原则：冲击→谨慎，稳妥→酌情，保底→必须",
]


# ════════════════════════════════════════════════════════════════
# 志愿填报 18 要点 (来源: 雪峰知识库模块十二)
# ════════════════════════════════════════════════════════════════

VOLUNTEER_TIPS: list[dict] = [
    {"id": 1, "tip": "普通家庭 → 军校、警校", "category": "家庭背景"},
    {"id": 2, "tip": "家庭富裕 → 金融、经济、经管", "category": "家庭背景"},
    {"id": 3, "tip": "高薪就业 → 名校计算机、电子通信", "category": "就业导向"},
    {"id": 4, "tip": "人工智能、大数据 → 非名校不要选", "category": "就业导向", "risk": "high"},
    {"id": 5, "tip": "非名校 → 不要选经管", "category": "院校层次"},
    {"id": 6, "tip": "生化环材 → 不硕博不碰", "category": "专业选择", "risk": "high"},
    {"id": 7, "tip": "农林/建土/地矿/石油/地信 → 经常风餐露宿", "category": "专业选择", "risk": "medium"},
    {"id": 8, "tip": "艺术 → 费钱费毕业，没实力不要碰", "category": "专业选择", "risk": "high"},
    {"id": 9, "tip": "医学法学 → 又苦又累，没有硕博难就业", "category": "专业选择", "risk": "medium"},
    {"id": 10, "tip": "金融 → 不能碰（除非家里搞金融）", "category": "家庭背景", "risk": "high"},
    {"id": 11, "tip": "管理类 → 不要碰（除非家里有企业需要管）", "category": "专业选择", "risk": "high"},
    {"id": 12, "tip": "想考公 → 优先选汉语言文学和思政，不要选英语", "category": "就业导向"},
    {"id": 13, "tip": "想当医生 → 在哪儿当医生就读哪儿的医学院", "category": "就业导向"},
    {"id": 14, "tip": "文科优先选学校，理工科优先选专业", "category": "策略原则"},
    {"id": 15, "tip": "城市有时候比学校更重要", "category": "策略原则"},
    {"id": 16, "tip": "工科比理科挣钱多", "category": "就业导向"},
    {"id": 17, "tip": "数学、计算机专业都很好", "category": "专业选择"},
    {"id": 18, "tip": "了解上大学的目的，是为了以后的就业生存", "category": "策略原则"},
]


# ════════════════════════════════════════════════════════════════
# 数据可信度分级 (来源: 雪峰知识库模块八)
# ════════════════════════════════════════════════════════════════

class DataTrustLevel(str, Enum):
    """数据可信度分级"""
    T1 = "T1"  # 官方公开数据
    T2 = "T2"  # 高校官方数据
    T3 = "T3"  # 经验规律/方法论
    T4 = "T4"  # LLM 训练数据/推测


DATA_TRUST_DESC: dict[DataTrustLevel, str] = {
    DataTrustLevel.T1: "官方公开数据（各省教育考试院一分一段表、录取批次线）",
    DataTrustLevel.T2: "高校官方数据（各校招生网公布的招生计划、录取分数线）",
    DataTrustLevel.T3: "经验规律/方法论（冲稳保规则、位次法、专业选择逻辑）",
    DataTrustLevel.T4: "LLM 训练数据/推测（非精确的就业趋势、行业判断）",
}


def get_rush_steady_guard_rule(province: str) -> RushSteadyGuardRule:
    """
    根据省份返回对应的冲稳保规则

    新高考模式一（一校一专业）: 浙江/山东/河北/重庆/辽宁
    新高考模式二（专业组）: 江苏/北京/上海/湖北/湖南/广东/福建/天津/海南
    其他: 老高考模式
    """
    mode1_provinces = {"浙江", "山东", "河北", "重庆", "辽宁"}
    mode2_provinces = {"江苏", "北京", "上海", "湖北", "湖南", "广东", "福建", "天津", "海南"}

    if province in mode1_provinces:
        mode = "mode1"
    elif province in mode2_provinces:
        mode = "mode2"
    else:
        mode = "legacy"

    for rule in RUSH_STEADY_GUARD_RULES:
        if rule.mode == mode:
            return rule
    return RUSH_STEADY_GUARD_RULES[-1]


def check_rush_steady_guard(
    user_rank: int | None,
    target_rank: int | None,
    province: str,
) -> dict:
    """
    检查志愿是否符合冲稳保梯度规则

    返回:
        {
            "tier": "rush" | "steady" | "guard" | "unknown",
            "risk": "high" | "medium" | "low",
            "advice": "建议文字"
        }
    """
    rule = get_rush_steady_guard_rule(province)

    if user_rank is None or target_rank is None:
        return {
            "tier": "unknown",
            "risk": "unknown",
            "advice": f"缺少位次数据，参考规则：{rule.mode_name} → {rule.rush}",
        }

    # 位次差：正值=用户位次靠后（分数低），负值=用户位次靠前（分数高）
    rank_diff = user_rank - target_rank

    if rule.mode == "mode1":
        # 一校一专业：用位次
        # rank_diff > 0 → 用户位次靠后（分数低于目标线）→ 冲
        # rank_diff < 0 → 用户位次靠前（分数高于目标线）→ 稳/保
        if rank_diff > 15000:
            return {"tier": "beyond_rush", "risk": "high",
                    "advice": f"冲过头了（位次差{rank_diff}），录取概率极低"}
        elif rank_diff > 10000:
            return {"tier": "rush", "risk": "medium",
                    "advice": f"高概率冲击区（位次差+{rank_diff}），有风险但可尝试"}
        elif rank_diff > 0:
            return {"tier": "rush", "risk": "low",
                    "advice": f"冲击区（用户位次+{rank_diff}，分数低于目标线）"}
        elif rank_diff >= -3000:
            return {"tier": "steady", "risk": "low",
                    "advice": f"第一稳阶梯（用户位次领先{abs(rank_diff)}），录取概率高"}
        elif rank_diff >= -6000:
            return {"tier": "steady", "risk": "low",
                    "advice": f"第二稳阶梯（用户位次领先{abs(rank_diff)}）"}
        elif rank_diff >= -9000:
            return {"tier": "steady", "risk": "low",
                    "advice": f"第三稳阶梯（用户位次领先{abs(rank_diff)}）"}
        elif rank_diff >= -15000:
            return {"tier": "guard", "risk": "low",
                    "advice": f"第一保阶梯（用户位次领先{abs(rank_diff)}）"}
        elif rank_diff >= -30000:
            return {"tier": "guard", "risk": "low",
                    "advice": f"第二保阶梯（用户位次领先{abs(rank_diff)}）"}
        else:
            return {"tier": "over_guard", "risk": "medium",
                    "advice": f"保过头了（位次领先{abs(rank_diff)}），浪费分数，建议换更高目标"}
    elif rule.mode == "mode2":
        # 专业组：位次差 1000 ≈ 分数差 1 分
        # rank_diff > 0 → 用户分低于目标线 → 冲
        # rank_diff < 0 → 用户分高于目标线 → 稳/保
        score_diff = -rank_diff / 1000  # 正值=用户分高于目标线
        if score_diff < -15:
            return {"tier": "beyond_rush", "risk": "high",
                    "advice": f"冲过头了（用户分约{score_diff:.0f}分，低于目标线15分以上），录取概率极低"}
        elif score_diff < 0:
            gap_abs = abs(int(score_diff))
            return {"tier": "rush", "risk": "medium",
                    "advice": f"冲击区（用户分约{score_diff:.0f}分，低于目标线{gap_abs}分内）"}
        elif score_diff <= 5:
            return {"tier": "steady", "risk": "low",
                    "advice": f"第一稳阶梯（用户分约+{score_diff:.0f}分，略高于目标线）"}
        elif score_diff <= 10:
            return {"tier": "steady", "risk": "low",
                    "advice": f"第二稳阶梯（用户分约+{score_diff:.0f}分）"}
        elif score_diff <= 30:
            return {"tier": "guard", "risk": "low",
                    "advice": f"保底区（用户分约+{score_diff:.0f}分，远高于目标线）"}
        else:
            return {"tier": "over_guard", "risk": "medium",
                    "advice": f"保过头了（用户分约+{score_diff:.0f}分），浪费分数"}
    else:
        # 老高考：简单判断
        if rank_diff < -10000:
            return {"tier": "rush", "risk": "medium", "advice": "冲击区"}
        elif rank_diff <= 10000:
            return {"tier": "steady", "risk": "low", "advice": "稳妥区"}
        else:
            return {"tier": "guard", "risk": "low", "advice": "保底区"}
