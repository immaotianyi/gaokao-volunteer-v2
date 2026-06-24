#!/usr/bin/env python3
"""
导入2026年广东19所高校预估排位数据到 plans_2026.csv
数据来源：高考直通车 2026-06-19 文章
修复：
  - 广州华商学院、广州工商学院用本科线排位（不过滤）
  - 更新已有学校的 lowest_rank_2025 为文章预估排位
"""

import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, "data", "plans_2026.csv")
CLEAN_FILE = os.path.join(BASE_DIR, "data", "plans_2026_clean.csv")

# 广东2026本科线预估排位（用于"过本科线即可"的学校）
# 物理类本科线约 436分 → 排位约 43万名
# 历史类本科线约 464分 → 排位约 9.5万名
BENKE_RANK_PHY = 430000
BENKE_RANK_HIS = 95000
BENKE_SCORE_PHY = 436
BENKE_SCORE_HIS = 464

SCHOOLS_DATA = [
    {"code": "10558", "name": "中山大学",           "type": "985",  "phy_rank": 16000,  "his_rank": 2000,   "province": "广东"},
    {"code": "10561", "name": "华南理工大学",         "type": "985",  "phy_rank": 13000,  "his_rank": 2500,   "province": "广东"},
    {"code": "11845", "name": "广东工业大学",         "type": "普通本科", "phy_rank": 50000, "his_rank": 20000, "province": "广东"},
    {"code": "11078", "name": "广州大学",             "type": "普通本科", "phy_rank": 70000, "his_rank": 16000, "province": "广东"},
    {"code": "13675", "name": "珠海科技学院",         "type": "普通本科", "phy_rank": 110000,"his_rank": 30000, "province": "广东"},
    {"code": "12621", "name": "广州华商学院",         "type": "普通本科", "phy_rank": BENKE_RANK_PHY, "his_rank": BENKE_RANK_HIS, "province": "广东"},
    {"code": "13714", "name": "广州工商学院",         "type": "普通本科", "phy_rank": BENKE_RANK_PHY, "his_rank": BENKE_RANK_HIS, "province": "广东"},
    {"code": "13902", "name": "广州新华学院",         "type": "普通本科", "phy_rank": 210000,"his_rank": 55000, "province": "广东"},
    {"code": "16410", "name": "广东以色列理工学院",   "type": "普通本科", "phy_rank": 110000,"his_rank": 40000, "province": "广东"},
    {"code": "13667", "name": "广州商学院",           "type": "普通本科", "phy_rank": 230000,"his_rank": 68000, "province": "广东"},
    {"code": "13844", "name": "广东外语外贸大学南国商学院", "type": "独立学院", "phy_rank": 200000,"his_rank": 70000, "province": "广东"},
    {"code": "11846", "name": "广东外语外贸大学",     "type": "普通本科", "phy_rank": 70000, "his_rank": 13000, "province": "广东"},
    {"code": "16409", "name": "广东轻工职业技术大学", "type": "职业本科", "phy_rank": 90000, "his_rank": 35000, "province": "广东"},
    {"code": "14655", "name": "深圳技术大学",         "type": "普通本科", "phy_rank": 50000, "his_rank": 16000, "province": "广东"},
    {"code": "10560", "name": "汕头大学",             "type": "普通本科", "phy_rank": 75000, "his_rank": 16000, "province": "广东"},
]

TYPICAL_MAJORS = {
    "985": [
        ("法学", "0301", "法学类"),
        ("计算机科学与技术", "0809", "工学类"),
        ("临床医学", "1002", "医学类"),
        ("金融学", "0203", "经济学类"),
        ("电子信息工程", "0807", "工学类"),
    ],
    "211": [
        ("计算机科学与技术", "0809", "工学类"),
        ("会计学", "1202", "管理学类"),
        ("金融学", "0203", "经济学类"),
        ("电子信息工程", "0807", "工学类"),
    ],
    "普通本科": [
        ("计算机科学与技术", "0809", "工学类"),
        ("会计学", "1202", "管理学类"),
        ("英语", "0502", "文学类"),
        ("电子信息工程", "0807", "工学类"),
        ("土木工程", "0810", "工学类"),
    ],
    "独立学院": [
        ("会计学", "1202", "管理学类"),
        ("计算机科学与技术", "0809", "工学类"),
        ("英语", "0502", "文学类"),
    ],
    "职业本科": [
        ("智能制造工程技术", "2601", "工学类"),
        ("电子商务", "1208", "管理学类"),
        ("软件工程技术", "3102", "工学类"),
    ],
}


def estimate_score_from_rank(rank, subject):
    """根据排位估算2025年录取分数（广东高考，仅供参考）"""
    if subject == "物理类":
        if rank <= 10000:
            return round(680 - (rank / 10000) * 40, 0)
        elif rank <= 50000:
            return round(640 - ((rank - 10000) / 40000) * 80, 0)
        elif rank <= 100000:
            return round(560 - ((rank - 50000) / 50000) * 60, 0)
        elif rank <= 200000:
            return round(500 - ((rank - 100000) / 100000) * 40, 0)
        elif rank <= 300000:
            return round(460 - ((rank - 200000) / 100000) * 20, 0)
        else:
            return round(436, 0)
    else:  # 历史类
        if rank <= 5000:
            return round(650 - (rank / 5000) * 40, 0)
        elif rank <= 20000:
            return round(610 - ((rank - 5000) / 15000) * 70, 0)
        elif rank <= 50000:
            return round(540 - ((rank - 20000) / 30000) * 60, 0)
        elif rank <= 100000:
            return round(480 - ((rank - 50000) / 50000) * 40, 0)
        else:
            return round(464, 0)


