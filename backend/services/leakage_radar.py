"""
捡漏雷达 — 核心 Pandas 算法 (V2 六维评分)

联合主键: university_code + group_code + major_code

捡漏策略矩阵（6个维度）:
  1. 新增专业/专业组 — 今年首次招生，无历史分数线参考
  2. 扩招 — 计划数大幅增长，分数线可能下降
  3. 异地新校区 — 985/211 外地新校区首招，分数线比本部低 15-30 分
  4. 首招批次变更 — 今年首次在本科批招生的专业
  5. 中外合作/高收费 — 学费 > 2.5 万/年，报考人数少
  6. 冷门选科 — 选科组合考生占比低，竞争小

流程:
  1. 省份+科类过滤
  2. 批次过滤 (可选)
  3. 院校类型过滤 (可选)
  4. 分数区间过滤 (可选)
  5. 构建联合主键
  6. 新增专业挖掘
  7. 扩招专业挖掘（分级扩招）
  8. 新校区匹配
  9. 首招批次变更检测
  10. 中外合作/高收费识别
  11. 选科稀缺度计算
  12. 纯净组过滤（V2: 风险占比 + 高偏好专业反向加权）
  13. 估值模型（新增专业分数预估）
  14. 六维评分
  15. 排序返回

"""
import re
from typing import List, Optional, Dict, Any, Tuple
import pandas as pd
import numpy as np


# ── 默认风险词典 ─────────────────────────────────────────────
DEFAULT_RISK_KEYWORDS = [
    "土木", "农学", "护理", "生化", "环境", "材料", "矿业", "冶金",
]

# ── 高偏好专业关键词（反向加权） ─────────────────────────────
HIGH_PREFERENCE_KEYWORDS = [
    "计算机", "软件工程", "人工智能", "数据科学", "电子信息",
    "临床医学", "口腔医学", "电气工程", "自动化",
    "会计学", "金融学", "法学", "汉语言文学", "网络空间安全",
]

# ── 中外合作关键词 ───────────────────────────────────────────
SINO_FOREIGN_KEYWORDS = [
    "中外合作", "合作办学", "国际班", "国际课程", "联合培养",
    "中英", "中美", "中澳", "中加", "中法", "中德",
]

# ── 院校层次映射 ─────────────────────────────────────────────
SCHOOL_TIER_MAP = {
    "985": 1,
    "211": 2,
    "双一流": 3,
    "省属重点": 4,
    "普通本科": 5,
    "民办": 6,
}

# ── 各省物理类考生占比（3+1+2 省份，基于 2024-2025 考试院选科统计） ──
# 数据来源：各省考试院公开的一分一段表物理类/历史类累计人数推算
# 用于省份自适应的选科稀缺度计算（物理类占比越高 → 历史类组合越稀缺）
PROVINCE_PHYSICS_RATIO = {
    "广东": 0.60, "福建": 0.60, "湖北": 0.62, "湖南": 0.58,
    "河北": 0.65, "辽宁": 0.63, "重庆": 0.64, "江苏": 0.61,
    "河南": 0.60, "安徽": 0.59, "四川": 0.56, "陕西": 0.58,
    "甘肃": 0.57, "江西": 0.55,
}
# 默认物理类占比（未收录省份回退）
DEFAULT_PHYSICS_RATIO = 0.60

# ── 选科组合条件概率（给定首选科目后的组合占比，各省差异小用全国统一值） ──
# 物理类下：物化生约占 70%，物化地约 30%（物化捆绑后第三科分布）
# 历史类下：史政地约占 60%，史政生约 20%，史地生约 17%
SUBJECT_COMBO_RATIO = {
    "物理+化学+生物": 0.42,
    "物理+化学+地理": 0.18,
    "物理+化学+政治": 0.05,
    "物理+生物+地理": 0.15,
    "物理+生物+政治": 0.03,
    "物理+地理+政治": 0.02,
    "历史+政治+地理": 0.35,
    "历史+政治+生物": 0.12,
    "历史+地理+生物": 0.10,
    "历史+化学+生物": 0.03,
    "物理+化学": 0.55,       # 物化捆绑（二选科）
    "物理+不限": 0.85,
    "历史+不限": 0.40,
}


# ── 科类兼容映射 ─────────────────────────────────────────────
# 3+3 新高考省份（山东/浙江/北京/上海/海南/天津）不分文理，只有"综合"
# 这些省份的历史数据标为"综合"，但招生计划可能标"物理类/历史类"
# 查询 df_history 时需把"综合"视为能匹配"物理类"和"历史类"
COMPREHENSIVE_PROVINCES = {"山东", "浙江", "北京", "上海", "海南", "天津"}

# 科类别名映射（统一到 标准科类）
SUBJECT_ALIAS = {
    "理科": "物理类",
    "文科": "历史类",
    "普通类(首选物理)": "物理类",
    "普通类(首选历史)": "历史类",
}


def _normalize_subject(s: str) -> str:
    """标准化科类名称。"""
    if not s or (isinstance(s, float) and pd.isna(s)):
        return ""
    return SUBJECT_ALIAS.get(str(s).strip(), str(s).strip())


def _subject_matches(hist_subject: str, user_subject: str, province: str) -> bool:
    """
    判断历史数据的科类是否与用户查询科类兼容。
    - 3+3 省份：历史标"综合" → 匹配用户的"物理类"或"历史类"
    - 其他省份：精确匹配（含别名归一化）
    """
    hs = _normalize_subject(hist_subject)
    us = _normalize_subject(user_subject)
    if not hs or not us:
        return True  # 空科类不限制
    if hs == us:
        return True
    # 3+3 省份"综合"通配
    if province in COMPREHENSIVE_PROVINCES and hs == "综合":
        return True
    return False


# ── 默认新校区字典 ───────────────────────────────────────────
DEFAULT_NEW_CAMPUSES: List[dict] = [
    {
        "campus": "华南师范大学（汕尾校区）",
        "parent": "华南师范大学",
        "first_year": 2026,
        "discount_ratio": 0.85,
    },
    {
        "campus": "北京师范大学（珠海校区）",
        "parent": "北京师范大学",
        "first_year": 2025,
        "discount_ratio": 0.88,
    },
    {
        "campus": "哈尔滨工业大学（深圳）",
        "parent": "哈尔滨工业大学",
        "first_year": 2024,
        "discount_ratio": 0.95,
    },
]


def _get_school_tier(university_name: str, school_type: str = None) -> int:
    """根据学校类型返回层次编号（数字越小越高）。"""
    if school_type:
        return SCHOOL_TIER_MAP.get(school_type, 5)
    return 5


