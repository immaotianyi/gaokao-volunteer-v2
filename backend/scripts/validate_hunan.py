#!/usr/bin/env python3
"""湖南省高考数据校验脚本。

校验规则（基于 p1_hunan.md 完成标准）:
  1. province 字段全部为"湖南"
  2. subject_group 只含"物理类"/"历史类"（普通类数据）
  3. lowest_score 在 0-750 之间（投档线）
  4. score 在 0-750 之间（一分一段表）
  5. 无空行、无完全重复行
  6. 无 null/NA/None/nan 字符串
  7. 关键字段无空值（如 university_name、score 等）

注意:
  - 省控线 subject_group 含体育类/艺术类，不做严格校验
  - 投档线 lowest_score 允许空（部分专业组无投档数据）
"""
from __future__ import annotations

import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROVINCE = "湖南"
VALID_SUBJECTS = {"物理类", "历史类"}
INVALID_STRINGS = {"null", "NA", "None", "nan", "NaN", "NULL", "none"}

errors: list[str] = []
warnings: list[str] = []


def check_no_invalid_strings(df: pd.DataFrame, filename: str):
    """检查是否有 null/NA/None/nan 等字符串。"""
    for col in df.columns:
        s = df[col].astype(str).str.strip()
        bad_mask = s.isin(INVALID_STRINGS)
        if bad_mask.any():
            errors.append(f"{filename}: 列 '{col}' 有 {bad_mask.sum()} 个无效字符串(null/NA/None)")


def check_province(df: pd.DataFrame, filename: str):
    """检查 province 是否全部为湖南。"""
    if "province" not in df.columns:
        return
    unique = df["province"].unique()
    if len(unique) != 1 or unique[0] != PROVINCE:
        errors.append(f"{filename}: province 含非湖南值: {unique}")


def check_subject_group(df: pd.DataFrame, filename: str, strict: bool = True):
    """检查 subject_group。

    strict=True: 必须只含物理类/历史类（一分一段表/投档线）
    strict=False: 允许其他科类（省控线含艺术体育类）
    """
    if "subject_group" not in df.columns:
        return
    unique = set(df["subject_group"].dropna().unique())
    if strict:
        bad = unique - VALID_SUBJECTS
        if bad:
            errors.append(f"{filename}: subject_group 含非法值: {bad}")
    else:
        # 普通类必须为物理类/历史类，其他科类可放行
        for sg in unique:
            if sg.startswith("普通类") and sg not in VALID_SUBJECTS:
                errors.append(f"{filename}: 普通类 subject_group 非法: {sg}")


def check_score_range(df: pd.DataFrame, filename: str, col: str, lo: int, hi: int):
    """检查分数列范围。"""
    if col not in df.columns:
        return
    s = pd.to_numeric(df[col], errors="coerce")
    # 允许空（部分投档线无数据）
    non_null = s.dropna()
    if non_null.empty:
        return
    bad = non_null[(non_null < lo) | (non_null > hi)]
    if len(bad) > 0:
        errors.append(f"{filename}: {col} 有 {len(bad)} 行超出 [{lo}, {hi}] 范围")


def check_duplicates(df: pd.DataFrame, filename: str, key_cols: list[str]):
    """检查关键列是否有完全重复行。"""
    missing_cols = [c for c in key_cols if c not in df.columns]
    if missing_cols:
        return
    dup = df.duplicated(subset=key_cols, keep=False)
    n_dup = dup.sum()
    if n_dup > 0:
        errors.append(f"{filename}: 关键列 {key_cols} 有 {n_dup} 行重复")


def check_required_fields(df: pd.DataFrame, filename: str, fields: list[str]):
    """检查必填字段是否为空。"""
    for f in fields:
        if f not in df.columns:
            errors.append(f"{filename}: 缺少必填字段 '{f}'")
            continue
        empty_mask = df[f].isna() | (df[f].astype(str).str.strip() == "")
        n_empty = empty_mask.sum()
        if n_empty > 0:
            warnings.append(f"{filename}: 必填字段 '{f}' 有 {n_empty} 行为空")


