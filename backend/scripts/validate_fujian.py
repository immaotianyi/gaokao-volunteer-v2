#!/usr/bin/env python3
"""福建数据校验脚本 - 验证5类CSV数据完整性。"""
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def check_csv(name, checks):
    """通用CSV校验。"""
    path = DATA_DIR / name
    print(f"\n{'='*60}")
    print(f"校验 {name}")
    print(f"{'='*60}")
    if not path.exists():
        print(f"  ❌ 文件不存在")
        return False
    df = pd.read_csv(path, dtype=str)
    print(f"  总行数: {len(df)}")
    
    fj = df[df["province"] == "福建"]
    print(f"  福建行数: {len(fj)}")
    if len(fj) == 0:
        print(f"  ⚠ 无福建数据")
        return False
    
    all_pass = True
    for check_name, check_fn in checks:
        try:
            result = check_fn(fj)
            status = "✓" if result else "⚠"
            print(f"  {status} {check_name}")
            if not result:
                all_pass = False
        except Exception as e:
            print(f"  ❌ {check_name}: {e}")
            all_pass = False
    return all_pass


def check_plans_2026():
    def sg(fj):
        return fj["subject_group"].isin(["物理类", "历史类"]).all()
    def plan_count(fj):
        pc = pd.to_numeric(fj["plan_count"], errors="coerce")
        return (pc > 0).all()
    def univ_code(fj):
        return fj["university_code"].str.len().between(4, 6).all()
    def school_type(fj):
        valid = {"985", "211", "双一流", "省属重点", "普通本科", "民办", "独立学院"}
        return fj["school_type"].isin(valid).all()
    def row_count(fj):
        return len(fj) > 500
    return check_csv("plans_2026.csv", [
        ("subject_group 物理类/历史类", sg),
        ("plan_count > 0", plan_count),
        ("university_code 4-6位", univ_code),
        ("school_type 合法", school_type),
        ("行数 > 500", row_count),
    ])


def check_control_line(year):
    def has_lines(fj):
        return len(fj) >= 6  # 物理类+历史类 × 本科+专科+特控
    def score_range(fj):
        s = pd.to_numeric(fj["lowest_score"], errors="coerce")
        return s.between(100, 750).all()
    return check_csv(f"control_line_{year}.csv", [
        ("有6+行控制线", has_lines),
        ("分数 100-750", score_range),
    ])


def check_yifenyiduan(year):
    def has_data(fj):
        return len(fj) > 0
    def score_range(fj):
        s = pd.to_numeric(fj["score"], errors="coerce")
        return s.between(0, 750).all()
    def sg(fj):
        return fj["subject_group"].isin(["物理类", "历史类"]).all()
    return check_csv(f"yifenyiduan_{year}.csv", [
        ("有数据", has_data),
        ("分数 0-750", score_range),
        ("subject_group 物理类/历史类", sg),
    ])


def check_admission_history():
    path = DATA_DIR / "admission_history.csv"
    print(f"\n{'='*60}")
    print(f"校验 admission_history.csv")
    print(f"{'='*60}")
    if not path.exists():
        print(f"  ❌ 文件不存在")
        return False
    df = pd.read_csv(path, dtype=str)
    fj = df[df["province"] == "福建"]
    print(f"  总行数: {len(df)}, 福建行数: {len(fj)}")
    if len(fj) > 0:
        print(f"  年份分布: {fj['year'].value_counts().to_dict()}")
        print(f"  科类分布: {fj['subject_group'].value_counts().to_dict()}")
    return True


def main():
    print("="*60)
    print("福建高考数据校验报告")
    print("="*60)
    
    results = []
    results.append(("plans_2026.csv", check_plans_2026()))
    results.append(("control_line_2026.csv", check_control_line(2026)))
    results.append(("control_line_2025.csv", check_control_line(2025)))
    results.append(("control_line_2024.csv", check_control_line(2024)))
    results.append(("yifenyiduan_2025.csv", check_yifenyiduan(2025)))
    results.append(("yifenyiduan_2024.csv", check_yifenyiduan(2024)))
    results.append(("admission_history.csv", check_admission_history()))
    
    print(f"\n{'='*60}")
    print("校验汇总")
    print(f"{'='*60}")
    for name, ok in results:
        status = "✓" if ok else "⚠"
        print(f"  {status} {name}")


if __name__ == "__main__":
    main()
