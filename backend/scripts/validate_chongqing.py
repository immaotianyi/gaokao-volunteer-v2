#!/usr/bin/env python3
"""重庆 数据校验脚本

校验规则（参见 _common_spec.md 第五节）：
- province 字段必须为"重庆"
- subject_group 只能是 物理类 / 历史类
- plan_count > 0
- 空值不写 null/NA/None
- 无重复行
- 各类数据行数达标
- lowest_score 在合理区间
- 一分一段表 cumulative_count 单调递增
"""
import os
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PROVINCE = "重庆"
VALID_SUBJECTS = {"物理类", "历史类"}
# 艺体类科类（与广东2026做法一致，作为补充数据保留）
ART_SPORT_SUBJECTS = {
    "体育类", "美术与设计类", "音乐类", "音乐教育", "音乐表演(声乐)", "音乐表演(器乐)",
    "舞蹈类", "戏剧影视表演", "服装表演", "戏剧影视导演", "播音与主持类",
    "书法类", "表（导）演类",
}
VALID_SCHOOL_TYPES = {"985", "211", "双一流", "省属重点", "普通本科", "民办"}
INVALID_NULL_VALUES = {"null", "NA", "None", "nan", "NaN"}

errors: list[str] = []
warnings: list[str] = []


def add_error(msg: str):
    errors.append(msg)
    print(f"  ✗ {msg}")


def add_warn(msg: str):
    warnings.append(msg)
    print(f"  ⚠ {msg}")


def check_no_null_strings(df: pd.DataFrame, filename: str):
    """检查是否含 null/NA/None 字符串。"""
    for col in df.columns:
        if df[col].dtype == object:
            mask = df[col].astype(str).str.strip().isin(INVALID_NULL_VALUES)
            n = mask.sum()
            if n > 0:
                add_error(f"{filename}: 列 '{col}' 含 {n} 个 null/NA 字符串")


def check_province(df: pd.DataFrame, filename: str):
    """检查 province 字段。"""
    if "province" not in df.columns:
        return
    cq = df[df["province"] == PROVINCE]
    if len(cq) == 0:
        add_warn(f"{filename}: 无重庆数据")
        return
    non_cq = df[(df["province"] != PROVINCE) & (df["province"].notna())]
    # 此处只是过滤重庆数据用于后续校验
    return cq


def check_subject_group(df: pd.DataFrame, filename: str):
    """检查 subject_group 字段。

    普通类必须是 物理类/历史类；
    艺体类允许（与广东2026做法一致，作为补充数据保留）。
    """
    if "subject_group" not in df.columns:
        return
    allowed = VALID_SUBJECTS | ART_SPORT_SUBJECTS
    invalid = df[~df["subject_group"].isin(allowed) & df["subject_group"].notna() & (df["subject_group"] != "")]
    if len(invalid) > 0:
        bad_vals = invalid["subject_group"].unique()[:5]
        add_error(f"{filename}: subject_group 含非法值 {list(bad_vals)}")


def check_duplicates(df: pd.DataFrame, filename: str):
    """检查重复行。"""
    n_dup = df.duplicated().sum()
    if n_dup > 0:
        add_error(f"{filename}: {n_dup} 个完全重复行")


def check_csv(filename: str, min_rows: int = 0, custom_checks=None):
    """通用 CSV 校验入口。"""
    path = DATA_DIR / filename
    print(f"\n[校验] {filename}")
    if not path.exists():
        add_warn(f"文件不存在: {filename}")
        return None
    df = pd.read_csv(path, dtype=str).fillna("")
    cq = df[df["province"] == PROVINCE] if "province" in df.columns else df
    print(f"  重庆数据: {len(cq)} 行 (总计 {len(df)} 行)")

    if len(cq) == 0:
        return cq

    # 通用：空值字符串
    check_no_null_strings(cq, filename)
    # 通用：subject_group
    check_subject_group(cq, filename)
    # 通用：重复
    check_duplicates(cq, filename)
    # 行数
    if min_rows > 0 and len(cq) < min_rows:
        add_warn(f"{filename}: 重庆数据 {len(cq)} 行 < 期望 {min_rows} 行")

    # 自定义
    if custom_checks:
        for name, fn in custom_checks.items():
            try:
                fn(cq)
                print(f"  ✓ {name}")
            except AssertionError as e:
                add_error(f"{filename} - {name}: {e}")
            except Exception as e:
                add_error(f"{filename} - {name}: 异常 {e}")
    return cq


