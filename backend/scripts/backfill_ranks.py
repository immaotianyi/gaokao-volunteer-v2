"""
回填 lowest_rank 字段：
1. plans_2026.csv 的 lowest_rank_2025（从 lowest_score_2025 + yifenyiduan_2025 反查）
2. admission_history.csv 的 lowest_rank（从 lowest_score + 对应年份的一分一段表反查）

仅回填广东数据（只有广东有一分一段表）。
"""
import pandas as pd
import numpy as np
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

def build_score_rank_map(year: int, subject_group: str) -> dict:
    """从一分一段表构建 score → rank 映射"""
    filepath = DATA / f"yifenyiduan_{year}.csv"
    if not filepath.exists():
        return {}
    df = pd.read_csv(filepath)
    # 只取本科批
    df = df[(df["subject_group"] == subject_group) & (df["batch"] == "本科")]
    if df.empty:
        return {}
    # 构建 score → cumulative_count 映射
    return dict(zip(df["score"], df["cumulative_count"]))

def score_to_rank(score, rank_map: dict) -> int | None:
    """从分数查位次（取最接近的分数段）"""
    if pd.isna(score) or not rank_map:
        return None
    score = int(score)
    # 精确匹配
    if score in rank_map:
        return rank_map[score]
    # 找最接近的分数（分数向下取，因为位次是累计的）
    lower_scores = [s for s in rank_map.keys() if s <= score]
    if lower_scores:
        best = max(lower_scores)
        return rank_map[best]
    return None

def backfill_plans_2026():
    """回填 plans_2026.csv 的 lowest_rank_2025"""
    print("=" * 60)
    print("回填 plans_2026.csv 的 lowest_rank_2025")
    print("=" * 60)

    df = pd.read_csv(DATA / "plans_2026.csv")
    before_non_null = df["lowest_rank_2025"].notna().sum()
    print(f"回填前: lowest_rank_2025 非空 {before_non_null}/{len(df)} ({before_non_null/len(df)*100:.1f}%)")

    # 构建广东 2025 一分一段表
    rank_map_physics = build_score_rank_map(2025, "物理类")
    rank_map_history = build_score_rank_map(2025, "历史类")
    print(f"  广东2025 物理类 score→rank 映射: {len(rank_map_physics)} 条")
    print(f"  广东2025 历史类 score→rank 映射: {len(rank_map_history)} 条")

    backfilled = 0
    for idx, row in df.iterrows():
        if pd.notna(row["lowest_rank_2025"]):
            continue  # 已有位次
        if pd.isna(row["lowest_score_2025"]):
            continue  # 无分数无法回填
        if row["province"] != "广东":
            continue  # 仅广东有一分一段表

        sg = row["subject_group"]
        rank_map = rank_map_physics if sg == "物理类" else rank_map_history
        rank = score_to_rank(row["lowest_score_2025"], rank_map)
        if rank is not None:
            df.at[idx, "lowest_rank_2025"] = rank
            backfilled += 1

    after_non_null = df["lowest_rank_2025"].notna().sum()
    print(f"回填 {backfilled} 行")
    print(f"回填后: lowest_rank_2025 非空 {after_non_null}/{len(df)} ({after_non_null/len(df)*100:.1f}%)")

    df.to_csv(DATA / "plans_2026.csv", index=False)
    print(f"✅ 已保存 plans_2026.csv")

def backfill_admission_history():
    """回填 admission_history.csv 的 lowest_rank"""
    print("\n" + "=" * 60)
    print("回填 admission_history.csv 的 lowest_rank")
    print("=" * 60)

    df = pd.read_csv(DATA / "admission_history.csv")
    before_non_null = df["lowest_rank"].notna().sum()
    print(f"回填前: lowest_rank 非空 {before_non_null}/{len(df)} ({before_non_null/len(df)*100:.1f}%)")

    # 构建各年份的一分一段表
    rank_maps = {}  # (year, subject_group) → rank_map
    for year in [2024, 2025]:
        for sg in ["物理类", "历史类"]:
            rm = build_score_rank_map(year, sg)
            if rm:
                rank_maps[(year, sg)] = rm
                print(f"  广东{year} {sg} score→rank 映射: {len(rm)} 条")

    # 广东数据用一分一段表回填
    gd_mask = df["province"] == "广东"
    gd_df = df[gd_mask]
    print(f"  广东数据: {len(gd_df)} 行")

    backfilled = 0
    for idx, row in gd_df.iterrows():
        if pd.notna(row["lowest_rank"]):
            continue
        if pd.isna(row["lowest_score"]):
            continue

        year = int(row["year"]) if pd.notna(row["year"]) else None
        sg = row["subject_group"]
        # 3+3 省份"综合"通配
        if sg == "综合":
            sg = "物理类"  # 默认用物理类

        key = (year, sg)
        if key not in rank_maps:
            continue

        rank = score_to_rank(row["lowest_score"], rank_maps[key])
        if rank is not None:
            df.at[idx, "lowest_rank"] = rank
            backfilled += 1

    after_non_null = df["lowest_rank"].notna().sum()
    print(f"回填 {backfilled} 行")
    print(f"回填后: lowest_rank 非空 {after_non_null}/{len(df)} ({after_non_null/len(df)*100:.1f}%)")

    df.to_csv(DATA / "admission_history.csv", index=False)
    print(f"✅ 已保存 admission_history.csv")

if __name__ == "__main__":
    backfill_plans_2026()
    backfill_admission_history()
    print("\n🎉 回填完成")
