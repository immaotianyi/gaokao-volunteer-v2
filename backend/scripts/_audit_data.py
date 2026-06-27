#!/usr/bin/env python3
"""盘点所有数据文件的覆盖情况，找出缺口"""
import pandas as pd
from pathlib import Path
from collections import Counter

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

print("=" * 70)
print("数据文件盘点")
print("=" * 70)

# 1. 一分一段表
print("\n【一分一段表 yifenyiduan_*.csv】")
for f in sorted(DATA_DIR.glob("yifenyiduan_*.csv")):
    df = pd.read_csv(f)
    year = f.stem.replace("yifenyiduan_", "")
    provs = df["province"].unique() if "province" in df.columns else []
    sgs = df["subject_group"].nunique() if "subject_group" in df.columns else 0
    has_batch = "batch" in df.columns
    print(f"  {f.name}: {len(df)}行, 年份={year}, 省份={list(provs)}, 科类数={sgs}, 有batch列={has_batch}")

# 2. 省控线
print("\n【省控线 control_line_*.csv】")
for f in sorted(DATA_DIR.glob("control_line_*.csv")):
    df = pd.read_csv(f)
    year = f.stem.replace("control_line_", "")
    provs = df["province"].unique() if "province" in df.columns else []
    batches = df["batch"].nunique() if "batch" in df.columns else 0
    print(f"  {f.name}: {len(df)}行, 年份={year}, 省份={list(provs)}, 批次数={batches}")

# 3. 投档历史
print("\n【投档历史 admission_history.csv】")
hist_fp = DATA_DIR / "admission_history.csv"
if hist_fp.exists():
    df = pd.read_csv(hist_fp)
    print(f"  总行数: {len(df)}")
    if "province" in df.columns and "year" in df.columns:
        pivot = df.groupby(["province", "year"]).size().unstack(fill_value=0)
        print(f"  省份×年份分布:")
        print(pivot.to_string())
    if "subject_group" in df.columns:
        print(f"  科类分布: {df['subject_group'].value_counts().to_dict()}")

# 4. 招生计划
print("\n【招生计划 plans_*.csv】")
for f in sorted(DATA_DIR.glob("plans_*.csv")):
    df = pd.read_csv(f)
    year = f.stem.replace("plans_", "")
    provs = df["province"].unique() if "province" in df.columns else []
    print(f"  {f.name}: {len(df)}行, 年份={year}, 省份={list(provs)}")
    if "province" in df.columns:
        for prov, cnt in df["province"].value_counts().items():
            has_rank = df[(df["province"]==prov) & df["lowest_rank_2025"].notna()].shape[0] if "lowest_rank_2025" in df.columns else 0
            print(f"    {prov}: {cnt}行 (有2025位次:{has_rank})")

# 5. 其他CSV
print("\n【其他CSV文件】")
known = {"yifenyiduan_2025.csv","yifenyiduan_2026.csv","control_line_2026.csv",
         "admission_history.csv","plans_2026.csv","risk_keywords.csv",
         "admission_plans.csv","user_profiles.csv","orders.csv","user_unlocks.csv"}
for f in sorted(DATA_DIR.glob("*.csv")):
    if f.name not in known and not f.name.startswith("admission"):
        df = pd.read_csv(f, nrows=2)
        print(f"  {f.name}: {sum(1 for _ in open(f))-1}行, 列={list(df.columns)[:6]}")

# 6. 原始数据目录
print("\n【原始数据目录 raw/】")
raw_dir = DATA_DIR / "raw"
if raw_dir.exists():
    for d in sorted(raw_dir.iterdir()):
        if d.is_dir():
            files = list(d.rglob("*"))
            file_count = len([f for f in files if f.is_file()])
            size_mb = sum(f.stat().st_size for f in files if f.is_file()) / 1024 / 1024
            print(f"  {d.name}/: {file_count}个文件, {size_mb:.1f}MB")
