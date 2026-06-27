#!/usr/bin/env python3
"""检查 is_first_batch 误判：plans_2025 vs plans_2026 group_code 一致性"""
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

p25 = pd.read_csv(DATA_DIR / "plans_2025.csv")
p26 = pd.read_csv(DATA_DIR / "plans_2026.csv")

# 从 API 测试结果中提取的 group_code
test_groups = ["10566003", "12617002", "12617003", "10487001", "10559001", "10559003", "10590001"]

print("=== 测试结果中的 group_code 在 plans_2025 中是否存在 ===")
for gc in test_groups:
    in_25 = gc in p25["group_code"].astype(str).values
    in_26 = gc in p26["group_code"].astype(str).values
    print(f"  {gc}: plans_2025={'✅' if in_25 else '❌'}  plans_2026={'✅' if in_26 else '❌'}")

# 统计 plans_2026 广东的 group_code 有多少在 plans_2025 中
print("\n=== plans_2026 广东 group_code 覆盖率 ===")
gd26 = p26[p26["province"] == "广东"]
gd25 = p25[p25["province"] == "广东"] if "广东" in p25["province"].values else p25

gc_25 = set(gd25["group_code"].astype(str).unique())
gc_26 = set(gd26["group_code"].astype(str).unique())

overlap = gc_26 & gc_25
new_groups = gc_26 - gc_25
print(f"  plans_2025 广东 group_code 数: {len(gc_25)}")
print(f"  plans_2026 广东 group_code 数: {len(gc_26)}")
print(f"  交集（两年都有）: {len(overlap)}")
print(f"  2026新增专业组: {len(new_groups)}")
print(f"  覆盖率: {len(overlap)/len(gc_26)*100:.1f}%")

# 抽样查看几个新增专业组
if new_groups:
    print(f"\n  新增专业组抽样（前5个）:")
    for gc in list(new_groups)[:5]:
        rows = gd26[gd26["group_code"].astype(str) == gc]
        if not rows.empty:
            r = rows.iloc[0]
            print(f"    {gc} → {r['university_name']} ({r.get('batch','?')})")

# 检查 plans_2025 是否只有广东数据
print(f"\n=== plans_2025 省份分布 ===")
print(p25["province"].value_counts().to_dict())
print(f"\n=== plans_2026 省份分布 ===")
print(p26["province"].value_counts().to_dict())
