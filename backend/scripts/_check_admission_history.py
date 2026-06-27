"""统计 admission_history.csv 中广东数据的覆盖情况。"""
import pandas as pd
from pathlib import Path

CSV_PATH = Path("/Users/sanzhaibanniang/Claude/Projects/gaokao/backend/data/admission_history.csv")

df = pd.read_csv(CSV_PATH)
print(f"总行数: {len(df)}")
print(f"列名: {list(df.columns)}")
print(f"\n省份分布 (top 15):")
print(df["province"].value_counts().head(15))

gd = df[df["province"] == "广东"]
print(f"\n广东数据: {len(gd)} 行")
if len(gd) > 0:
    print(f"  年份分布: {gd['year'].value_counts().to_dict()}")
    print(f"  科类分布: {gd['subject_group'].value_counts().to_dict()}")
    print(f"  批次分布: {gd['batch'].value_counts().to_dict()}")
    print(f"  学校数: {gd['university_name'].nunique()}")
    print(f"  专业组数: {gd['group_code'].nunique() if 'group_code' in gd.columns else 'N/A'}")
    print(f"  有最低分: {gd['lowest_score'].notna().sum()}")
    print(f"  有最低位次: {gd['lowest_rank'].notna().sum()}")
    print(f"\n样本 (前 5 行):")
    print(gd.head().to_string())
