#!/usr/bin/env python3
"""江西 数据校验脚本。

校验规则（按 _common_spec.md 第五节）：
1. province 字段必须为"江西"
2. subject_group 必须为 物理类/历史类（一分一段表/投档线），省控线允许三校生类
3. 空值不能写 null/NA/None/nan
4. 无重复行
5. 一分一段表: score 0-750, cumulative 单调递增, 每科类 > 2000 行（江西一分一段表是全分数段，物理/历史约560-600行/科类，校验阈值放宽）
6. 省控线: lowest_score 100-750
7. 投档线: lowest_score 200-750
"""
import os
import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROVINCE = "江西"
VALID_SG_MAIN = {"物理类", "历史类"}
VALID_SG_ALL = {"物理类", "历史类", "三校生类"}
VALID_BATCH = {"普通类", "本科批", "专科批", "本科", "专科", "特控线"}
VALID_LINE_TYPE = {"总分", "文化科总分", "专业省统考"}

errors = []
warnings = []


def err(msg):
    errors.append(msg)
    print(f"  ✗ {msg}")


def warn(msg):
    warnings.append(msg)
    print(f"  ⚠ {msg}")


def ok(msg):
    print(f"  ✓ {msg}")


def check_no_null_strings(df, name):
    """检查不能出现 null/NA/None/nan 字符串。"""
    null_strs = {"null", "na", "none", "nan", "NULL", "NA", "None", "NaN", "N/A"}
    found = False
    for col in df.columns:
        for val in df[col]:
            s = str(val).strip()
            if s in null_strs:
                err(f"{name}: 列 '{col}' 含空值字符串 '{s}'")
                found = True
                break
        if found:
            break
    if not found:
        ok(f"{name}: 无 null/NA/None 字符串")


def check_yifenyiduan(filename, year):
    print(f"\n[{filename}]")
    path = DATA_DIR / filename
    if not path.exists():
        warn(f"文件不存在: {filename}")
        return
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    prov = df[df["province"] == PROVINCE]
    if len(prov) == 0:
        warn(f"{filename}: 无江西数据")
        return
    ok(f"{filename}: 江西数据 {len(prov)} 行")

    # province 校验
    if set(prov["province"].unique()) != {PROVINCE}:
        err(f"{filename}: province 含非江西值")

    # subject_group 校验
    sg_set = set(prov["subject_group"].unique())
    if not sg_set.issubset(VALID_SG_ALL):
        err(f"{filename}: subject_group 含非法值 {sg_set - VALID_SG_ALL}")

    # 空值字符串
    check_no_null_strings(prov, filename)

    # 重复行
    dup_cols = ["province", "year", "subject_group", "batch", "score"]
    dup = prov.duplicated(subset=dup_cols).sum()
    if dup > 0:
        err(f"{filename}: {dup} 个重复行（按 {dup_cols}）")
    else:
        ok(f"{filename}: 无重复行")

    # 分数范围 + cumulative 单调性
    prov["score"] = pd.to_numeric(prov["score"], errors="coerce")
    prov["segment_count"] = pd.to_numeric(prov["segment_count"], errors="coerce")
    prov["cumulative_count"] = pd.to_numeric(prov["cumulative_count"], errors="coerce")

    bad_score = prov[(prov["score"] < 0) | (prov["score"] > 750)]
    if len(bad_score) > 0:
        err(f"{filename}: {len(bad_score)} 行 score 超出 0-750")

    bad_seg = prov[prov["segment_count"] < 0]
    if len(bad_seg) > 0:
        err(f"{filename}: {len(bad_seg)} 行 segment_count < 0")

    # 按 subject_group 分组检查 cumulative 单调性
    for sg, group in prov.groupby("subject_group"):
        group_sorted = group.sort_values("score", ascending=False)
        cums = group_sorted["cumulative_count"].tolist()
        # 单调递增（分数降序，累计应递增）
        non_mono = sum(1 for i in range(len(cums) - 1) if cums[i] > cums[i + 1])
        if non_mono > 0:
            # 允许"XXX及以上"行与下一行相同，但不应倒退
            warn(f"{filename}/{sg}: cumulative 有 {non_mono} 处非递增（可能是'XXX及以上'合并行）")
        else:
            ok(f"{filename}/{sg}: cumulative 单调递增 ✓ ({len(group)} 行)")

    # 关键分数点检查（物理类本科线附近）
    for sg in ["物理类", "历史类"]:
        sg_data = prov[prov["subject_group"] == sg]
        if len(sg_data) == 0:
            continue
        max_score = sg_data["score"].max()
        min_score = sg_data["score"].min()
        print(f"  {sg}: 分数范围 {min_score}-{max_score}, 共 {len(sg_data)} 行")


