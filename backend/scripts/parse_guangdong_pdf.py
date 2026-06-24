#!/usr/bin/env python3
"""
广东省教育考试院投档线 PDF 解析脚本

数据来源: 广东省教育考试院 (eea.gd.gov.cn) 官方发布的投档线 PDF
覆盖: 2025年本科普通类（物理）+ 本科普通类（历史）

PDF 表格结构（7列）:
  院校代码 | 院校名称 | 专业组代码 | 计划数 | 投档人数 | 投档最低分 | 投档最低排位

输出: 合并到 admission_history.csv（追加广东数据，替换雪峰的垃圾广东数据）
"""
import pdfplumber
import pandas as pd
import csv
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PDF_DIR = DATA_DIR / "guangdong_pdfs"
HISTORY_CSV = DATA_DIR / "admission_history.csv"

# 广东 PDF 文件
PDF_FILES = [
    {
        "path": PDF_DIR / "gd_2025_physics.pdf",
        "subject_group": "物理类",
        "year": 2025,
        "batch": "本科批",
    },
    {
        "path": PDF_DIR / "gd_2025_history.pdf",
        "subject_group": "历史类",
        "year": 2025,
        "batch": "本科批",
    },
]


def clean_cell(val):
    """清洗单元格：去除噪声字符，转整数。"""
    if val is None:
        return None
    s = str(val).strip()
    # 去除前缀噪声字（PDF 解析偶尔出现的"院""试"等字）
    s = re.sub(r"^[院试第\s]+", "", s)
    # 去除千分位逗号
    s = s.replace(",", "")
    if s == "" or s == "-":
        return None
    # 尝试转整数
    try:
        return int(float(s))
    except ValueError:
        return s  # 保留字符串（如院校名称）


def parse_pdf(filepath, subject_group, year, batch):
    """解析单个 PDF，返回行列表。"""
    rows = []
    pdf = pdfplumber.open(str(filepath))
    total_pages = len(pdf.pages)

    for page_idx, page in enumerate(pdf.pages):
        tables = page.extract_tables()
        for table in tables:
            for row in table:
                if not row or len(row) < 7:
                    continue
                # 跳过表头行
                if row[0] and "院校代码" in str(row[0]):
                    continue
                # 清洗
                code = clean_cell(row[0])
                name = clean_cell(row[1])
                group_code = clean_cell(row[2])
                plan_count = clean_cell(row[3])
                admit_count = clean_cell(row[4])
                score = clean_cell(row[5])
                rank = clean_cell(row[6])

                # 校验：必须有院校代码和名称
                if not code or not name:
                    continue
                # 分数必须是 0-750 的整数
                if not isinstance(score, int) or score <= 0 or score > 750:
                    score = None

                rows.append({
                    "year": year,
                    "province": "广东",
                    "subject_group": subject_group,
                    "batch": batch,
                    "university_code": str(code),
                    "university_name": str(name),
                    "group_code": str(group_code) if group_code else "",
                    "major_code": "",  # 广东投档线是专业组级，无具体专业
                    "major_name": f"专业组{group_code}" if group_code else "",
                    "lowest_score": score,
                    "lowest_rank": rank if isinstance(rank, int) and rank > 0 else None,
                    "avg_score": None,
                    "applicant_count": admit_count if isinstance(admit_count, int) else None,
                    "source_file": filepath.name,
                })

        if (page_idx + 1) % 20 == 0:
            print(f"  [{filepath.name}] 解析进度: {page_idx+1}/{total_pages} 页")

    pdf.close()
    return rows


def main():
    all_rows = []

    for pdf_info in PDF_FILES:
        if not pdf_info["path"].exists():
            print(f"⚠ 跳过（文件不存在）: {pdf_info['path']}")
            continue

        print(f"\n[解析] {pdf_info['path'].name} ({pdf_info['subject_group']})")
        rows = parse_pdf(
            pdf_info["path"],
            pdf_info["subject_group"],
            pdf_info["year"],
            pdf_info["batch"],
        )
        print(f"  ✅ 提取 {len(rows)} 行")
        all_rows.extend(rows)

    if not all_rows:
        print("❌ 未提取到任何数据")
        return

    print(f"\n[汇总] 广东数据总计: {len(all_rows)} 行")

    # 转为 DataFrame
    df_new = pd.DataFrame(all_rows)
    print(f"  物理类: {len(df_new[df_new['subject_group']=='物理类'])} 行")
    print(f"  历史类: {len(df_new[df_new['subject_group']=='历史类'])} 行")
    print(f"  有分数: {df_new['lowest_score'].notna().sum()} 行")
    print(f"  有位次: {df_new['lowest_rank'].notna().sum()} 行")
    print(f"  覆盖大学: {df_new['university_name'].nunique()} 所")

    # 读取现有的 admission_history.csv
    if HISTORY_CSV.exists():
        df_old = pd.read_csv(HISTORY_CSV)
        print(f"\n[合并] 现有历史数据: {len(df_old)} 行")

        # 删除雪峰的广东数据（只有 202 条垃圾数据）
        df_old_no_gd = df_old[df_old["province"] != "广东"]
        removed = len(df_old) - len(df_old_no_gd)
        print(f"  移除旧广东数据: {removed} 行")

        # 追加新广东数据
        df_merged = pd.concat([df_old_no_gd, df_new], ignore_index=True)
        print(f"  合并后总计: {len(df_merged)} 行")
    else:
        df_merged = df_new

    # 写回 CSV
    df_merged.to_csv(HISTORY_CSV, index=False, encoding="utf-8-sig")
    print(f"\n[完成] 已写入: {HISTORY_CSV}")

    # 验证
    print(f"\n[验证] 合并后省份分布:")
    for prov, cnt in df_merged["province"].value_counts().head(10).items():
        has_rank = df_merged[(df_merged["province"] == prov) & df_merged["lowest_rank"].notna()].shape[0]
        has_score = df_merged[(df_merged["province"] == prov) & df_merged["lowest_score"].notna()].shape[0]
        print(f"  {prov:8s} {cnt:>8,} 行 (有分:{has_score:,} 有位次:{has_rank:,})")

    print(f"\n[验证] 广东数据样本（前10行）:")
    gd_sample = df_merged[df_merged["province"] == "广东"].head(10)
    for _, row in gd_sample.iterrows():
        print(f"  {row['university_code']} | {row['university_name'][:18]:18s} | 组{row['group_code']} | 分{row['lowest_score']} | 位{row['lowest_rank']}")


if __name__ == "__main__":
    main()
