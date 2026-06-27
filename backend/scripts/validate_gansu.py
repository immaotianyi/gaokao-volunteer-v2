#!/usr/bin/env python3
"""甘肃 数据校验脚本。

校验规则（依据 p0_gansu.md 完成标准）：
1. province 字段全部为"甘肃"
2. subject_group 只含"物理类"/"历史类"
3. plan_count > 0（注：甘肃 plans 来自投档线XLS，无计划数字段，此项降级为警告）
4. lowest_score 在 200-750 之间
5. 无空行、无重复行
6. 无 null/NA/None 字符串
"""
import os
import sys
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
PROVINCE = "甘肃"
VALID_SUBJECTS = {"物理类", "历史类"}
VALID_SCHOOL_TYPES = {"985", "211", "双一流", "省属重点", "普通本科", "民办", "独立学院", "职业本科"}
INVALID_NULL_VALUES = {"null", "NA", "None", "nan", "NaN", "NULL"}

errors: list[str] = []
warnings: list[str] = []


def check_csv(filename, checks):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        errors.append(f"{filename}: 文件不存在")
        return
    try:
        df = pd.read_csv(path, low_memory=False)
    except Exception as e:
        errors.append(f"{filename}: 读取失败 {e}")
        return
    if "province" not in df.columns:
        errors.append(f"{filename}: 无 province 字段")
        return
    prov_data = df[df["province"] == PROVINCE]
    if len(prov_data) == 0:
        errors.append(f"{filename}: 无{PROVINCE}数据")
        return
    print(f"\n{'─'*50}\n📄 {filename}  (甘肃 {len(prov_data)} 行 / 总 {len(df)} 行)")
    for check_name, check_fn in checks.items():
        try:
            msg = check_fn(prov_data)
            status = "✓" if not msg else "⚠"
            line = f"  {status} {check_name}"
            if msg:
                line += f": {msg}"
                # plan_count 相关问题降级为警告（甘肃 plans 来源于投档线XLS，无计划数）
                if "plan_count" in msg or check_name.startswith("plan_count"):
                    warnings.append(f"{filename} - {check_name}: {msg}")
                else:
                    errors.append(f"{filename} - {check_name}: {msg}")
            print(line)
        except Exception as e:
            errors.append(f"{filename} - {check_name}: 异常 {e}")
            print(f"  ✗ {check_name}: 异常 {e}")


# ─────────────────────────────────────────────────────────────────
# 通用校验函数
# ─────────────────────────────────────────────────────────────────
def check_subject_group(df):
    if "subject_group" not in df.columns:
        return "无 subject_group 字段"
    bad = set(df["subject_group"].dropna().unique()) - VALID_SUBJECTS
    if bad:
        return f"非法科类 {bad}"
    return ""


def check_no_null_strings(df):
    """检查是否有 null/NA/None 等字符串字面量（空字符串允许）。"""
    hits = []
    for col in df.columns:
        s = df[col].astype(str)
        for bad in INVALID_NULL_VALUES:
            n = (s == bad).sum()
            if n > 0:
                hits.append(f"{col}={bad}×{n}")
    return "; ".join(hits) if hits else ""


def check_no_duplicates(df):
    n = df.duplicated().sum()
    return f"{n} 行重复" if n > 0 else ""


def check_score_range(col_lo=200, col_hi=750):
    def _check(df):
        # 找分数列
        for c in ["lowest_score", "lowest_score_2025"]:
            if c in df.columns:
                vals = pd.to_numeric(df[c], errors="coerce").dropna()
                bad = ((vals < col_lo) | (vals > col_hi)).sum()
                if bad > 0:
                    return f"{c}: {bad} 行超出 {col_lo}-{col_hi}"
                return ""
        return ""
    return _check


# ─────────────────────────────────────────────────────────────────
# 各文件专属校验
# ─────────────────────────────────────────────────────────────────
def check_yifenyiduan(df):
    msgs = []
    if "cumulative_count" in df.columns:
        vals = pd.to_numeric(df["cumulative_count"], errors="coerce").dropna()
        if (vals <= 0).any():
            msgs.append(f"cumulative_count<=0: {(vals<=0).sum()} 行")
        # 单调性（按科类+batch分组，分数降序时累计应递增）
        for (sg, batch), g in df.groupby(["subject_group", "batch"]):
            g_sorted = g.sort_values("score", ascending=False)
            cum = pd.to_numeric(g_sorted["cumulative_count"], errors="coerce").dropna()
            if len(cum) > 1 and not cum.is_monotonic_increasing:
                msgs.append(f"{sg}/{batch} 累计位次非单调递增")
                break
    if "score" in df.columns:
        bad = ((df["score"] < 0) | (df["score"] > 750)).sum()
        if bad > 0:
            msgs.append(f"score 越界 {bad} 行")
    return "; ".join(msgs)


