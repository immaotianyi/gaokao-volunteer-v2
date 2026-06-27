#!/usr/bin/env python3
"""split_master_to_raw.py — 把当前主 CSV 按省份拆分到 data/raw/（#14 数据恢复辅助）

用途：#13 事故后，把当前损坏的主 CSV 按省份拆分到 raw，供 merge_all.py 重建。
这不是恢复完整数据，而是把现有数据隔离到分省 raw 文件，避免再并发写。

用法：
    python backend/scripts/split_master_to_raw.py           # 全量拆分
    python backend/scripts/split_master_to_raw.py --type yifenyiduan_2026  # 只拆分指定类型
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"

# 主 CSV → 类型 key 映射（与 merge_all.py 一致）
MASTER_FILES = {
    "plans_2026.csv": "plans_2026",
    "plans_2025.csv": "plans_2025",
    "plans_2024.csv": "plans_2024",
    "yifenyiduan_2024.csv": "yifenyiduan_2024",
    "yifenyiduan_2025.csv": "yifenyiduan_2025",
    "yifenyiduan_2026.csv": "yifenyiduan_2026",
    "admission_history.csv": "admission_history",
    "control_line_2024.csv": "control_line_2024",
    "control_line_2025.csv": "control_line_2025",
    "control_line_2026.csv": "control_line_2026",
}


def split_one(master_filename: str) -> int:
    """把一个主 CSV 按省份拆分到 raw。返回拆分出的省份数。"""
    master_path = DATA_DIR / master_filename
    if not master_path.exists():
        print(f"[split] ⚠ {master_filename} 不存在，跳过")
        return 0

    try:
        df = pd.read_csv(master_path, dtype=str)
    except Exception as e:
        print(f"[split] ⚠ 读取 {master_filename} 失败: {e}")
        return 0

    if df.empty:
        print(f"[split] ⚠ {master_filename} 为空，跳过")
        return 0

    if "province" not in df.columns:
        print(f"[split] ⚠ {master_filename} 缺少 province 列，跳过")
        return 0

    # 过滤空 province
    df = df[df["province"].fillna("").str.strip() != ""]
    if df.empty:
        print(f"[split] ⚠ {master_filename} 过滤空 province 后为空，跳过")
        return 0

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    provinces = df["province"].unique()
    count = 0
    for prov in provinces:
        prov_df = df[df["province"] == prov]
        raw_path = RAW_DIR / f"{prov}_{master_filename}"
        prov_df.to_csv(raw_path, index=False, encoding="utf-8-sig")
        print(f"[split]   {prov} → {raw_path.name} ({len(prov_df)} 行)")
        count += 1

    print(f"[split] {master_filename}: 拆分 {count} 个省份，总 {len(df)} 行")
    return count


def main():
    parser = argparse.ArgumentParser(description="把当前主 CSV 按省份拆分到 data/raw/")
    parser.add_argument("--type", default=None, help="只拆分指定类型（如 yifenyiduan_2026）")
    args = parser.parse_args()

    print("=" * 60)
    print("[split_master_to_raw] 把当前主 CSV 按省份拆分到 data/raw/")
    print(f"[split] DATA_DIR = {DATA_DIR}")
    print(f"[split] RAW_DIR = {RAW_DIR}")
    print("=" * 60)

    total_provinces = 0
    for master_filename, type_key in MASTER_FILES.items():
        if args.type and type_key != args.type:
            continue
        print(f"\n--- {master_filename} ---")
        total_provinces += split_one(master_filename)

    print(f"\n[split] 完成。共拆分 {total_provinces} 个省-类型文件。")
    print(f"[split] raw 目录现有文件：")
    if RAW_DIR.exists():
        for f in sorted(RAW_DIR.glob("*.csv")):
            print(f"  {f.name}")


if __name__ == "__main__":
    main()
