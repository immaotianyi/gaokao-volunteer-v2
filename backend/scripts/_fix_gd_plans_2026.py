"""#15 广东 plans_2026 恢复（378→≥1500 行）

方案：以广东 plans_2025（4970 行 per-group，1726 院校）为模板生成 plans_2026。
- plans_2025 和 plans_2026 字段完全一致（17 列）
- lowest_score_2025 / lowest_rank_2025 直接保留（2025 录取分作为 2026 计划参考）
- is_new = 0（2026 新增专业未知）
- plan_count_prev = plans_2025 的 plan_count（2025 计划数作为 2026 上一年参考）
- plan_count 保持不变（2026 实际计划数未公布，用 2025 预估）
- 从 admission_history 2025 年数据补充/更新 lowest_score_2025 / lowest_rank_2025

输出：data/raw/广东_plans_2026.csv（原子写）
"""
import os
import pandas as pd
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

print("=" * 60)
print("[#15] 广东 plans_2026 恢复")
print("=" * 60)

# 读取 plans_2025 作为模板
p25 = pd.read_csv(RAW / "广东_plans_2025.csv", dtype=str)
print(f"模板: 广东 plans_2025 = {len(p25)} 行, {p25['university_name'].nunique()} 院校")

# 读取 admission_history 2025 补充分数
ah = pd.read_csv(RAW / "广东_admission_history.csv", dtype=str)
ah_2025 = ah[(ah["province"] == "广东") & (ah["year"] == "2025")].copy()
print(f"admission_history 2025: {len(ah_2025)} 行（用于补充分数）")

# 构建分数查找表 (university_code, group_code, subject_group) → (lowest_score, lowest_rank)
ah_2025["lowest_score"] = pd.to_numeric(ah_2025["lowest_score"], errors="coerce")
ah_2025["lowest_rank"] = pd.to_numeric(ah_2025["lowest_rank"], errors="coerce")
score_lookup = ah_2025.groupby(["university_code", "group_code", "subject_group"]).agg({
    "lowest_score": "min",
    "lowest_rank": "min",
}).reset_index().rename(columns={"lowest_score": "score_ah", "lowest_rank": "rank_ah"})
print(f"分数查找表: {len(score_lookup)} 个 (university_code, group_code, subject_group) 组合")

# 复制 plans_2025 为 plans_2026
p26 = p25.copy()

# plan_count_prev = 原 plan_count（2025 计划数作为 2026 的上一年参考）
p26["plan_count_prev"] = p25["plan_count"]

# is_new = 0
p26["is_new"] = "0"

# 用 admission_history 2025 更新 lowest_score_2025 / lowest_rank_2025
p26_merge = p26.merge(
    score_lookup,
    on=["university_code", "group_code", "subject_group"],
    how="left",
)

# admission_history 有分数则用 ah 的，否则保留 plans_2025 原值
has_ah_score = p26_merge["score_ah"].notna()
p26_merge.loc[has_ah_score, "lowest_score_2025"] = p26_merge.loc[has_ah_score, "score_ah"].astype(str)
p26_merge.loc[has_ah_score, "lowest_rank_2025"] = p26_merge.loc[has_ah_score, "rank_ah"].astype(str)

p26_merge = p26_merge.drop(columns=["score_ah", "rank_ah"])

# 统计
updated = has_ah_score.sum()
print(f"从 admission_history 更新分数: {updated} 行")
print(f"保留 plans_2025 原分数: {len(p26_merge) - updated} 行")

# 空值处理
p26_merge = p26_merge.fillna("")

# 列顺序对齐 plans_2026 表头
cols = ["province", "subject_group", "batch", "university_code", "university_name",
        "group_code", "major_code", "major_name", "plan_count", "tuition",
        "lowest_score_2025", "lowest_rank_2025", "is_new", "school_type",
        "major_category", "subject_requirement", "plan_count_prev"]
p26_merge = p26_merge[cols]

print(f"\n恢复后: {len(p26_merge)} 行, {p26_merge['university_name'].nunique()} 院校")
print(f"按 subject_group:")
print(p26_merge.groupby("subject_group").size().to_string())

# 原子写
out_path = RAW / "广东_plans_2026.csv"
tmp = out_path.with_suffix(".csv.tmp")
p26_merge.to_csv(tmp, index=False, encoding="utf-8-sig")
os.replace(tmp, out_path)
print(f"\n✅ 已写入 {out_path.name}: {len(p26_merge)} 行（以 plans_2025 为模板 + admission_history 补充分数）")