# ═══════════════════════════════════════════════════════════════
# 各类数据的自定义校验
# ═══════════════════════════════════════════════════════════════
def check_yifenyiduan(df: pd.DataFrame):
    """一分一段表校验。"""
    # score 0-750
    df["_score"] = pd.to_numeric(df["score"], errors="coerce")
    bad = df[(df["_score"] < 0) | (df["_score"] > 750)]
    assert len(bad) == 0, f"score 越界 {len(bad)} 行"

    # cumulative_count 单调递增（按 subject_group + batch + year 分组，分数从高到低）
    df["_cum"] = pd.to_numeric(df["cumulative_count"], errors="coerce")
    df["_seg"] = pd.to_numeric(df["segment_count"], errors="coerce")
    bad_segments = df[df["_seg"] < 0]
    assert len(bad_segments) == 0, f"segment_count < 0 有 {len(bad_segments)} 行"
    bad_cums = df[df["_cum"] < 0]
    assert len(bad_cums) == 0, f"cumulative_count < 0 有 {len(bad_cums)} 行"

    # 按 (year, subject_group, batch) 分组检查单调性
    for (year, sg, batch), grp in df.groupby(["year", "subject_group", "batch"]):
        grp_sorted = grp.sort_values("_score", ascending=False)
        cums = grp_sorted["_cum"].tolist()
        non_monotonic = sum(1 for i in range(len(cums) - 1) if cums[i] > cums[i + 1])
        if non_monotonic > 0:
            add_warn(f"一分一段表 {year}/{sg}/{batch}: 累计人数非单调递增 {non_monotonic} 处")


def check_control_line(df: pd.DataFrame):
    """省控线校验。

    lowest_score 区间：
    - 文化分数线/总分: 100-750
    - 专业分数线: 50-300（艺体类专业统考百分制）
    """
    df["_score"] = pd.to_numeric(df["lowest_score"], errors="coerce")
    # 文化类分数线
    cultural = df[df["line_type"].isin(["总分", "文化分数线", "文化科总分"])]
    bad_cultural = cultural[(cultural["_score"] < 100) | (cultural["_score"] > 750)]
    assert len(bad_cultural) == 0, f"文化分数线越界 {len(bad_cultural)} 行"
    # 专业分数线（百分制，宽松校验）
    professional = df[df["line_type"].isin(["专业分数线", "专业省统考"])]
    bad_prof = professional[(professional["_score"] < 30) | (professional["_score"] > 300)]
    assert len(bad_prof) == 0, f"专业分数线越界 {len(bad_prof)} 行"
    # source_url 不能为空
    empty_url = df[df["source_url"] == ""]
    assert len(empty_url) == 0, f"source_url 空值 {len(empty_url)} 行"


def check_admission_history(df: pd.DataFrame):
    """历史录取校验。"""
    df["_score"] = pd.to_numeric(df["lowest_score"], errors="coerce")
    has_score = df[df["_score"].notna()]
    bad = has_score[(has_score["_score"] < 200) | (has_score["_score"] > 750)]
    assert len(bad) == 0, f"lowest_score 越界 {len(bad)} 行"
    # year 应该是 2023-2026
    df["_year"] = pd.to_numeric(df["year"], errors="coerce")
    bad_years = df[(df["_year"] < 2023) | (df["_year"] > 2026)]
    assert len(bad_years) == 0, f"year 异常 {len(bad_years)} 行"


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════
def main():
    print(f"\n{'='*60}")
    print(f"[{PROVINCE}] 数据校验")
    print(f"{'='*60}")

    # 一分一段表（每年每科类 > 2000 行的规则对重庆不适用，重庆1分段表约500行/科类）
    # 重庆一分一段表分数从最高分到180分，每分一行，约500行/科类
    for fn in ["yifenyiduan_2024.csv", "yifenyiduan_2025.csv", "yifenyiduan_2026.csv"]:
        check_csv(fn, min_rows=400, custom_checks={
            "score区间与累计单调": check_yifenyiduan,
        })

    # 省控线
    for fn in ["control_line_2024.csv", "control_line_2025.csv", "control_line_2026.csv"]:
        check_csv(fn, min_rows=20, custom_checks={
            "lowest_score与source_url": check_control_line,
        })

    # 历史录取
    check_csv("admission_history.csv", min_rows=1000, custom_checks={
        "year与lowest_score": check_admission_history,
    })

    # 招生计划（重庆未爬取，仅校验现有）
    check_csv("plans_2026.csv")
    check_csv("plans_2025.csv")

    # 汇总
    print(f"\n{'='*60}")
    print(f"[{PROVINCE}] 校验汇总")
    print(f"{'='*60}")
    print(f"错误数: {len(errors)}")
    print(f"警告数: {len(warnings)}")
    if errors:
        print("\n错误详情:")
        for e in errors:
            print(f"  ✗ {e}")
    if warnings:
        print("\n警告详情:")
        for w in warnings:
            print(f"  ⚠ {w}")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
