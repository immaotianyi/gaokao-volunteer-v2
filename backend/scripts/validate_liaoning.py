#!/usr/bin/env python3
"""辽宁 数据校验脚本

校验内容:
  1. 通用: province 一致性、subject_group 取值、空值处理、去重
  2. 一分一段表: 分数范围、累计单调性、覆盖完整性
  3. 省控线: 分数范围、关键科类覆盖
  4. 投档线: 年份、分数范围、代码格式
"""
import os
import sys
from pathlib import Path

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
PROVINCE = "辽宁"
VALID_SUBJECTS = {"物理类", "历史类"}
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


def load_ln(filename):
    path = DATA_DIR / filename
    if not path.exists():
        return None
    df = pd.read_csv(path, dtype=str)
    return df[df["province"] == PROVINCE] if "province" in df.columns else df


# ═══════════════════════════════════════════════════════════════
# 1. 一分一段表校验
# ═══════════════════════════════════════════════════════════════
def validate_yifenyiduan():
    print(f"\n{'=' * 50}")
    print("校验一分一段表")
    for year in [2025, 2026]:
        csv_name = f"yifenyiduan_{year}.csv"
        df = load_ln(csv_name)
        if df is None or len(df) == 0:
            warn(f"{csv_name}: 无辽宁数据")
            continue
        print(f"\n--- {csv_name} ({len(df)} 行) ---")

        # subject_group 取值
        sgs = set(df["subject_group"].unique())
        bad_sg = sgs - VALID_SUBJECTS
        if bad_sg:
            err(f"非法科类: {bad_sg}")
        else:
            ok(f"科类取值正确: {sgs}")

        # 分数范围
        scores = pd.to_numeric(df["score"], errors="coerce")
        if scores.min() < 0 or scores.max() > 750:
            err(f"分数越界: {scores.min()}-{scores.max()}")
        else:
            ok(f"分数范围: {int(scores.min())}-{int(scores.max())}")

        # 空值检查
        for col in ["score", "segment_count", "cumulative_count"]:
            vals = df[col].replace("", pd.NA)
            null_cnt = vals.isna().sum()
            if null_cnt > 0:
                err(f"{col} 有 {null_cnt} 个空值")

        # 累计单调性 (分数从高到低, 累计递增)
        for sg in ["物理类", "历史类"]:
            for batch in ["本科批", "专科批"]:
                sub = df[(df["subject_group"] == sg) & (df["batch"] == batch)]
                if len(sub) == 0:
                    continue
                sub = sub.sort_values("score", ascending=False)
                cum = pd.to_numeric(sub["cumulative_count"], errors="coerce").tolist()
                monotonic = all(cum[i] <= cum[i + 1] for i in range(len(cum) - 1))
                if monotonic:
                    ok(f"{sg}/{batch}: {len(sub)}行, 累计单调递增 ✓")
                else:
                    # 找到非单调点
                    bad_idx = [i for i in range(len(cum) - 1) if cum[i] > cum[i + 1]]
                    err(f"{sg}/{batch}: 累计非单调 ({len(bad_idx)}处), 首处分数={sub.iloc[bad_idx[0]]['score']}")

        # 去重检查
        dup = df.duplicated(subset=["year", "subject_group", "batch", "score"]).sum()
        if dup > 0:
            err(f"重复行: {dup}")
        else:
            ok("无重复行")

        # 行数提示 (辽宁一分一段表分数范围150-最高分, 非全覆盖0-750)
        for sg in ["物理类", "历史类"]:
            cnt = len(df[df["subject_group"] == sg])
            if cnt < 400:
                warn(f"{sg} 行数偏少 ({cnt}), 辽宁一分一段表覆盖分数150-最高分")


# ═══════════════════════════════════════════════════════════════
# 2. 省控线校验
# ═══════════════════════════════════════════════════════════════
def validate_control_line():
    print(f"\n{'=' * 50}")
    print("校验省控线")
    for year in [2024, 2025, 2026]:
        csv_name = f"control_line_{year}.csv"
        df = load_ln(csv_name)
        if df is None or len(df) == 0:
            warn(f"{csv_name}: 无辽宁数据")
            continue
        print(f"\n--- {csv_name} ({len(df)} 行) ---")

        # 分数范围
        scores = pd.to_numeric(df["lowest_score"], errors="coerce")
        if scores.min() < 100 or scores.max() > 750:
            err(f"分数越界: {scores.min()}-{scores.max()}")
        else:
            ok(f"分数范围: {int(scores.min())}-{int(scores.max())}")

        # 关键科类覆盖 (物理类/历史类 本科批)
        for sg in ["物理类", "历史类"]:
            bk = df[(df["subject_group"] == sg) & (df["batch"] == "本科")]
            if len(bk) == 0:
                err(f"缺少 {sg} 本科批控制线")
            else:
                ok(f"{sg} 本科批: {int(bk.iloc[0]['lowest_score'])}分")

        # source_url 非空
        if df["source_url"].replace("", pd.NA).isna().all():
            warn("source_url 全空")

        # 去重
        dup = df.duplicated(subset=["year", "batch_section", "batch",
                                     "subject_group", "line_type"]).sum()
        if dup > 0:
            err(f"重复行: {dup}")
        else:
            ok("无重复行")


