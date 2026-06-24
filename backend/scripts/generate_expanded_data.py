#!/usr/bin/env python3
"""
数据扩容生成脚本 — 基于现有 9 校 Demo 数据，生成 ≥5 省、≥30 校、≥3000 行的模拟招生计划数据

生成逻辑：
- 使用高校列表 + 典型专业列表 + 各省份科类组合
- 模拟 realistic 的计划数、学费、最低分/位次
- 输出 plans_2025_expanded.csv 和 plans_2026_expanded.csv

用法:
  python scripts/generate_expanded_data.py
"""
import csv
import random
import os
from pathlib import Path

random.seed(42)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ── 配置 ────────────────────────────────────────────────────────

PROVINCES = ["广东", "河南", "山东", "四川", "江苏"]
SUBJECT_GROUPS = ["物理类", "历史类"]
BATCHES = ["本科批", "专科批", "提前批"]

# ≥30 所大学的模拟数据
UNIVERSITIES = [
    # 985 (8所)
    ("10558", "中山大学", "985"),
    ("10561", "华南理工大学", "985"),
    ("10001", "北京大学", "985"),
    ("10003", "清华大学", "985"),
    ("10246", "复旦大学", "985"),
    ("10248", "上海交通大学", "985"),
    ("10335", "浙江大学", "985"),
    ("10486", "武汉大学", "985"),
    # 211 (10所)
    ("10574", "华南师范大学", "211"),
    ("10559", "暨南大学", "211"),
    ("10027", "北京师范大学", "211"),
    ("10269", "华东师范大学", "211"),
    ("10422", "山东大学", "211"),
    ("10284", "南京大学", "211"),
    ("10610", "四川大学", "211"),
    ("10487", "华中科技大学", "211"),
    ("10055", "南开大学", "211"),
    ("10213", "哈尔滨工业大学", "211"),
    # 双一流 (7所)
    ("10590", "深圳大学", "双一流"),
    ("11845", "广东工业大学", "双一流"),
    ("10564", "华南农业大学", "双一流"),
    ("11078", "广州大学", "双一流"),
    ("12121", "南方医科大学", "双一流"),
    ("10572", "广州中医药大学", "双一流"),
    ("10004", "北京交通大学", "双一流"),
    # 省属重点/普通本科/民办 (5所)
    ("10566", "广东海洋大学", "省属重点"),
    ("10570", "广州医科大学", "省属重点"),
    ("10592", "广东财经大学", "省属重点"),
    ("11819", "东莞理工学院", "普通本科"),
    ("12617", "广东培正学院", "民办"),
]

# 专业列表 (含大类)
MAJORS = [
    # 工学
    ("080901", "计算机科学与技术", "工学"),
    ("080902", "软件工程", "工学"),
    ("080703", "通信工程", "工学"),
    ("080717", "人工智能", "工学"),
    ("080907", "集成电路设计与集成系统", "工学"),
    ("080601", "电气工程及其自动化", "工学"),
    ("080202", "机械设计制造及其自动化", "工学"),
    ("080207", "车辆工程", "工学"),
    ("080213", "智能制造工程", "工学"),
    ("081001", "土木工程", "工学"),
    ("081002", "建筑环境与能源应用工程", "工学"),
    ("081003", "给排水科学与工程", "工学"),
    ("082801", "建筑学", "工学"),
    ("082502", "环境工程", "工学"),
    ("082503", "环境科学", "工学"),
    ("080903", "网络空间安全", "工学"),
    ("080904", "信息安全", "工学"),
    ("080905", "物联网工程", "工学"),
    ("080910", "数据科学与大数据技术", "工学"),
    # 理学
    ("070101", "数学与应用数学", "理学"),
    ("070201", "物理学", "理学"),
    ("071201", "统计学", "理学"),
    ("070301", "化学", "理学"),
    ("071001", "生物科学", "理学"),
    ("071002", "生物技术", "理学"),
    # 医学
    ("100201", "临床医学", "医学"),
    ("100301", "口腔医学", "医学"),
    ("100501", "中医学", "医学"),
    ("100502", "针灸推拿学", "医学"),
    ("100701", "药学", "医学"),
    ("100801", "中药学", "医学"),
    ("101101", "护理学", "医学"),
    ("100205", "精神医学", "医学"),
    # 管理学
    ("120203", "会计学", "管理学"),
    ("120201", "工商管理", "管理学"),
    ("120102", "信息管理与信息系统", "管理学"),
    # 经济学
    ("020101", "经济学", "经济学"),
    ("020301", "金融学", "经济学"),
    ("020401", "国际经济与贸易", "经济学"),
    # 文学
    ("050101", "汉语言文学", "文学"),
    ("050201", "英语", "文学"),
    ("050261", "翻译", "文学"),
    # 法学
    ("030101", "法学", "法学"),
    # 教育学
    ("040101", "教育学", "教育学"),
    ("040106", "学前教育", "教育学"),
    # 农学
    ("090101", "农学", "农学"),
    ("090102", "园艺", "农学"),
    ("090401", "动物医学", "农学"),
    ("082701", "食品科学与工程", "农学"),
    ("083001", "生物工程", "工学"),
    # 艺术学
    ("130202", "音乐学", "艺术学"),
    ("130401", "美术学", "艺术学"),
]