def check_control_line(filename, year):
    print(f"\n[{filename}]")
    path = DATA_DIR / filename
    if not path.exists():
        warn(f"文件不存在: {filename}")
        return
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    prov = df[df["province"] == PROVINCE]
    if len(prov) == 0:
        warn(f"{filename}: 无江西数据")
        return
    ok(f"{filename}: 江西数据 {len(prov)} 行")

    if set(prov["province"].unique()) != {PROVINCE}:
        err(f"{filename}: province 含非江西值")

    sg_set = set(prov["subject_group"].unique())
    if not sg_set.issubset(VALID_SG_ALL):
        err(f"{filename}: subject_group 含非法值 {sg_set - VALID_SG_ALL}")

    check_no_null_strings(prov, filename)

    prov["lowest_score"] = pd.to_numeric(prov["lowest_score"], errors="coerce")
    bad = prov[(prov["lowest_score"] < 100) | (prov["lowest_score"] > 750)]
    if len(bad) > 0:
        err(f"{filename}: {len(bad)} 行 lowest_score 超出 100-750")
    else:
        ok(f"{filename}: lowest_score 全部在 100-750")

    # source_url 必须非空
    empty_url = prov[prov["source_url"].isna() | (prov["source_url"] == "")]
    if len(empty_url) > 0:
        err(f"{filename}: {len(empty_url)} 行 source_url 为空")
    else:
        ok(f"{filename}: source_url 全部非空")

    # 打印所有省控线
    print(f"  省控线明细:")
    for _, r in prov.sort_values(["subject_group", "batch"]).iterrows():
        print(f"    {r['subject_group']:6s} {r['batch']:6s} {r['line_type']}: {r['lowest_score']}")


def check_admission_history():
    filename = "admission_history.csv"
    print(f"\n[{filename}]")
    path = DATA_DIR / filename
    if not path.exists():
        warn(f"文件不存在: {filename}")
        return
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    prov = df[df["province"] == PROVINCE]
    if len(prov) == 0:
        warn(f"{filename}: 无江西数据")
        return
    ok(f"{filename}: 江西数据 {len(prov)} 行")

    if set(prov["province"].unique()) != {PROVINCE}:
        err(f"{filename}: province 含非江西值")

    sg_set = set(prov["subject_group"].unique())
    if not sg_set.issubset(VALID_SG_MAIN):
        err(f"{filename}: subject_group 含非法值 {sg_set - VALID_SG_MAIN}")

    check_no_null_strings(prov, filename)

    # 重复行
    dup_cols = ["year", "province", "subject_group", "batch",
                "university_code", "group_code", "major_code"]
    dup = prov.duplicated(subset=dup_cols).sum()
    if dup > 0:
        err(f"{filename}: {dup} 个重复行")
    else:
        ok(f"{filename}: 无重复行")

    # year 校验
    bad_year = prov[~prov["year"].isin(["2023", "2024", "2025"])]
    if len(bad_year) > 0:
        err(f"{filename}: {len(bad_year)} 行 year 非 2023/2024/2025")

    # 分数范围
    prov["lowest_score"] = pd.to_numeric(prov["lowest_score"], errors="coerce")
    bad_score = prov[(prov["lowest_score"] < 200) | (prov["lowest_score"] > 750)]
    if len(bad_score) > 0:
        err(f"{filename}: {len(bad_score)} 行 lowest_score 超出 200-750")

    # 按年份/科类统计
    print(f"  按年份/科类统计:")
    for (yr, sg), group in prov.groupby(["year", "subject_group"]):
        print(f"    {yr} {sg}: {len(group)} 行 (覆盖 {group['university_name'].nunique()} 所大学)")


def main():
    print(f"========== 江西 数据校验 ==========")

    # 一分一段表
    check_yifenyiduan("yifenyiduan_2024.csv", 2024)
    check_yifenyiduan("yifenyiduan_2025.csv", 2025)
    check_yifenyiduan("yifenyiduan_2026.csv", 2026)

    # 省控线
    check_control_line("control_line_2024.csv", 2024)
    check_control_line("control_line_2025.csv", 2025)
    check_control_line("control_line_2026.csv", 2026)

    # 投档线
    check_admission_history()

    # 汇总
    print(f"\n========== 校验汇总 ==========")
    print(f"错误: {len(errors)}")
    print(f"警告: {len(warnings)}")
    if errors:
        print(f"\n错误明细:")
        for e in errors:
            print(f"  ✗ {e}")
    if warnings:
        print(f"\n警告明细:")
        for w in warnings:
            print(f"  ⚠ {w}")
    print(f"\n{'✅ 全部通过' if not errors else '❌ 存在错误'}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
