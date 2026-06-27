#!/usr/bin/env python3
"""捡漏雷达数据依赖完整性检查"""
import pandas as pd
from pathlib import Path
import json

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

print("=" * 70)
print("捡漏雷达数据依赖完整性检查")
print("=" * 70)

# 1. plans_2025.csv 是否存在（Step 6 新增专业挖掘依赖）
print("\n【1. plans_2025.csv】（新增专业挖掘依赖）")
p25 = DATA_DIR / "plans_2025.csv"
if p25.exists():
    df = pd.read_csv(p25)
    print(f"  ✅ 存在: {len(df)}行")
    print(f"  列: {list(df.columns)}")
    print(f"  省份分布: {df['province'].value_counts().to_dict()}")
    print(f"  科类分布: {df['subject_group'].value_counts().to_dict()}")
else:
    print(f"  ❌ 不存在！Step 6 新增专业挖掘将完全失效")

# 2. plans_2026.csv 字段填充率
print("\n【2. plans_2026.csv 字段填充率】")
p26 = DATA_DIR / "plans_2026.csv"
if p26.exists():
    df = pd.read_csv(p26)
    print(f"  总行数: {len(df)}")
    for col in df.columns:
        non_null = df[col].notna().sum()
        pct = non_null / len(df) * 100
        status = "✅" if pct >= 90 else "⚠️" if pct >= 50 else "❌"
        print(f"  {status} {col:25s}: {non_null:>5}/{len(df)} ({pct:.1f}%)")

# 3. admission_history.csv 字段填充率
print("\n【3. admission_history.csv 字段填充率】")
ah = DATA_DIR / "admission_history.csv"
if ah.exists():
    df = pd.read_csv(ah)
    print(f"  总行数: {len(df)}")
    for col in df.columns:
        non_null = df[col].notna().sum()
        pct = non_null / len(df) * 100
        status = "✅" if pct >= 90 else "⚠️" if pct >= 50 else "❌"
        print(f"  {status} {col:25s}: {non_null:>5}/{len(df)} ({pct:.1f}%)")

# 4. new_campuses.json
print("\n【4. new_campuses.json】（新校区折价依赖）")
nc = DATA_DIR / "new_campuses.json"
if nc.exists():
    data = json.loads(nc.read_text())
    print(f"  ✅ 存在: {len(data)} 条新校区")
    for item in data:
        print(f"    {item.get('campus','?')} (parent={item.get('parent','?')}, ratio={item.get('discount_ratio','?')})")
else:
    print(f"  ❌ 不存在！Step 10c 新校区检测将用默认3条")

# 5. plans_2025 vs plans_2026 字段差异
print("\n【5. plans_2025 vs plans_2026 字段差异】")
if p25.exists() and p26.exists():
    c25 = set(pd.read_csv(p25, nrows=0).columns)
    c26 = set(pd.read_csv(p26, nrows=0).columns)
    print(f"  2025独有: {c25 - c26}")
    print(f"  2026独有: {c26 - c25}")
    print(f"  共有: {c25 & c26}")

# 6. 广东2026计划的位次/分数覆盖
print("\n【6. 广东2026计划位次/分数覆盖】")
if p26.exists():
    df = pd.read_csv(p26)
    gd = df[df["province"] == "广东"]
    print(f"  广东2026计划: {len(gd)}行")
    print(f"  有lowest_score_2025: {gd['lowest_score_2025'].notna().sum()} ({gd['lowest_score_2025'].notna().mean()*100:.1f}%)")
    print(f"  有lowest_rank_2025: {gd['lowest_rank_2025'].notna().sum()} ({gd['lowest_rank_2025'].notna().mean()*100:.1f}%)")
    print(f"  有plan_count: {gd['plan_count'].notna().sum()} ({gd['plan_count'].notna().mean()*100:.1f}%)")
    print(f"  有tuition: {gd['tuition'].notna().sum()} ({gd['tuition'].notna().mean()*100:.1f}%)")
    print(f"  有school_type: {gd['school_type'].notna().sum()} ({gd['school_type'].notna().mean()*100:.1f}%)")
    print(f"  有major_category: {gd['major_category'].notna().sum()} ({gd['major_category'].notna().mean()*100:.1f}%)")
    if "subject_requirement" in gd.columns:
        print(f"  有subject_requirement: {gd['subject_requirement'].notna().sum()} ({gd['subject_requirement'].notna().mean()*100:.1f}%)")
    if "plan_count_prev" in gd.columns:
        print(f"  有plan_count_prev: {gd['plan_count_prev'].notna().sum()} ({gd['plan_count_prev'].notna().mean()*100:.1f}%)")