def _extract_major_keywords(major_name: str) -> List[str]:
    """从专业名提取关键词用于相似专业匹配。"""
    if not isinstance(major_name, str):
        return []
    # 去掉括号内容（如"数字经济（实验班）"→"数字经济"）
    clean = re.sub(r"[（(].*?[)）]", "", major_name).strip()
    # 提取有意义的关键词
    keywords = []
    # 常见专业后缀词
    for kw in ["工程", "科学", "技术", "管理", "经济", "金融", "医学",
                "计算机", "软件", "智能", "数据", "电子", "电气", "机械",
                "土木", "建筑", "化学", "生物", "物理", "数学", "统计",
                "法学", "会计", "新闻", "教育", "文学", "历史", "哲学",
                "临床", "口腔", "护理", "药学", "农学", "园艺", "动物"]:
        if kw in clean:
            keywords.append(kw)
    return keywords if keywords else [clean]


def _match_new_campus(university_name: str, new_campuses: List[dict]) -> Optional[dict]:
    """检查大学名是否匹配新校区字典中的条目。"""
    for campus in new_campuses:
        if campus["campus"] in university_name:
            return campus
    return None


def _detect_sino_foreign(major_name: str, notes: str = None) -> bool:
    """检测是否为中外合作/高收费专业。"""
    combined = (major_name or "")
    if notes:
        combined += " " + notes
    for kw in SINO_FOREIGN_KEYWORDS:
        if kw in combined:
            return True
    return False


def _detect_first_batch(
    cur_row: pd.Series,
    prev_df: pd.DataFrame,
) -> bool:
    """
    检测首招批次变更：某大学今年首次在本科批招生。
    用 (university_name, batch) 匹配（兼容不同年份 group_code 编码体系差异）。
    """
    if prev_df is None or prev_df.empty:
        return True
    uni_name = str(cur_row.get("university_name", "")).strip()
    batch = str(cur_row.get("batch", ""))

    if not uni_name:
        return False

    # 检查上年是否有同一大学在同一批次招生
    same_uni_batch = prev_df[
        (prev_df["university_name"].astype(str).str.strip() == uni_name)
        & (prev_df["batch"].astype(str) == batch)
    ]
    return same_uni_batch.empty


def _calc_subject_scarcity(
    subject_requirement: str,
    user_subject_group: str,
    province: str = "",
) -> Optional[float]:
    """
    计算选科稀缺度（省份自适应版）。
    返回 0-1 之间的小数，代表满足该选科要求的考生占比。
    占比越低 → 竞争越小 → 捡漏价值越高。

    省份自适应算法：
    1. 解析选科要求字符串，提取"首选科目"和"再选要求"
    2. 查 PROVINCE_PHYSICS_RATIO 获取该省物理类考生占比
    3. 物理类组合按 province_physics_ratio / 0.60 缩放（广东基准）
       历史类组合按 (1-province_physics_ratio) / 0.40 缩放
    4. 支持模糊匹配、单科要求、不限等场景
    """
    if not subject_requirement or pd.isna(subject_requirement):
        return None

    req = str(subject_requirement).strip()

    # 省份物理类占比（用于自适应缩放）
    physics_ratio = PROVINCE_PHYSICS_RATIO.get(province, DEFAULT_PHYSICS_RATIO)
    # 物理类组合缩放因子（广东基准 0.60）
    physics_scale = physics_ratio / 0.60
    # 历史类组合缩放因子（广东基准 0.40）
    history_scale = (1 - physics_ratio) / 0.40

    def _scale(ratio: float, req_str: str) -> float:
        """按 province 物理类占比缩放组合占比。"""
        if req_str.startswith("物理"):
            return min(1.0, ratio * physics_scale)
        elif req_str.startswith("历史"):
            return min(1.0, ratio * history_scale)
        return ratio

    # 1. 精确匹配预定义字典
    ratio = SUBJECT_COMBO_RATIO.get(req)
    if ratio is not None:
        return _scale(ratio, req)

    # 2. 模糊匹配预定义字典
    for key, val in SUBJECT_COMBO_RATIO.items():
        if key in req or req in key:
            return _scale(val, key)

    # 3. 通用解析：基于选科要求字符串动态计算
    req_lower = req.lower()

    # 检测"不限"场景
    if "不限" in req or "任意" in req or req == "":
        return 1.0

    # 检测首选科目
    has_physics = "物理" in req
    has_history = "历史" in req
    has_either = "物理或历史" in req or "首选不限" in req or "物理/历史" in req

    # 检测再选科目
    has_chemistry = "化学" in req
    has_biology = "生物" in req
    has_politics = "政治" in req
    has_geography = "地理" in req
    has_technology = "技术" in req

    # 计算再选要求数量（每增加一个硬性要求，稀缺度提升）
    reselect_required = sum([has_chemistry, has_biology, has_politics, has_geography, has_technology])

    # 基础占比：根据首选科目
    if has_either or (has_physics and has_history):
        base = 0.95  # 首选不限，几乎所有考生可报
    elif has_physics:
        base = 0.60  # 物理类约占60%
    elif has_history:
        base = 0.40  # 历史类约占40%
    else:
        # 未明确首选，根据用户科类推断
        base = 0.55 if user_subject_group == "物理类" else 0.35

    # 物化捆绑是关键门槛：要求化学的，物理类中约55%满足
    if has_physics and has_chemistry:
        base = min(base, 0.55)  # 物化捆绑约55%

    # 再选科目稀缺度系数（每增加一个硬性再选要求，占比乘以0.7）
    if reselect_required > 0:
        # 物理+化学+生物 ≈ 42%, 物理+化学+政治 ≈ 5%
        if has_chemistry and has_politics:
            base = min(base, 0.08)  # 物化政极稀缺
        elif has_chemistry and has_biology:
            base = min(base, 0.45)  # 物化生
        elif has_chemistry and has_geography:
            base = min(base, 0.20)  # 物化地
        elif has_chemistry:
            base = min(base, 0.55)  # 仅物化
        elif has_politics and has_history:
            base = min(base, 0.30)  # 史政
        elif has_politics:
            base = min(base, 0.25)
        elif has_biology:
            base = min(base, 0.50)
        elif has_geography:
            base = min(base, 0.35)

    return max(0.02, min(1.0, base))


# ═══════════════════════════════════════════════════════════════
#  估值模型
# ═══════════════════════════════════════════════════════════════