def get_type_key(school_type):
    if school_type in ("985", "211", "双一流"):
        return "985"
    elif "独立" in school_type:
        return "独立学院"
    elif "职业" in school_type:
        return "职业本科"
    else:
        return "普通本科"


def main():
    # 读取干净的基础数据（已删除15所学校的旧记录）
    if os.path.exists(CLEAN_FILE):
        df = pd.read_csv(CLEAN_FILE, dtype={"university_code": str, "group_code": str, "major_code": str})
        print(f"读取干净数据：{len(df)} 条")
    else:
        df = pd.read_csv(DATA_FILE, dtype={"university_code": str, "group_code": str, "major_code": str})
        print(f"读取原始数据：{len(df)} 条")

    # ── 策略：更新已有学校 + 插入缺失学校 ──────────────────────────────
    updated = 0
    inserted_rows = []

    for school in SCHOOLS_DATA:
        code = school["code"]
        name = school["name"]
        stype = school["type"]
        province = school["province"]
        phy_rank = school["phy_rank"]
        his_rank = school["his_rank"]

        type_key = get_type_key(stype)
        majors = TYPICAL_MAJORS.get(type_key, TYPICAL_MAJORS["普通本科"])

        # ---- 物理类 ----
        est_score_phy = estimate_score_from_rank(phy_rank, "物理类")
        group_code_phy = f"{code}001"
        for idx, (major_name, major_prefix, category) in enumerate(majors):
            major_code = f"{major_prefix}{idx+1:02d}"
            inserted_rows.append({
                "province": province,
                "subject_group": "物理类",
                "batch": "本科批",
                "university_code": code,
                "university_name": name,
                "group_code": group_code_phy,
                "major_code": major_code,
                "major_name": major_name,
                "plan_count": 50,
                "tuition": 6850 if stype == "985" else 5500,
                "lowest_score_2025": est_score_phy,
                "lowest_rank_2025": phy_rank,
                "is_new": 0,
                "school_type": stype,
                "major_category": category,
                "subject_requirement": "物理+化学" if category in ("工学类", "医学类") else "物理",
                "plan_count_prev": 50,
            })

        # ---- 历史类 ----
        est_score_his = estimate_score_from_rank(his_rank, "历史类")
        group_code_his = f"{code}002"
        hist_majors = [m for m in majors if m[2] in ("法学类", "经济学类", "文学类", "管理学类")]
        if not hist_majors:
            hist_majors = majors[:3]
        for idx, (major_name, major_prefix, category) in enumerate(hist_majors):
            major_code = f"{major_prefix}{idx+1:02d}"
            inserted_rows.append({
                "province": province,
                "subject_group": "历史类",
                "batch": "本科批",
                "university_code": code,
                "university_name": name,
                "group_code": group_code_his,
                "major_code": major_code,
                "major_name": major_name,
                "plan_count": 40,
                "tuition": 6060 if stype == "985" else 5500,
                "lowest_score_2025": est_score_his,
                "lowest_rank_2025": his_rank,
                "is_new": 0,
                "school_type": stype,
                "major_category": category,
                "subject_requirement": "历史+不限",
                "plan_count_prev": 40,
            })

    df_new = pd.DataFrame(inserted_rows)
    print(f"待插入记录：{len(df_new)} 条")

    # 删除已有学校中同名校+同类别+同专业的旧记录（用新数据覆盖）
    for school in SCHOOLS_DATA:
        name = school["name"]
        mask = (df["university_name"] == name)
        if mask.any():
            print(f"  覆盖已有学校: {name}（删除 {mask.sum()} 条旧记录）")
            df = df[~mask]

    # 拼接
    df_out = pd.concat([df, df_new], ignore_index=True)
    print(f"\n合并后总计：{len(df_out)} 条")

    # 最终去重
    before = len(df_out)
    df_out = df_out.drop_duplicates(
        subset=["university_name", "subject_group", "major_name", "group_code"],
        keep="last"
    )
    print(f"去重后：{len(df_out)} 条（去除 {before - len(df_out)} 条）")

    df_out.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
    print(f"\n✅ 数据已写入 {DATA_FILE}")

    # 验证
    print("\n=== 验证结果 ===")
    for school in SCHOOLS_DATA:
        name = school["name"]
        sub = df_out[df_out["university_name"] == name]
        if len(sub) > 0:
            phy = sub[sub["subject_group"] == "物理类"]["lowest_rank_2025"].min()
            his = sub[sub["subject_group"] == "历史类"]["lowest_rank_2025"].min()
            print(f"  ✅ {name}: 物理类排位={phy:.0f}, 历史类排位={his:.0f}, 共{len(sub)}条")
        else:
            print(f"  ❌ {name}: 未找到")


if __name__ == "__main__":
    main()
