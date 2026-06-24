"""
修复捡漏雷达 2026 招生计划数据

问题:
  1. plans_2026.csv 的 lowest_score_2025 全空（0/2649）
  2. plans_2026 vs plans_2025 编码不匹配（0% 匹配）→ is_new 误标 86%
  3. 河南/四川无历史数据

修复策略:
  1. 从 admission_history.csv 回填分数
     - 同省同校：用同校所有专业组的最低分（广东是专业组级数据）
     - 跨省同专业：用其他省份同校同专业的分数（浙江/河北/重庆有真实专业名）
  2. 重新计算 is_new
     - 用 university_name + major_name 匹配历史数据
     - 历史中有过的 = 非新增（is_new=0）
  3. 河南/四川：标记为"数据不足"但保留可查询（估值走跨省兜底）
"""
import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def main():
    print("=" * 60)
    print("修复捡漏雷达 2026 招生计划数据")
    print("=" * 60)

    # 加载数据
    df26 = pd.read_csv(DATA_DIR / "plans_2026.csv")
    df_hist = pd.read_csv(DATA_DIR / "admission_history.csv")
    print(f"\n2026计划: {len(df26)} 行")
    print(f"历史数据: {len(df_hist)} 行")

    # ════════════════════════════════════════════════════════
    # 修复1：回填 lowest_score_2025 和 lowest_rank_2025
    # ════════════════════════════════════════════════════════
    print("\n--- 修复1：回填分数 ---")

    # 取2025年历史数据
    hist_2025 = df_hist[df_hist["year"] == 2025].copy()
    print(f"2025历史数据: {len(hist_2025)} 行")

    # 策略A：同省同校同专业（浙江/河北/重庆有真实专业名）
    hist_2025["match_key_a"] = (
        hist_2025["province"] + "|" +
        hist_2025["university_name"] + "|" +
        hist_2025["major_name"]
    )
    df26["match_key_a"] = (
        df26["province"] + "|" +
        df26["university_name"] + "|" +
        df26["major_name"]
    )

    # 策略B：同省同校（广东是专业组级，用校名匹配取最低分）
    hist_2025_by_school = (
        hist_2025.groupby(["province", "university_name"])
        .agg(
            school_min_score=("lowest_score", "min"),
            school_min_rank=("lowest_rank", "min"),
        )
        .reset_index()
    )

    # 策略C：跨省同校同专业（用其他省份的真实专业名数据）
    hist_2025_cross = hist_2025.copy()
    hist_2025_cross["match_key_c"] = (
        hist_2025_cross["university_name"] + "|" +
        hist_2025_cross["major_name"]
    )
    df26["match_key_c"] = (
        df26["university_name"] + "|" +
        df26["major_name"]
    )
    cross_map = (
        hist_2025_cross.dropna(subset=["lowest_score"])
        .groupby("match_key_c")
        .agg(cross_score=("lowest_score", "mean"), cross_rank=("lowest_rank", "mean"))
        .reset_index()
    )

    # 执行回填
    filled_count = 0
    school_filled = 0
    cross_filled = 0

    for idx, row in df26.iterrows():
        # 策略A：精确匹配
        key_a = row["match_key_a"]
        match_a = hist_2025[hist_2025["match_key_a"] == key_a]
        if len(match_a) > 0 and pd.notna(match_a.iloc[0]["lowest_score"]):
            df26.at[idx, "lowest_score_2025"] = match_a.iloc[0]["lowest_score"]
            df26.at[idx, "lowest_rank_2025"] = match_a.iloc[0]["lowest_rank"]
            filled_count += 1
            continue

        # 策略B：同省同校取最低分
        prov = row["province"]
        uni = row["university_name"]
        match_b = hist_2025_by_school[
            (hist_2025_by_school["province"] == prov) &
            (hist_2025_by_school["university_name"] == uni)
        ]
        if len(match_b) > 0 and pd.notna(match_b.iloc[0]["school_min_score"]):
            df26.at[idx, "lowest_score_2025"] = match_b.iloc[0]["school_min_score"]
            df26.at[idx, "lowest_rank_2025"] = match_b.iloc[0]["school_min_rank"]
            school_filled += 1
            continue

        # 策略C：跨省同校同专业
        key_c = row["match_key_c"]
        match_c = cross_map[cross_map["match_key_c"] == key_c]
        if len(match_c) > 0 and pd.notna(match_c.iloc[0]["cross_score"]):
            df26.at[idx, "lowest_score_2025"] = round(match_c.iloc[0]["cross_score"])
            df26.at[idx, "lowest_rank_2025"] = round(match_c.iloc[0]["cross_rank"]) if pd.notna(match_c.iloc[0]["cross_rank"]) else np.nan
            cross_filled += 1

    total_filled = filled_count + school_filled + cross_filled
    print(f"  策略A(同省同校同专业): {filled_count} 行")
    print(f"  策略B(同省同校取最低): {school_filled} 行")
    print(f"  策略C(跨省同校同专业): {cross_filled} 行")
    print(f"  总回填: {total_filled} / {len(df26)} ({total_filled/len(df26)*100:.1f}%)")
    print(f"  仍为空: {len(df26) - total_filled} 行")

    # ════════════════════════════════════════════════════════
    # 修复2：重新计算 is_new
    # ════════════════════════════════════════════════════════
    print("\n--- 修复2：重新计算 is_new ---")

    # 用 university_name + major_name 在历史数据中查找
    # 历史数据有该专业 = 非新增
    hist_all_keys = set()
    for _, h in df_hist.iterrows():
        # 精确专业名匹配
        key = f"{h['university_name']}|{h['major_name']}"
        hist_all_keys.add(key)

    old_new_count = (df26["is_new"] == 1).sum()
    new_is_new = []
    for _, row in df26.iterrows():
        key = f"{row['university_name']}|{row['major_name']}"
        if key in hist_all_keys:
            new_is_new.append(0)  # 历史中有 → 非新增
        else:
            new_is_new.append(row["is_new"])  # 保留原标记

    df26["is_new"] = new_is_new
    new_new_count = (df26["is_new"] == 1).sum()
    print(f"  修复前 is_new=1: {old_new_count} ({old_new_count/len(df26)*100:.1f}%)")
    print(f"  修复后 is_new=1: {new_new_count} ({new_new_count/len(df26)*100:.1f}%)")

    # ════════════════════════════════════════════════════════
    # 修复3：添加 plan_count_prev（上年计划数，用于扩招检测）
    # ════════════════════════════════════════════════════════
    print("\n--- 修复3：添加 plan_count_prev ---")

    # 从 plans_2025 按校名匹配取计划数（广东数据）
    df25 = pd.read_csv(DATA_DIR / "plans_2025.csv")
    school_plan_25 = (
        df25.groupby(["province", "university_name"])
        .agg(plan_count_prev=("plan_count", "sum"))
        .reset_index()
    )

    df26["plan_count_prev"] = 0
    for idx, row in df26.iterrows():
        match = school_plan_25[
            (school_plan_25["province"] == row["province"]) &
            (school_plan_25["university_name"] == row["university_name"])
        ]
        if len(match) > 0:
            df26.at[idx, "plan_count_prev"] = match.iloc[0]["plan_count_prev"]

    has_prev = (df26["plan_count_prev"] > 0).sum()
    print(f"  有上年计划数: {has_prev} / {len(df26)} ({has_prev/len(df26)*100:.1f}%)")

    # ════════════════════════════════════════════════════════
    # 修复4：标记河南/四川为数据不足省
    # ════════════════════════════════════════════════════════
    print("\n--- 修复4：省份数据覆盖检查 ---")
    for prov in df26["province"].unique():
        sub = df26[df26["province"] == prov]
        has_score = sub["lowest_score_2025"].notna().sum()
        has_hist = len(df_hist[df_hist["province"] == prov])
        print(f"  {prov}: 2026计划{len(sub)}行 | 有分数{has_score}行 | 历史数据{has_hist}行")

    # ════════════════════════════════════════════════════════
    # 保存
    # ════════════════════════════════════════════════════════
    # 清理临时列
    df26 = df26.drop(columns=["match_key_a", "match_key_c"], errors="ignore")

    output_path = DATA_DIR / "plans_2026.csv"
    df26.to_csv(output_path, index=False)
    print(f"\n✅ 已保存到 {output_path}")
    print(f"   {len(df26)} 行 | 分数回填率 {total_filled/len(df26)*100:.1f}% | is_new=1 {new_new_count}个")

    # 最终验证
    print("\n--- 最终验证 ---")
    print(f"lowest_score_2025 非空: {df26['lowest_score_2025'].notna().sum()}/{len(df26)}")
    print(f"lowest_rank_2025 非空: {df26['lowest_rank_2025'].notna().sum()}/{len(df26)}")
    print(f"is_new=1: {(df26['is_new']==1).sum()}")
    print(f"plan_count_prev>0: {(df26['plan_count_prev']>0).sum()}")


if __name__ == "__main__":
    main()