# ── 专业热度系数（基于历年报考热度，热度越高分数线越高） ──
MAJOR_HOTNESS: Dict[str, float] = {
    # 高热度（分数线溢价 +5~+15分）
    "计算机": 1.03, "软件": 1.03, "人工智能": 1.05, "数据": 1.02,
    "临床": 1.04, "口腔": 1.05, "电气": 1.02, "电子": 1.02,
    "金融": 1.03, "会计": 1.01, "法学": 1.02, "通信": 1.01,
    # 中热度（基准）
    "机械": 1.00, "自动化": 1.01, "数学": 1.00, "统计": 1.00,
    "经济": 0.99, "管理": 0.98, "教育": 0.97, "英语": 0.97,
    "建筑": 0.99, "车辆": 0.99, "信息": 1.00,
    # 低热度（分数线折价 -3~-10分）
    "土木": 0.95, "农学": 0.93, "园艺": 0.92, "动物": 0.93,
    "护理": 0.93, "环境": 0.95, "材料": 0.96, "矿业": 0.92,
    "冶金": 0.92, "化学": 0.96, "生物": 0.97, "哲学": 0.94,
    "历史": 0.95, "音乐": 0.93, "美术": 0.93, "翻译": 0.97,
    "针灸": 0.94, "中药": 0.95, "学前": 0.94, "工商": 0.98,
}


def _get_major_hotness(major_name: str) -> float:
    """根据专业名计算热度系数。"""
    if not isinstance(major_name, str):
        return 1.0
    hotness = 1.0
    match_count = 0
    for kw, coeff in MAJOR_HOTNESS.items():
        if kw in major_name:
            hotness *= coeff
            match_count += 1
    if match_count == 0:
        return 1.0
    # 多个关键词取几何平均
    return hotness ** (1.0 / max(1, match_count))


def estimate_score_for_new_major(
    major_name: str,
    university_name: str,
    province: str,
    school_type: str,
    df_history: pd.DataFrame,
    new_campuses: List[dict],
) -> Optional[Dict[str, Any]]:
    """
    对新增专业预估分数线（V2：加入热度系数校准）。

    策略：
    1. 同大学同类专业的历史分，取中位数
    2. 无同大学数据时，同层次大学同类专业的历史分，取中位数
    3. 用专业热度系数校准（冷门专业向下修正，热门向上修正）
    4. 用大学在该省的平均分做锚定校准
    5. 如果是新校区，在估算分上乘以折价系数
    6. 置信区间：动态计算（样本标准差 × 1.5，至少 ±12 分）
    """
    if df_history is None or df_history.empty:
        return None

    keywords = _extract_major_keywords(major_name)
    if not keywords:
        return None

    pattern = "|".join(keywords)
    hotness = _get_major_hotness(major_name)

    # 0. 大学在该省的平均录取分（锚定基准），本省无分数则跨省
    uni_avg = df_history[
        (df_history["university_name"] == university_name)
        & (df_history["province"] == province)
        & (df_history["lowest_score"].notna())
    ]["lowest_score"].median()
    if pd.isna(uni_avg):
        # 跨省兜底
        uni_avg = df_history[
            (df_history["university_name"] == university_name)
            & (df_history["lowest_score"].notna())
        ]["lowest_score"].median()

    # 1. 同大学同类专业（跨省：本省优先，无分数则扩到全国）
    same_school = df_history[
        (df_history["university_name"] == university_name)
        & (df_history["province"] == province)
        & (df_history["major_name"].str.contains(pattern, regex=True, na=False))
        & (df_history["lowest_score"].notna())
    ]
    # 本省无分数 → 跨省查同校同类专业
    if len(same_school) < 3:
        same_school_all = df_history[
            (df_history["university_name"] == university_name)
            & (df_history["major_name"].str.contains(pattern, regex=True, na=False))
            & (df_history["lowest_score"].notna())
        ]
        if len(same_school_all) >= 3:
            same_school = same_school_all

    # 退化：专业关键词匹配不到（如历史数据是专业组级"专业组206"）
    # → 用同校所有专业组的分数兜底（取最低分，最容易上的）
    same_school_fallback = pd.DataFrame()
    if len(same_school) < 3:
        same_school_fallback = df_history[
            (df_history["university_name"] == university_name)
            & (df_history["province"] == province)
            & (df_history["lowest_score"].notna())
        ]
        if len(same_school_fallback) < 1:
            # 跨省兜底
            same_school_fallback = df_history[
                (df_history["university_name"] == university_name)
                & (df_history["lowest_score"].notna())
            ]

    sample_size = 0
    estimated = None
    source = ""
    std_dev = 15  # 默认标准差

    if len(same_school) >= 3:
        estimated = same_school["lowest_score"].median()
        std_dev = same_school["lowest_score"].std()
        if pd.isna(std_dev) or std_dev < 8:
            std_dev = 12
        sample_size = len(same_school)
        source = "同校同类专业(跨省)" if province not in same_school["province"].values else "同校同类专业"
    else:
        # 优先：同校专业组兜底（历史数据是专业组级，关键词匹配不到时）
        # 这比跨省同类专业更精准，应优先使用
        if len(same_school_fallback) >= 1:
            estimated = same_school_fallback["lowest_score"].min()
            std_dev = same_school_fallback["lowest_score"].std()
            if pd.isna(std_dev) or std_dev < 10:
                std_dev = 18  # 专业组级兜底不确定性更大
            sample_size = len(same_school_fallback)
            is_cross = province not in same_school_fallback["province"].values
            source = "同校专业组最低分(跨省)" if is_cross else "同校专业组最低分"
        else:
            # 2. 同层次大学同类专业（df_history 无 school_type 列时退化为同省同类）
            has_school_type = "school_type" in df_history.columns
            if has_school_type and school_type:
                school_tier = _get_school_tier(university_name, school_type)
                if school_tier <= 3:
                    tier_types = ["985", "211", "双一流"]
                    same_tier = df_history[
                        (df_history["province"] == province)
                        & (df_history["school_type"].isin(tier_types))
                        & (df_history["major_name"].str.contains(pattern, regex=True, na=False))
                        & (df_history["lowest_score"].notna())
                    ]
                else:
                    same_tier = df_history[
                        (df_history["province"] == province)
                        & (~df_history["school_type"].isin(["985", "211", "双一流"]))
                        & (df_history["major_name"].str.contains(pattern, regex=True, na=False))
                        & (df_history["lowest_score"].notna())
                    ]
            else:
                # 退化：无 school_type 信息，查同省所有同类专业（有分数的）
                same_tier = df_history[
                    (df_history["province"] == province)
                    & (df_history["major_name"].str.contains(pattern, regex=True, na=False))
                    & (df_history["lowest_score"].notna())
                ]

            # 同省无分数 → 跨省兜底：全国同类专业
            if len(same_tier) < 5:
                same_tier = df_history[
                    (df_history["major_name"].str.contains(pattern, regex=True, na=False))
                    & (df_history["lowest_score"].notna())
                ]

            if len(same_tier) >= 5:
                estimated = same_tier["lowest_score"].median()
                std_dev = same_tier["lowest_score"].std()
                if pd.isna(std_dev) or std_dev < 10:
                    std_dev = 15
                sample_size = len(same_tier)
                source = "全国同类专业(跨省兜底)" if len(same_tier) > 0 and province not in same_tier["province"].values else "同层次院校同类专业"

                # 用大学平均分做锚定校准
                if not pd.isna(uni_avg) and estimated is not None:
                    tier_avg = same_tier["lowest_score"].median()
                    uni_offset = uni_avg - tier_avg
                    # 如果该大学整体比同层次高/低，校准估值
                    if abs(uni_offset) > 10:
                        estimated = estimated + uni_offset * 0.5  # 半幅度校准
            else:
                return None

    if estimated is None or pd.isna(estimated):
        return None

    # 3. 热度系数校准
    if hotness != 1.0:
        estimated = estimated * hotness

    # 4. 大学锚定二次校准（确保不偏离大学定位太远）
    if not pd.isna(uni_avg):
        if estimated > uni_avg + 40:
            estimated = uni_avg + 40
        elif estimated < uni_avg - 40:
            estimated = uni_avg - 40

    # 5. 新校区折价
    campus = _match_new_campus(university_name, new_campuses)
    if campus:
        estimated = int(estimated * campus["discount_ratio"])
        std_dev = max(std_dev, 18)  # 新校区不确定性更大

    estimated = int(estimated)
    margin = max(12, int(std_dev * 1.5))

    return {
        "estimated_score": estimated,
        "confidence_range": (max(0, estimated - margin), min(750, estimated + margin)),
        "source": source,
        "sample_size": sample_size,
        "hotness_applied": hotness if hotness != 1.0 else None,
    }


