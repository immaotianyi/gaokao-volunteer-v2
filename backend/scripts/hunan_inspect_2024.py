#!/usr/bin/env python3
"""快速验证2024数据结构。"""
import pandas as pd
from pathlib import Path

RAW_2024 = Path(__file__).resolve().parent.parent / "data" / "raw" / "hunan_2024"

# 1. 2024 投档线 Excel
xlsx = RAW_2024 / "toudang_benke.xlsx"
print(f"=== 2024 投档线 Excel ===")
xls = pd.ExcelFile(xlsx)
print(f"  sheets: {xls.sheet_names}")
df = pd.read_excel(xlsx, sheet_name=xls.sheet_names[0], header=None)
print(f"  shape: {df.shape}")
print(df.iloc[2:5].to_string())  # 表头+前2行

# 2. 2024 一分一段表
for name, sg in [("yifenyiduan_physics.html", "物理"), ("yifenyiduan_history.html", "历史")]:
    p = RAW_2024 / name
    if not p.exists():
        continue
    tables = pd.read_html(str(p), encoding="utf-8")
    print(f"\n=== 2024 {sg} 一分一段表 ===")
    if tables:
        df = tables[0]
        print(f"  shape: {df.shape}, 列数: {df.shape[1]}")
        print(df.head(5).to_string())
        print("  ...")
        print(df.tail(3).to_string())