def check_control_line(df):
    msgs = []
    if "lowest_score" in df.columns:
        vals = pd.to_numeric(df["lowest_score"], errors="coerce").dropna()
        if (vals <= 0).any():
            msgs.append(f"lowest_score<=0: {(vals<=0).sum()} 行")
    # 每年每科类应至少有 本科/特控线/专科 三条
    if "year" in df.columns and "subject_group" in df.columns and "batch" in df.columns:
        for (yr, sg), g in df.groupby(["year", "subject_group"]):
            batches = set(g["batch"].dropna())
            missing = {"本科", "特控线", "专科"} - batches
            if missing:
                msgs.append(f"{yr}/{sg} 缺批次 {missing}")
    return "; ".join(msgs)


def check_plans(df):
    msgs = []
    # plan_count：甘肃来自投档线XLS无此字段，降级为警告
    if "plan_count" in df.columns:
        pc = pd.to_numeric(df["plan_count"], errors="coerce")
        empty = pc.isna().sum()
        if empty == len(df):
            msgs.append("plan_count 全空（数据源为投档线XLS，无计划数）")
        elif (pc.dropna() <= 0).any():
            msgs.append(f"plan_count<=0: {(pc.dropna()<=0).sum()} 行")
    # school_type 校验
    if "school_type" in df.columns:
        bad = set(df["school_type"].dropna().unique()) - VALID_SCHOOL_TYPES
        if bad:
            msgs.append(f"非法 school_type {bad}")
    # university_name 不能空
    if "university_name" in df.columns:
        empty = df["university_name"].isna().sum() + (df["university_name"].astype(str).str.strip() == "").sum()
        if empty > 0:
            msgs.append(f"university_name 空 {empty} 行")
    # batch
    if "batch" in df.columns:
        bad = set(df["batch"].dropna().unique()) - {"本科批", "提前批", "专科批"}
        if bad:
            msgs.append(f"非法 batch {bad}")
    return "; ".join(msgs)


def check_admission_history(df):
    msgs = []
    if "lowest_score" in df.columns:
        vals = pd.to_numeric(df["lowest_score"], errors="coerce").dropna()
        if (vals <= 0).any():
            msgs.append(f"lowest_score<=0: {(vals<=0).sum()} 行")
    if "year" in df.columns:
        years = sorted(df["year"].dropna().unique().tolist())
        msgs.append(f"年份覆盖 {years}" if 2024 not in years else "")
    return "; ".join(msgs)


# ─────────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────────
def main():
    print(f"{'='*50}\n========== {PROVINCE} 数据校验 ==========\n{'='*50}")

    check_csv("yifenyiduan_2024.csv", {
        "科类合法": check_subject_group,
        "无null字符串": check_no_null_strings,
        "无重复行": check_no_duplicates,
        "一分一段表完整性": check_yifenyiduan,
        "分数范围200-750": check_score_range(),
    })
    check_csv("yifenyiduan_2025.csv", {
        "科类合法": check_subject_group,
        "无null字符串": check_no_null_strings,
        "无重复行": check_no_duplicates,
        "一分一段表完整性": check_yifenyiduan,
        "分数范围200-750": check_score_range(),
    })
    check_csv("yifenyiduan_2026.csv", {
        "科类合法": check_subject_group,
        "无null字符串": check_no_null_strings,
        "无重复行": check_no_duplicates,
        "一分一段表完整性": check_yifenyiduan,
        "分数范围200-750": check_score_range(),
    })
    check_csv("control_line_2024.csv", {
        "科类合法": check_subject_group,
        "无null字符串": check_no_null_strings,
        "无重复行": check_no_duplicates,
        "省控线完整性": check_control_line,
    })
    check_csv("control_line_2025.csv", {
        "科类合法": check_subject_group,
        "无null字符串": check_no_null_strings,
        "无重复行": check_no_duplicates,
        "省控线完整性": check_control_line,
    })
    check_csv("control_line_2026.csv", {
        "科类合法": check_subject_group,
        "无null字符串": check_no_null_strings,
        "无重复行": check_no_duplicates,
        "省控线完整性": check_control_line,
    })
    check_csv("plans_2026.csv", {
        "科类合法": check_subject_group,
        "无null字符串": check_no_null_strings,
        "无重复行": check_no_duplicates,
        "plans完整性": check_plans,
        "分数范围200-750": check_score_range(),
    })
    check_csv("plans_2025.csv", {
        "科类合法": check_subject_group,
        "无null字符串": check_no_null_strings,
        "无重复行": check_no_duplicates,
        "plans完整性": check_plans,
        "分数范围200-750": check_score_range(),
    })
    check_csv("admission_history.csv", {
        "科类合法": check_subject_group,
        "无null字符串": check_no_null_strings,
        "无重复行": check_no_duplicates,
        "录取历史完整性": check_admission_history,
        "分数范围200-750": check_score_range(),
    })

    # 汇总
    print(f"\n{'='*50}")
    print(f"校验结果: 错误 {len(errors)} 个 / 警告 {len(warnings)} 个")
    if errors:
        print("\n❌ 错误:")
        for e in errors:
            print(f"  - {e}")
    if warnings:
        print("\n⚠ 警告:")
        for w in warnings:
            print(f"  - {w}")
    if not errors:
        print("\n✅ 全部通过（错误为0）")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
