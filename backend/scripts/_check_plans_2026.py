"""校验 plans_2026.csv 数据完整性 + 后端是否需要重启加载新数据。"""
import pandas as pd
from pathlib import Path

PLANS_CSV = Path("/Users/sanzhaibanniang/Claude/Projects/gaokao/backend/data/plans_2026.csv")
YIFENYIDUAN_2025 = Path("/Users/sanzhaibanniang/Claude/Projects/gaokao/backend/data/yifenyiduan_2025.csv")
YIFENYIDUAN_2026 = Path("/Users/sanzhaibanniang/Claude/Projects/gaokao/backend/data/yifenyiduan_2026.csv")
CONTROL_LINE_2026 = Path("/Users/sanzhaibanniang/Claude/Projects/gaokao/backend/data/control_line_2026.csv")

print("=== 1. plans_2026.csv 校验 ===")
df = pd.read_csv(PLANS_CSV)
print(f"行数: {len(df)}")
print(f"列名: {list(df.columns)}")
print(f"\n省份分布:")
print(df["province"].value_counts())
print(f"\n科类分布:")
print(df["subject_group"].value_counts())
print(f"\n批次分布:")
print(df["batch"].value_counts() if "batch" in df.columns else "无 batch 列")
print(f"\n关键字段空值统计:")
for col in ["university_code", "university_name", "group_code", "major_code", "plan_count", "lowest_score_2025", "lowest_rank_2025"]:
    if col in df.columns:
        n_missing = df[col].isna().sum()
        print(f"  {col}: 缺失 {n_missing}/{len(df)} ({100*n_missing/len(df):.1f}%)")
print(f"\n覆盖高校数: {df['university_name'].nunique()}")
print(f"覆盖专业组数: {df['group_code'].nunique() if 'group_code' in df.columns else 'N/A'}")

print(f"\n=== 2. 2026 一分一段表 ===")
df_y = pd.read_csv(YIFENYIDUAN_2026)
print(f"行数: {len(df_y)}")
print(f"科类分布: {df_y['subject_group'].value_counts().to_dict()}")
print(f"批次分布: {df_y['batch'].value_counts().to_dict()}")
print(f"年份分布: {df_y['year'].value_counts().to_dict()}")

print(f"\n=== 3. 2026 省控线 ===")
df_c = pd.read_csv(CONTROL_LINE_2026)
print(f"行数: {len(df_c)}")
phy_benke = df_c[(df_c["subject_group"]=="物理类") & (df_c["batch"]=="本科")]
his_benke = df_c[(df_c["subject_group"]=="历史类") & (df_c["batch"]=="本科")]
print(f"物理类本科线: {phy_benke['lowest_score'].iloc[0] if len(phy_benke)>0 else 'N/A'}")
print(f"历史类本科线: {his_benke['lowest_score'].iloc[0] if len(his_benke)>0 else 'N/A'}")

print(f"\n=== 4. 2025 一分一段表（旧插值数据）===")
df_25 = pd.read_csv(YIFENYIDUAN_2025)
print(f"行数: {len(df_25)}")
print(f"列名: {list(df_25.columns)}")
print(f"科类分布: {df_25['subject_group'].value_counts().to_dict()}")
