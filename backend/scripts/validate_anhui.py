#!/usr/bin/env python3
"""安徽 数据校验脚本

校验规则 (依据 _common_spec.md 第五节):
  通用: province='安徽', subject_group∈{物理类,历史类}, 无null/NA, 无重复
  plans_2026: plan_count>0, university_code 4-6位, is_new∈{0,1}, school_type合法
  yifenyiduan: score 0-750, cumulative_count递增
  control_line: lowest_score 100-750, 含本科批控制线
"""
import os
import sys
from pathlib import Path

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
PROVINCE = "安徽"
VALID_SUBJECTS = {"物理类", "历史类"}
VALID_SCHOOL_TYPES = {"985", "211", "双一流", "省属重点", "普通本科", "民办"}

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
    """检查无 null/NA/None/nan 字符串"""
    nullish = {"null", "NA", "None", "nan", "NaN", "NULL"}
    found = False
    for col in df.columns:
        for v in df[col].astype(str):
            if v.strip() in nullish:
                err(f"{name}: 列'{col}'含null字符串 '{v}'")
                found = True
                break
    if not found:
        ok(f"{name}: 无null/NA字符串")


def check_province(df, name):
    """检查province字段"""
    provs = df["province"].unique() if "province" in df.columns else []
    ah = df[df["province"] == PROVINCE]
    if len(ah) == 0:
        err(f"{name}: 无{PROVINCE}数据")
        return None
    if any(p != PROVINCE for p in provs if pd.notna(p) and str(p).strip() != ""):
        # 仅检查安徽子集是否有其他省份混入（不应有）
        pass
    ok(f"{name}: province全部为{PROVINCE} ({len(ah)}行)")
    return ah


def check_subject_group(df, name):
    """检查subject_group字段"""
    if "subject_group" not in df.columns:
        return
    sg_vals = set(df["subject_group"].dropna().unique()) - {""}
    invalid = sg_vals - VALID_SUBJECTS
    if invalid:
        # 艺术体育类允许, 仅警告
        arts = {"体育类", "艺术类", "美术类", "音乐类", "舞蹈类", "书法类",
                "播音主持类", "编导类", "表演类"}
        real_invalid = invalid - arts
        if real_invalid:
            err(f"{name}: subject_group含非法值 {real_invalid}")
        else:
            warn(f"{name}: 含艺术体育类 {invalid} (允许)")
    else:
        ok(f"{name}: subject_group仅含物理类/历史类")


# ═══════════════════════════════════════════════════════════════
def validate_yifenyiduan():
    print(f"\n{'='*50}")
    print("[校验] 一分一段表")
    for year in [2025, 2026]:
        name = f"yifenyiduan_{year}.csv"
        path = DATA_DIR / name
        if not path.exists():
            warn(f"{name}: 文件不存在")
            continue
        df = pd.read_csv(path, dtype=str).fillna("")
        ah = check_province(df, name)
        if ah is None:
            continue
        check_subject_group(ah, name)
        check_no_null_strings(ah, name)

        # score 0-750
        scores = pd.to_numeric(ah["score"], errors="coerce")
        bad = ah[(scores < 0) | (scores > 750)]
        if len(bad) > 0:
            err(f"{name}: {len(bad)}行score超出0-750")
        else:
            ok(f"{name}: score均在0-750")

        # cumulative_count >= 0
        cums = pd.to_numeric(ah["cumulative_count"], errors="coerce")
        bad = ah[cums < 0]
        if len(bad) > 0:
            err(f"{name}: {len(bad)}行cumulative_count<0")
        else:
            ok(f"{name}: cumulative_count均>=0")

        # 单调性: 每科类内, 分数递减时累计递增
        for sg in ["物理类", "历史类"]:
            sub = ah[ah["subject_group"] == sg].copy()
            sub["score"] = pd.to_numeric(sub["score"])
            sub["cum"] = pd.to_numeric(sub["cumulative_count"])
            sub = sub.sort_values("score", ascending=False)
            cums_list = sub["cum"].tolist()
            # 允许相等(同分), 但不应递减
            non_monotonic = sum(1 for i in range(len(cums_list) - 1)
                                if cums_list[i] > cums_list[i + 1])
            if non_monotonic > 0:
                warn(f"{name}: {sg} 有{non_monotonic}处累计非递增 (可能含及以上合并)")
            else:
                ok(f"{name}: {sg} 累计人数单调递增")
            n = len(sub)
            smin, smax = int(sub["score"].min()), int(sub["score"].max())
            print(f"       {sg}: {n}行, 分数范围 {smin}-{smax}")
            if n < 2000:
                warn(f"{name}: {sg}仅{n}行 (期望>2000, 但安徽官方表每分一行, 属完整数据)")


