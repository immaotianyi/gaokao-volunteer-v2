#!/usr/bin/env python3
"""江西省教育考试院 高考数据同步管道（2024-2026）。

数据源: https://www.jxeea.cn
覆盖:
  - 一分一段表 2025/2026（物理类/历史类/三校生类，PDF）
  - 省控线 2024/2025/2026（硬编码，已从考试院官网核实）
  - 历史投档线 2024（本科批，PDF，162页）

注意:
  - 江西是 3+1+2 省份，subject_group 只用 物理类/历史类（三校生类单独标注）
  - 一分一段表原始 PDF 不分本专科，batch 统一填 "普通类"
  - 投档线 PDF 是专业组级（无专业级），major_code 填组代号
  - 所有 CSV 追加模式，去重，不覆盖其他省份数据

用法:
    python backend/scripts/sync_jiangxi_2026.py            # 全流程
    python backend/scripts/sync_jiangxi_2026.py --download  # 仅下载
    python backend/scripts/sync_jiangxi_2026.py --parse     # 仅解析+写入
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import httpx
import pandas as pd
import pdfplumber

# ─────────────────────────────────────────────────────────────────
# 路径配置
# ─────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw"

PROVINCE = "江西"

# ─────────────────────────────────────────────────────────────────
# 数据源 URL（已从考试院官网核实）
# ─────────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/pdf,text/html,*/*;q=0.8",
}

DOWNLOAD_FILES = [
    # 2026 一分一段表
    ("jiangxi_2026/jiangxi_yifenyiduan_2026_history.pdf",
     "http://www.jxeea.cn/jxsjyksy/gsgg91/2070077118825013248/xkO8FFcL.pdf"),
    ("jiangxi_2026/jiangxi_yifenyiduan_2026_physics.pdf",
     "http://www.jxeea.cn/jxsjyksy/gsgg91/2070077118825013248/lKCJfQem.pdf"),
    ("jiangxi_2026/jiangxi_yifenyiduan_2026_sanxiao.pdf",
     "http://www.jxeea.cn/jxsjyksy/gsgg91/2070077118825013248/4Cvw3CGy.pdf"),
    # 2025 一分一段表
    ("jiangxi_2025/jiangxi_yifenyiduan_2025_history.pdf",
     "http://www.jxeea.cn/jxsjyksy/tzgg92/1938096542515826688/WOn27m6u.pdf"),
    ("jiangxi_2025/jiangxi_yifenyiduan_2025_physics.pdf",
     "http://www.jxeea.cn/jxsjyksy/tzgg92/1938096542515826688/7L9uupAh.pdf"),
    ("jiangxi_2025/jiangxi_yifenyiduan_2025_sanxiao.pdf",
     "http://www.jxeea.cn/jxsjyksy/tzgg92/1938096542515826688/kppv25dX.pdf"),
    # 2024 一分一段表（江西首改 3+1+2）
    ("jiangxi_2024/jiangxi_yifenyiduan_2024_history.pdf",
     "http://www.jxeea.cn/jxsjyksy/gsgg91/1856091555406221312/2JEulIxD.pdf"),
    ("jiangxi_2024/jiangxi_yifenyiduan_2024_physics.pdf",
     "http://www.jxeea.cn/jxsjyksy/gsgg91/1856091555406221312/lgaPMP53.pdf"),
    ("jiangxi_2024/jiangxi_yifenyiduan_2024_sanxiao.pdf",
     "http://www.jxeea.cn/jxsjyksy/gsgg91/1856091555406221312/LUVSPiBv.pdf"),
    # 2024 投档线（本科批，普通类+三校生类）
    ("jiangxi_2024/jiangxi_toudang_2024.pdf",
     "http://www.jxeea.cn/jxsjyksy/tzgg92/1856090657296683008/MNwXup7k.pdf"),
]

# 省控线发布页 URL（写入 source_url 字段）
CONTROL_LINE_URLS = {
    2024: "http://www.jxeea.cn/jxsjyksy/tzgg92/content/content_1856090657296683008.html",
    2025: "http://www.jxeea.cn/jxsjyksy/tzgg92/content/content_1938096604994179072.html",
    2026: "http://www.jxeea.cn/jxsjyksy/gzdt38/pc/content/content_2069974603030765568.html",
}

# 省控线数据（已从考试院官网核实，硬编码避免 HTML 解析误差）
# 格式: (year, batch_section, batch, subject_group, line_type, lowest_score)
CONTROL_LINES = [
    # ─── 2024 ───
    (2024, "本科院校", "本科", "历史类", "总分", 463, CONTROL_LINE_URLS[2024]),
    (2024, "专科院校", "专科", "历史类", "总分", 270, CONTROL_LINE_URLS[2024]),
    (2024, "特殊类型招生", "特控线", "历史类", "总分", 532, CONTROL_LINE_URLS[2024]),
    (2024, "本科院校", "本科", "物理类", "总分", 448, CONTROL_LINE_URLS[2024]),
    (2024, "专科院校", "专科", "物理类", "总分", 240, CONTROL_LINE_URLS[2024]),
    (2024, "特殊类型招生", "特控线", "物理类", "总分", 520, CONTROL_LINE_URLS[2024]),
    (2024, "本科院校", "本科", "三校生类", "总分", 503, CONTROL_LINE_URLS[2024]),
    (2024, "专科院校", "专科", "三校生类", "总分", 270, CONTROL_LINE_URLS[2024]),
    # ─── 2025 ───
    (2025, "本科院校", "本科", "历史类", "总分", 486, CONTROL_LINE_URLS[2025]),
    (2025, "专科院校", "专科", "历史类", "总分", 290, CONTROL_LINE_URLS[2025]),
    (2025, "特殊类型招生", "特控线", "历史类", "总分", 539, CONTROL_LINE_URLS[2025]),
    (2025, "本科院校", "本科", "物理类", "总分", 429, CONTROL_LINE_URLS[2025]),
    (2025, "专科院校", "专科", "物理类", "总分", 240, CONTROL_LINE_URLS[2025]),
    (2025, "特殊类型招生", "特控线", "物理类", "总分", 505, CONTROL_LINE_URLS[2025]),
    (2025, "本科院校", "本科", "三校生类", "总分", 510, CONTROL_LINE_URLS[2025]),
    (2025, "专科院校", "专科", "三校生类", "总分", 240, CONTROL_LINE_URLS[2025]),
    # ─── 2026 ───
    (2026, "本科院校", "本科", "历史类", "总分", 479, CONTROL_LINE_URLS[2026]),
    (2026, "专科院校", "专科", "历史类", "总分", 220, CONTROL_LINE_URLS[2026]),
    (2026, "特殊类型招生", "特控线", "历史类", "总分", 535, CONTROL_LINE_URLS[2026]),
    (2026, "本科院校", "本科", "物理类", "总分", 412, CONTROL_LINE_URLS[2026]),
    (2026, "专科院校", "专科", "物理类", "总分", 200, CONTROL_LINE_URLS[2026]),
    (2026, "特殊类型招生", "特控线", "物理类", "总分", 505, CONTROL_LINE_URLS[2026]),
    (2026, "本科院校", "本科", "三校生类", "总分", 448, CONTROL_LINE_URLS[2026]),
    (2026, "专科院校", "专科", "三校生类", "总分", 220, CONTROL_LINE_URLS[2026]),
]

# 一分一段表 PDF 路径映射
YIFENYIDUAN_PDFS = [
    (2026, "物理类", RAW_DIR / "jiangxi_2026/jiangxi_yifenyiduan_2026_physics.pdf"),
    (2026, "历史类", RAW_DIR / "jiangxi_2026/jiangxi_yifenyiduan_2026_history.pdf"),
    (2026, "三校生类", RAW_DIR / "jiangxi_2026/jiangxi_yifenyiduan_2026_sanxiao.pdf"),
    (2025, "物理类", RAW_DIR / "jiangxi_2025/jiangxi_yifenyiduan_2025_physics.pdf"),
    (2025, "历史类", RAW_DIR / "jiangxi_2025/jiangxi_yifenyiduan_2025_history.pdf"),
    (2025, "三校生类", RAW_DIR / "jiangxi_2025/jiangxi_yifenyiduan_2025_sanxiao.pdf"),
    (2024, "物理类", RAW_DIR / "jiangxi_2024/jiangxi_yifenyiduan_2024_physics.pdf"),
    (2024, "历史类", RAW_DIR / "jiangxi_2024/jiangxi_yifenyiduan_2024_history.pdf"),
    (2024, "三校生类", RAW_DIR / "jiangxi_2024/jiangxi_yifenyiduan_2024_sanxiao.pdf"),
]

TOUDANG_PDF = RAW_DIR / "jiangxi_2024/jiangxi_toudang_2024.pdf"


# ═══════════════════════════════════════════════════════════════
# 阶段 1：DOWNLOAD
# ═══════════════════════════════════════════════════════════════
def download_files():
    """下载所有原始 PDF。"""
    print(f"\n[DOWNLOAD] 下载江西考试院 PDF")
    ok, fail = 0, 0
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=60) as c:
        for rel, url in DOWNLOAD_FILES:
            out = RAW_DIR / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.exists() and out.stat().st_size > 5000:
                print(f"  [SKIP] {rel} ({out.stat().st_size} bytes)")
                ok += 1
                continue
            try:
                r = c.get(url)
                if r.status_code == 200 and len(r.content) > 5000:
                    out.write_bytes(r.content)
                    print(f"  [OK]   {rel} ({len(r.content)} bytes)")
                    ok += 1
                else:
                    print(f"  [FAIL] {rel}: status={r.status_code} size={len(r.content)}")
                    fail += 1
            except Exception as e:
                print(f"  [ERR]  {rel}: {e}")
                fail += 1
    print(f"  总计: {ok} 成功, {fail} 失败")
    return fail == 0


# ═══════════════════════════════════════════════════════════════
# 阶段 2：PARSE - 一分一段表
# ═══════════════════════════════════════════════════════════════
def _clean_cell(val):
    """清洗单元格。"""
    if val is None:
        return None
    s = str(val).strip().replace("\n", "").replace(" ", "")
    if s == "" or s == "-":
        return None
    return s


def _parse_int(val):
    s = _clean_cell(val)
    if s is None:
        return None
    # 处理 "698及以上" → 698
    m = re.match(r"^(\d+)", s)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def parse_yifenyiduan_pdf(pdf_path: Path, year: int, subject_group: str) -> list[dict]:
    """解析一分一段表 PDF。

    表格结构（3列）: 分数 | 人数 | 累计人数
    最高分用 "XXX及以上" 表示。
    江西一分一段表不分本专科，batch 统一填 "普通类"。
    """
    rows = []
    if not pdf_path.exists():
        print(f"  [WARN] 文件不存在: {pdf_path}")
        return rows

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or len(row) < 3:
                        continue
                    score_raw = _clean_cell(row[0])
                    if not score_raw:
                        continue
                    # 跳过表头
                    if "分数" in score_raw:
                        continue
                    score = _parse_int(score_raw)
                    if score is None or score < 0 or score > 750:
                        continue
                    segment = _parse_int(row[1])
                    cumulative = _parse_int(row[2])
                    if segment is None or cumulative is None:
                        continue
                    if segment < 0 or cumulative < 0:
                        continue
                    # cumulative 上限校验（防止水印噪声）
                    if cumulative > 500000:
                        continue
                    rows.append({
                        "province": PROVINCE,
                        "year": year,
                        "subject_group": subject_group,
                        "batch": "普通类",
                        "score": score,
                        "segment_count": segment,
                        "cumulative_count": cumulative,
                    })
    return rows


def parse_all_yifenyiduan() -> list[dict]:
    """解析所有一分一段表 PDF。"""
    print(f"\n[PARSE] 一分一段表 PDF")
    all_rows = []
    for year, sg, pdf_path in YIFENYIDUAN_PDFS:
        rows = parse_yifenyiduan_pdf(pdf_path, year, sg)
        print(f"  [{pdf_path.name}] {year} {sg}: {len(rows)} 行")
        all_rows.extend(rows)
    print(f"  一分一段表总计: {len(all_rows)} 行")
    return all_rows


# ═══════════════════════════════════════════════════════════════
# 阶段 3：PARSE - 省控线（硬编码数据）
# ═══════════════════════════════════════════════════════════════
def build_control_lines() -> list[dict]:
    """构建省控线数据（已从考试院官网核实，硬编码）。"""
    print(f"\n[BUILD] 省控线（硬编码，已核实）")
    rows = []
    for year, batch_section, batch, sg, line_type, score, url in CONTROL_LINES:
        rows.append({
            "province": PROVINCE,
            "year": year,
            "batch_section": batch_section,
            "batch": batch,
            "subject_group": sg,
            "line_type": line_type,
            "lowest_score": score,
            "source_url": url,
        })
    print(f"  省控线总计: {len(rows)} 行 (2024:{sum(1 for r in rows if r['year']==2024)}, "
          f"2025:{sum(1 for r in rows if r['year']==2025)}, "
          f"2026:{sum(1 for r in rows if r['year']==2026)})")
    return rows


# ═══════════════════════════════════════════════════════════════
# 阶段 4：PARSE - 投档线（admission_history）
# ═══════════════════════════════════════════════════════════════
def parse_toudang_pdf(pdf_path: Path) -> list[dict]:
    """解析 2024 本科投档线 PDF。

    表格结构（9列）:
        序号 | 科类 | 院校代码 | 院校名称 | 专业组代号 | 专业组名称 | 投档线 | 最低投档排名 | 备注

    科类字段含: 历史类 / 物理类 / 三校生类
    spec 要求 subject_group 只能是 物理类/历史类，三校生类跳过。

    admission_history.csv 字段:
        year, province, subject_group, batch, university_code, university_name,
        group_code, major_code, major_name, lowest_score, lowest_rank,
        avg_score, applicant_count, source_file
    """
    rows = []
    if not pdf_path.exists():
        print(f"  [WARN] 文件不存在: {pdf_path}")
        return rows

    print(f"\n[PARSE] 2024 投档线 PDF ({pdf_path.name})")
    with pdfplumber.open(str(pdf_path)) as pdf:
        total_pages = len(pdf.pages)
        for page_idx, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or len(row) < 8:
                        continue
                    # 跳过表头行
                    if row[0] and "序号" in str(row[0]):
                        continue
                    seq = _clean_cell(row[0])
                    subject = _clean_cell(row[1])
                    uni_code = _clean_cell(row[2])
                    uni_name = _clean_cell(row[3])
                    group_code = _clean_cell(row[4])
                    group_name = _clean_cell(row[5])
                    score = _parse_int(row[6])
                    rank = _parse_int(row[7])

                    # 必须有科类和院校代码
                    if not subject or not uni_code or not uni_name:
                        continue
                    # spec 要求 subject_group 只能是物理类/历史类，跳过三校生类
                    if subject not in ("物理类", "历史类"):
                        continue
                    # 分数必须合理
                    if score is None or score < 200 or score > 750:
                        continue

                    rows.append({
                        "year": 2024,
                        "province": PROVINCE,
                        "subject_group": subject,
                        "batch": "本科批",
                        "university_code": str(uni_code),
                        "university_name": str(uni_name),
                        "group_code": str(group_code) if group_code else "",
                        "major_code": str(group_code) if group_code else "",
                        "major_name": str(group_name) if group_name else f"第{group_code}组",
                        "lowest_score": float(score),
                        "lowest_rank": float(rank) if rank and rank > 0 else "",
                        "avg_score": "",
                        "applicant_count": "",
                        "source_file": pdf_path.name,
                    })

            if (page_idx + 1) % 30 == 0:
                print(f"  解析进度: {page_idx+1}/{total_pages} 页, 累计 {len(rows)} 行")

    print(f"  投档线总计: {len(rows)} 行 "
          f"(物理类:{sum(1 for r in rows if r['subject_group']=='物理类')}, "
          f"历史类:{sum(1 for r in rows if r['subject_group']=='历史类')})")
    return rows


# ═══════════════════════════════════════════════════════════════
# 阶段 5：LOAD - 追加写入 CSV（去重）
# ═══════════════════════════════════════════════════════════════
def append_to_csv(new_rows: list[dict], csv_filename: str, dedup_cols: list[str]) -> int:
    """安全追加数据到 CSV（按 dedup_cols 去重）。

    返回新增行数（去重后）。
    """
    if not new_rows:
        print(f"  [SKIP] {csv_filename}: 无新数据")
        return 0

    csv_path = DATA_DIR / csv_filename
    # #14 root fix: 重定向到 data/raw/{省}_{文件名}，禁止直接写主 CSV
    _raw_dir = DATA_DIR / "raw"
    _raw_dir.mkdir(exist_ok=True)
    csv_path = _raw_dir / f"{PROVINCE}_{csv_path.name}"
    new_df = pd.DataFrame(new_rows)

    if csv_path.exists():
        existing = pd.read_csv(csv_path, dtype=str)
        # 删除目标省份的旧数据（避免重复追加导致重复行）
        # 但保留其他省份数据
        if "province" in existing.columns:
            existing_other = existing[existing["province"] != PROVINCE]
            existing_prov = existing[existing["province"] == PROVINCE]
        else:
            existing_other = existing.iloc[0:0]
            existing_prov = existing.iloc[0:0]
        # 合并：其他省份 + 旧江西数据 + 新江西数据
        merged = pd.concat([existing_other, existing_prov, new_df], ignore_index=True)
        # 统一 dedup_cols 为字符串再去重（避免 int/str 类型不一致导致去重失效）
        for col in dedup_cols:
            if col in merged.columns:
                merged[col] = merged[col].astype(str)
        merged = merged.drop_duplicates(subset=dedup_cols, keep="last")
        # 重新排序：其他省份在前，江西在后（按 dedup_cols 排序江西部分）
        other = merged[merged["province"] != PROVINCE] if "province" in merged.columns else merged.iloc[0:0]
        prov = merged[merged["province"] == PROVINCE] if "province" in merged.columns else merged
        prov = prov.sort_values(by=dedup_cols)
        merged = pd.concat([other, prov], ignore_index=True)
    else:
        merged = new_df.copy()
        for col in dedup_cols:
            if col in merged.columns:
                merged[col] = merged[col].astype(str)
        merged = merged.drop_duplicates(subset=dedup_cols, keep="last")
        merged = merged.sort_values(by=dedup_cols)

    # 空值填空字符串（不写 null/NA/None）
    merged = merged.fillna("")
    merged.to_csv(csv_path, index=False, encoding="utf-8")
    n_new = len(new_df)
    n_after = len(merged[merged["province"] == PROVINCE]) if "province" in merged.columns else len(merged)
    print(f"  [OK] {csv_filename}: 追加 {n_new} 行 → 江西总计 {n_after} 行")
    return n_new


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="仅下载原始 PDF")
    parser.add_argument("--parse", action="store_true", help="仅解析并写入 CSV")
    args = parser.parse_args()

    # 默认全流程
    if not args.download and not args.parse:
        args.download = True
        args.parse = True

    print(f"========== 江西 高考数据同步 ==========")
    print(f"省份: {PROVINCE} (3+1+2 模式)")
    print(f"工作目录: {DATA_DIR}")

    if args.download:
        if not download_files():
            print("[WARN] 部分文件下载失败，继续处理已下载的")

    if not args.parse:
        return

    # ─── 一分一段表 ───
    yfd_rows = parse_all_yifenyiduan()
    # 按年份分组写入
    yfd_2024 = [r for r in yfd_rows if r["year"] == 2024]
    yfd_2025 = [r for r in yfd_rows if r["year"] == 2025]
    yfd_2026 = [r for r in yfd_rows if r["year"] == 2026]
    append_to_csv(yfd_2024, "yifenyiduan_2024.csv",
                  ["province", "year", "subject_group", "batch", "score"])
    append_to_csv(yfd_2025, "yifenyiduan_2025.csv",
                  ["province", "year", "subject_group", "batch", "score"])
    append_to_csv(yfd_2026, "yifenyiduan_2026.csv",
                  ["province", "year", "subject_group", "batch", "score"])

    # ─── 省控线 ───
    cl_rows = build_control_lines()
    cl_2024 = [r for r in cl_rows if r["year"] == 2024]
    cl_2025 = [r for r in cl_rows if r["year"] == 2025]
    cl_2026 = [r for r in cl_rows if r["year"] == 2026]
    append_to_csv(cl_2024, "control_line_2024.csv",
                  ["province", "year", "batch_section", "batch", "subject_group", "line_type"])
    append_to_csv(cl_2025, "control_line_2025.csv",
                  ["province", "year", "batch_section", "batch", "subject_group", "line_type"])
    append_to_csv(cl_2026, "control_line_2026.csv",
                  ["province", "year", "batch_section", "batch", "subject_group", "line_type"])

    # ─── 投档线（admission_history） ───
    td_rows = parse_toudang_pdf(TOUDANG_PDF)
    append_to_csv(td_rows, "admission_history.csv",
                  ["year", "province", "subject_group", "batch",
                   "university_code", "group_code", "major_code"])

    # ─── 汇总报告 ───
    print(f"\n========== 江西 数据爬取报告 ==========")
    print(f"yifenyiduan_2024.csv: 追加 {len(yfd_2024)} 行 (物理类 {sum(1 for r in yfd_2024 if r['subject_group']=='物理类')} + 历史类 {sum(1 for r in yfd_2024 if r['subject_group']=='历史类')} + 三校生 {sum(1 for r in yfd_2024 if r['subject_group']=='三校生类')})")
    print(f"yifenyiduan_2025.csv: 追加 {len(yfd_2025)} 行 (物理类 {sum(1 for r in yfd_2025 if r['subject_group']=='物理类')} + 历史类 {sum(1 for r in yfd_2025 if r['subject_group']=='历史类')} + 三校生 {sum(1 for r in yfd_2025 if r['subject_group']=='三校生类')})")
    print(f"yifenyiduan_2026.csv: 追加 {len(yfd_2026)} 行 (物理类 {sum(1 for r in yfd_2026 if r['subject_group']=='物理类')} + 历史类 {sum(1 for r in yfd_2026 if r['subject_group']=='历史类')} + 三校生 {sum(1 for r in yfd_2026 if r['subject_group']=='三校生类')})")
    print(f"control_line_*.csv:   追加 {len(cl_rows)} 行 (2024:{len(cl_2024)}, 2025:{len(cl_2025)}, 2026:{len(cl_2026)})")
    print(f"admission_history.csv: 追加 {len(td_rows)} 行 (2024物理类:{sum(1 for r in td_rows if r['subject_group']=='物理类')}, 2024历史类:{sum(1 for r in td_rows if r['subject_group']=='历史类')})")
    print(f"\n注意: plans_2026.csv / plans_2025.csv 未写入 — 江西考试院官网未直接发布 PDF 招生计划（需大厚本）")
    print(f"原始文件: data/raw/jiangxi_{{2024,2025,2026}}/ (共 {len(DOWNLOAD_FILES)} 个文件)")


if __name__ == "__main__":
    main()
