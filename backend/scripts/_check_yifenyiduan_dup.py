#!/usr/bin/env python3
"""快速校验 yifenyiduan_2026.csv 是否同一 (subject_group, score) 出现多行（多batch）"""
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

for year in [2025, 2026]:
    fp = DATA_DIR / f"yifenyiduan_{year}.csv"
    if not fp.exists():
        print(f"[{year}] 不存在: {fp}")
        continue
    df = pd.read_csv(fp)
    print(f"\n=== {year} ===")
    print(f"  总行数: {len(df)}")
    print(f"  列: {list(df.columns)}")
    print(f"  subject_group 唯一值: {df['subject_group'].unique().tolist()}")
    if "batch" in df.columns:
        print(f"  batch 唯一值: {df['batch'].unique().tolist()}")
        # 检查 (subject_group, score) 是否唯一
        dup = df.groupby(["subject_group", "score"]).size()
        dup_multi = dup[dup > 1]
        print(f"  (subject_group, score) 重复组数: {len(dup_multi)}")
        if len(dup_multi) > 0:
            print(f"  示例重复:")
            sg, sc = dup_multi.index[0]
            print(df[(df["subject_group"] == sg) & (df["score"] == sc)].to_string())
    else:
        # 检查 (subject_group, score) 是否唯一
        dup = df.groupby(["subject_group", "score"]).size()
        dup_multi = dup[dup > 1]
        print(f"  (subject_group, score) 重复组数: {len(dup_multi)}")