# ═══════════════════════════════════════════════════════════════
#  六维评分
# ═══════════════════════════════════════════════════════════════

def calculate_leakage_score(
    candidate: Dict[str, Any],
    user_score: Optional[int],
    df_history: pd.DataFrame,
    new_campuses: List[dict],
) -> Dict[str, Any]:
    """
    对每个候选志愿计算 leakage_score（0-100 分），综合八个维度。

    维度权重：
    - 维度1：新增专业 (25)
    - 维度2：扩招幅度 (20)
    - 维度3：新校区折价 (20)
    - 维度4：纯净组 (15)
    - 维度5：选科稀缺度 (10)
    - 维度6：分数匹配度 (10)
    - 维度7：院校层次加成 (10) — 来源: 雪峰知识库模块十一
    - 维度8：就业稳定性加成 (10) — 来源: 雪峰知识库模块十三
    """
    # 延迟导入避免循环依赖
    from .career_knowledge import (
        get_university_alliance, get_employer_recognition,
        get_stable_career_for_major, get_major_recommendation,
        get_ai_impact_risk, INDUSTRY_SCHOOLS,
    )

    score = 0
    reasons = []
    opportunity_type = candidate.get("opportunity_type", "")

    # ── 维度1：新增专业 (权重 20) ──
    if opportunity_type == "新增专业":
        base_score = 20
        if candidate.get("estimated_score") is not None:
            base_score += 5
        # 如果是该大学内部新增（同校有其他专业历史）加分
        if candidate.get("_has_school_history"):
            base_score += 5
        score += base_score
        reasons.append("新增专业（首次招生，无历史竞争数据）")

    # ── 维度2：扩招幅度 (权重 25，提高因为扩招确定性高) ──
    if opportunity_type == "扩招专业":
        plan_prev = candidate.get("plan_count_prev", 0)
        plan_cur = candidate.get("plan_count", 0)
        if plan_prev and plan_cur:
            growth = plan_cur / plan_prev
            abs_growth = plan_cur - plan_prev
            if growth >= 3.0 and abs_growth >= 10:
                score += 25
                reasons.append(f"爆发扩招 {int((growth-1)*100)}%（+{abs_growth}人）→ 分数线大概率下降")
            elif growth >= 2.0:
                score += 20
                reasons.append(f"大幅扩招 {int((growth-1)*100)}%（+{abs_growth}人）")
            elif abs_growth >= 20:
                score += 18
                reasons.append(f"大量扩招 +{abs_growth}人")
            else:
                score += 12
                reasons.append(f"显著扩招 +{abs_growth}人")

    # ── 维度2.5：分数匹配 (权重 10，基础分，后续维度6会叠加分数匹配度) ──
    if opportunity_type == "分数匹配":
        score += 10
        reasons.append("分数匹配可达（用户分数在历史录取线范围内）")

    # ── 维度3：新校区折价 (权重 20) ──
    campus = _match_new_campus(candidate.get("university_name", ""), new_campuses)
    if campus:
        score += 20
        discount = int((1 - campus["discount_ratio"]) * 100)
        reasons.append(f"新校区首次招生，预计分数线比本部低约{discount}%")

    # ── 维度4：纯净组 (权重 15) ──
    if candidate.get("is_pure_group"):
        group_size = candidate.get("group_size", 0)
        if group_size == 1:
            score += 15
            reasons.append("独享专业组（无调剂风险）")
        else:
            score += 10
            reasons.append(f"纯净组（{group_size}个专业均无调剂风险）")

    # ── 维度5：选科稀缺度 (权重 10) ──
    scarcity = candidate.get("subject_scarcity")
    if scarcity is not None:
        if scarcity < 0.15:
            score += 10
            reasons.append(f"选科限制严格（仅约{int(scarcity * 100)}%考生可报）")
        elif scarcity < 0.30:
            score += 5
            reasons.append(f"选科有一定门槛（约{int(scarcity * 100)}%考生可报）")

    # ── 维度6：分数匹配度 (权重 30，最关键维度) ──
    # 有历史分的：直接用历史分判断
    lowest_hist = candidate.get("lowest_score_2025")
    if user_score is not None and lowest_hist is not None and not pd.isna(lowest_hist):
        gap = user_score - float(lowest_hist)
        if 0 <= gap <= 15:
            score += 30
            reasons.append(f"历史分{int(lowest_hist)}，用户{user_score}分，分差+{gap}（匹配度极高）")
        elif 16 <= gap <= 30:
            score += 20
            reasons.append(f"历史分{int(lowest_hist)}，用户{user_score}分，分差+{gap}（稳过线）")
        elif -10 <= gap < 0:
            score += 10
            reasons.append(f"历史分{int(lowest_hist)}，用户{user_score}分，差{abs(gap)}分（可冲刺）")
        elif gap < -10:
            score -= 30  # 惩罚：大概率上不了
            reasons.append(f"历史分{int(lowest_hist)}，用户{user_score}分，差{abs(gap)}分（难度较大）")
    # 无历史分的（新增专业）：用估值
    elif user_score is not None and candidate.get("estimated_score") is not None:
        est = candidate["estimated_score"]
        gap = user_score - est
        if 0 <= gap <= 20:
            score += 25
            reasons.append(f"估分{est}分，用户{user_score}分，分差+{gap}（过线概率大）")
        elif -10 <= gap < 0:
            score += 10
            reasons.append(f"估分{est}分，用户{user_score}分，接近边缘（可尝试冲刺）")
        elif gap > 20:
            score += 15
            reasons.append(f"估分{est}分，用户{user_score}分，分差+{gap}（稳过线）")

    # ── 维度7：院校层次加成 (权重 10) — 来源: 雪峰知识库模块十一 ──
    uni_name = candidate.get("university_name", "")
    if uni_name:
        # 查用人单位认可度星级
        star = get_employer_recognition(uni_name)
        if star:
            star_map = {"十星": 10, "九星": 8, "八星": 6, "七星": 4, "六星": 3}
            bonus = star_map.get(star, 0)
            if bonus > 0:
                score += min(bonus, 10)
                reasons.append(f"用人单位认可度{star}（院校层次加成+{min(bonus, 10)}）")
        else:
            # 查行业对口强校
            for industry, schools in INDUSTRY_SCHOOLS.items():
                for school in schools:
                    if school in uni_name or uni_name in school:
                        score += 5
                        reasons.append(f"行业对口强校（{industry}方向，+5）")
                        break
                else:
                    continue
                break
            # 查院校联盟
            else:
                alliances = get_university_alliance(uni_name)
                if alliances:
                    score += 4
                    reasons.append(f"名校联盟成员（{', '.join(alliances[:2])}，+4）")

    # ── 维度8：就业稳定性加成 (权重 10) — 来源: 雪峰知识库模块十三 ──
    # 同时评估：稳定就业路径加分 + 不推荐/AI风险扣分
    major_name = candidate.get("major_name", "")
    if major_name:
        stable_paths = get_stable_career_for_major(major_name)
        if stable_paths:
            # 命中稳定就业路径 → 加分
            high_stability = [p for p in stable_paths if p["stability"] == "high"]
            if high_stability:
                score += 10
                path_names = [p["path"] for p in high_stability[:2]]
                reasons.append(f"对口稳定就业路径（{', '.join(path_names)}，+10）")
            else:
                score += 5
                path_names = [p["path"] for p in stable_paths[:2]]
                reasons.append(f"可对接就业路径（{', '.join(path_names)}，+5）")

        # 无论是否命中稳定路径，都检查不推荐和 AI 风险（可叠加扣分）
        rec = get_major_recommendation(major_name)
        if rec and rec["level"] == "not_recommended":
            score -= 8
            reasons.append(f"就业风险专业（{rec['category']}，-8）")
        ai_risk = get_ai_impact_risk(major_name)
        if ai_risk and ai_risk["risk"] == "high":
            score -= 5
            reasons.append(f"AI 替代风险高（{ai_risk['detail'][:30]}，-5）")

    # ── 额外：中外合作加分 (权重 15，捡漏确定性最高) ──
    if candidate.get("is_sino_foreign"):
        score += 15
        reasons.append("中外合作办学（学费高+单独代码，分数线显著低于普通专业）")

    # ── 额外：高收费加分 (权重 8) ──
    if candidate.get("is_high_tuition"):
        score += 8
        reasons.append(f"高收费专业（{candidate.get('tuition', '')}元/年，竞争较小）")

    # ── 额外：首招批次变更加分 (权重 10) ──
    if candidate.get("is_first_batch"):
        score += 10
        reasons.append("今年首次在本科批招生（往年仅在提前批/专项计划）")

    return {
        "leakage_score": max(0, min(score, 100)),
        "score_breakdown": reasons,
    }


