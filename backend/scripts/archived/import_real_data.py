#!/usr/bin/env python3
"""
真实数据导入脚本 — 2026-ready 数据管道

用法：
  # 导入2025年真实招生计划 + 录取结果
  python3 backend/scripts/import_real_data.py --year 2025 --source ./data/raw/2025_plans.csv

  # 导入2024年真实招生计划 + 录取结果（用于训练估值模型）
  python3 backend/scripts/import_real_data.py --year 2024 --source ./data/raw/2024_plans.csv

  # 导入2026年招生计划（分数线待出，仅计划数据）
  python3 backend/scripts/import_real_data.py --year 2026 --source ./data/raw/2026_plans.csv --plans-only

CSV 格式要求（UTF-8）：
  province,subject_group,batch,university_code,university_name,
  group_code,major_code,major_name,plan_count,tuition,
  lowest_score_YYYY,lowest_rank_YYYY,  ← 录取结果（如有）
  school_type,major_category,
  subject_requirement,                  ← 选科要求（如"物理+化学"）
  notes                                  ← 备注（中外合作等）
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REQUIRED_COLS = [
    "province", "subject_group", "batch",
    "university_code", "university_name",
    "group_code", "major_code", "major_name",
    "plan_count", "tuition",
    "school_type",
]

OPTIONAL_COLS = [
    "lowest_score",      # 该年录取最低分
    "lowest_rank",       # 该年录取最低位次
    "major_category",    # 专业大类
    "subject_requirement",  # 选科要求
    "notes",             # 备注
    "is_new",            # 是否新增
]


def validate_and_clean(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """验证列完整性并清洗数据。"""
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"缺少必要列: {missing}")

    # 类型转换
    df["plan_count"] = pd.to_numeric(df["plan_count"], errors="coerce").fillna(0).astype(int)
    df["tuition"] = pd.to_numeric(df["tuition"], errors="coerce").fillna(5000).astype(int)

    # 字符串列标准化
    for col in ["university_code", "group_code", "major_code"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # 年份标记
    df["year"] = year

    # 录取分标准化（如果有）
    score_col = f"lowest_score_{year}"
    if "lowest_score" in df.columns:
        df[score_col] = pd.to_numeric(df["lowest_score"], errors="coerce")
        df = df.drop(columns=["lowest_score"], errors="ignore")
    elif score_col in df.columns:
        df[score_col] = pd.to_numeric(df[score_col], errors="coerce")

    rank_col = f"lowest_rank_{year}"
    if "lowest_rank" in df.columns:
        df[rank_col] = pd.to_numeric(df["lowest_rank"], errors="coerce")
        df = df.drop(columns=["lowest_rank"], errors="ignore")

    return df


def build_history_from_plans(
    plans_df: pd.DataFrame,
    year: int,
) -> pd.DataFrame:
    """
    从招生计划中提取历年录取数据，构建 admission_history.csv。

    输入：含 lowest_score_YYYY 列的招生计划
    输出：标准化的历年录取数据
    """
    score_col = f"lowest_score_{year}"
    rank_col = f"lowest_rank_{year}"

    if score_col not in plans_df.columns:
        print(f"  ⚠️  plans 中无 {score_col} 列，跳过历史数据构建")
        return pd.DataFrame()

    valid = plans_df[plans_df[score_col].notna()].copy()

    history = pd.DataFrame({
        "year": year,
        "province": valid["province"],
        "subject_group": valid["subject_group"],
        "university_code": valid["university_code"],
        "university_name": valid["university_name"],
        "group_code": valid["group_code"],
        "major_code": valid["major_code"],
        "major_name": valid["major_name"],
        "lowest_score": valid[score_col],
        "lowest_rank": valid[rank_col] if rank_col in valid.columns else np.nan,
        "school_type": valid.get("school_type", ""),
    })

    return history


def main():
    parser = argparse.ArgumentParser(description="导入真实招生计划数据")
    parser.add_argument("--year", type=int, required=True, help="数据年份 (2024/2025/2026)")
    parser.add_argument("--source", type=str, required=True, help="源CSV文件路径")
    parser.add_argument("--plans-only", action="store_true", help="仅导入计划数据（无录取结果）")
    parser.add_argument("--output-dir", type=str, default=None, help="输出目录")
    args = parser.parse_args()

    data_dir = Path(args.output_dir) if args.output_dir else Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{datetime.now().isoformat()}] 导入 {args.year} 年数据")
    print(f"  源文件: {args.source}")
    print(f"  输出目录: {data_dir}")

    # 读取
    df = pd.read_csv(args.source)
    print(f"  原始行数: {len(df)}")

    # 验证清洗
    df = validate_and_clean(df, args.year)
    print(f"  清洗后: {len(df)} 行")
    print(f"  省份: {sorted(df['province'].unique())}")
    print(f"  学校数: {df['university_name'].nunique()}")
    print(f"  批次: {sorted(df['batch'].dropna().unique())}")

    # 保存招生计划
    plan_path = data_dir / f"plans_{args.year}.csv"
    df.to_csv(plan_path, index=False)
    print(f"  ✅ 招生计划已保存: {plan_path}")

    # 构建历年录取数据（如果包含录取分）
    if not args.plans_only:
        history = build_history_from_plans(df, args.year)
        if not history.empty:
            # 合并到已有历史数据
            history_path = data_dir / "admission_history.csv"
            if history_path.exists():
                existing = pd.read_csv(history_path)
                # 去重：同年同省同校同专业只保留最新
                combined = pd.concat([existing, history], ignore_index=True)
                combined = combined.drop_duplicates(
                    subset=["year", "province", "university_code", "group_code", "major_code"],
                    keep="last",
                )
            else:
                combined = history

            combined.to_csv(history_path, index=False)
            print(f"  ✅ 历年录取数据已更新: {history_path} ({len(combined)} 行)")
        else:
            print(f"  ⚠️  无录取分数数据，跳过历史数据构建")

    # 打印数据摘要
    score_col = f"lowest_score_{args.year}"
    if score_col in df.columns and df[score_col].notna().sum() > 0:
        scores = df[score_col].dropna()
        print(f"\n  录取分统计:")
        print(f"    范围: {scores.min():.0f} - {scores.max():.0f}")
        print(f"    中位: {scores.median():.0f}")
        print(f"    覆盖率: {df[score_col].notna().sum()}/{len(df)}")

    print(f"\n[{datetime.now().isoformat()}] 导入完成")


if __name__ == "__main__":
    main()
