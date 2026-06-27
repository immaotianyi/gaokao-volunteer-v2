#!/usr/bin/env python3
"""陕西 高考数据校验脚本。

校验规则（参考 _common_spec.md 第五节）：
1. province 字段必须为"陕西"
2. subject_group 只能是"物理类"/"历史类"
3. 空值不能为 null/NA/None/nan 字符串
4. 无重复行
5. 各数据类型特定校验
"""
import os
import sys
from pathlib import Path

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
PROVINCE = "陕西"
VALID_SUBJECTS = {"物理类", "历史类"}

errors = []
warnings = []


def check_csv(filename, checks):
    """运行一组校验。"""
    path = DATA_DIR / filename
    if not path.exists():
        errors.append(f"{filename}: 文件不存在")
        return None
    df = pd.read_csv(path, dtype=str)
    prov_data = df[df["province"] == PROVINCE] if "province" in df.columns else df
    if len(prov_data) == 0:
        warnings.append(f"{filename}: 无{PROVINCE}数据")
        return None
    print(f"\n{'─'*50}")
    print(f"校验 {filename} ({PROVINCE}数据: {len(prov_data)}行)")
    print(f"{'─'*50}")
    for check_name, check_fn in checks.items():
        try:
            check_fn(prov_data)
            print(f"  ✓ {check_name}")
        except Exception as e:
            errors.append(f"{filename} - {check_name}: {e}")
            print(f"  ✗ {check_name}: {e}")
    return prov_data


# ═══════════════════════════════════════════════════════════════
# 通用校验函数
# ═══════════════════════════════════════════════════════════════
def check_province_only(df):
    """province字段必须全部为陕西。"""
    if "province" not in df.columns:
        raise Exception("无province字段")
    unique = df["province"].unique()
    if len(unique) > 1 or unique[0] != PROVINCE:
        raise Exception(f"province含非{PROVINCE}值: {list(unique)}")


def check_subject_group(df):
    """subject_group只能为物理类/历史类。"""
    if "subject_group" not in df.columns:
        raise Exception("无subject_group字段")
    invalid = set(df["subject_group"].dropna().unique()) - VALID_SUBJECTS
    if invalid:
        raise Exception(f"subject_group含非法值: {invalid}")


def check_no_null_strings(df):
    """不能有null/NA/None/nan字符串。"""
    null_strings = {"null", "NA", "None", "nan", "NaN"}
    for col in df.columns:
        vals = df[col].dropna().astype(str)
        bad = vals[vals.isin(null_strings)]
        if len(bad) > 0:
            raise Exception(f"列'{col}'含null字符串: {bad.unique()[:3]}")


def check_no_duplicates(df):
    """无完全重复行。"""
    dup_count = df.duplicated().sum()
    if dup_count > 0:
        raise Exception(f"有{dup_count}行完全重复")


# ═══════════════════════════════════════════════════════════════
# 一分一段表校验
# ═══════════════════════════════════════════════════════════════
def check_yifenyiduan_score_range(df):
    """score在0-750之间。"""
    scores = pd.to_numeric(df["score"], errors="coerce")
    bad = scores[(scores < 0) | (scores > 750)]
    if len(bad) > 0:
        raise Exception(f"score超出0-750: {bad.unique()[:5]}")


def check_yifenyiduan_cumulative(df):
    """cumulative_count >= 0。"""
    cum = pd.to_numeric(df["cumulative_count"], errors="coerce")
    bad = cum[cum < 0]
    if len(bad) > 0:
        raise Exception(f"cumulative_count有负值: {len(bad)}行")


def check_yifenyiduan_coverage(df):
    """每科类行数检查。"""
    for sg in df["subject_group"].unique():
        sg_data = df[df["subject_group"] == sg]
        n = len(sg_data)
        if n < 400:
            warnings.append(f"yifenyiduan {sg}: 仅{n}行（预期>2000，但陕西表格不覆盖0-200分段）")
        else:
            print(f"    {sg}: {n}行, 分数{pd.to_numeric(sg_data['score']).min()}-{pd.to_numeric(sg_data['score']).max()}")


