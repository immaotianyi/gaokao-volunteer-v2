#!/usr/bin/env python3
"""
数据清洗脚本 — 处理招生计划 CSV 的常见问题

功能：
- 大学名称去重与标准化
- 专业组代码补齐
- 学费字段数值提取
- 计划数为 0 或空白的记录剔除
- 必填字段检查

用法:
  python scripts/clean_plans.py [input.csv] [output.csv]
  默认: data/plans_2025.csv → data/plans_2025_cleaned.csv
        data/plans_2026.csv → data/plans_2026_cleaned.csv
"""
import csv
import re
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def extract_numeric_tuition(tuition_str) -> int:
    """从学费字符串中提取数值，去除 '元/年' '约' '左右' 等"""
    if tuition_str is None or tuition_str == "":
        return None
    s = str(tuition_str)
    # 移除非数字内容
    s = re.sub(r"[^\d.]", "", s)
    try:
        val = int(float(s))
        return val if val > 0 else None
    except ValueError:
        return None


def normalize_university_name(name: str) -> str:
    """标准化大学名称"""
    if not name:
        return name
    # 去除多余空格
    name = re.sub(r"\s+", "", name)
    # 统一括号
    name = name.replace("（", "(").replace("）", ")")
    return name


def fill_group_code(rows: list[dict]) -> list[dict]:
    """专业组代码补齐：如果某行的 group_code 为空，尝试从前一行推断"""
    last_group = ""
    for row in rows:
        gc = row.get("group_code", "").strip()
        if gc:
            last_group = gc
        elif last_group:
            row["group_code"] = last_group
    return rows


def clean_csv(input_path: str, output_path: str) -> dict:
    """清洗单个 CSV 文件，返回统计信息"""
    stats = {
        "total": 0,
        "removed_zero_plan": 0,
        "removed_empty_major": 0,
        "tuition_fixed": 0,
        "name_normalized": 0,
        "final": 0,
    }

    with open(input_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        header = reader.fieldnames

    stats["total"] = len(rows)

    cleaned = []
    for row in rows:
        # 剔除计划数为 0 或空白的记录
        plan_str = row.get("plan_count", "0").strip()
        try:
            plan_count = int(plan_str)
        except ValueError:
            plan_count = 0

        if plan_count <= 0:
            stats["removed_zero_plan"] += 1
            continue

        # 剔除专业名称为空的记录
        major_name = row.get("major_name", "").strip()
        if not major_name:
            stats["removed_empty_major"] += 1
            continue

        # 学费字段数值提取
        tuition_raw = row.get("tuition", "")
        if tuition_raw and not str(tuition_raw).isdigit():
            numeric = extract_numeric_tuition(tuition_raw)
            if numeric:
                row["tuition"] = str(numeric)
                stats["tuition_fixed"] += 1

        # 大学名称标准化
        uni_name = row.get("university_name", "")
        if uni_name:
            normalized = normalize_university_name(uni_name)
            if normalized != uni_name:
                row["university_name"] = normalized
                stats["name_normalized"] += 1

        cleaned.append(row)

    # 补齐专业组代码
    cleaned = fill_group_code(cleaned)

    # 写入输出文件
    # 确保输出 header 包含新字段
    output_header = list(header)
    for col in ["batch", "lowest_score_2025", "lowest_rank_2025",
                 "is_new", "school_type", "major_category"]:
        if col not in output_header:
            output_header.append(col)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_header, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(cleaned)

    stats["final"] = len(cleaned)
    return stats


def main():
    import argparse
    parser = argparse.ArgumentParser(description="清洗招生计划 CSV 数据")
    parser.add_argument("input", nargs="?", help="输入 CSV 文件路径")
    parser.add_argument("output", nargs="?", help="输出 CSV 文件路径")
    args = parser.parse_args()

    if args.input and args.output:
        files = [(args.input, args.output)]
    else:
        files = [
            (str(DATA_DIR / "plans_2025.csv"), str(DATA_DIR / "plans_2025_cleaned.csv")),
            (str(DATA_DIR / "plans_2026.csv"), str(DATA_DIR / "plans_2026_cleaned.csv")),
        ]

    for input_path, output_path in files:
        if not Path(input_path).exists():
            print(f"⚠️  跳过不存在的文件: {input_path}")
            continue
        stats = clean_csv(input_path, output_path)
        print(f"\n📊 {Path(input_path).name}:")
        print(f"  总行数: {stats['total']}")
        print(f"  剔除(计划数≤0): {stats['removed_zero_plan']}")
        print(f"  剔除(专业名空): {stats['removed_empty_major']}")
        print(f"  学费修正: {stats['tuition_fixed']}")
        print(f"  名称标准化: {stats['name_normalized']}")
        print(f"  最终保留: {stats['final']}")
        print(f"  输出: {output_path}")


if __name__ == "__main__":
    main()
