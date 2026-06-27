#!/usr/bin/env python3
"""检查 plans_2025 vs plans_2026 group_code 编码格式差异"""
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

p25 = pd.read_csv(DATA_DIR / "plans_2025.csv")
p26 = pd.read_csv(DATA_DIR / "plans_2026.csv")

gd25 = p25[p25["province"] == "广东"]
gd26 = p26[p26["province"] == "广东"]

print("=== plans_2025 广东 group_code 样本 ===")
for gc in gd25["group_code"].astype(str).unique()[:10]:
    row = gd25[gd25["group_code"].astype(str) == gc].iloc[0]
    print(f"  {gc:>15s} → {row['university_name']}")

print("\n=== plans_2026 广东 group_code 样本 ===")
for gc in gd26["group_code"].astype(str).unique()[:10]:
    row = gd26[gd26["group_code"].astype(str) == gc].iloc[0]
    print(f"  {gc:>15s} → {row['university_name']}")

# 检查是否有同一大学在两年中的 group_code 不同
print("\n=== 同一大学在两年中的 group_code 对比 ===")
common_unis = set(gd25["university_name"].unique()) & set(gd26["university_name"].unique())
print(f"  两年共有的大学数: {len(common_unis)}")
for uni in list(common_unis)[:8]:
    gc25 = gd25[gd25["university_name"] == uni]["group_code"].astype(str).unique()
    gc26 = gd26[gd26["university_name"] == uni]["group_code"].astype(str).unique()
    print(f"  {uni}:")
    print(f"    2025: {list(gc25)[:3]}")
    print(f"    2026: {list(gc26)[:3]}")
