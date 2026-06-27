"""广东省 2024 历史投档线同步脚本。

把 raw 目录里的 2024 投档线数据（物理类 CSV + 历史类 PDF）导入 admission_history.csv。
2025 数据已入库，2026 投档线 7-8 月才有，2024 暂缺。

数据源：
- backend/data/raw/2024_physics_toudang.csv (3121 行)
- backend/data/raw/gd_2024_toudang_pdfs/gd_2024_history.pdf (730 KB)
- backend/data/raw/gd_2024_toudang_pdfs/gd_2024_physics.pdf (1328 KB)  ← 备用，CSV 已是 PDF 解析后的结果

输出：
- 追加到 backend/data/admission_history.csv（先删 2024 广东旧数据，再插入）
"""
from __future__ import annotations

import csv
import pdfplumber
import pandas as pd
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PDF_DIR = RAW_DIR / "gd_2024_toudang_pdfs"
# #14 root fix: 重定向到 data/raw/广东_admission_history.csv，禁止直接写主 CSV
_RAW_OUT = DATA_DIR / "raw"
_RAW_OUT.mkdir(exist_ok=True)
HISTORY_CSV = _RAW_OUT / "广东_admission_history.csv"

PHYSICS_CSV = RAW_DIR / "2024_physics_toudang.csv"
HISTORY_PDF = PDF_DIR / "gd_2024_history.pdf"


def clean_cell(val):
    """清洗单元格：去除噪声字符，转整数。"""
    if val is None:
        return None
    s = str(val).strip()
    s = re.sub(r"^[院试第\s]+", "", s)
    s = s.replace(",", "")
    if s == "" or s == "-":
        return None
    try:
        return int(float(s))
    except ValueError:
        return s


def parse_pdf(filepath: Path, subject_group: str, year: int, batch: str) -> list[dict]:
    """解析 PDF 表格 → admission_history 行列表。

    复用 parse_guangdong_pdf.py 的逻辑（已验证可用）。
    """
    rows = []
    with pdfplumber.open(str(filepath)) as pdf:
        total_pages = len(pdf.pages)
        for page_idx, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or len(row) < 7:
                        continue
                    if row[0] and "院校代码" in str(row[0]):
                        continue
                    code = clean_cell(row[0])
                    name = clean_cell(row[1])
                    group_code = clean_cell(row[2])
                    plan_count = clean_cell(row[3])
                    admit_count = clean_cell(row[4])
                    score = clean_cell(row[5])
                    rank = clean_cell(row[6])

                    if not code or not name:
                        continue
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
                        "major_code": "",
                        "major_name": f"专业组{group_code}" if group_code else "",
                        "lowest_score": score,
                        "lowest_rank": rank if isinstance(rank, int) and rank > 0 else None,
                        "avg_score": None,
                        "applicant_count": admit_count if isinstance(admit_count, int) else None,
                        "source_file": filepath.name,
                    })
            if (page_idx + 1) % 20 == 0:
                print(f"  [{filepath.name}] 解析进度: {page_idx+1}/{total_pages} 页")
    return rows