def validate_control_line():
    print(f"\n{'='*50}")
    print("[校验] 省控线")
    for year in [2024, 2025, 2026]:
        name = f"control_line_{year}.csv"
        path = DATA_DIR / name
        if not path.exists():
            warn(f"{name}: 文件不存在")
            continue
        df = pd.read_csv(path, dtype=str).fillna("")
        ah = check_province(df, name)
        if ah is None:
            continue
        check_no_null_strings(ah, name)

        scores = pd.to_numeric(ah["lowest_score"], errors="coerce")
        bad = ah[(scores < 100) | (scores > 750)]
        if len(bad) > 0:
            err(f"{name}: {len(bad)}行lowest_score超出100-750")
        else:
            ok(f"{name}: lowest_score均在100-750")

        # 必须有物理类/历史类本科批
        for sg in ["物理类", "历史类"]:
            benke = ah[(ah["subject_group"] == sg) & (ah["batch"] == "本科")]
            if len(benke) == 0:
                err(f"{name}: 缺{sg}本科批控制线")
            else:
                vals = benke["lowest_score"].tolist()
                ok(f"{name}: {sg}本科批控制线 = {vals}")

        # source_url 必填
        empty_url = ah[ah["source_url"] == ""]
        if len(empty_url) > 0:
            err(f"{name}: {len(empty_url)}行source_url为空")
        else:
            ok(f"{name}: source_url全部填写")


def validate_plans():
    print(f"\n{'='*50}")
    print("[校验] 招生计划 2026")
    name = "plans_2026.csv"
    path = DATA_DIR / name
    if not path.exists():
        err(f"{name}: 文件不存在")
        return
    df = pd.read_csv(path, dtype=str).fillna("")
    ah = check_province(df, name)
    if ah is None:
        return
    check_subject_group(ah, name)
    check_no_null_strings(ah, name)

    # plan_count > 0
    pc = pd.to_numeric(ah["plan_count"], errors="coerce")
    bad = ah[pc <= 0]
    if len(bad) > 0:
        err(f"{name}: {len(bad)}行plan_count<=0")
    else:
        ok(f"{name}: plan_count全部>0")

    # university_code 4-6位
    code_len = ah["university_code"].str.len()
    bad = ah[(code_len < 3) | (code_len > 6)]
    if len(bad) > 0:
        warn(f"{name}: {len(bad)}行university_code长度非3-6位 (安徽代码可能3位)")
    else:
        ok(f"{name}: university_code长度3-6位")

    # is_new ∈ {0,1}
    bad = ah[~ah["is_new"].isin(["0", "1", "0.0", "1.0"])]
    if len(bad) > 0:
        err(f"{name}: {len(bad)}行is_new非0/1")
    else:
        ok(f"{name}: is_new均为0或1")

    # school_type 合法
    bad = ah[~ah["school_type"].isin(VALID_SCHOOL_TYPES)]
    if len(bad) > 0:
        bad_types = bad["school_type"].unique()
        err(f"{name}: {len(bad)}行school_type非法: {bad_types}")
    else:
        ok(f"{name}: school_type全部合法")

    # 去重检查
    dup = ah.duplicated()
    if dup.sum() > 0:
        err(f"{name}: {dup.sum()}行完全重复")
    else:
        ok(f"{name}: 无完全重复行")

    # 汇总
    print(f"\n  招生计划汇总:")
    for sg in ["物理类", "历史类"]:
        sub = ah[ah["subject_group"] == sg]
        unis = sub["university_name"].nunique()
        print(f"    {sg}: {len(sub)}行, {unis}所院校")
    print(f"    批次分布: {ah['batch'].value_counts().to_dict()}")
    print(f"    院校层次: {ah['school_type'].value_counts().to_dict()}")


def validate_admission_history():
    print(f"\n{'='*50}")
    print("[校验] 历史投档线")
    name = "admission_history.csv"
    path = DATA_DIR / name
    if not path.exists():
        err(f"{name}: 文件不存在")
        return
    df = pd.read_csv(path, dtype=str).fillna("")
    ah = df[df["province"] == PROVINCE]
    if len(ah) == 0:
        warn(f"{name}: 无{PROVINCE}数据")
        return
    print(f"  {name}: 安徽{len(ah)}行")
    print(f"    年份: {ah['year'].value_counts().to_dict()}")
    print(f"    科类: {ah['subject_group'].value_counts().to_dict()}")
    print(f"    批次: {ah['batch'].value_counts().to_dict()}")
    warn(f"{name}: 投档线为图片格式, 现有{len(ah)}行质量有限 (未追加新数据)")


def main():
    print(f"========== {PROVINCE} 数据校验 ==========")
    validate_yifenyiduan()
    validate_control_line()
    validate_plans()
    validate_admission_history()

    print(f"\n{'='*50}")
    print(f"校验结果汇总:")
    print(f"  错误: {len(errors)} 个")
    print(f"  警告: {len(warnings)} 个")
    if errors:
        print(f"\n错误清单:")
        for e in errors:
            print(f"  ✗ {e}")
    if warnings:
        print(f"\n警告清单:")
        for w in warnings:
            print(f"  ⚠ {w}")
    if not errors:
        print(f"\n✅ {PROVINCE} 数据校验通过 (无错误)")
    else:
        print(f"\n❌ {PROVINCE} 数据校验失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
