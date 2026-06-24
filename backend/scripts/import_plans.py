"""
招生计划数据导入脚本 — 支持从多来源批量导入

用法:
  # 从 Excel 导入
  python3 scripts/import_plans.py --source excel --file plans.xlsx --year 2026

  # 从 CSV 追加
  python3 scripts/import_plans.py --source csv --file new_plans.csv --year 2026

  # 预览当前数据
  python3 scripts/import_plans.py --preview

CSV 列要求:
  province, subject_group, university_code, university_name,
  group_code, major_code, major_name, plan_count, tuition

注意: 当前仅广东物理类 6 校 37 条数据。
      需从广东省教育考试院获取完整招生专业目录进行扩充。
      其他省份（河南、山东、四川、湖南、江苏）需单独获取。
"""
import argparse
import csv
import os
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
REQUIRED_COLUMNS = [
    "province", "subject_group", "university_code", "university_name",
    "group_code", "major_code", "major_name", "plan_count",
]


def preview_plans():
    """预览当前数据概况"""
    for csv_file in sorted(DATA_DIR.glob("plans_*.csv")):
        with open(csv_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        provinces = set(r.get("province", "") for r in rows)
        unis = set(r.get("university_name", "") for r in rows)
        subjects = set(r.get("subject_group", "") for r in rows)

        print(f"\n📄 {csv_file.name}")
        print(f"   总行数: {len(rows)}")
        print(f"   省份: {', '.join(sorted(provinces))}")
        print(f"   科类: {', '.join(sorted(subjects))}")
        print(f"   大学: {', '.join(sorted(unis))}")


def import_csv(source_file: str, year: int, append: bool = False):
    """从 CSV 导入招生计划数据"""
    source_path = Path(source_file)
    if not source_path.exists():
        print(f"❌ 文件不存在: {source_file}")
        sys.exit(1)

    with open(source_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        new_rows = list(reader)

    # 校验列
    missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        print(f"❌ 缺少必要列: {missing}")
        print(f"   现有列: {reader.fieldnames}")
        sys.exit(1)

    target_file = DATA_DIR / f"plans_{year}.csv"

    if append and target_file.exists():
        # 追加模式
        with open(target_file, encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
        # 按联合主键去重
        existing_keys = set()
        for r in existing:
            key = (r["university_code"], r["group_code"], r["major_code"])
            existing_keys.add(key)

        added = 0
        for r in new_rows:
            key = (r["university_code"], r["group_code"], r["major_code"])
            if key not in existing_keys:
                existing.append(r)
                added += 1

        fieldnames = list(existing[0].keys())
        with open(target_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(existing)

        print(f"✅ 追加到 {target_file.name}: 新增 {added} 条，总计 {len(existing)} 条")
    else:
        # 新建模式
        fieldnames = list(new_rows[0].keys())
        with open(target_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(new_rows)

        print(f"✅ 创建 {target_file.name}: {len(new_rows)} 条记录")

    # 显示新增概况
    new_unis = set(r.get("university_name", "") for r in new_rows)
    new_provinces = set(r.get("province", "") for r in new_rows)
    print(f"   新增大学: {len(new_unis)} 所")
    print(f"   覆盖省份: {', '.join(sorted(new_provinces))}")


def main():
    parser = argparse.ArgumentParser(description="招生计划数据导入工具")
    parser.add_argument("--source", choices=["csv", "excel"], help="数据来源")
    parser.add_argument("--file", help="源文件路径")
    parser.add_argument("--year", type=int, default=2026, help="年份")
    parser.add_argument("--append", action="store_true", help="追加而非覆盖")
    parser.add_argument("--preview", action="store_true", help="预览当前数据")
    args = parser.parse_args()

    if args.preview:
        preview_plans()
        return

    if not args.source or not args.file:
        parser.print_help()
        print("\n提示: 使用 --preview 查看当前数据概况")
        return

    if args.source == "csv":
        import_csv(args.file, args.year, args.append)
    elif args.source == "excel":
        print("⚠️ Excel 导入需要 openpyxl 库: pip install openpyxl")
        print("   或先用 Excel 另存为 CSV，再用 --source csv 导入")
        sys.exit(1)


if __name__ == "__main__":
    main()
