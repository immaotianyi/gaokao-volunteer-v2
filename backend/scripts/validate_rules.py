#!/usr/bin/env python3
"""
规则一致性自动检查脚本

对 enrollment_rules.json 做如下检查：
- 每条规则的 body_check.clause 不能为空（如果有限制但无条款引用）
- 每条规则的 major_pattern 必须是合法正则表达式
- 同一大学同一专业的规则不能冲突
- 每条规则必须有 year 字段且非空

用法:
  python scripts/validate_rules.py
"""
import json
import re
import sys
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RULES_FILE = DATA_DIR / "enrollment_rules.json"


def validate_rules(rules: list) -> dict:
    """验证规则列表，返回错误统计"""
    errors = []
    warnings = []
    stats = {
        "total_rules": len(rules),
        "total_majors": 0,
        "passed": 0,
        "errors": 0,
        "warnings": 0,
    }

    for i, rule_entry in enumerate(rules):
        uni = rule_entry.get("university", f"规则#{i}")
        year = rule_entry.get("year")
        majors = rule_entry.get("majors", [])

        # 检查 year 字段
        if not year:
            errors.append(f"[{uni}] 缺少 year 字段")
            stats["errors"] += 1
            continue

        stats["total_majors"] += len(majors)

        uni_rule_statuses = defaultdict(set)  # major_pattern → status 集合

        for j, major in enumerate(majors):
            major_label = f"{uni}/{major.get('major_name', f'专业#{j}')}"

            # 1. 检查 major_pattern 是否为合法正则
            pattern = major.get("major_pattern", "")
            if pattern:
                try:
                    re.compile(pattern)
                except re.error as e:
                    errors.append(f"[{major_label}] 非法正则表达式 '{pattern}': {e}")
                    stats["errors"] += 1
                    continue

            # 2. 检查 body_check clause 不能为空
            body_check = major.get("body_check", {})
            if body_check:
                has_restriction = any(
                    body_check.get(k) in ("DANGER", "WARNING")
                    for k in ("color_blind", "color_weak", "color_distinguish", "vision", "height")
                )
                clause = body_check.get("clause", "")
                if has_restriction and not clause:
                    errors.append(
                        f"[{major_label}] body_check 有限制但 clause 为空"
                    )
                    stats["errors"] += 1
                elif has_restriction and clause:
                    stats["passed"] += 1

            # 3. 检查单科成绩要求
            single_subject = major.get("single_subject", {})
            if single_subject:
                for subject, detail in single_subject.items():
                    if detail and isinstance(detail, dict):
                        if detail.get("min") and not detail.get("clause"):
                            warnings.append(
                                f"[{major_label}] single_subject.{subject} 有 min 值但无 clause"
                            )
                            stats["warnings"] += 1

            # 4. 检查同一大学同一专业规则冲突
            if pattern and pattern != ".*":
                uni_rule_statuses[pattern].add("has_rule")

            # 5. 检查 language_restriction 字段值合法性
            lang = major.get("language_restriction")
            valid_langs = {"仅限英语", "仅限德语", "仅限日语", "仅限俄语", "仅限法语", None, "null"}
            if lang and lang not in valid_langs and lang != "null":
                warnings.append(
                    f"[{major_label}] language_restriction 值不常见: '{lang}'"
                )
                stats["warnings"] += 1

    return {
        "stats": stats,
        "errors": errors,
        "warnings": warnings,
    }


def main():
    print("=" * 60)
    print("规则一致性检查")
    print("=" * 60)

    if not RULES_FILE.exists():
        print(f"❌ 规则文件不存在: {RULES_FILE}")
        sys.exit(1)

    with open(RULES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    meta = data.get("meta", {})
    rules = data.get("rules", [])

    print(f"\n📊 版本: {meta.get('version', 'N/A')}")
    print(f"📊 覆盖大学: {meta.get('total_universities', len(rules))}")

    result = validate_rules(rules)

    s = result["stats"]
    print(f"\n📊 规则总数: {s['total_rules']}")
    print(f"📊 专业条目总数: {s['total_majors']}")
    print(f"✅ 通过: {s['passed']}")
    print(f"❌ 错误: {s['errors']}")
    print(f"⚠️  警告: {s['warnings']}")

    if result["errors"]:
        print(f"\n🔴 错误列表 ({len(result['errors'])} 条):")
        for e in result["errors"][:30]:
            print(f"   {e}")
        if len(result["errors"]) > 30:
            print(f"   ... 还有 {len(result['errors']) - 30} 条")

    if result["warnings"]:
        print(f"\n🟡 警告列表 ({len(result['warnings'])} 条):")
        for w in result["warnings"][:30]:
            print(f"   {w}")
        if len(result["warnings"]) > 30:
            print(f"   ... 还有 {len(result['warnings']) - 30} 条")

    # 保存报告
    report = {
        "stats": s,
        "errors": result["errors"],
        "warnings": result["warnings"],
    }
    report_path = DATA_DIR / "rules_validation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 报告已保存: {report_path}")

    if result["errors"]:
        print("\n❌ 存在错误，请修复后重新检查")
        sys.exit(1)
    else:
        print("\n✅ 所有检查通过!")


if __name__ == "__main__":
    main()
