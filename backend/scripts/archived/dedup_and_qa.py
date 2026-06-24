#!/usr/bin/env python3
"""
Step 4: 规则去重与合并 + Step 5: 质检脚本

用法:
  python scripts/dedup_and_qa.py          # 执行去重 + 质检
  python scripts/dedup_and_qa.py --qa-only # 仅质检, 不去重
  python scripts/dedup_and_qa.py --dedup-only  # 仅去重, 不质检
"""
import json
import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RULES_FILE = DATA_DIR / "enrollment_rules.json"
ZSZC_DIR = DATA_DIR / "zszc"


def load_rules() -> tuple[dict, list]:
    """加载规则文件"""
    if not RULES_FILE.exists():
        print(f"❌ 规则文件不存在: {RULES_FILE}")
        sys.exit(1)
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("meta", {}), data.get("rules", [])


def save_rules(meta: dict, rules: list):
    """保存规则"""
    meta["last_updated"] = __import__("time").strftime("%Y-%m-%d %H:%M:%S")
    meta["total_universities"] = len(rules)
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "rules": rules}, f, ensure_ascii=False, indent=2)
    print(f"💾 已保存: {len(rules)} 所大学")


# ── Step 4: 去重合并 ──────────────────────────────────────────

def dedup_rules(rules: list) -> list:
    """去重合并规则"""
    print("\n" + "=" * 60)
    print("Step 4: 规则去重与合并")
    print("=" * 60)

    # 按 university 分组
    groups = defaultdict(list)
    for rule in rules:
        uni = rule.get("university", "")
        if uni:
            groups[uni].append(rule)

    duplicates = {uni: entries for uni, entries in groups.items() if len(entries) > 1}
    print(f"重复大学: {len(duplicates)} 所")

    merged = []
    for uni, entries in groups.items():
        if len(entries) == 1:
            merged.append(entries[0])
        else:
            # 保留 majors 数组更长（规则更精细）的那个
            best = max(entries, key=lambda r: len(r.get("majors", [])))
            merged.append(best)

    # 同一大学内部去重：同一 major_pattern 保留 year 更新的
    final_rules = []
    for rule in merged:
        majors = rule.get("majors", [])
        seen_patterns = {}
        deduped_majors = []
        for major in majors:
            pattern = major.get("major_pattern", "")
            if pattern in seen_patterns:
                # 保留 year 更新的（这里都是2026，保留先出现的）
                continue
            seen_patterns[pattern] = True
            deduped_majors.append(major)
        rule["majors"] = deduped_majors
        final_rules.append(rule)

    removed = len(rules) - len(final_rules)
    print(f"去重: {len(rules)} → {len(final_rules)} (移除 {removed} 条)")
    return final_rules


# ── Step 5: 质检 ──────────────────────────────────────────────

