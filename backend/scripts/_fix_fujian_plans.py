"""#16 福建 plans_2026 去重 + 聚合到 per-group 粒度

福建 raw 26864 行是 per-major（每个专业一行），需聚合到 per-group（每个专业组一行），
与广东/甘肃 plans_2025/2026 粒度一致。

聚合规则：
- groupby (province, subject_group, batch, university_code, university_name, group_code)
- plan_count 求和
- major_name = "{院校名}组{group_code}"（与广东格式一致）
- major_code = "{group_code}_001"（与广东格式一致）
- lowest_score_2025 / lowest_rank_2025 取 min（专业组最低分/位次）
- tuition / school_type / major_category / subject_requirement 取第一个非空
- is_new 取 max（有任一新专业则标 1）
- plan_count_prev 取求和
"""
import pandas as pd
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
FJ_RAW = RAW_DIR / "福建_plans_2026.csv"

print(f"读取 {FJ_RAW.name} ...")
df = pd.read_csv(FJ_RAW, dtype=str)
print(f"  原始: {len(df)} 行 (per-major)")

# 数值列转换
for col in ["plan_count", "plan_count_prev", "is_new"]:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
for col in ["lowest_score_2025", "lowest_rank_2025", "tuition"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# 聚合
group_cols = ["province", "subject_group", "batch", "university_code", "university_name", "group_code"]

agg = df.groupby(group_cols, as_index=False).agg({
    "plan_count": "sum",
    "tuition": lambda x: x.dropna().iloc[0] if not x.dropna().empty else "",
    "lowest_score_2025": "min",
    "lowest_rank_2025": "min",
    "is_new": "max",
    "school_type": lambda x: x.dropna().iloc[0] if not x.dropna().empty else "",
    "major_category": lambda x: x.dropna().iloc[0] if not x.dropna().empty else "",
    "subject_requirement": lambda x: x.dropna().iloc[0] if not x.dropna().empty else "",
    "plan_count_prev": "sum",
})

# 生成 major_name / major_code（与广东格式一致）
agg["major_name"] = agg["university_name"] + "组" + agg["group_code"]
agg["major_code"] = agg["group_code"] + "_001"

# 列顺序对齐 plans_2026 表头
cols = ["province", "subject_group", "batch", "university_code", "university_name",
        "group_code", "major_code", "major_name", "plan_count", "tuition",
        "lowest_score_2025", "lowest_rank_2025", "is_new", "school_type",
        "major_category", "subject_requirement", "plan_count_prev"]
agg = agg[cols]

# 空值处理
agg = agg.fillna("")
agg["plan_count"] = agg["plan_count"].astype(int)
agg["plan_count_prev"] = agg["plan_count_prev"].astype(int)
agg["is_new"] = agg["is_new"].astype(int)

print(f"  聚合后: {len(agg)} 行 (per-group)")
print(f"  unique (university_code, group_code): {agg.groupby(['university_code','group_code']).ngroups}")
print(f"  按 subject_group 分布:")
print(agg.groupby("subject_group").size().to_string())

# 原子写回 raw
tmp = FJ_RAW.with_suffix(".csv.tmp")
agg.to_csv(tmp, index=False, encoding="utf-8-sig")
import os
os.replace(tmp, FJ_RAW)
print(f"✅ 已写回 {FJ_RAW.name}: {len(agg)} 行（per-group）")
