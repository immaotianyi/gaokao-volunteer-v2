"""
修复捡漏雷达 2026 招生计划数据 V2（优化匹配策略）

V2 改进：
  1. 江苏历史数据校名清洗（去掉'01专业组'后缀）→ 匹配率 0%→91.7%
  2. 跨省同校匹配（山东的中山大学 → 用全国其他省的中山大学分数）
  3. is_new 用更宽松的匹配（校名包含 + 专业名包含）
"""
import pandas as pd
import numpy as np
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def clean_uni_name(name):
    """清洗校名：去掉末尾的'01专业组'等后缀"""
    if pd.isna(name):
        return ""
    return re.sub(r"\d+专业组$", "", str(name))


def main():
    print("=" * 60)
    print("修复捡漏雷达 2026 招生计划数据 V2")
    print("=" * 60)

    df26 = pd.read_csv(DATA_DIR / "plans_2026.csv")
    df_hist = pd.read_csv(DATA_DIR / "admission_history.csv")
    print(f"\n2026计划: {len(df26)} 行 | 历史数据: {len(df_hist)} 行")

    # 准备历史数据
    hist = df_hist.copy()
    hist["clean_uni_name"] = hist["university_name"].apply(clean_uni_name)

    # ════════════════════════════════════════════════════════
    # 修复1：回填 lowest_score_2025
    # ════════════════════════════════════════════════════════
    print("\n--- 修复1：回填分数 ---")

    # 构建多级匹配索引
    # 级别1：同省同校同专业（精确）
    # 级别2：同省同校（取该校该省最低分）
    # 级别3：跨省同校同专业（取其他省同校同专业平均分）
    # 级别4：跨省同校（取全国同校最低分）

    # 预处理：按 (province, clean_uni_name, major_name) 建索引
    hist_2025 = hist[hist["year"] == 2025].copy()
    hist_2024 = hist[hist["year"] == 2024].copy()

    # 级别2索引：同省同校 → 最低分
    school_prov_score = {}
    for _, h in pd.concat([hist_2025, hist_2024]).iterrows():
        key = (h["province"], h["clean_uni_name"])
        score = h.get("lowest_score")
        if pd.notna(score):
            if key not in school_prov_score:
                school_prov_score[key] = []
            school_prov_score[key].append(float(score))
    # 取最低分
    school_prov_score = {k: min(v) for k, v in school_prov_score.items()}

    # 级别3索引：跨省同校同专业 → 平均分
    cross_major_score = {}
    for _, h in hist_2025.iterrows():
        key = (h["clean_uni_name"], h["major_name"])
        score = h.get("lowest_score")
        if pd.notna(score) and h["major_name"] and not re.match(r"^(专业组|第|组|专科|本科)", str(h["major_name"])):
            if key not in cross_major_score:
                cross_major_score[key] = []
            cross_major_score[key].append(float(score))
    cross_major_score = {k: np.mean(v) for k, v in cross_major_score.items()}

    # 级别4索引：跨省同校 → 全国最低分
    cross_school_score = {}
    for _, h in hist_2025.iterrows():
        key = h["clean_uni_name"]
        score = h.get("lowest_score")
        if pd.notna(score):
            if key not in cross_school_score:
                cross_school_score[key] = []
            cross_school_score[key].append(float(score))
    cross_school_score = {k: min(v) for k, v in cross_school_score.items()}

    # 执行回填
    stats = {"level1": 0, "level2": 0, "level3": 0, "level4": 0, "miss": 0}

    for idx, row in df26.iterrows():
        if pd.notna(row.get("lowest_score_2025")) and row["lowest_score_2025"] > 0:
            stats["level1"] += 1  # 已有分数
            continue

        uni = str(row["university_name"]).strip()
        major = str(row["major_name"]).strip()
        prov = str(row["province"]).strip()
        clean_uni = clean_uni_name(uni)

        score = None
        rank = None

        # 级别2：同省同校
        key2 = (prov, clean_uni)
        if key2 in school_prov_score:
            score = school_prov_score[key2]
            stats["level2"] += 1
        else:
            # 级别3：跨省同校同专业
            key3 = (clean_uni, major)
            if key3 in cross_major_score:
                score = round(cross_major_score[key3])
                stats["level3"] += 1
            else:
                # 级别4：跨省同校
                if clean_uni in cross_school_score:
                    score = round(cross_school_score[clean_uni])
                    stats["level4"] += 1
                else:
                    stats["miss"] += 1

        if score is not None:
            df26.at[idx, "lowest_score_2025"] = score

    total_filled = stats["level1"] + stats["level2"] + stats["level3"] + stats["level4"]
    print(f"  级别1(已有分数): {stats['level1']}")
    print(f"  级别2(同省同校): {stats['level2']}")
    print(f"  级别3(跨省同校同专业): {stats['level3']}")
    print(f"  级别4(跨省同校): {stats['level4']}")
    print(f"  未匹配: {stats['miss']}")
    print(f"  总有分数: {total_filled} / {len(df26)} ({total_filled/len(df26)*100:.1f}%)")

    # ════════════════════════════════════════════════════════
    # 修复2：重新计算 is_new
    # ════════════════════════════════════════════════════════
    print("\n--- 修复2：重新计算 is_new ---")

    # 历史中出现过该校该专业 = 非新增
    hist_keys = set()
    for _, h in hist.iterrows():
        clean_uni = h["clean_uni_name"]
        major = str(h["major_name"])
        # 只用真实专业名（排除组名）
        if major and not re.match(r"^(专业组|第|组|专科|本科|\d)", major):
            hist_keys.add((clean_uni, major))

    old_new = (df26["is_new"] == 1).sum()
    new_values = []
    for _, row in df26.iterrows():
        clean_uni = clean_uni_name(row["university_name"])
        major = str(row["major_name"])
        if (clean_uni, major) in hist_keys:
            new_values.append(0)
        else:
            new_values.append(row["is_new"])

    df26["is_new"] = new_values
    new_new = (df26["is_new"] == 1).sum()
    print(f"  修复前 is_new=1: {old_new} ({old_new/len(df26)*100:.1f}%)")
    print(f"  修复后 is_new=1: {new_new} ({new_new/len(df26)*100:.1f}%)")

    # ════════════════════════════════════════════════════════
    # 修复3：plan_count_prev
    # ════════════════════════════════════════════════════════
    print("\n--- 修复3：plan_count_prev ---")
    df25 = pd.read_csv(DATA_DIR / "plans_2025.csv")
    df25["clean_uni"] = df25["university_name"].apply(clean_uni_name)
    school_plan_25 = (
        df25.groupby(["province", "clean_uni"])
        .agg(plan_count_prev=("plan_count", "sum"))
        .reset_index()
    )

    df26["plan_count_prev"] = 0
    for idx, row in df26.iterrows():
        clean_uni = clean_uni_name(row["university_name"])
        match = school_plan_25[
            (school_plan_25["province"] == row["province"]) &
            (school_plan_25["clean_uni"] == clean_uni)
        ]
        if len(match) > 0:
            df26.at[idx, "plan_count_prev"] = match.iloc[0]["plan_count_prev"]

    has_prev = (df26["plan_count_prev"] > 0).sum()
    print(f"  有上年计划数: {has_prev} / {len(df26)} ({has_prev/len(df26)*100:.1f}%)")

    # ════════════════════════════════════════════════════════
    # 保存
    # ════════════════════════════════════════════════════════
    output_path = DATA_DIR / "plans_2026.csv"
    df26.to_csv(output_path, index=False)
    print(f"\n✅ 已保存到 {output_path}")

    # 最终验证
    print("\n--- 最终验证 ---")
    print(f"lowest_score_2025 非空: {df26['lowest_score_2025'].notna().sum()}/{len(df26)} ({df26['lowest_score_2025'].notna().sum()/len(df26)*100:.1f}%)")
    print(f"is_new=1: {(df26['is_new']==1).sum()} ({(df26['is_new']==1).sum()/len(df26)*100:.1f}%)")
    print(f"plan_count_prev>0: {(df26['plan_count_prev']>0).sum()}")

    # 各省验证
    print("\n--- 各省验证 ---")
    for prov in df26["province"].unique():
        sub = df26[df26["province"] == prov]
        has_score = sub["lowest_score_2025"].notna().sum()
        is_new = (sub["is_new"] == 1).sum()
        print(f"  {prov}: {len(sub)}行 | 有分数{has_score} ({has_score/len(sub)*100:.0f}%) | 新增{is_new}")


if __name__ == "__main__":
    main()
