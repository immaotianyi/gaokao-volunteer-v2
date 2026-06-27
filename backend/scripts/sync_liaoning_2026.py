#!/usr/bin/env python3
"""
辽宁 高考数据爬取脚本
数据源: https://www.lnzsks.com (辽宁招生考试之窗)

覆盖数据:
  - 一分一段表: 2025, 2026 (物理类 + 历史类, PDF)
  - 省控线: 2024, 2025, 2026 (HTML 公告)
  - 投档线(admission_history): 2023, 2024 (物理类 + 历史类, 专业级, Excel)

说明: 2025 投档线 Excel 加密无法解密; 2024 一分一段表 URL 未找到 — 这两项留空待补。
"""
from __future__ import annotations
import csv
import os
import re
import sys
from pathlib import Path

import openpyxl
import pandas as pd
import pdfplumber

# ─────────────────────────────────────────────────────────────────
# 路径配置
# ─────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw" / "liaoning_2026"

PROVINCE = "辽宁"
SUBJECT_GROUPS = ["物理类", "历史类"]

# PDF 水印噪声字符 (辽宁省高中等教育招生考试委员会办公室 + 表头散字)
WATERMARK_CHARS = "上中人以会公分办及员委宁室招教数生省等累考育计试辽高"

# 各年本科控制线 (用于一分一段表 batch 划分: >=本科线→本科批, <本科线→专科批)
BENKE_LINE = {
    (2026, "物理类"): 344,
    (2026, "历史类"): 442,
    (2025, "物理类"): 367,
    (2025, "历史类"): 437,
}

# 省控线来源 URL
CONTROL_LINE_URLS = {
    2026: "https://www.lnzsks.com/newsinfo/IMS_20260624_46115_UJql15dfN3.htm",
    2025: "https://www.lnzsks.com/newsinfo/IMS_20250624_44984_IBfYRUieb1.htm",
    2024: "https://www.lnzsks.com/newsinfo/IMS_20240624_44044_BsiQxPSqmG.htm",
}


# ═══════════════════════════════════════════════════════════════
# 阶段 1: 解析一分一段表 PDF
# ═══════════════════════════════════════════════════════════════
def clean_yifenyiduan_cell(cell: str) -> str:
    """清洗一分一段表单元格: 去除水印字符、换行、千分位逗号。"""
    if not cell:
        return ""
    s = str(cell)
    # 去除水印字符
    for ch in WATERMARK_CHARS:
        s = s.replace(ch, "")
    # 去除换行、空格归一
    s = s.replace("\n", " ").replace("\u3000", " ")
    # 去除千分位逗号 (6,028 → 6028)
    s = re.sub(r"(\d),(\d)", r"\1\2", s)
    return s.strip()


def parse_yifenyiduan_pdf(pdf_path: Path, year: int, subject_group: str) -> list[dict]:
    """解析单个一分一段表 PDF, 返回行列表。

    PDF 表格结构: 4 列并排布局, 每列 "分数 人数 累计"。
    单元格含竖排水印噪声, 需清洗后提取 3 个数字。
    最高分单元格含 "及以上" 标记。
    """
    rows: list[dict] = []
    benke = BENKE_LINE.get((year, subject_group), 400)

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue
                for row in table:
                    if not row:
                        continue
                    for cell in row:
                        if not cell:
                            continue
                        raw = str(cell)
                        # 跳过表头行
                        if "分数" in raw and "人数" in raw:
                            continue
                        is_top = "及以上" in raw.replace(" ", "") or "及以" in raw
                        cleaned = clean_yifenyiduan_cell(raw)
                        # 提取所有数字
                        nums = re.findall(r"\d+", cleaned)
                        if len(nums) < 3:
                            continue
                        try:
                            score = int(nums[0])
                            segment = int(nums[1])
                            cumulative = int(nums[2])
                        except (ValueError, IndexError):
                            continue
                        # 合理性校验
                        if score < 0 or score > 750:
                            continue
                        if cumulative > 1_000_000:
                            continue
                        # batch 划分
                        batch = "本科批" if score >= benke else "专科批"
                        rows.append({
                            "province": PROVINCE,
                            "year": year,
                            "subject_group": subject_group,
                            "batch": batch,
                            "score": score,
                            "segment_count": segment,
                            "cumulative_count": cumulative,
                        })
    # 去重 (同 province/year/subject_group/batch/score 只保留一行, 取累计最大)
    seen: dict[tuple, dict] = {}
    for r in rows:
        key = (r["province"], r["year"], r["subject_group"], r["batch"], r["score"])
        if key not in seen or r["cumulative_count"] > seen[key]["cumulative_count"]:
            seen[key] = r
    return list(seen.values())