# 学费参考范围
TUITION_RANGES = {
    "工学": (5000, 8000),
    "理学": (5000, 7000),
    "医学": (6000, 9000),
    "管理学": (4500, 6500),
    "经济学": (4500, 6500),
    "文学": (4000, 6000),
    "法学": (4500, 6000),
    "教育学": (4000, 5500),
    "农学": (4000, 5500),
    "艺术学": (8000, 12000),
}


def generate_plans(year: int, output_path: str):
    """生成指定年份的招生计划 CSV"""
    header = [
        "province", "subject_group", "batch", "university_code",
        "university_name", "group_code", "major_code", "major_name",
        "plan_count", "tuition", "lowest_score_2025",
        "lowest_rank_2025", "is_new", "school_type", "major_category"
    ]
    
    rows = []
    
    for uni_code, uni_name, school_type in UNIVERSITIES:
        # 每所大学在每个省份都招生，但科类和专业可能不同
        for province in PROVINCES:
            for subject_group in SUBJECT_GROUPS:
                # 历史类跳过纯工学/理学/医学专业 (减少)
                if subject_group == "历史类":
                    available_majors = [
                        m for m in MAJORS
                        if m[2] in ("文学", "法学", "经济学", "管理学", "教育学", "艺术学")
                    ]
                    # 历史类大学数少一些
                    if random.random() < 0.2:
                        continue
                else:
                    available_majors = MAJORS
                
                # 每校每省每科类随机选 5-15 个专业
                num_majors = random.randint(5, min(15, len(available_majors)))
                selected_majors = random.sample(available_majors, num_majors)
                
                # 给这组专业分配 1-3 个专业组
                num_groups = min(random.randint(1, 3), num_majors)
                major_per_group = num_majors // num_groups
                
                for g in range(num_groups):
                    group_code = f"{uni_code}{g+1:03d}"
                    group_majors = selected_majors[
                        g * major_per_group : (g + 1) * major_per_group
                    ]
                    if g == num_groups - 1:
                        group_majors = selected_majors[g * major_per_group:]
                    
                    for major_code, major_name, major_cat in group_majors:
                        # 批次分配
                        if school_type in ("民办",) and random.random() < 0.3:
                            batch = "专科批"
                        elif random.random() < 0.05:
                            batch = "提前批"
                        else:
                            batch = "本科批"
                        
                        # 计划数
                        if school_type in ("985", "211"):
                            plan_count = random.randint(20, 100)
                        elif school_type == "双一流":
                            plan_count = random.randint(30, 120)
                        else:
                            plan_count = random.randint(15, 80)
                        
                        # 学费
                        t_min, t_max = TUITION_RANGES.get(major_cat, (4500, 6500))
                        tuition = random.randint(t_min // 500, t_max // 500) * 500
                        
                        # 模拟最低分/位次 (仅 2025 年数据有)
                        if year == 2025:
                            # 根据学校层次生成分数
                            base_score = {
                                "985": random.randint(620, 680),
                                "211": random.randint(580, 640),
                                "双一流": random.randint(540, 610),
                                "省属重点": random.randint(500, 570),
                                "普通本科": random.randint(460, 530),
                                "民办": random.randint(400, 480),
                            }.get(school_type, random.randint(450, 520))
                            
                            # 热门专业加分
                            hot_majors = ("计算机科学与技术", "软件工程", "人工智能",
                                         "临床医学", "口腔医学", "电气工程及其自动化")
                            if major_name in hot_majors:
                                base_score += random.randint(5, 20)
                            
                            lowest_score = base_score + random.randint(-10, 10)
                            lowest_rank = max(100, int(50000 * (750 - lowest_score) / 300
                                                        + random.randint(-2000, 2000)))
                        else:
                            lowest_score = ""
                            lowest_rank = ""
                        
                        # is_new: 先生成全部为0，后续通过后处理正确标记
                        is_new = "0"
                        
                        rows.append([
                            province,
                            subject_group,
                            batch,
                            uni_code,
                            uni_name,
                            group_code,
                            major_code,
                            major_name,
                            plan_count,
                            tuition,
                            lowest_score,
                            lowest_rank,
                            is_new,
                            school_type,
                            major_cat,
                        ])
    
    # 去重 (基于 province + subject_group + batch + university_code + group_code + major_code)
    seen = set()
    unique_rows = []
    for row in rows:
        key = (row[0], row[1], row[2], row[3], row[5], row[6])
        if key not in seen:
            seen.add(key)
            unique_rows.append(row)
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(unique_rows)
    
    print(f"[generate] {year} 年: {len(unique_rows)} 条记录 → {output_path}")
    return len(unique_rows)


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    
    n_2025 = generate_plans(2025, str(DATA_DIR / "plans_2025.csv"))
    n_2026 = generate_plans(2026, str(DATA_DIR / "plans_2026.csv"))
    
    # 后处理：正确标记 is_new（对比 2025 年数据）
    _mark_is_new(str(DATA_DIR / "plans_2025.csv"), str(DATA_DIR / "plans_2026.csv"))
    
    total = n_2025 + n_2026
    print(f"\n总计: {total} 条记录 (目标 ≥3000)")
    
    # 验证
    for year, path in [(2025, str(DATA_DIR / "plans_2025.csv")),
                        (2026, str(DATA_DIR / "plans_2026.csv"))]:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            provinces = set(r["province"] for r in rows)
            subjects = set(r["subject_group"] for r in rows)
            unis = set(r["university_name"] for r in rows)
            is_new_cnt = sum(1 for r in rows if r.get("is_new") == "1")
            print(f"  {year}: {len(rows)} 行, {len(provinces)} 省, "
                  f"{len(subjects)} 科类, {len(unis)} 大学, is_new={is_new_cnt}")
    
    if total >= 3000:
        print("\n✅ 数据量达标!")
    else:
        print(f"\n⚠️ 数据量 {total} < 3000，需要调整参数")


def _mark_is_new(path_2025: str, path_2026: str):
    """后处理：对比两年数据，正确标记 2026 年中的 is_new 字段"""
    with open(path_2025, "r", encoding="utf-8") as f:
        rows_2025 = list(csv.DictReader(f))
    
    with open(path_2026, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        rows_2026 = list(reader)
    
    # 构建 2025 年 unique_key 集合
    keys_2025 = set()
    for r in rows_2025:
        key = (r["province"], r["subject_group"], r["university_code"],
               r["group_code"], r["major_code"])
        keys_2025.add(key)
    
    # 标记新增
    new_count = 0
    for r in rows_2026:
        key = (r["province"], r["subject_group"], r["university_code"],
               r["group_code"], r["major_code"])
        if key not in keys_2025:
            r["is_new"] = "1"
            new_count += 1
    
    # 写回
    with open(path_2026, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows_2026)
    
    print(f"[is_new] 标记完成: {new_count} 个新增专业")


if __name__ == "__main__":
    main()
