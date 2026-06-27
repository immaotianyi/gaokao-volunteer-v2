#!/usr/bin/env python3
"""河北 高考数据校验脚本

校验 5 类数据文件中河北数据的完整性：
  1. yifenyiduan_{2024,2025,2026}.csv — 一分一段表
  2. control_line_{2024,2025,2026}.csv — 省控线
  3. admission_history.csv — 历史投档线（已有2024/2025）
  4. plans_2026.csv / plans_2025.csv — 招生计划（可能无河北数据）

校验规则参考 prompts/_common_spec.md 第五节。
"""
import os
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PROVINCE = "河北"
VALID_SUBJECTS = {"物理类", "历史类"}
VALID_SCHOOL_TYPES = {"985", "211", "双一流", "省属重点", "普通本科", "民办"}

errors: list[str] = []
warnings: list[str] = []


def check_csv(filename: str, checks: dict) -> None:
    """对一个CSV运行多个检查。"""
    path = DATA_DIR / filename
    if not path.exists():
        warnings.append(f"{filename}: 文件不存在")
        return
    try:
        df = pd.read_csv(path, dtype=str)
    except Exception as e:
        errors.append(f"{filename}: 读取失败 {e}")
        return
    if "province" not in df.columns:
        warnings.append(f"{filename}: 无 province 列")
        return
    prov_data = df[df["province"] == PROVINCE]
    if len(prov_data) == 0:
        warnings.append(f"{filename}: 无{PROVINCE}数据")
        return
    print(f"\n[检查] {filename} ({PROVINCE}数据 {len(prov_data)} 行)")
    for check_name, check_fn in checks.items():
        try:
            check_fn(prov_data)
            print(f"  ✓ {check_name}")
        except Exception as e:
            errors.append(f"{filename} - {check_name}: {e}")
            print(f"  ✗ {check_name}: {e}")


# ─────────────────────────────────────────────────────────────────
# 一分一段表校验
# ─────────────────────────────────────────────────────────────────
def yifenyiduan_subject_group(df):
    sg = set(df["subject_group"].dropna().unique())
    invalid = sg - VALID_SUBJECTS
    if invalid:
        raise AssertionError(f"非法科类: {invalid}")
    # 必须同时有物理类和历史类
    missing = VALID_SUBJECTS - sg
    if missing:
        raise AssertionError(f"缺少科类: {missing}")


def yifenyiduan_score_range(df):
    scores = pd.to_numeric(df["score"], errors="coerce")
    bad = scores[(scores < 0) | (scores > 750)]
    if len(bad) > 0:
        raise AssertionError(f"{len(bad)}行分数越界 (0-750)")


def yifenyiduan_cumulative_monotonic(df):
    """累计人数必须随分数下降递增。"""
    non_monotonic = 0
    for sg in VALID_SUBJECTS:
        sub = df[df["subject_group"] == sg].copy()
        if len(sub) == 0:
            continue
        sub["score"] = pd.to_numeric(sub["score"], errors="coerce")
        sub["cum"] = pd.to_numeric(sub["cumulative_count"], errors="coerce")
        sub = sub.sort_values("score", ascending=False).dropna(subset=["cum"])
        cum = sub["cum"].tolist()
        for i in range(len(cum) - 1):
            if cum[i] > cum[i + 1]:
                non_monotonic += 1
    # 允许少量OCR误差
    if non_monotonic > 10:
        raise AssertionError(f"累计非单调 {non_monotonic} 处（>10）")


def yifenyiduan_row_count(df):
    """每科类每年应 > 400 行（分数从140-700约560个分数）。"""
    grouped = df.groupby(["year", "subject_group"]).size()
    for (year, sg), n in grouped.items():
        if n < 400:
            warnings.append(f"yifenyiduan {year}/{sg}: 仅 {n} 行 (<400)")


# ─────────────────────────────────────────────────────────────────
# 省控线校验
# ─────────────────────────────────────────────────────────────────
def control_line_score_range(df):
    scores = pd.to_numeric(df["lowest_score"], errors="coerce")
    bad = scores[(scores < 100) | (scores > 750)]
    if len(bad) > 0:
        raise AssertionError(f"{len(bad)}行分数线越界 (100-750)")