# ═══════════════════════════════════════════════════════════════
# 阶段 2: 省控线 (从 HTML 公告提取, 此处硬编码已核实的数值)
# ═══════════════════════════════════════════════════════════════
def parse_control_line() -> list[dict]:
    """返回 2024/2025/2026 省控线数据 (普通类为主 + 主要艺术类本科)。"""
    rows: list[dict] = []

    # (year, subject_group, batch_section, batch, line_type, lowest_score)
    data = [
        # 2026
        (2026, "历史类", "特殊类型招生", "特控线", "总分", 527),
        (2026, "历史类", "本科院校", "本科", "总分", 442),
        (2026, "历史类", "专科院校", "专科", "总分", 150),
        (2026, "物理类", "特殊类型招生", "特控线", "总分", 508),
        (2026, "物理类", "本科院校", "本科", "总分", 344),
        (2026, "物理类", "专科院校", "专科", "总分", 150),
        (2026, "艺术类(历史)", "本科院校", "本科", "文化课总分", 331),
        (2026, "艺术类(物理)", "本科院校", "本科", "文化课总分", 258),
        (2026, "体育类(历史)", "本专科", "本专科", "文化课总分", 150),
        (2026, "体育类(物理)", "本专科", "本专科", "文化课总分", 150),
        # 2025
        (2025, "历史类", "特殊类型招生", "特控线", "总分", 522),
        (2025, "历史类", "本科院校", "本科", "总分", 437),
        (2025, "历史类", "专科院校", "专科", "总分", 150),
        (2025, "物理类", "特殊类型招生", "特控线", "总分", 515),
        (2025, "物理类", "本科院校", "本科", "总分", 367),
        (2025, "物理类", "专科院校", "专科", "总分", 150),
        (2025, "艺术类(历史)", "本科院校", "本科", "文化课总分", 327),
        (2025, "艺术类(物理)", "本科院校", "本科", "文化课总分", 275),
        (2025, "体育类(历史)", "本专科", "本专科", "文化课总分", 150),
        (2025, "体育类(物理)", "本专科", "本专科", "文化课总分", 150),
        # 2024
        (2024, "历史类", "特殊类型招生", "特控线", "总分", 510),
        (2024, "历史类", "本科院校", "本科", "总分", 400),
        (2024, "历史类", "专科院校", "专科", "总分", 150),
        (2024, "物理类", "特殊类型招生", "特控线", "总分", 510),
        (2024, "物理类", "本科院校", "本科", "总分", 368),
        (2024, "物理类", "专科院校", "专科", "总分", 150),
        (2024, "艺术类(历史)", "本科院校", "本科", "文化课总分", 300),
        (2024, "艺术类(物理)", "本科院校", "本科", "文化课总分", 276),
        (2024, "体育类(历史)", "本专科", "本专科", "文化课总分", 150),
        (2024, "体育类(物理)", "本专科", "本专科", "文化课总分", 150),
    ]
    for year, sg, section, batch, ltype, score in data:
        rows.append({
            "province": PROVINCE,
            "year": year,
            "batch_section": section,
            "batch": batch,
            "subject_group": sg,
            "line_type": ltype,
            "lowest_score": score,
            "source_url": CONTROL_LINE_URLS[year],
        })
    return rows