def validate_yifenyiduan(year: int):
    filename = f"yifenyiduan_{year}.csv"
    path = DATA_DIR / filename
    if not path.exists():
        warnings.append(f"{filename}: 文件不存在")
        return 0
    df = pd.read_csv(path, dtype=str)
    prov_df = df[df["province"] == PROVINCE]
    if len(prov_df) == 0:
        warnings.append(f"{filename}: 无湖南数据")
        return 0
    print(f"\n[{filename}] 湖南 {len(prov_df)} 行")
    check_no_invalid_strings(prov_df, filename)
    check_province(prov_df, filename)
    check_subject_group(prov_df, filename, strict=True)
    check_score_range(prov_df, filename, "score", 0, 750)
    check_score_range(prov_df, filename, "segment_count", 0, 100000)
    check_score_range(prov_df, filename, "cumulative_count", 0, 1000000)
    check_duplicates(prov_df, filename,
                     ["province", "year", "subject_group", "batch", "score"])
    check_required_fields(prov_df, filename, ["province", "year", "subject_group", "score"])
    # 科类分布
    for sg, cnt in prov_df["subject_group"].value_counts().items():
        print(f"  {sg}: {cnt} 行")
    return len(prov_df)


def validate_control_line(year: int):
    filename = f"control_line_{year}.csv"
    path = DATA_DIR / filename
    if not path.exists():
        warnings.append(f"{filename}: 文件不存在")
        return 0
    df = pd.read_csv(path, dtype=str)
    prov_df = df[df["province"] == PROVINCE]
    if len(prov_df) == 0:
        warnings.append(f"{filename}: 无湖南数据")
        return 0
    print(f"\n[{filename}] 湖南 {len(prov_df)} 行")
    check_no_invalid_strings(prov_df, filename)
    check_province(prov_df, filename)
    check_subject_group(prov_df, filename, strict=False)
    check_score_range(prov_df, filename, "lowest_score", 0, 750)
    check_duplicates(prov_df, filename,
                     ["province", "year", "batch", "subject_group", "line_type"])
    check_required_fields(prov_df, filename, ["province", "year", "batch", "lowest_score"])
    return len(prov_df)


def validate_admission_history():
    filename = "admission_history.csv"
    path = DATA_DIR / filename
    if not path.exists():
        warnings.append(f"{filename}: 文件不存在")
        return 0
    df = pd.read_csv(path, dtype=str)
    prov_df = df[df["province"] == PROVINCE]
    if len(prov_df) == 0:
        warnings.append(f"{filename}: 无湖南数据")
        return 0
    print(f"\n[{filename}] 湖南 {len(prov_df)} 行")
    check_no_invalid_strings(prov_df, filename)
    check_province(prov_df, filename)
    check_subject_group(prov_df, filename, strict=True)
    # 投档线分数允许空（部分专业组无投档数据），但若有值必须在 0-750
    check_score_range(prov_df, filename, "lowest_score", 0, 750)
    check_duplicates(prov_df, filename,
                     ["year", "province", "subject_group", "batch",
                      "university_code", "group_code"])
    check_required_fields(prov_df, filename,
                          ["year", "province", "subject_group", "university_code"])
    # 年份分布
    print("  年份分布:")
    for y, cnt in prov_df["year"].value_counts().sort_index().items():
        print(f"    {y}: {cnt} 行")
    # 科类分布
    print("  科类分布:")
    for sg, cnt in prov_df["subject_group"].value_counts().items():
        print(f"    {sg}: {cnt} 行")
    # 覆盖院校数
    n_uni = prov_df["university_name"].nunique()
    print(f"  覆盖院校: {n_uni} 所")
    # 投档线有效率
    s = pd.to_numeric(prov_df["lowest_score"], errors="coerce")
    has_score = s.notna().sum()
    print(f"  有效投档线: {has_score}/{len(prov_df)} ({has_score/len(prov_df)*100:.1f}%)")
    return len(prov_df)


def main():
    print(f"{'=' * 60}")
    print(f"湖南省高考数据校验")
    print(f"{'=' * 60}")

    total = 0
    total += validate_yifenyiduan(2024)
    total += validate_yifenyiduan(2025)
    total += validate_yifenyiduan(2026)
    total += validate_control_line(2024)
    total += validate_control_line(2025)
    total += validate_control_line(2026)
    total += validate_admission_history()

    print(f"\n{'=' * 60}")
    print(f"校验结果汇总")
    print(f"{'=' * 60}")
    print(f"湖南数据总行数: {total}")
    print(f"错误数: {len(errors)}")
    print(f"警告数: {len(warnings)}")

    if errors:
        print(f"\n--- 错误 ---")
        for e in errors:
            print(f"  ✗ {e}")
    if warnings:
        print(f"\n--- 警告 ---")
        for w in warnings:
            print(f"  ⚠ {w}")

    if not errors:
        print(f"\n✅ 全部通过校验")
    else:
        print(f"\n❌ 有 {len(errors)} 个错误需要修复")
    return 1 if errors else 0


if __name__ == "__main__":
    exit(main())