# ═══════════════════════════════════════════════════════════════
# 3. 投档线 (admission_history) 校验
# ═══════════════════════════════════════════════════════════════
def validate_admission_history():
    print(f"\n{'=' * 50}")
    print("校验投档线 admission_history")
    df = load_ln("admission_history.csv")
    if df is None or len(df) == 0:
        warn("admission_history.csv: 无辽宁数据")
        return
    print(f"\n--- admission_history.csv 辽宁 ({len(df)} 行) ---")

    # 年份
    years = set(df["year"].unique())
    expected_years = {"2023", "2024", "2025"}
    missing_years = expected_years - years
    if missing_years:
        warn(f"缺少年份: {missing_years} (2025投档线Excel加密, 待补)")
    ok(f"覆盖年份: {sorted(years)}")

    # 科类
    sgs = set(df["subject_group"].unique())
    bad_sg = sgs - VALID_SUBJECTS
    if bad_sg:
        err(f"非法科类: {bad_sg}")
    else:
        ok(f"科类取值: {sgs}")

    # 分数范围
    scores = pd.to_numeric(df["lowest_score"], errors="coerce")
    valid_scores = scores.dropna()
    if len(valid_scores) > 0:
        if valid_scores.min() < 200 or valid_scores.max() > 750:
            warn(f"分数范围异常: {valid_scores.min()}-{valid_scores.max()}")
        else:
            ok(f"分数范围: {int(valid_scores.min())}-{int(valid_scores.max())}")

    # 院校代码格式
    codes = df["university_code"].dropna()
    bad_codes = [c for c in codes if not str(c).isdigit() or len(str(c)) < 4]
    if bad_codes:
        warn(f"异常院校代码: {len(bad_codes)}个")
    else:
        ok(f"院校代码格式正确 ({len(codes)}个)")

    # 各年各科类行数
    print(f"  各年各科类行数:")
    for (yr, sg), cnt in df.groupby(["year", "subject_group"]).size().items():
        print(f"    {yr} {sg}: {cnt} 行")
        if cnt < 1000:
            warn(f"{yr} {sg} 行数偏少 ({cnt})")

    # 去重
    dup = df.duplicated(subset=["year", "province", "subject_group", "batch",
                                 "university_code", "major_code"]).sum()
    if dup > 0:
        err(f"重复行: {dup}")
    else:
        ok("无重复行")

    # 空值检查 (不能有 null/NA/None 字符串)
    for col in df.columns:
        bad_null = df[col].astype(str).str.lower().isin(["null", "nan", "none", "na"])
        if bad_null.sum() > 0:
            err(f"{col} 含 null/NA/None 字符串: {bad_null.sum()}个")
    ok("无 null/NA/None 字符串")


# ═══════════════════════════════════════════════════════════════
# 4. 通用: 其他省份数据未被破坏
# ═══════════════════════════════════════════════════════════════
def validate_no_other_province_corruption():
    print(f"\n{'=' * 50}")
    print("校验其他省份数据完整性")
    for csv_name in ["yifenyiduan_2026.csv", "control_line_2026.csv", "admission_history.csv"]:
        path = DATA_DIR / csv_name
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype=str)
        provs = df["province"].unique() if "province" in df.columns else []
        non_ln = [p for p in provs if p != PROVINCE]
        if non_ln:
            ok(f"{csv_name}: 保留其他省份 {len(non_ln)}个: {non_ln[:5]}...")
        else:
            print(f"  - {csv_name}: 仅含辽宁")


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════
def main():
    print(f"========== {PROVINCE} 数据校验 ==========")
    validate_yifenyiduan()
    validate_control_line()
    validate_admission_history()
    validate_no_other_province_corruption()

    print(f"\n{'=' * 50}")
    print(f"校验结果汇总:")
    print(f"  错误: {len(errors)} 个")
    print(f"  警告: {len(warnings)} 个")
    if errors:
        print(f"\n  错误详情:")
        for e in errors:
            print(f"    ✗ {e}")
    if warnings:
        print(f"\n  警告详情:")
        for w in warnings:
            print(f"    ⚠ {w}")
    if not errors:
        print(f"\n  ✅ 全部通过 (有 {len(warnings)} 个警告)")
    else:
        print(f"\n  ❌ {len(errors)} 个错误")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