def load_physics_from_csv() -> list[dict]:
    """从 2024_physics_toudang.csv 读取（已 PDF 解析后的结构化数据）。"""
    print(f"\n[LOAD] 物理类 CSV: {PHYSICS_CSV}")
    if not PHYSICS_CSV.exists():
        raise RuntimeError(f"未找到 {PHYSICS_CSV}")
    df = pd.read_csv(PHYSICS_CSV)
    print(f"  CSV 行数: {len(df)}")
    print(f"  列名: {list(df.columns)}")
    rows = []
    for _, r in df.iterrows():
        # 列名: 院校代码, 院校名称, 专业组代码, 计划数, 投档人数, 投档最低分, 投档最低排位
        score = r.get("投档最低分")
        if pd.isna(score) or not isinstance(score, (int, float)):
            score = None
        else:
            score = int(score)
        rank = r.get("投档最低排位")
        if pd.isna(rank) or not isinstance(rank, (int, float)):
            rank = None
        else:
            rank = int(rank)
        admit_count = r.get("投档人数")
        if pd.isna(admit_count) or not isinstance(admit_count, (int, float)):
            admit_count = None
        else:
            admit_count = int(admit_count)
        rows.append({
            "year": 2024, "province": "广东",
            "subject_group": "物理类", "batch": "本科批",
            "university_code": str(r["院校代码"]),
            "university_name": str(r["院校名称"]),
            "group_code": str(r["专业组代码"]) if not pd.isna(r["专业组代码"]) else "",
            "major_code": "",
            "major_name": f"专业组{r['专业组代码']}" if not pd.isna(r["专业组代码"]) else "",
            "lowest_score": score,
            "lowest_rank": rank,
            "avg_score": None,
            "applicant_count": admit_count,
            "source_file": PHYSICS_CSV.name,
        })
    print(f"  [OK] 物理类: {len(rows)} 行")
    return rows


def load_history_from_pdf() -> list[dict]:
    """从 2024 历史类 PDF 解析。"""
    print(f"\n[LOAD] 历史类 PDF: {HISTORY_PDF}")
    if not HISTORY_PDF.exists():
        raise RuntimeError(f"未找到 {HISTORY_PDF}")
    rows = parse_pdf(HISTORY_PDF, subject_group="历史类", year=2024, batch="本科批")
    print(f"  [OK] 历史类: {len(rows)} 行")
    return rows


def merge_into_admission_history(new_rows: list[dict]) -> None:
    """合并新数据到 admission_history.csv（覆盖式更新 2024 广东数据）。"""
    print(f"\n[MERGE] 合并到 admission_history.csv")
    if HISTORY_CSV.exists():
        df_old = pd.read_csv(HISTORY_CSV)
        print(f"  原 CSV 行数: {len(df_old)}")
        # 删除旧的 2024 广东数据（避免重复）
        mask = (df_old["year"] == 2024) & (df_old["province"] == "广东")
        removed = mask.sum()
        df_old = df_old[~mask].copy()
        print(f"  删除旧 2024 广东: {removed} 行")
        # 追加新数据
        df_new = pd.DataFrame(new_rows)
        df_merged = pd.concat([df_old, df_new], ignore_index=True)
        print(f"  合并后: {len(df_merged)} 行")
    else:
        df_merged = pd.DataFrame(new_rows)

    # 备份原文件
    backup = HISTORY_CSV.with_suffix(".csv.bak_2024")
    if HISTORY_CSV.exists() and not backup.exists():
        backup.write_bytes(HISTORY_CSV.read_bytes())
        print(f"  [BACKUP] 原文件备份到: {backup.name}")

    df_merged.to_csv(HISTORY_CSV, index=False, encoding="utf-8-sig")
    print(f"  [OK] 已写入: {HISTORY_CSV}")

    # 验证
    print(f"\n[VERIFY] 合并后广东数据:")
    gd = df_merged[df_merged["province"] == "广东"]
    print(f"  总行数: {len(gd)}")
    print(f"  年份分布: {gd['year'].value_counts().to_dict()}")
    print(f"  科类分布: {gd.groupby(['year','subject_group']).size().to_dict()}")


def main():
    new_rows: list[dict] = []
    new_rows.extend(load_physics_from_csv())
    new_rows.extend(load_history_from_pdf())

    print(f"\n[汇总] 2024 广东投档线总计: {len(new_rows)} 行")
    by_sg = {}
    for r in new_rows:
        by_sg[r["subject_group"]] = by_sg.get(r["subject_group"], 0) + 1
    print(f"  按科类: {by_sg}")

    if not new_rows:
        print("  [FAIL] 无数据可入库")
        sys.exit(1)

    merge_into_admission_history(new_rows)
    print("\n[完成] 2024 广东投档线已入库")


if __name__ == "__main__":
    main()