def qa_check(rules: list):
    """质检并输出报告"""
    print("\n" + "=" * 60)
    print("Step 5: 质检报告")
    print("=" * 60)

    report = {}

    # 1. source_files 为空的大学
    empty_source = []
    for rule in rules:
        uni = rule.get("university", "?")
        sources = rule.get("source_files", [])
        if not sources:
            empty_source.append(uni)
    report["empty_source_files"] = {
        "count": len(empty_source),
        "universities": empty_source,
        "note": "这些是手写规则或历史规则，需要优先补抓章程 TXT"
    }
    print(f"\n📋 1. source_files 为空: {len(empty_source)} 所")
    for uni in empty_source[:10]:
        print(f"   - {uni}")
    if len(empty_source) > 10:
        print(f"   ... 还有 {len(empty_source) - 10} 所")

    # 2. 只有通配规则且 notes 含「未发现显性限制」
    no_effective = []
    for rule in rules:
        uni = rule.get("university", "?")
        majors = rule.get("majors", [])
        if len(majors) == 1:
            m = majors[0]
            if (m.get("major_pattern") == ".*" and
                    m.get("notes", "").find("未发现显性限制") != -1):
                no_effective.append(uni)
    report["no_effective_rules"] = {
        "count": len(no_effective),
        "universities": no_effective,
        "note": "这些大学实际没有提取到有效规则"
    }
    print(f"\n📋 2. 无有效规则: {len(no_effective)} 所")
    for uni in no_effective[:10]:
        print(f"   - {uni}")
    if len(no_effective) > 10:
        print(f"   ... 还有 {len(no_effective) - 10} 所")

    # 3. 非法正则
    invalid_patterns = []
    for rule in rules:
        uni = rule.get("university", "?")
        for major in rule.get("majors", []):
            pattern = major.get("major_pattern", "")
            if pattern:
                try:
                    re.compile(pattern)
                except re.error as e:
                    invalid_patterns.append({
                        "university": uni,
                        "major_pattern": pattern,
                        "error": str(e),
                    })
    report["invalid_patterns"] = {
        "count": len(invalid_patterns),
        "details": invalid_patterns,
    }
    print(f"\n📋 3. 非法正则: {len(invalid_patterns)} 条")
    for item in invalid_patterns[:10]:
        print(f"   - {item['university']}: '{item['major_pattern']}' → {item['error']}")

    # 4. TXT 文件覆盖交叉比对
    txt_unis = set()
    if ZSZC_DIR.exists():
        for f in ZSZC_DIR.glob("*_2026招生章程_*.txt"):
            name = f.stem.split('_2026')[0]
            txt_unis.add(name)

    rules_unis = {r.get("university", "") for r in rules}
    rules_unis_safe = {re.sub(r'[\\/:*?"<>|]', '_', u) for u in rules_unis}

    only_txt = txt_unis - rules_unis_safe
    only_rules = rules_unis - txt_unis

    report["txt_coverage"] = {
        "txt_total": len(txt_unis),
        "rules_total": len(rules_unis),
        "matched": len(txt_unis & rules_unis_safe),
        "only_in_txt": len(only_txt),
        "only_in_rules": len(only_rules),
    }
    print(f"\n📋 4. 章程TXT覆盖:")
    print(f"   TXT文件大学数: {len(txt_unis)}")
    print(f"   JSON规则大学数: {len(rules_unis)}")
    print(f"   匹配: {len(txt_unis & rules_unis_safe)}")
    print(f"   仅TXT (未提取规则): {len(only_txt)}")
    print(f"   仅JSON (无TXT文件): {len(only_rules)}")

    # 5. 按 year 分组统计
    year_stats = defaultdict(int)
    for rule in rules:
        year = rule.get("year", "unknown")
        year_stats[str(year)] += 1
    report["year_distribution"] = dict(year_stats)
    print(f"\n📋 5. 年份分布:")
    for year, count in sorted(year_stats.items()):
        pct = count / len(rules) * 100
        print(f"   {year}: {count} 所 ({pct:.0f}%)")

    # 6. 精细度统计
    total_majors = 0
    wildcard_majors = 0
    for rule in rules:
        for major in rule.get("majors", []):
            total_majors += 1
            if major.get("major_pattern") == ".*":
                wildcard_majors += 1

    fine_rate = (total_majors - wildcard_majors) / max(total_majors, 1) * 100
    report["fineness"] = {
        "total_majors": total_majors,
        "wildcard_majors": wildcard_majors,
        "specific_majors": total_majors - wildcard_majors,
        "fineness_rate": f"{fine_rate:.1f}%",
    }
    print(f"\n📋 6. 精细度:")
    print(f"   总规则条目: {total_majors}")
    print(f"   通配规则: {wildcard_majors} ({wildcard_majors/max(total_majors,1)*100:.0f}%)")
    print(f"   精细规则: {total_majors - wildcard_majors} ({fine_rate:.0f}%)")

    # 保存报告
    report_path = DATA_DIR / "qa_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 质检报告已保存: {report_path}")

    return report


def main():
    parser = argparse.ArgumentParser(description="规则去重合并 + 质检")
    parser.add_argument("--qa-only", action="store_true", help="仅质检")
    parser.add_argument("--dedup-only", action="store_true", help="仅去重")
    args = parser.parse_args()

    meta, rules = load_rules()
    print(f"加载规则: {len(rules)} 所大学")

    if args.dedup_only:
        rules = dedup_rules(rules)
        save_rules(meta, rules)
    elif args.qa_only:
        qa_check(rules)
    else:
        rules = dedup_rules(rules)
        save_rules(meta, rules)
        qa_check(rules)


if __name__ == "__main__":
    main()
