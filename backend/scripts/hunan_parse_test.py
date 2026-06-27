#!/usr/bin/env python3
"""用 pandas 解析湖南一分一段表 HTML，确认数据范围。"""
import pandas as pd
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "hunan_2026"

for name, sg in [("yifenyiduan_physics.html", "物理类"),
                 ("yifenyiduan_history.html", "历史类")]:
    p = RAW / name
    tables = pd.read_html(str(p), encoding="utf-8")
    print(f"\n=== {name} ({sg}) ===")
    print(f"  表格数量: {len(tables)}")
    for i, df in enumerate(tables):
        print(f"  表{i}: shape={df.shape}, 列={list(df.columns)}")
        print(df.head(5).to_string())
        print("  ...")
        print(df.tail(5).to_string())
        # 检查分数范围
        # 第一列是档分
        col = df.iloc[:, 0]
        # 转数字
        nums = pd.to_numeric(col, errors="coerce").dropna()
        if len(nums) > 0:
            print(f"  分数范围: {int(nums.min())} - {int(nums.max())}, 共 {len(nums)} 行")