def control_line_subject_group(df):
    # 省控线可能含艺术类等，但物理类/历史类必须存在
    sg = set(df["subject_group"].dropna().unique())
    if "物理类" not in sg or "历史类" not in sg:
        raise AssertionError(f"缺少物理类/历史类: {sg}")


def control_line_batch(df):
    """必须有本科批控制线。"""
    batches = df["batch"].dropna().unique()
    if not any("本科" in str(b) for b in batches):
        raise AssertionError(f"无本科批控制线: {batches}")


# ─────────────────────────────────────────────────────────────────
# 投档线校验
# ─────────────────────────────────────────────────────────────────
def admission_score_range(df):
    scores = pd.to_numeric(df["lowest_score"], errors="coerce")
    bad = scores[(scores < 200) | (scores > 750)]
    # 投档线可能有空值，只校验有值的
    if len(bad) > 0:
        raise AssertionError(f"{len(bad)}行分数异常 (200-750)")


def admission_year(df):
    years = set(pd.to_numeric(df["year"], errors="coerce").dropna().astype(int))
    # 应包含2024/2025
    if 2024 not in years or 2025 not in years:
        raise AssertionError(f"缺少2024/2025年: {years}")


def admission_subject_group(df):
    sg = set(df["subject_group"].dropna().unique())
    invalid = sg - VALID_SUBJECTS - {"艺术类", "体育类", "艺术类(历史)", "艺术类(物理)"}
    if invalid:
        raise AssertionError(f"非法科类: {invalid}")


# ─────────────────────────────────────────────────────────────────
# 通用校验
# ─────────────────────────────────────────────────────────────────
def check_no_null_strings(df):
    """不能有 null/NA/None/nan 字符串。"""
    null_like = df.astype(str).apply(lambda x: x.str.lower().isin(["null", "na", "none", "nan"])).sum().sum()
    if null_like > 0:
        raise AssertionError(f"{null_like} 个 null/NA/None 字符串")


def check_province_only(df):
    """province 字段必须全部为河北（针对当前数据切片已保证）。"""
    pass  # 已在 check_csv 中按 province 切片


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════
def main():
    print(f"{'='*60}")
    print(f"  {PROVINCE} 数据校验")
    print(f"{'='*60}")

    # 一分一段表
    yifenyiduan_checks = {
        "科类正确": yifenyiduan_subject_group,
        "分数范围0-750": yifenyiduan_score_range,
        "累计单调递增": yifenyiduan_cumulative_monotonic,
        "无null字符串": check_no_null_strings,
        "行数充足": yifenyiduan_row_count,
    }
    for year in [2024, 2025, 2026]:
        check_csv(f"yifenyiduan_{year}.csv", yifenyiduan_checks)

    # 省控线
    control_checks = {
        "分数线范围100-750": control_line_score_range,
        "科类含物理类/历史类": control_line_subject_group,
        "有本科批控制线": control_line_batch,
        "无null字符串": check_no_null_strings,
    }
    for year in [2024, 2025, 2026]:
        check_csv(f"control_line_{year}.csv", control_checks)

    # 投档线
    admission_checks = {
        "分数范围200-750": admission_score_range,
        "年份含2024/2025": admission_year,
        "科类正确": admission_subject_group,
        "无null字符串": check_no_null_strings,
    }
    check_csv("admission_history.csv", admission_checks)

    # 招生计划（可能无河北数据，仅警告）
    plans_checks = {
        "无null字符串": check_no_null_strings,
    }
    check_csv("plans_2026.csv", plans_checks)
    check_csv("plans_2025.csv", plans_checks)

    # 汇总
    print(f"\n{'='*60}")
    print(f"  校验结果汇总")
    print(f"{'='*60}")
    print(f"  错误: {len(errors)} 个")
    for e in errors:
        print(f"    ✗ {e}")
    print(f"  警告: {len(warnings)} 个")
    for w in warnings:
        print(f"    ⚠ {w}")

    if errors:
        print(f"\n  ❌ 校验失败（{len(errors)}个错误）")
        sys.exit(1)
    print(f"\n  ✅ 校验通过（{len(warnings)}个警告可忽略）")


if __name__ == "__main__":
    main()
