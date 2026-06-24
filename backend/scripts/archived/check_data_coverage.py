"""
招生计划 ↔ 章程规则 交叉校验脚本

检查内容:
  1. CSV 中每所大学是否有对应的章程 TXT
  2. CSV 中每所大学是否有 enrollment_rules.json 条目
  3. 各大学的规则精细度（专业级 vs 通配规则）

用法:
  cd backend
  python3 scripts/check_data_coverage.py
"""
import csv
import json
import os
import re
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
ZSZC_DIR = DATA_DIR / "zszc"
RULES_FILE = DATA_DIR / "enrollment_rules.json"


def load_plans():
    """加载招生计划 CSV，提取所有不重复的大学名称"""
    universities = set()
    for csv_file in ["plans_2025.csv", "plans_2026.csv"]:
        filepath = DATA_DIR / csv_file
        if not filepath.exists():
            continue
        with open(filepath, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("university_name", "").strip()
                if name:
                    universities.add(name)
    return sorted(universities)


def find_zszc_files(university_name: str) -> list[str]:
    """查找某大学的章程 TXT 文件"""
    if not ZSZC_DIR.exists():
        return []
    files = []
    # 尝试多种匹配方式
    for f in ZSZC_DIR.iterdir():
        if f.suffix != ".txt":
            continue
        fname = f.stem  # 去掉 .txt
        # 匹配: 大学名可能以"大学名_年份招生章程_第N段"格式
        if fname.startswith(university_name):
            files.append(f.name)
        # 也尝试去"大学"后缀的匹配
        elif university_name.endswith("大学"):
            short = university_name[:-2]
            if fname.startswith(short):
                files.append(f.name)
    return files


def check_rules_coverage():
    """检查 enrollment_rules.json 中各大学的规则精细度"""
    if not RULES_FILE.exists():
        return {}
    with open(RULES_FILE, encoding="utf-8") as f:
        data = json.load(f)

    rules_list = data.get("rules", [])
    coverage = {}
    for entry in rules_list:
        uni_name = entry.get("university", "")
        if not uni_name:
            continue
        majors = entry.get("majors", [])
        total_rules = len(majors)
        # 精细规则: major_pattern 不是 ".*"
        detailed = sum(1 for m in majors if m.get("major_pattern", "") not in ("", ".*"))
        wildcard = total_rules - detailed

        # 是否有实质内容（不止是通用描述）
        has_substance = any(
            m.get("body_check") or
            m.get("single_subject") or
            m.get("language_restriction") or
            m.get("subject_election")
            for m in majors
        )

        coverage[uni_name] = {
            "total_rules": total_rules,
            "detailed_rules": detailed,
            "wildcard_rules": wildcard,
            "has_substance": has_substance,
        }
    return coverage


def main():
    print("=" * 60)
    print("招生计划 ↔ 章程规则 交叉校验报告")
    print("=" * 60)

    # 1. 加载招生计划中的大学
    plan_universities = load_plans()
    print(f"\n📊 招生计划 CSV 覆盖大学: {len(plan_universities)} 所")
    for u in plan_universities:
        print(f"   - {u}")

    # 2. 加载规则覆盖情况
    rules_coverage = check_rules_coverage()
    print(f"\n📊 enrollment_rules.json 覆盖大学: {len(rules_coverage)} 所")

    # 3. 逐大学交叉检查
    print("\n" + "=" * 60)
    print("逐大学交叉检查")
    print("=" * 60)

    missing_zszc = []
    missing_rules = []
    low_detail = []

    for uni in plan_universities:
        zszc_files = find_zszc_files(uni)
        rule_info = rules_coverage.get(uni)

        status = []
        if not zszc_files:
            status.append("❌ 无章程TXT")
            missing_zszc.append(uni)
        else:
            status.append(f"✅ 章程TXT ({len(zszc_files)}个文件)")

        if not rule_info:
            status.append("❌ 无规则条目")
            missing_rules.append(uni)
        elif not rule_info["has_substance"]:
            status.append("⚠️ 规则条目无实质内容")
            low_detail.append(uni)
        elif rule_info["detailed_rules"] == 0:
            status.append("⚠️ 仅通配规则 (无专业级精细化)")
            low_detail.append(uni)
        else:
            detail_pct = rule_info["detailed_rules"] / max(rule_info["total_rules"], 1) * 100
            status.append(f"✅ 规则: {rule_info['detailed_rules']}/{rule_info['total_rules']} 精细 ({detail_pct:.0f}%)")

        print(f"\n🏫 {uni}")
        for s in status:
            print(f"   {s}")

    # 4. 汇总报告
    print("\n" + "=" * 60)
    print("汇总报告")
    print("=" * 60)
    print(f"\n🔴 缺失章程TXT: {len(missing_zszc)} 所")
    for u in missing_zszc:
        print(f"   - {u}")

    print(f"\n🔴 缺失规则条目: {len(missing_rules)} 所")
    for u in missing_rules:
        print(f"   - {u}")

    print(f"\n🟡 规则精细度不足 (仅通配/无实质内容): {len(low_detail)} 所")
    for u in low_detail:
        print(f"   - {u}")

    # 统计所有规则库中的精细度
    total_unis = len(rules_coverage)
    detailed_unis = sum(1 for v in rules_coverage.values() if v["detailed_rules"] > 0)
    print(f"\n📊 规则库总体: {total_unis} 所大学")
    print(f"   有专业级精细化规则: {detailed_unis} 所 ({detailed_unis/max(total_unis,1)*100:.0f}%)")
    print(f"   仅通配规则: {total_unis - detailed_unis} 所 ({(total_unis-detailed_unis)/max(total_unis,1)*100:.0f}%)")


if __name__ == "__main__":
    main()