# ═══════════════════════════════════════════════════════════════
# 省控线校验
# ═══════════════════════════════════════════════════════════════
def check_control_line_score(df):
    """lowest_score在100-750之间。"""
    scores = pd.to_numeric(df["lowest_score"], errors="coerce")
    bad = scores[(scores < 100) | (scores > 750)]
    if len(bad) > 0:
        raise Exception(f"lowest_score超出100-750: {bad.unique()[:5]}")


def check_control_line_batches(df):
    """每年至少有本科批控制线。"""
    for year in df["year"].unique():
        year_data = df[df["year"] == year]
        has_benke = year_data["batch"].str.contains("本科", na=False).any()
        if not has_benke:
            raise Exception(f"{year}年缺少本科批控制线")


# ═══════════════════════════════════════════════════════════════
# 历史投档线校验
# ═══════════════════════════════════════════════════════════════
def check_admission_year(df):
    """year必须是2023/2024/2025之一。"""
    valid_years = {2023, 2024, 2025}
    years = set(pd.to_numeric(df["year"], errors="coerce").dropna().astype(int))
    invalid = years - valid_years
    if invalid:
        raise Exception(f"year含非法值: {invalid}")


def check_admission_score(df):
    """lowest_score在100-750之间（有值时，专科批可低至150）。"""
    scores = pd.to_numeric(df["lowest_score"], errors="coerce")
    valid_scores = scores.dropna()
    bad = valid_scores[(valid_scores < 100) | (valid_scores > 750)]
    if len(bad) > 0:
        raise Exception(f"lowest_score超出100-750: {len(bad)}行")


def check_admission_coverage(df):
    """每省每年每科类应>1000行。"""
    for year in df["year"].unique():
        for sg in df["subject_group"].unique():
            count = len(df[(df["year"] == year) & (df["subject_group"] == sg)])
            if count < 500:
                warnings.append(f"admission_history {year}年{sg}: 仅{count}行")


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════
def main():
    print(f"\n{'='*60}")
    print(f"========== {PROVINCE} 数据校验 ==========")
    print(f"{'='*60}")

    # 一分一段表
    for year in [2024, 2025, 2026]:
        check_csv(
            f"yifenyiduan_{year}.csv",
            {
                "province仅为陕西": check_province_only,
                "subject_group合法": check_subject_group,
                "无null字符串": check_no_null_strings,
                "无重复行": check_no_duplicates,
                "score范围0-750": check_yifenyiduan_score_range,
                "cumulative_count>=0": check_yifenyiduan_cumulative,
                "覆盖度检查": check_yifenyiduan_coverage,
            },
        )

    # 省控线
    for year in [2024, 2025, 2026]:
        check_csv(
            f"control_line_{year}.csv",
            {
                "province仅为陕西": check_province_only,
                "subject_group合法": check_subject_group,
                "无null字符串": check_no_null_strings,
                "无重复行": check_no_duplicates,
                "lowest_score范围100-750": check_control_line_score,
                "含本科批控制线": check_control_line_batches,
            },
        )

    # 历史投档线
    check_csv(
        "admission_history.csv",
        {
            "province仅为陕西": check_province_only,
            "subject_group合法": check_subject_group,
            "无null字符串": check_no_null_strings,
            "无重复行": check_no_duplicates,
            "year为2023/2024/2025": check_admission_year,
            "lowest_score范围200-750": check_admission_score,
            "覆盖度检查": check_admission_coverage,
        },
    )

    # 汇总
    print(f"\n{'='*60}")
    print(f"校验结果汇总")
    print(f"{'='*60}")
    print(f"错误数: {len(errors)}")
    print(f"警告数: {len(warnings)}")
    if errors:
        print(f"\n❌ 错误详情:")
        for e in errors:
            print(f"  - {e}")
    if warnings:
        print(f"\n⚠ 警告详情:")
        for w in warnings:
            print(f"  - {w}")
    if not errors:
        print(f"\n✅ 全部校验通过！")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