# ═══════════════════════════════════════════════════════════════
#  纯净组过滤 V2
# ═══════════════════════════════════════════════════════════════

def _filter_pure_groups_v2(
    candidates: pd.DataFrame,
    cur_df: pd.DataFrame,
    risk_keywords: List[str],
) -> pd.DataFrame:
    """
    V2 纯净组过滤器：

    规则：
    1. 组内全部专业中，高风险专业占比 ≤ 30% → 放行
    2. 组内全部专业中，含有高偏好专业（计算机/软件/临床/口腔/金融）→ 放行
    3. 组内只有 1 个专业（独享组）→ 放行
    4. 其余 → 剔除
    """
    major_col = cur_df["major_name"].fillna("")

    # 风险检测
    risk_pattern = "|".join(risk_keywords)
    has_risk_series = major_col.str.contains(risk_pattern, regex=True, na=False)

    # 高偏好检测
    high_pattern = "|".join(HIGH_PREFERENCE_KEYWORDS)
    has_high_series = major_col.str.contains(high_pattern, regex=True, na=False)

    # 按 (university_code, group_code) 聚类画像
    # 注意: group_size 用 "size" 而非 "count"，因为 count 不计 NaN，
    # 当 major_code 全为 NaN 时会得到 0，导致 group_size==1 放行规则失效
    group_stats = (
        cur_df.assign(
            _has_risk=has_risk_series,
            _has_high=has_high_series,
        )
        .groupby(["university_code", "group_code"], as_index=False)
        .agg(
            group_size=("major_code", "size"),
            risk_count=("_has_risk", "sum"),
            has_high_pref=("_has_high", "any"),
        )
    )
    group_stats["risk_ratio"] = group_stats["risk_count"] / group_stats["group_size"]

    # Merge 到候选集
    merged = pd.merge(
        candidates,
        group_stats,
        on=["university_code", "group_code"],
        how="left",
    )

    # 放行条件：风险占比 ≤ 30% OR 有高偏好专业 OR 组内只有 1 个专业
    safe_mask = (
        (merged["risk_ratio"] <= 0.3)
        | (merged["has_high_pref"])
        | (merged["group_size"] == 1)
    )

    # 保留画像列（用于后续评分和展示）
    # 不移除 group_size, risk_ratio 等，它们在后续处理中有用
    return merged[safe_mask].copy()


# ═══════════════════════════════════════════════════════════════
#  主函数
# ═══════════════════════════════════════════════════════════════

