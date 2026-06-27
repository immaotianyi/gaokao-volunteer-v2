"""分析 plans_2026.csv 中 lowest_rank_2025 缺失的原因。"""
import pandas as pd
from pathlib import Path

PLANS_CSV = Path("/Users/sanzhaibanniang/Claude/Projects/gaokao/backend/data/plans_2026.csv")
HISTORY_CSV = Path("/Users/sanzhaibanniang/Claude/Projects/gaokao/backend/data/admission_history.csv")

df = pd.read_csv(PLANS_CSV)
gd = df[df["province"] == "广东"].copy()
print(f"广东 2026 招生计划: {len(gd)} 行")

# 按 is_new 分组看 lowest_rank_2025 缺失情况
print(f"\n=== is_new vs lowest_rank_2025 缺失情况 ===")
print(gd.groupby("is_new")["lowest_rank_2025"].agg(["count", lambda x: x.isna().sum(), "size"]))

# 看 is_new=0 (老专业组) 但 lowest_rank_2025 缺失的样本
old_missing = gd[(gd["is_new"] == 0) & (gd["lowest_rank_2025"].isna())]
print(f"\n=== 老专业组(is_new=0) 但缺 rank 的: {len(old_missing)} 行 ===")
print(old_missing[["university_code", "university_name", "group_code", "major_code", "subject_group", "is_new"]].head(10).to_string())

# 看这些缺失 rank 的专业组在 admission_history 中是否能找到 2025 数据
print(f"\n=== 检查老专业组缺 rank 是否能在 admission_history 找到 2025 数据 ===")
hist = pd.read_csv(HISTORY_CSV)
gd_hist_2025 = hist[(hist["province"] == "广东") & (hist["year"] == 2025)]
print(f"admission_history 广东 2025 行数: {len(gd_hist_2025)}")

# 取前 5 个缺失 rank 的老专业组，看能不能匹配
sample_missing = old_missing.head(5)
for _, plan_row in sample_missing.iterrows():
    match = gd_hist_2025[
        (gd_hist_2025["university_code"] == plan_row["university_code"]) &
        (gd_hist_2025["group_code"] == plan_row["group_code"]) &
        (gd_hist_2025["subject_group"] == plan_row["subject_group"])
    ]
    if len(match) > 0:
        m = match.iloc[0]
        print(f"  [{plan_row['university_name'][:15]} 组{plan_row['group_code']}] "
              f"hist 找到 {len(match)} 行: score={m['lowest_score']} rank={m['lowest_rank']}")
    else:
        # 试 university_code + subject_group 模糊匹配（不含 group_code）
        loose_match = gd_hist_2025[
            (gd_hist_2025["university_code"] == plan_row["university_code"]) &
            (gd_hist_2025["subject_group"] == plan_row["subject_group"])
        ]
        print(f"  [{plan_row['university_name'][:15]} 组{plan_row['group_code']}] "
              f"hist 精确匹配 0 行, 模糊匹配 {len(loose_match)} 行（同校不同组）")
