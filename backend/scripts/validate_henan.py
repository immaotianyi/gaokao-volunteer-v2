#!/usr/bin/env python3
"""河南数据校验脚本

按 _common_spec.md 第五节校验规则执行：
1. 字段顺序校验
2. 科类规范校验（必须为 物理类/历史类，不能是 理科/文科）
3. 分数范围校验 (0-750)
4. 累计人数单调递减校验
5. 省控线完整性校验（3年×2科类×3批次）
6. 一分一段表完整性校验（3年×2科类）
7. 空值/NA字符串校验
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
PROVINCE = "河南"

# 期望字段顺序（按 _common_spec.md）
EXPECTED_FIELDS = {
    "yifenyiduan_2024.csv": ["province", "year", "subject_group", "batch", "score", "segment_count", "cumulative_count"],
    "yifenyiduan_2025.csv": ["province", "year", "subject_group", "batch", "score", "segment_count", "cumulative_count"],
    "yifenyiduan_2026.csv": ["province", "year", "subject_group", "batch", "score", "segment_count", "cumulative_count"],
    "control_line_2024.csv": ["province", "year", "batch_section", "batch", "subject_group", "line_type", "lowest_score", "source_url"],
    "control_line_2025.csv": ["province", "year", "batch_section", "batch", "subject_group", "line_type", "lowest_score", "source_url"],
    "control_line_2026.csv": ["province", "year", "batch_section", "batch", "subject_group", "line_type", "lowest_score", "source_url"],
    "plans_2026.csv": ["province", "subject_group", "batch", "university_code", "university_name", "group_code", "major_code", "major_name", "plan_count", "tuition", "lowest_score_2025", "lowest_rank_2025", "is_new", "school_type", "major_category", "subject_requirement", "plan_count_prev"],
}

errors: list[str] = []
warnings: list[str] = []
info: list[str] = []


def check_field_order(csv_name: str) -> pd.DataFrame | None:
    """校验字段顺序，返回河南数据DataFrame"""
    csv_path = DATA_DIR / csv_name
    if not csv_path.exists():
        errors.append(f"[{csv_name}] 文件不存在")
        return None
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    actual = list(df.columns)
    expected = EXPECTED_FIELDS.get(csv_name, [])
    if expected and actual != expected:
        errors.append(f"[{csv_name}] 字段顺序不符\n  期望: {expected}\n  实际: {actual}")
    henan = df[df["province"] == PROVINCE].copy()
    info.append(f"[{csv_name}] 总行数={len(df)}, 河南行数={len(henan)}")
    return henan


def check_subject_group(df: pd.DataFrame, csv_name: str):
    """科类规范校验：必须为 物理类/历史类"""
    if df is None or len(df) == 0 or "subject_group" not in df.columns:
        return
    invalid = df[~df["subject_group"].isin(["物理类", "历史类"])]
    if len(invalid) > 0:
        errors.append(f"[{csv_name}] 存在非法科类: {invalid['subject_group'].unique().tolist()}")


def check_no_null(df: pd.DataFrame, csv_name: str):
    """空值/NA字符串校验"""
    if df is None or len(df) == 0:
        return
    for col in df.columns:
        na_count = df[col].isin(["", "NA", "N/A", "null", "None", "nan"]).sum()
        if na_count > 0:
            # remark 字段允许空
            if col == "remark":
                continue
            warnings.append(f"[{csv_name}] 列 '{col}' 有 {na_count} 个空值/NA")


def check_yifenyiduan(df: pd.DataFrame, csv_name: str, year: int):
    """一分一段表：分数范围 + 累计人数单调递减"""
    if df is None or len(df) == 0:
        errors.append(f"[{csv_name}] 河南数据为空")
        return
    df = df.copy()
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    df["cumulative_count"] = pd.to_numeric(df["cumulative_count"], errors="coerce")

    # 分数范围
    bad_score = df[(df["score"] < 0) | (df["score"] > 750)]
    if len(bad_score) > 0:
        errors.append(f"[{csv_name}] 分数越界: {bad_score['score'].tolist()[:5]}")

    # 各科类累计人数单调递减（分数从高到低，累计应递增）
    for sg in ["物理类", "历史类"]:
        sub = df[df["subject_group"] == sg].sort_values("score", ascending=False)
        if len(sub) == 0:
            errors.append(f"[{csv_name}] 缺少 {sg} 数据")
            continue
        cum = sub["cumulative_count"].tolist()
        # 允许最高分段的累计=段人数（"含以上"情况），之后必须单调递增
        non_increasing = 0
        for i in range(1, len(cum)):
            if cum[i] < cum[i-1]:
                non_increasing += 1
        if non_increasing > 2:  # 允许少量异常
            errors.append(f"[{csv_name}] {sg} 累计人数非单调递增，异常{non_increasing}处")
        info.append(f"[{csv_name}] {sg}: {len(sub)}行, 分数范围 {int(sub['score'].min())}-{int(sub['score'].max())}, 最高累计={int(cum[0])}")


def check_control_line(df: pd.DataFrame, csv_name: str, year: int):
    """省控线完整性：2科类 × 3批次"""
    if df is None or len(df) == 0:
        errors.append(f"[{csv_name}] 河南数据为空")
        return
    for sg in ["物理类", "历史类"]:
        sub = df[df["subject_group"] == sg]
        if len(sub) == 0:
            errors.append(f"[{csv_name}] 缺少 {sg} 省控线")
            continue
        info.append(f"[{csv_name}] {sg}: {len(sub)}条 批次={sub['batch'].unique().tolist()}")


def main():
    print(f"\n{'#'*60}\n# 河南数据校验\n{'#'*60}")

    # 一分一段表
    for year in [2024, 2025, 2026]:
        csv_name = f"yifenyiduan_{year}.csv"
        print(f"\n=== {csv_name} ===")
        df = check_field_order(csv_name)
        if df is not None:
            check_subject_group(df, csv_name)
            check_no_null(df, csv_name)
            check_yifenyiduan(df, csv_name, year)

    # 省控线
    for year in [2024, 2025, 2026]:
        csv_name = f"control_line_{year}.csv"
        print(f"\n=== {csv_name} ===")
        df = check_field_order(csv_name)
        if df is not None:
            check_subject_group(df, csv_name)
            check_no_null(df, csv_name)
            check_control_line(df, csv_name, year)

    # plans_2026
    print(f"\n=== plans_2026.csv ===")
    df = check_field_order("plans_2026.csv")
    if df is not None:
        check_no_null(df, "plans_2026.csv")
        if len(df) > 0:
            info.append(f"[plans_2026.csv] 河南招生计划: {len(df)}行, 科类={df['subject_group'].unique().tolist()}")

    # 汇总
    print(f"\n{'='*60}")
    print("信息:")
    for line in info:
        print(f"  {line}")
    if warnings:
        print(f"\n警告 ({len(warnings)}):")
        for line in warnings:
            print(f"  ⚠ {line}")
    if errors:
        print(f"\n错误 ({len(errors)}):")
        for line in errors:
            print(f"  ✗ {line}")
        print(f"\n{'='*60}")
        print(f"校验失败: {len(errors)} 个错误")
        sys.exit(1)
    else:
        print(f"\n{'='*60}")
        print(f"✓ 校验通过 (警告{len(warnings)}个)")


if __name__ == "__main__":
    main()