def find_leakage_opportunities(
    df_current_year: pd.DataFrame,
    df_last_year: pd.DataFrame,
    df_history: pd.DataFrame = None,
    new_campuses: List[dict] = None,
    user_province: str = "",
    user_subject: str = "",
    user_score: Optional[int] = None,
    user_subjects_detail: Optional[str] = None,
    risk_keywords: Optional[List[str]] = None,
    batch: Optional[str] = None,
    school_types: Optional[List[str]] = None,
    min_score: Optional[int] = None,
    max_score: Optional[int] = None,
    score_tolerance: int = 30,
) -> List[dict]:
    """
    寻找捡漏机会（V2 六维评分版）。

    Args:
        df_current_year:  当年招生计划 DataFrame
        df_last_year:     上年招生计划 DataFrame
        df_history:       历年录取数据 DataFrame（3年历史）
        new_campuses:     新校区字典列表
        user_province:    考生省份
        user_subject:     考生科类
        user_score:       用户分数（用于估分匹配）
        user_subjects_detail: 具体选科（用于稀缺度计算）
        risk_keywords:    自定义风险词列表
        batch:            批次过滤
        school_types:     院校类型过滤
        min_score:        分数区间下限
        max_score:        分数区间上限
        score_tolerance:  分数容差（默认 ±30 分）

    Returns:
        List[dict]: 安全候选集（含 leakage_score、estimated_score 等字段）
    """
    if risk_keywords is None:
        risk_keywords = DEFAULT_RISK_KEYWORDS
    if new_campuses is None:
        new_campuses = DEFAULT_NEW_CAMPUSES

    required_cols = [
        "province", "subject_group", "university_code", "university_name",
        "group_code", "major_code", "major_name", "plan_count",
    ]
    for col in required_cols:
        if col not in df_current_year.columns:
            raise ValueError(f"df_current_year 缺少必要列: {col}")
        if col not in df_last_year.columns:
            raise ValueError(f"df_last_year 缺少必要列: {col}")

    # ── 1. 省份 + 科类过滤 ──
    cur = df_current_year[
        (df_current_year["province"] == user_province)
        & (df_current_year["subject_group"] == user_subject)
    ].copy()

    prev = df_last_year[
        (df_last_year["province"] == user_province)
        & (df_last_year["subject_group"] == user_subject)
    ].copy()

    if cur.empty:
        return []

    # ── 2. 批次过滤 ──
    if batch is not None:
        if "batch" in cur.columns:
            cur = cur[cur["batch"] == batch].copy()
        if "batch" in prev.columns and not prev.empty:
            prev = prev[prev["batch"] == batch].copy()

    if cur.empty:
        return []

    # ── 3. 院校类型过滤 ──
    if school_types is not None and "school_type" in cur.columns:
        cur = cur[cur["school_type"].isin(school_types)].copy()
        if not prev.empty and "school_type" in prev.columns:
            prev = prev[prev["school_type"].isin(school_types)].copy()

    if cur.empty:
        return []

    # ── 4. 分数区间过滤 ──
    # 用 lowest_score_2025（有则精确）或 estimated_score（估值）作为过滤依据
    # 同时保留无分数的行（新增专业等），让估值模型后续处理
    if min_score is not None or max_score is not None:
        _min = min_score if min_score is not None else 0
        _max = max_score if max_score is not None else 750

        # 优先用 lowest_score_2025，否则用 estimated_score（如果有），都没有则放行
        if "lowest_score_2025" in cur.columns:
            score_col = cur["lowest_score_2025"]
        else:
            score_col = None

        keep_mask = pd.Series(True, index=cur.index)
        if score_col is not None:
            # 有分数的：在区间内保留
            has_score = score_col.notna()
            in_range = (score_col >= _min) & (score_col <= _max)
            keep_mask = has_score & in_range
            # 无分数的也保留（新增专业/估值专业）
            keep_mask = keep_mask | score_col.isna()
        cur = cur[keep_mask].copy()

    if cur.empty:
        return []

    # ── 4.5 用户分数适配层：基于历史分预估用户能否上 ──
    # 对有历史分的专业，如果历史分远高于用户分 → 直接排除
    if user_score is not None:
        # 建立学校名 → 最近一年最低分的映射（来自 admission_history）
        hist_score_map = {}
        if df_history is not None and not df_history.empty:
            recent_year = df_history["year"].max() if "year" in df_history.columns else None
            if recent_year is not None:
                df_hist_recent = df_history[df_history["year"] == recent_year]
            else:
                df_hist_recent = df_history
            for _, hrow in df_hist_recent.iterrows():
                uni_name = str(hrow.get("university_name", "")).strip()
                score_val = hrow.get("lowest_score", None)
                if uni_name and score_val is not None and not pd.isna(score_val):
                    prev_val = hist_score_map.get(uni_name)
                    if prev_val is None or float(score_val) < float(prev_val):
                        hist_score_map[uni_name] = float(score_val)

        def _user_can_reach(row):
            """预估用户是否能上这个专业组（双重检查：专业组级 + 学校级）"""
            # 检查1：plans_2026 自身的专业组级分数（最精确）
            plan_score = row.get("lowest_score_2025", None)
            if plan_score is not None and not pd.isna(plan_score):
                optimistic = float(plan_score) - score_tolerance  # 用 score_tolerance 替代硬编码
                if optimistic > user_score:
                    return False  # 专业组历史分太高，用户够不到
            # 检查2：admission_history 的学校级最低分（补充）
            uni_name = str(row.get("university_name", "")).strip()
            hist_score = hist_score_map.get(uni_name)
            if hist_score is not None and not pd.isna(hist_score):
                optimistic = float(hist_score) - score_tolerance
                if optimistic > user_score:
                    return False
            return True  # 保留（无历史分 → 新增专业 → 可能捡漏）

        reachable_mask = cur.apply(_user_can_reach, axis=1)
        cur = cur[reachable_mask].copy()

    if cur.empty:
        return []

    # ── 5. 构建联合主键 ──
    # 注意: fillna("") 避免 major_code 为 NaN 时 astype(str) 产生 "nan"/NaN
    # 导致所有行的 unique_key 相同，进而 merge 时产生笛卡尔积
    for col in ["university_code", "group_code", "major_code"]:
        cur[col] = cur[col].fillna("").astype(str)
        if not prev.empty:
            prev[col] = prev[col].fillna("").astype(str)

    cur["unique_key"] = (
        cur["university_code"] + "_" + cur["group_code"] + "_" + cur["major_code"]
    )
    if not prev.empty:
        prev["unique_key"] = (
            prev["university_code"] + "_" + prev["group_code"] + "_" + prev["major_code"]
        )

    # ── 6. 左连接：标记新增专业 ──
    if prev.empty:
        cur["plan_count_prev"] = None
        merged = cur
    else:
        # 如果 cur 已有 plan_count_prev 列（2026修复脚本回填的），先重命名避免冲突
        if "plan_count_prev" in cur.columns:
            cur = cur.rename(columns={"plan_count_prev": "plan_count_prev_fixed"})
        merged = pd.merge(
            cur,
            prev[["unique_key", "plan_count"]],
            on="unique_key",
            how="left",
            suffixes=("", "_prev"),
        )
        # merge 后 plan_count_prev 来自 prev，优先用修复脚本回填的值
        if "plan_count_prev_fixed" in merged.columns:
            merged["plan_count_prev"] = merged["plan_count_prev_fixed"]
            merged = merged.drop(columns=["plan_count_prev_fixed"])

    # 新增专业：上年不存在
    new_majors = merged[merged["plan_count_prev"].isna()].copy()

    # ── 噪音过滤：只保留同校有历史数据的新增专业 ──
    # 逻辑：该大学去年在广东招过生（prev中有记录），今年新开了专业组 → 真捡漏
    #       该大学去年根本没在广东招生 → 省外首次招生，不算捡漏
    if not prev.empty:
        schools_with_history = set(prev["university_code"].astype(str).unique())
        new_majors["_school_has_history"] = new_majors["university_code"].astype(str).isin(schools_with_history)
        new_majors = new_majors[new_majors["_school_has_history"]].copy()
        new_majors = new_majors.drop(columns=["_school_has_history"], errors="ignore")

    if not new_majors.empty:
        new_majors["opportunity_type"] = "新增专业"
        new_majors["reason"] = "本年首次招生，无历史竞争数据"

    # ── 7. 扩招专业：分级扩招（提高阈值减少噪音） ──
    expanded = pd.DataFrame()
    if not prev.empty:
        both_exist = merged[merged["plan_count_prev"].notna()].copy()
        # 扩招条件：增幅 ≥ 100%（翻倍）且绝对增量 ≥ 5人
        # 或者：增幅 ≥ 50% 且绝对增量 ≥ 20人（基数大）
        expanded = both_exist[
            (both_exist["plan_count_prev"] > 0)
            & (
                ((both_exist["plan_count"] >= both_exist["plan_count_prev"] * 2.0)
                 & ((both_exist["plan_count"] - both_exist["plan_count_prev"]) >= 5))
                | ((both_exist["plan_count"] >= both_exist["plan_count_prev"] * 1.5)
                   & ((both_exist["plan_count"] - both_exist["plan_count_prev"]) >= 20))
            )
        ].copy()
        if not expanded.empty:
            expanded["opportunity_type"] = "扩招专业"
            expanded["reason"] = expanded.apply(
                lambda row: (
                    f"计划数从 {int(row['plan_count_prev'])} 增至 {int(row['plan_count'])}"
                    f"（增幅 {int((row['plan_count'] / row['plan_count_prev'] - 1) * 100)}%）"
                ),
                axis=1,
            )

    # ── 8. 合并候选集 ──
    candidates_list = [new_majors]
    if not expanded.empty:
        candidates_list.append(expanded)

    candidates = pd.concat(candidates_list, ignore_index=True).drop_duplicates(
        subset=["unique_key"]
    )

    # ── 8.5 分数匹配机会：用户分数可达范围内的院校（第7种捡漏策略） ──
    # 逻辑：当用户提供分数时，额外纳入分数在 [user_score - score_tolerance, user_score + 15] 
    # 范围内的专业。这些是用户"踮脚能够到"或"稳过线"的院校，
    # 后续评分中会通过纯净组/选科稀缺/中外合作等维度筛选真正有捡漏价值的。
    if user_score is not None and "lowest_score_2025" in cur.columns:
        score_lower = user_score - score_tolerance
        score_upper = user_score + 15
        score_match = cur[
            cur["lowest_score_2025"].notna()
            & (cur["lowest_score_2025"] >= score_lower)
            & (cur["lowest_score_2025"] <= score_upper)
        ].copy()
        if not score_match.empty:
            # 排除已在 candidates 中的
            existing_keys = set(candidates["unique_key"].tolist())
            score_match = score_match[~score_match["unique_key"].isin(existing_keys)].copy()
            if not score_match.empty:
                score_match["opportunity_type"] = "分数匹配"
                score_match["reason"] = score_match.apply(
                    lambda row: f"历史分{int(row['lowest_score_2025'])}，用户{user_score}分，分数匹配可达",
                    axis=1,
                )
                # 确保 plan_count_prev 列存在（Step 6 可能将其重命名为 plan_count_prev_fixed）
                if "plan_count_prev" not in score_match.columns:
                    if "plan_count_prev_fixed" in score_match.columns:
                        score_match["plan_count_prev"] = score_match["plan_count_prev_fixed"]
                    else:
                        score_match["plan_count_prev"] = None
                candidates = pd.concat(
                    [candidates, score_match], ignore_index=True
                ).drop_duplicates(subset=["unique_key"])

    if candidates.empty:
        return []

    # ── 9. 纯净组过滤 V2 ──
    safe_candidates = _filter_pure_groups_v2(candidates, cur, risk_keywords)

    if safe_candidates.empty:
        return []

    # ── 10. 增强标注：中外合作、高收费、新校区、首招批次、选科稀缺 ──

    # 10a. 中外合作
    if "major_name" in safe_candidates.columns:
        safe_candidates["is_sino_foreign"] = safe_candidates["major_name"].apply(
            lambda x: _detect_sino_foreign(str(x))
        )
        # 对中外合作专业也加入候选（如果尚未在 candidates 中，但合并了数据）
        sino_extra = cur[
            cur["major_name"].apply(lambda x: _detect_sino_foreign(str(x)))
        ].copy()
        if not sino_extra.empty:
            sino_extra["unique_key"] = (
                sino_extra["university_code"] + "_" + sino_extra["group_code"] + "_" + sino_extra["major_code"]
            )
            existing_keys = set(safe_candidates["unique_key"].tolist())
            sino_new = sino_extra[~sino_extra["unique_key"].isin(existing_keys)].copy()
            if not sino_new.empty:
                sino_new["opportunity_type"] = "中外合作"
                sino_new["reason"] = "中外合作/高收费专业，报考人数少，分数线可能低"
                sino_new["plan_count_prev"] = None
                sino_new["is_sino_foreign"] = True  # 防止 concat 后 NaN→False
                # 纯净组过滤
                sino_safe = _filter_pure_groups_v2(sino_new, cur, risk_keywords)
                if not sino_safe.empty:
                    safe_candidates = pd.concat(
                        [safe_candidates, sino_safe], ignore_index=True
                    ).drop_duplicates(subset=["unique_key"])
                    # concat 后重新校准 is_sino_foreign（防止 NaN）
                    safe_candidates["is_sino_foreign"] = safe_candidates["major_name"].apply(
                        lambda x: _detect_sino_foreign(str(x))
                    )
    else:
        safe_candidates["is_sino_foreign"] = False

    # 10b. 高收费
    if "tuition" in safe_candidates.columns:
        safe_candidates["is_high_tuition"] = safe_candidates["tuition"].apply(
            lambda x: pd.notna(x) and x > 25000
        )
    else:
        safe_candidates["is_high_tuition"] = False

    # 10c. 新校区匹配
    safe_candidates["is_new_campus"] = safe_candidates["university_name"].apply(
        lambda x: _match_new_campus(x, new_campuses) is not None
    )
    safe_candidates["new_campus_info"] = safe_candidates["university_name"].apply(
        lambda x: _match_new_campus(x, new_campuses)
    )

    # 10d. 首招批次变更
    safe_candidates["is_first_batch"] = safe_candidates.apply(
        lambda row: _detect_first_batch(row, prev) if not prev.empty else False,
        axis=1,
    )

    # 10e. 选科稀缺度（省份自适应）
    if "subject_requirement" in safe_candidates.columns:
        safe_candidates["subject_scarcity"] = safe_candidates["subject_requirement"].apply(
            lambda x: _calc_subject_scarcity(x, user_subject, user_province)
        )
    else:
        safe_candidates["subject_scarcity"] = None

    # ── 11. 估值模型：为无历史分的候选预估分数 ──
    if df_history is not None and not df_history.empty:
        safe_candidates["_estimation"] = safe_candidates.apply(
            lambda row: estimate_score_for_new_major(
                major_name=str(row.get("major_name", "")),
                university_name=str(row.get("university_name", "")),
                province=user_province,
                school_type=str(row.get("school_type", "")),
                df_history=df_history,
                new_campuses=new_campuses,
            ) if pd.isna(row.get("lowest_score_2025")) else None,
            axis=1,
        )
        safe_candidates["estimated_score"] = safe_candidates["_estimation"].apply(
            lambda x: x["estimated_score"] if x else None
        )
        safe_candidates["confidence_range"] = safe_candidates["_estimation"].apply(
            lambda x: x["confidence_range"] if x else None
        )
        safe_candidates["estimation_source"] = safe_candidates["_estimation"].apply(
            lambda x: x["source"] if x else None
        )
    else:
        safe_candidates["estimated_score"] = None
        safe_candidates["confidence_range"] = None
        safe_candidates["estimation_source"] = None

    # ── 12. 六维评分 ──
    score_results = safe_candidates.apply(
        lambda row: calculate_leakage_score(
            candidate=row.to_dict(),
            user_score=user_score,
            df_history=df_history,
            new_campuses=new_campuses,
        ),
        axis=1,
    )
    safe_candidates["leakage_score"] = score_results.apply(lambda x: x["leakage_score"])
    safe_candidates["score_breakdown"] = score_results.apply(lambda x: x["score_breakdown"])

    # ── 13. 排序并返回 ──
    safe_candidates = safe_candidates.sort_values(
        by=["leakage_score", "plan_count"], ascending=[False, False]
    )

    # ── 14. 构建输出 ──
    output_cols = [
        "university_name", "major_name", "group_code",
        "plan_count", "opportunity_type", "reason",
        "leakage_score", "score_breakdown",
    ]

    # 附加字段
    for extra_col in [
        "lowest_score_2025", "lowest_rank_2025", "school_type", "batch",
        "estimated_score", "confidence_range", "estimation_source",
        "is_sino_foreign", "is_high_tuition", "is_new_campus",
        "is_first_batch", "subject_scarcity", "group_size",
        "tuition", "plan_count_prev", "university_code",
    ]:
        if extra_col in safe_candidates.columns:
            output_cols.append(extra_col)

    result = safe_candidates[output_cols].to_dict(orient="records")

    # 清洗：将 numpy 类型转为 Python 原生类型，nan → None
    # Pydantic v2 拒绝 nan 值给 Optional[int] 字段
    _numeric_cols = {
        "lowest_score_2025", "lowest_rank_2025", "plan_count_prev",
        "estimated_score", "tuition", "plan_count", "group_size",
        "leakage_score", "subject_scarcity",
    }
    for item in result:
        for k, v in list(item.items()):
            # NaN → None（Pydantic 兼容）
            if k in _numeric_cols and v is not None:
                try:
                    if pd.isna(v):
                        item[k] = None
                        continue
                except (TypeError, ValueError):
                    pass
            # numpy integer → Python int
            if isinstance(v, (np.integer,)):
                item[k] = int(v)
            elif isinstance(v, (np.floating,)):
                item[k] = None if np.isnan(v) else float(v)
            elif isinstance(v, np.ndarray):
                item[k] = v.tolist()
            elif isinstance(v, float) and np.isnan(v):
                item[k] = None
        # 处理 confidence_range
        cr = item.get("confidence_range")
        if cr is not None:
            if isinstance(cr, tuple):
                item["confidence_range"] = [
                    int(cr[0]) if cr[0] is not None and not pd.isna(cr[0]) else None,
                    int(cr[1]) if cr[1] is not None and not pd.isna(cr[1]) else None,
                ]
            elif isinstance(cr, list):
                item["confidence_range"] = [
                    int(x) if x is not None and not pd.isna(x) else None
                    for x in cr
                ]
        # 清理 score_breakdown（确保都是字符串）
        if "score_breakdown" in item and isinstance(item["score_breakdown"], np.ndarray):
            item["score_breakdown"] = item["score_breakdown"].tolist()

        # ── 数据可信度标注 (来源: 雪峰知识库模块八 T1-T4 分级) ──
        # lowest_score_2025 有值 → T1/T2 (官方录取数据)
        # estimated_score 有值 → T3 (估值模型，经验规律)
        # 都没有 → T4 (推测)
        if item.get("lowest_score_2025") is not None:
            item["data_trust_level"] = "T1"
            item["data_trust_desc"] = "官方录取数据（各省考试院/高校招生网）"
        elif item.get("estimated_score") is not None:
            item["data_trust_level"] = "T3"
            item["data_trust_desc"] = "估值模型（基于同校同类专业/同层次院校推算，属经验规律）"
        else:
            item["data_trust_level"] = "T4"
            item["data_trust_desc"] = "无精确数据参考（建议查询最新官方公告）"

    return result


# ═══════════════════════════════════════════════════════════════
#  兼容旧版接口（纯净组 V1 保留）
# ═══════════════════════════════════════════════════════════════

def _filter_pure_groups(
    candidates: pd.DataFrame,
    cur_df: pd.DataFrame,
    risk_keywords: List[str],
) -> pd.DataFrame:
    """旧版纯净组过滤器（向后兼容）。"""
    return _filter_pure_groups_v2(candidates, cur_df, risk_keywords)