# ═══════════════════════════════════════════════════════════════
# 阶段 3: 解析投档线 Excel (admission_history)
# ═══════════════════════════════════════════════════════════════
def parse_toudang_xlsx(xlsx_path: Path, year: int, source_name: str) -> list[dict]:
    """解析投档线 Excel, 返回行列表。

    Excel 结构 (12 列, 数据从第 6 行开始):
      院校编号 | 招生院校 | 专业编号 | 招生专业 | 投档最低分 |
      语数成绩 | 语数最高 | 外语 | 首选科目 | 再选最高 | 再选次高 | 志愿号

    sheet 名标识科类: "历史学科类"→历史类, "物理学科类"→物理类
    辽宁投档线为专业级 (含专业编号/专业名称)。
    """
    rows: list[dict] = []
    wb = openpyxl.load_workbook(str(xlsx_path), read_only=True, data_only=True)
    for ws in wb.worksheets:
        sheet_name = ws.title or ""
        if "历史" in sheet_name:
            subject_group = "历史类"
        elif "物理" in sheet_name:
            subject_group = "物理类"
        else:
            continue
        count = 0
        for row_idx, row in enumerate(
            ws.iter_rows(min_row=6, values_only=True), start=6
        ):
            if not row or not row[0]:
                continue
            code = str(row[0]).strip() if row[0] is not None else ""
            name = str(row[1]).strip() if row[1] is not None else ""
            major_code = str(row[2]).strip() if row[2] is not None else ""
            major_name = str(row[3]).strip() if row[3] is not None else ""
            score_raw = row[4]
            # 投档最低分
            try:
                lowest_score = float(score_raw) if score_raw is not None else None
            except (ValueError, TypeError):
                lowest_score = None
            # 校验
            if not code or not name:
                continue
            if lowest_score is not None and (lowest_score < 0 or lowest_score > 750):
                lowest_score = None
            # 院校代码纯数字校验
            if not re.match(r"^\d{4,5}$", code):
                continue
            rows.append({
                "year": year,
                "province": PROVINCE,
                "subject_group": subject_group,
                "batch": "本科批",
                "university_code": code,
                "university_name": name,
                "group_code": code,  # 辽宁无专业组概念, 用院校代码
                "major_code": major_code,
                "major_name": major_name,
                "lowest_score": lowest_score,
                "lowest_rank": "",  # 辽宁投档线 PDF/Excel 不含位次
                "avg_score": "",
                "applicant_count": "",
                "source_file": source_name,
            })
            count += 1
        print(f"  [{source_name}/{sheet_name}] {subject_group}: {count} 行")
    wb.close()
    return rows


