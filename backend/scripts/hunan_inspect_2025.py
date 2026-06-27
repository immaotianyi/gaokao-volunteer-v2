#!/usr/bin/env python3
"""检查湖南2025投档线Excel结构 + 2025一分一段表。"""
import pandas as pd
from pathlib import Path

RAW_2025 = Path(__file__).resolve().parent.parent / "data" / "raw" / "hunan_2025"

# 1. 投档线 Excel
xlsx = RAW_2025 / "toudang_benke.xlsx"
print(f"=== 投档线 Excel: {xlsx.name} ===")
xls = pd.ExcelFile(xlsx)
print(f"  sheet_names: {xls.sheet_names}")
for sn in xls.sheet_names:
    df = pd.read_excel(xlsx, sheet_name=sn, header=None)
    print(f"\n  --- sheet: {sn} shape={df.shape} ---")
    print(df.head(8).to_string())
    print("  ...")
    print(df.tail(3).to_string())

# 2. 2025 一分一段表
for name, sg in [("yifenyiduan_physics.html", "物理类"),
                 ("yifenyiduan_history.html", "历史类")]:
    p = RAW_2025 / name
    if not p.exists():
        continue
    print(f"\n=== {name} ({sg}) ===")
    tables = pd.read_html(str(p), encoding="utf-8")
    print(f"  表格数: {len(tables)}")
    if tables:
        df = tables[0]
        print(f"  shape: {df.shape}")
        print(df.head(5).to_string())
        print("  ...")
        print(df.tail(3).to_string())
