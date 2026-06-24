#!/usr/bin/env python3
"""
ETL 脚本：从雪峰 Agent 的 admission_clean.db 导出录取历史数据
→ 生成 admission_history.csv（供 leakage_radar.py 的估值模型和维度6使用）

数据源: xuefeng-agent (MIT License, https://github.com/ziqihe10-droid/xuefeng-agent)
致谢: 感谢 ziqihe10-droid 开源的 24 万条官方投档线数据

字段映射:
  雪峰 admission 表          →  我们的 admission_history.csv
  province                   →  province
  year                       →  year
  category                   →  subject_group (映射: 综合→综合, 物理类→物理类, 历史类→历史类, 等)
  batch                      →  batch
  school_name                →  university_name (清洗 [公办]/[民办] 后缀)
  major_name                 →  major_name
  score                      →  lowest_score
  rank                       →  lowest_rank
  quota                      →  (丢弃, 我们的 schema 无此字段)
  source_file                →  source_file (保留用于溯源)

清洗规则:
  1. 过滤无效分数 (score IS NULL 或 score <= 0 或 score > 750)
  2. 清洗学校名: 去除 [公办]/[民办]/[中外合作] 等方括号后缀
  3. 统一科类: "普通类(首选物理)" → "物理类", "理科" → "物理类", 等
  4. 丢弃 school_name 或 major_name 为空的记录
  5. 补充占位字段以兼容 leakage_radar.py 的列期望:
     - university_code: 用 "XF" + 行号 占位
     - group_code: 用 "XF" 占位
     - major_code: 用 "XF" + 行号 占位
     - avg_score: None
     - applicant_count: None
"""
import sqlite3
import csv
import re
import os
from pathlib import Path

# ── 路径配置 ────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent          # backend/scripts/
BACKEND_DIR = HERE.parent                         # backend/
DATA_DIR = BACKEND_DIR / "data"                   # backend/data/
DB_PATH = DATA_DIR / "admission_clean.db"
OUTPUT_CSV = DATA_DIR / "admission_history.csv"

# ── 科类映射（雪峰 → 我们） ─────────────────────────────────────
CATEGORY_MAP = {
    "物理类": "物理类",
    "历史类": "历史类",
    "综合": "综合",
    "理科": "物理类",
    "文科": "历史类",
    "普通类(首选物理)": "物理类",
    "普通类(首选历史)": "历史类",
    "艺术类": "艺术类",
    "体育类": "体育类",
}


def clean_school_name(name: str) -> str:
    """清洗学校名：去除 [公办]/[民办]/[中外合作] 等方括号后缀。"""
    if not name:
        return ""
    # 去除末尾的 [xxx] 后缀
    cleaned = re.sub(r"\s*\[[^\]]+\]\s*$", "", name).strip()
    return cleaned


def map_category(raw: str) -> str:
    """统一科类字段。"""
    if not raw:
        return ""
    return CATEGORY_MAP.get(raw.strip(), raw.strip())


def main():
    if not DB_PATH.exists():
        print(f"❌ 数据库不存在: {DB_PATH}")
        print("   请先下载: curl -L -o data/admission_clean.db.gz "
              "\"https://github.com/ziqihe10-droid/xuefeng-agent/raw/master/admission_clean.db.gz\"")
        print("   然后解压: python3 -c \"import gzip,shutil; "
              "shutil.copyfileobj(gzip.open('data/admission_clean.db.gz','rb'),"
              "open('data/admission_clean.db','wb'))\"")
        return

    print(f"[ETL] 连接数据库: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # 统计原始数据
    c.execute("SELECT COUNT(*) FROM admission")
    total_raw = c.fetchone()[0]
    print(f"[ETL] 原始记录数: {total_raw:,}")

    # 查询有效数据
    # 过滤条件：(有分数 OR 有位次) 且 school_name/major_name 非空
    # 注意：山东数据"有位次无分数"，需保留用于维度6位次匹配
    c.execute("""
        SELECT province, year, category, batch, school_name, major_name, score, rank, source_file
        FROM admission
        WHERE (
            (score IS NOT NULL AND score > 0 AND score <= 750)
            OR (rank IS NOT NULL AND rank > 0)
        )
        AND school_name IS NOT NULL
        AND school_name != ''
        AND major_name IS NOT NULL
        AND major_name != ''
        ORDER BY province, year, school_name
    """)

    rows = c.fetchall()
    print(f"[ETL] 有效记录数 (有分数+有校名+有专业): {len(rows):,}")

    # 写 CSV
    fieldnames = [
        "year", "province", "subject_group", "batch",
        "university_code", "university_name",
        "group_code", "major_code", "major_name",
        "lowest_score", "lowest_rank",
        "avg_score", "applicant_count",
        "source_file",
    ]

    written = 0
    skipped = 0
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for i, row in enumerate(rows):
            province, year, category, batch, school_name, major_name, score, rank, source_file = row

            # 清洗
            clean_name = clean_school_name(school_name)
            if not clean_name:
                skipped += 1
                continue

            subject_group = map_category(category)

            writer.writerow({
                "year": year,
                "province": province,
                "subject_group": subject_group,
                "batch": batch or "",
                "university_code": f"XF{i}",
                "university_name": clean_name,
                "group_code": "XF",
                "major_code": f"XF{i}",
                "major_name": major_name,
                "lowest_score": score,
                "lowest_rank": rank if rank and rank > 0 else "",
                "avg_score": "",
                "applicant_count": "",
                "source_file": source_file or "",
            })
            written += 1

    conn.close()

    print(f"[ETL] ✅ 导出完成: {OUTPUT_CSV}")
    print(f"[ETL]    写入: {written:,} 条")
    print(f"[ETL]    跳过: {skipped:,} 条 (清洗后校名为空)")

    # 验证导出结果
    print(f"\n[ETL] 验证导出数据...")
    import pandas as pd
    df = pd.read_csv(OUTPUT_CSV)
    print(f"  总行数: {len(df):,}")
    print(f"  年份分布: {df['year'].value_counts().to_dict()}")
    print(f"  省份分布:")
    for prov, cnt in df["province"].value_counts().items():
        has_rank = df[(df["province"] == prov) & df["lowest_rank"].notna()].shape[0]
        print(f"    {prov:8s} {cnt:>8,} 条 (有位次: {has_rank:,})")
    print(f"  科类分布: {df['subject_group'].value_counts().to_dict()}")
    print(f"  有分数: {df['lowest_score'].notna().sum():,}")
    print(f"  有位次: {df['lowest_rank'].notna().sum():,}")
    print(f"  覆盖大学数: {df['university_name'].nunique():,}")


if __name__ == "__main__":
    main()