# ═══════════════════════════════════════════════════════════════
# 阶段 4: 追加写入 CSV (去重, 不覆盖已有数据)
# ═══════════════════════════════════════════════════════════════
def append_to_csv(new_rows: list[dict], csv_filename: str, dedup_cols: list[str]) -> int:
    """安全追加数据到 CSV (按 dedup_cols 去重)。

    追加模式: 保留已有数据, 仅追加新省份数据, 按 dedup_cols 去重。
    """
    if not new_rows:
        return 0
    csv_path = DATA_DIR / csv_filename
    # #14 root fix: 重定向到 data/raw/{省}_{文件名}，禁止直接写主 CSV
    _raw_dir = DATA_DIR / "raw"
    _raw_dir.mkdir(exist_ok=True)
    csv_path = _raw_dir / f"{PROVINCE}_{csv_path.name}"
    new_df = pd.DataFrame(new_rows)

    if csv_path.exists():
        existing = pd.read_csv(csv_path, dtype=str)
        # 删除已有的同省数据 (重跑时覆盖本省, 不影响其他省)
        if "province" in existing.columns:
            existing_no_prov = existing[existing["province"] != PROVINCE]
        else:
            existing_no_prov = existing
        merged = pd.concat([existing_no_prov, new_df], ignore_index=True)
    else:
        merged = new_df

    # 去重
    if all(c in merged.columns for c in dedup_cols):
        merged = merged.drop_duplicates(subset=dedup_cols, keep="last")
    else:
        merged = merged.drop_duplicates()

    # 空值处理: 不写 null/NA/None
    merged = merged.fillna("")
    merged.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return len(new_rows)


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════
def main():
    print(f"[{PROVINCE}] 开始解析数据...")
    stats = {}

    # ── 1. 一分一段表 ──
    print(f"\n[1/3] 解析一分一段表 PDF")
    yfd_rows = []
    yfd_files = [
        (RAW_DIR / "liaoning_yifenyiduan_2026_physics.pdf", 2026, "物理类"),
        (RAW_DIR / "liaoning_yifenyiduan_2026_history.pdf", 2026, "历史类"),
        (RAW_DIR / "liaoning_yifenyiduan_2025_wl.pdf", 2025, "物理类"),
        (RAW_DIR / "liaoning_yifenyiduan_2025_ls.pdf", 2025, "历史类"),
    ]
    yfd_by_year = {2024: 0, 2025: 0, 2026: 0}
    for pdf_path, year, sg in yfd_files:
        if not pdf_path.exists():
            print(f"  [SKIP] {pdf_path.name} 不存在")
            continue
        rows = parse_yifenyiduan_pdf(pdf_path, year, sg)
        scores = [r["score"] for r in rows]
        score_range = f"{min(scores)}-{max(scores)}" if scores else "N/A"
        print(f"  [辽宁] ✓ 已解析 {pdf_path.name} ({len(rows)}行, {sg}, 分数{score_range})")
        yfd_rows.extend(rows)
        yfd_by_year[year] += len(rows)

    # 写入 yifenyiduan_2025.csv 和 yifenyiduan_2026.csv
    for year, csv_name in [(2025, "yifenyiduan_2025.csv"), (2026, "yifenyiduan_2026.csv")]:
        year_rows = [r for r in yfd_rows if r["year"] == year]
        n = append_to_csv(year_rows, csv_name,
                          dedup_cols=["province", "year", "subject_group", "batch", "score"])
        stats[csv_name] = n
        print(f"  [辽宁] ✓ 写入 {csv_name}: 追加 {n} 行")

    # ── 2. 省控线 ──
    print(f"\n[2/3] 解析省控线")
    cl_rows = parse_control_line()
    cl_by_year = {}
    for r in cl_rows:
        cl_by_year.setdefault(r["year"], 0)
        cl_by_year[r["year"]] += 1
    for year, csv_name in [(2024, "control_line_2024.csv"),
                           (2025, "control_line_2025.csv"),
                           (2026, "control_line_2026.csv")]:
        year_rows = [r for r in cl_rows if r["year"] == year]
        n = append_to_csv(year_rows, csv_name,
                          dedup_cols=["province", "year", "batch_section", "batch",
                                      "subject_group", "line_type"])
        stats[csv_name] = n
        print(f"  [辽宁] ✓ 写入 {csv_name}: 追加 {n} 行 ({year}年)")

    # ── 3. 投档线 (admission_history) ──
    print(f"\n[3/3] 解析投档线 Excel (admission_history)")
    td_rows = []
    td_files = [
        (RAW_DIR / "liaoning_toudang_2023_w.xlsx", 2023, "2023历史.xlsx"),
        (RAW_DIR / "liaoning_toudang_2023_l.xlsx", 2023, "2023物理.xlsx"),
        (RAW_DIR / "liaoning_toudang_2024_w_extracted" / "w.xlsx", 2024, "2024历史.xlsx"),
        (RAW_DIR / "liaoning_toudang_2024_l_extracted" / "l.xlsx", 2024, "2024物理.xlsx"),
    ]
    td_by_year = {2023: {"物理类": 0, "历史类": 0},
                  2024: {"物理类": 0, "历史类": 0},
                  2025: {"物理类": 0, "历史类": 0}}
    for xlsx_path, year, source_name in td_files:
        if not xlsx_path.exists():
            print(f"  [SKIP] {xlsx_path} 不存在")
            continue
        rows = parse_toudang_xlsx(xlsx_path, year, source_name)
        for r in rows:
            td_by_year[year][r["subject_group"]] += 1
        td_rows.extend(rows)
    n_td = append_to_csv(td_rows, "admission_history.csv",
                         dedup_cols=["year", "province", "subject_group", "batch",
                                     "university_code", "major_code"])
    stats["admission_history.csv"] = n_td
    print(f"  [辽宁] ✓ 写入 admission_history.csv: 追加 {n_td} 行")

    # ── 统计报告 ──
    print(f"\n{'=' * 50}")
    print(f"========== {PROVINCE} 数据爬取报告 ==========")
    for k, v in stats.items():
        print(f"  {k}: 追加 {v} 行")
    print(f"\n  一分一段表明细:")
    for y, n in yfd_by_year.items():
        print(f"    {y}年: {n} 行")
    print(f"\n  省控线明细:")
    for y, n in cl_by_year.items():
        print(f"    {y}年: {n} 条")
    print(f"\n  投档线明细:")
    for y, d in td_by_year.items():
        print(f"    {y}年: 物理类 {d['物理类']} + 历史类 {d['历史类']}")
    print(f"\n  原始文件: {RAW_DIR}")
    print(f"  [辽宁] ✓ 爬取完成")
    print(f"\n  ⚠ 注意: 2025 投档线 Excel 加密无法解密; 2024 一分一段表 URL 未找到 — 这两项待补。")
    print(f"  ⚠ 完成后请重启后端服务 (uvicorn main:app) 以加载新数据。")


if __name__ == "__main__":
    main()
