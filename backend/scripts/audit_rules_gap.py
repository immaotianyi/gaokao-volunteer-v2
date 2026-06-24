#!/usr/bin/env python3
"""
规则缺口审计脚本 — 交叉比对 plans_2026.csv 与 enrollment_rules.json

输出三类结果：
1. 完全缺失：CSV 中有但 JSON 中没有的大学
2. 仅有通配规则：JSON 中有但 major_pattern 全部为 ".*" 的大学
3. 精细度不足：JSON 中有但仅覆盖不到 30% 专业关键词的大学

用法:
  python scripts/audit_rules_gap.py
"""
import csv
import json
import sys
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

PLANS_FILE = DATA_DIR / "plans_2026.csv"
RULES_FILE = DATA_DIR / "enrollment_rules.json"


def load_plans_universities(csv_path: Path) -> set:
    """从 CSV 中提取大学名称去重集合"""
    if not csv_path.exists():
        print(f"❌ CSV 文件不存在: {csv_path}")
        return set()
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        unis = set()
        for row in reader:
            uni = row.get("university_name", "").strip()
            if uni:
                unis.add(uni)
    return unis


def load_rules(rules_path: Path) -> tuple[dict, list]:
    """加载 enrollment_rules.json，返回 (meta, rules_list)"""
    if not rules_path.exists():
        print(f"❌ 规则文件不存在: {rules_path}")
        return {}, []
    
    with open(rules_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("meta", {}), data.get("rules", [])


def analyze_gap(plans_unis: set, rules: list) -> dict:
    """分析缺口"""
    rules_unis = set()
    wildcard_unis = []
    low_coverage_unis = []

    for rule_entry in rules:
        uni = rule_entry.get("university", "")
        if not uni:
            continue
        rules_unis.add(uni)

        majors = rule_entry.get("majors", [])
        if not majors:
            continue

        # 检查是否全部通配规则
        all_wildcard = all(
            m.get("major_pattern") == ".*" for m in majors
        )
        if all_wildcard:
            wildcard_unis.append(uni)
            continue

        # 检查精细度：非通配规则的专业关键词数量
        specific_patterns = [
            m.get("major_pattern") for m in majors
            if m.get("major_pattern") != ".*"
        ]
        # 粗略估计：通配规则意味着覆盖不足
        if len(specific_patterns) < 3 and len(majors) <= 2:
            low_coverage_unis.append(uni)

    # 完全缺失
    missing_unis = plans_unis - rules_unis

    return {
        "missing": sorted(missing_unis),
        "wildcard_only": sorted(wildcard_unis),
        "low_coverage": sorted(low_coverage_unis),
        "total_csv_unis": len(plans_unis),
        "total_rules_unis": len(rules_unis),
        "coverage_rate": f"{len(rules_unis & plans_unis) / max(len(plans_unis), 1) * 100:.1f}%",
    }


def main():
    print("=" * 60)
    print("规则缺口审计")
    print("=" * 60)

    plans_unis = load_plans_universities(PLANS_FILE)
    meta, rules = load_rules(RULES_FILE)

    print(f"\n📊 CSV 中大学数: {len(plans_unis)}")
    print(f"📊 JSON 中大学数: {len(rules_unis := set(r.get('university','') for r in rules))}")

    result = analyze_gap(plans_unis, rules)

    print(f"\n📊 覆盖率: {result['coverage_rate']}")

    print(f"\n🔴 1. 完全缺失 ({len(result['missing'])} 所):")
    for uni in result["missing"][:20]:
        print(f"   - {uni}")
    if len(result["missing"]) > 20:
        print(f"   ... 还有 {len(result['missing']) - 20} 所")

    print(f"\n🟡 2. 仅有通配规则 ({len(result['wildcard_only'])} 所):")
    for uni in result["wildcard_only"][:20]:
        print(f"   - {uni}")
    if len(result["wildcard_only"]) > 20:
        print(f"   ... 还有 {len(result['wildcard_only']) - 20} 所")

    print(f"\n🟠 3. 精细度不足 ({len(result['low_coverage'])} 所):")
    for uni in result["low_coverage"][:20]:
        print(f"   - {uni}")
    if len(result["low_coverage"]) > 20:
        print(f"   ... 还有 {len(result['low_coverage']) - 20} 所")

    # 输出 JSON 摘要
    summary_path = DATA_DIR / "rules_gap_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 摘要已保存: {summary_path}")

    # 缺失大学清单 (用于 Phase 2.2 补全章程)
    if result["missing"]:
        missing_path = DATA_DIR / "missing_universities.txt"
        with open(missing_path, "w", encoding="utf-8") as f:
            for uni in result["missing"]:
                f.write(f"{uni}\n")
        print(f"✅ 缺失大学清单: {missing_path}")


if __name__ == "__main__":
    main()
