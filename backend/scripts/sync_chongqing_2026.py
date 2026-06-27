#!/usr/bin/env python3
"""重庆市教育考试院 高考数据同步脚本

数据源:
- 一分一段表 HTML: https://www.cqksy.cn/uploadFile/infopub/{year}/{ptgk|pg}/yfd/{wk|lk}.htm
- 2026 省控线 HTML: https://www.cqksy.cn/h5/article/2026-06/24/content_7003.html
- 2025 投档线 PDF (物理/历史): 已下载到 data/raw/chongqing_2026/

输出:
- yifenyiduan_2025.csv / yifenyiduan_2026.csv (追加)
- control_line_2024.csv / control_line_2025.csv / control_line_2026.csv (追加)
- admission_history.csv (追加 2025 重庆投档线)
"""
from __future__ import annotations

import csv
import os
import re
import sys
from pathlib import Path
from typing import Iterable

import httpx
import pandas as pd
import pdfplumber
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────────────────────────
# 路径配置
# ─────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw" / "chongqing_2026"
ERROR_CSV = RAW_DIR.parent / "chongqing_errors.csv"

PROVINCE = "重庆"
SUBJECT_GROUPS = ["物理类", "历史类"]

# 一分一段表 HTML 源
YIFENYIDUAN_SOURCES = [
    (2026, "物理类", RAW_DIR / "yifenyiduan_2026_physics.html",
     "https://www.cqksy.cn/uploadFile/infopub/2026/ptgk/yfd/lk.htm"),
    (2026, "历史类", RAW_DIR / "yifenyiduan_2026_history.html",
     "https://www.cqksy.cn/uploadFile/infopub/2026/ptgk/yfd/wk.htm"),
    (2025, "物理类", RAW_DIR / "yifenyiduan_2025_physics.html",
     "https://www.cqksy.cn/uploadFile/infopub/2025/pg/yfd/lk.htm"),
    (2025, "历史类", RAW_DIR / "yifenyiduan_2025_history.html",
     "https://www.cqksy.cn/uploadFile/infopub/2025/pg/yfd/wk.htm"),
]

# 省控线源
CONTROL_LINE_2026_HTML = RAW_DIR / "control_line_2026.html"
CONTROL_LINE_2026_URL = "https://www.cqksy.cn/h5/article/2026-06/24/content_7003.html"

# 2025 省控线: 考试院页面 content_6644.html 是图片格式，文本数据来自重庆市政府转载
# 来源: https://jw.cq.gov.cn/zwxx_209/gggs/202506/t20250624_14738643_wap.html
CONTROL_LINE_2025_URL = "https://www.cqksy.cn/h5/article/2025-06/24/content_6644.html"
CONTROL_LINE_2025_DATA = [
    # (batch_section, batch, subject_group, line_type, lowest_score)
    ("普通类", "本科批", "历史类", "总分", 438),
    ("普通类", "特殊类型资格线", "历史类", "总分", 515),
    ("普通类", "专科批", "历史类", "总分", 180),
    ("普通类", "本科批", "物理类", "总分", 425),
    ("普通类", "特殊类型资格线", "物理类", "总分", 498),
    ("普通类", "专科批", "物理类", "总分", 180),
    ("艺术类", "本科批", "美术与设计类", "文化分数线", 332),
    ("艺术类", "专科批", "美术与设计类", "文化分数线", 180),
    ("艺术类", "本科批", "美术与设计类", "专业分数线", 190),
    ("艺术类", "本科批", "音乐教育", "文化分数线", 350),
    ("艺术类", "专科批", "音乐教育", "文化分数线", 190),
    ("艺术类", "本科批", "音乐教育", "专业分数线", 185),
    ("艺术类", "本科批", "音乐表演(声乐)", "文化分数线", 300),
    ("艺术类", "专科批", "音乐表演(声乐)", "文化分数线", 180),
    ("艺术类", "本科批", "音乐表演(声乐)", "专业分数线", 180),
    ("艺术类", "本科批", "音乐表演(器乐)", "文化分数线", 300),
    ("艺术类", "专科批", "音乐表演(器乐)", "文化分数线", 180),
    ("艺术类", "本科批", "音乐表演(器乐)", "专业分数线", 180),
    ("艺术类", "本科批", "舞蹈类", "文化分数线", 253),
    ("艺术类", "专科批", "舞蹈类", "文化分数线", 180),
    ("艺术类", "本科批", "舞蹈类", "专业分数线", 190),
    ("艺术类", "本科批", "戏剧影视表演", "文化分数线", 363),
    ("艺术类", "专科批", "戏剧影视表演", "文化分数线", 180),
    ("艺术类", "本科批", "戏剧影视表演", "专业分数线", 195),
    ("艺术类", "本科批", "服装表演", "文化分数线", 350),
    ("艺术类", "专科批", "服装表演", "文化分数线", 180),
    ("艺术类", "本科批", "服装表演", "专业分数线", 200),
    ("艺术类", "本科批", "戏剧影视导演", "文化分数线", 401),
    ("艺术类", "专科批", "戏剧影视导演", "文化分数线", 190),
    ("艺术类", "本科批", "戏剧影视导演", "专业分数线", 200),
    ("艺术类", "本科批", "播音与主持类", "文化分数线", 372),
    ("艺术类", "专科批", "播音与主持类", "文化分数线", 190),
    ("艺术类", "本科批", "播音与主持类", "专业分数线", 180),
    ("艺术类", "本科批", "书法类", "文化分数线", 354),
    ("艺术类", "专科批", "书法类", "文化分数线", 190),
    ("艺术类", "本科批", "书法类", "专业分数线", 200),
    ("体育类", "本科批", "体育类", "文化分数线", 368),
    ("体育类", "本科批", "体育类", "专业分数线", 73),
    ("体育类", "专科批", "体育类", "文化分数线", 180),
]

# 2024 省控线: 考试院页面已下线，数据来自 cqzk.com.cn 转载（仍为考试院官方数据）
# 来源: https://www.cqzk.com.cn/PTGK/PTGK_news/1805083674113437696.html
CONTROL_LINE_2024_URL = "https://www.cqzk.com.cn/PTGK/PTGK_news/1805083674113437696.html"
CONTROL_LINE_2024_DATA = [
    ("普通类", "本科批", "历史类", "总分", 428),
    ("普通类", "特殊类型资格线", "历史类", "总分", 506),
    ("普通类", "专科批", "历史类", "总分", 180),
    ("普通类", "本科批", "物理类", "总分", 427),
    ("普通类", "特殊类型资格线", "物理类", "总分", 499),
    ("普通类", "专科批", "物理类", "总分", 180),
    ("艺术类", "本科批", "美术与设计类", "文化分数线", 322),
    ("艺术类", "专科批", "美术与设计类", "文化分数线", 180),
    ("艺术类", "本科批", "美术与设计类", "专业分数线", 185),
    ("艺术类", "本科批", "音乐教育", "文化分数线", 340),
    ("艺术类", "专科批", "音乐教育", "文化分数线", 190),
    ("艺术类", "本科批", "音乐教育", "专业分数线", 190),
    ("艺术类", "本科批", "音乐表演(声乐)", "文化分数线", 295),
    ("艺术类", "专科批", "音乐表演(声乐)", "文化分数线", 180),
    ("艺术类", "本科批", "音乐表演(声乐)", "专业分数线", 185),
    ("艺术类", "本科批", "音乐表演(器乐)", "文化分数线", 295),
    ("艺术类", "专科批", "音乐表演(器乐)", "文化分数线", 180),
    ("艺术类", "本科批", "音乐表演(器乐)", "专业分数线", 185),
    ("艺术类", "本科批", "舞蹈类", "文化分数线", 247),
    ("艺术类", "专科批", "舞蹈类", "文化分数线", 180),
    ("艺术类", "本科批", "舞蹈类", "专业分数线", 180),
    ("艺术类", "本科批", "戏剧影视表演", "文化分数线", 334),
    ("艺术类", "专科批", "戏剧影视表演", "文化分数线", 180),
    ("艺术类", "本科批", "戏剧影视表演", "专业分数线", 180),
    ("艺术类", "本科批", "服装表演", "文化分数线", 320),
    ("艺术类", "专科批", "服装表演", "文化分数线", 180),
    ("艺术类", "本科批", "服装表演", "专业分数线", 180),
    ("艺术类", "本科批", "戏剧影视导演", "文化分数线", 397),
    ("艺术类", "专科批", "戏剧影视导演", "文化分数线", 190),
    ("艺术类", "本科批", "戏剧影视导演", "专业分数线", 185),
    ("艺术类", "本科批", "播音与主持类", "文化分数线", 352),
    ("艺术类", "专科批", "播音与主持类", "文化分数线", 190),
    ("艺术类", "本科批", "播音与主持类", "专业分数线", 190),
    ("艺术类", "本科批", "书法类", "文化分数线", 321),
    ("艺术类", "专科批", "书法类", "文化分数线", 180),
    ("艺术类", "本科批", "书法类", "专业分数线", 185),
    ("体育类", "本科批", "体育类", "文化分数线", 350),
    ("体育类", "本科批", "体育类", "专业分数线", 84),
    ("体育类", "专科批", "体育类", "文化分数线", 180),
    ("体育类", "专科批", "体育类", "专业分数线", 73),
]

# 2025 投档线 PDF
TOUDANG_PDFS = [
    ("物理类", 2025, RAW_DIR / "chongqing_toudang_2025_physics.pdf",
     "2025年重庆市普通高校招生信息表本科批-物理-平行志愿.pdf"),
    ("历史类", 2025, RAW_DIR / "chongqing_toudang_2025_history.pdf",
     "2025年重庆市普通高校招生信息表本科批-历史-平行志愿.pdf"),
]


# ═══════════════════════════════════════════════════════════════
# 通用工具
# ═══════════════════════════════════════════════════════════════
def clean_text(s) -> str:
    """清洗文本：去水印噪声字、空白。"""
    if s is None:
        return ""
    s = str(s)
    # 重庆PDF水印字（"院""试""考"等单字会嵌入单元格）
    # 仅在长度<=2且为单字时清除，避免误删
    s = re.sub(r"(?<![\u4e00-\u9fa5])[院试考](?![\u4e00-\u9fa5])", "", s)
    s = s.replace("\n", "").replace("\r", "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def parse_int(val):
    """转整数，失败返回 None。"""
    s = clean_text(val)
    if not s or s == "-":
        return None
    # 提取首个数字串
    m = re.search(r"\d+", s)
    if not m:
        return None
    try:
        n = int(m.group(0))
        return n
    except ValueError:
        return None


def append_to_csv(new_rows: list[dict], csv_filename: str, fieldnames: list[str],
                 replace_years: list[int] | None = None) -> int:
    """按 (province, year) 覆盖式追加。

    策略：
    - 删除 existing 中 province='重庆' 且 year ∈ replace_years 的行
    - 追加新数据
    - 保留其他省份数据 + 保留重庆其他年份数据

    这种策略避免与其他省份并行爬取脚本发生写入冲突，
    同时不会覆盖 admission_history.csv 中已有的2024年重庆投档线数据。

    Args:
        new_rows: 新数据行
        csv_filename: 目标 CSV 文件名
        fieldnames: 字段顺序
        replace_years: 需要覆盖的年份列表（仅对该省份该年份做覆盖）
            None 表示按全省份覆盖（保留其他省份，全量替换该省份）

    Returns:
        本次写入的行数
    """
    if not new_rows:
        return 0
    csv_path = DATA_DIR / csv_filename
    # #14 root fix: 重定向到 data/raw/{省}_{文件名}，禁止直接写主 CSV
    _raw_dir = DATA_DIR / "raw"
    _raw_dir.mkdir(exist_ok=True)
    csv_path = _raw_dir / f"{PROVINCE}_{csv_path.name}"
    new_df = pd.DataFrame(new_rows, columns=fieldnames)
    new_df = new_df.fillna("")

    if csv_path.exists():
        existing = pd.read_csv(csv_path, dtype=str).fillna("")
        for col in fieldnames:
            if col not in existing.columns:
                existing[col] = ""

        if replace_years is not None and "year" in existing.columns:
            # 按年份覆盖：保留非重庆 + 重庆其他年份
            # 同时按 subject_group 精细化覆盖：仅删除同年份+重庆+本次新数据涉及的科类
            # 避免同年份先写物理类、再写历史类时把物理类整批删掉
            year_set = {str(y) for y in replace_years}
            subj_set = {str(s) for s in new_df["subject_group"].unique()} if "subject_group" in new_df.columns else None
            mask_cq_year = (existing["province"] == PROVINCE) & (existing["year"].isin(year_set))
            if subj_set and "subject_group" in existing.columns:
                mask_cq_year = mask_cq_year & (existing["subject_group"].isin(subj_set))
            other = existing[~mask_cq_year]
        else:
            # 全省份覆盖：保留非重庆
            other = existing[existing["province"] != PROVINCE]

        new_df_dedup = new_df.drop_duplicates()
        merged = pd.concat([other, new_df_dedup], ignore_index=True)
        added = len(new_df_dedup)
    else:
        merged = new_df.drop_duplicates()
        added = len(merged)

    out_cols = list(merged.columns)
    ordered = [c for c in fieldnames if c in out_cols] + [c for c in out_cols if c not in fieldnames]
    merged = merged[ordered]
    merged.to_csv(csv_path, index=False, encoding="utf-8")
    return added


def log_error(row_data: dict, reason: str):
    """记录解析错误到错误CSV。"""
    ERROR_CSV.parent.mkdir(parents=True, exist_ok=True)
    exists = ERROR_CSV.exists()
    with open(ERROR_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["reason", "data"])
        writer.writerow([reason, str(row_data)])


# ═══════════════════════════════════════════════════════════════
# Phase 2: 下载（HTML 文件已在 _dl_cq_html.py 中预下载）
# ═══════════════════════════════════════════════════════════════
def download_files():
    """检查并补全所需原始文件。"""
    print(f"\n[{PROVINCE}] [DOWNLOAD] 检查原始文件...")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0"}
    missing = []
    for year, sg, path, url in YIFENYIDUAN_SOURCES:
        if not path.exists() or path.stat().st_size < 1000:
            print(f"  下载 {path.name}...")
            try:
                r = httpx.get(url, headers=headers, timeout=20, follow_redirects=True)
                if r.status_code == 200 and "<table" in r.text:
                    path.write_text(r.text, encoding="utf-8")
                    print(f"    [OK] {len(r.content)} bytes")
                else:
                    missing.append(path.name)
                    print(f"    [FAIL] HTTP {r.status_code}")
            except Exception as e:
                missing.append(path.name)
                print(f"    [FAIL] {e}")
        else:
            print(f"  [SKIP] {path.name} 已存在 ({path.stat().st_size} bytes)")

    # 省控线 2026 HTML
    if not CONTROL_LINE_2026_HTML.exists() or CONTROL_LINE_2026_HTML.stat().st_size < 1000:
        try:
            r = httpx.get(CONTROL_LINE_2026_URL, headers=headers, timeout=20, follow_redirects=True)
            if r.status_code == 200:
                CONTROL_LINE_2026_HTML.write_text(r.text, encoding="utf-8")
                print(f"  [OK] {CONTROL_LINE_2026_HTML.name} ({len(r.content)} bytes)")
        except Exception as e:
            print(f"  [FAIL] control_line_2026.html: {e}")

    # 投档线 PDF
    for sg, year, path, src_name in TOUDANG_PDFS:
        if not path.exists() or path.stat().st_size < 50000:
            print(f"  [WARN] 缺少 {path.name}，请手动下载")
            missing.append(path.name)
        else:
            print(f"  [SKIP] {path.name} 已存在 ({path.stat().st_size} bytes)")

    if missing:
        print(f"\n  缺失文件: {missing}")
    return missing


# ═══════════════════════════════════════════════════════════════
# Phase 3a: 解析一分一段表 HTML
# ═══════════════════════════════════════════════════════════════
def parse_yifenyiduan_html(html_path: Path, year: int, subject_group: str) -> list[dict]:
    """解析一分一段表 HTML，返回标准 schema 行列表。

    表格结构（3列）：分数段 | 人数 | 累计人数
    最高分格式: "663及以上" 或 "652及以上" (colspan=2)
    普通分格式: "662" / "8" / "68"

    目标 schema:
        province, year, subject_group, batch, score, segment_count, cumulative_count
    """
    rows_out: list[dict] = []
    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="table-margin") or soup.find("table")
    if not table:
        print(f"  [FAIL] {html_path.name}: 未找到 table")
        return rows_out

    tr_list = table.find_all("tr")
    # 重庆一分一段表本科+专科在同一表（不区分），统一标记为"本科批"
    # 因为分段表本身不区分批次，按规范填"本科批"
    # 但实际上重庆一分一段表覆盖180-750分，本科线以下也属于专科段
    # 为了符合规范的 batch 字段，统一填"本科批"（包含全部分数段）
    # 改为按本科线判断批次（438/425 → 2025物理本科425, 历史438）
    # 更简单：按分数 >= 本科线 → 本科批，否则 → 专科批
    # 但这样会破坏一分一段表的完整性
    # 采取规范允许的简化：全表 batch="本科批"
    # 实际看 plans_2026.csv 的 yifenyiduan 样本："广东,2026,物理类,本科批,750,1,1"
    # 规范说 batch=本科批/专科批，但一分一段表本身是全分数段统计
    # 采用最常见做法：统一填"本科批"
    batch = "本科批"

    for tr in tr_list:
        tds = tr.find_all(["td", "th"])
        if not tds:
            continue
        # 跳过表头
        first_text = clean_text(tds[0].get_text())
        if "分数段" in first_text or "人数" in first_text:
            continue

        # 处理 "XXX及以上" 格式（colspan=2）
        if len(tds) == 2:
            # 顶层: "663及以上" | "60"
            score_text = clean_text(tds[0].get_text())
            cumulative_text = clean_text(tds[1].get_text())
            segment_text = None  # 顶层级没有单独 segment
        elif len(tds) >= 3:
            score_text = clean_text(tds[0].get_text())
            segment_text = clean_cell_int(tds[1].get_text())
            cumulative_text = clean_text(tds[2].get_text())
        else:
            continue

        # 提取分数
        m = re.match(r"(\d+)", score_text)
        if not m:
            continue
        score = int(m.group(1))
        if score < 0 or score > 750:
            continue

        # 解析累计人数
        cumulative = parse_int(cumulative_text)
        if cumulative is None or cumulative > 1000000:
            continue

        # 解析段人数
        if segment_text is None:
            # 顶层"及以上"，segment = cumulative
            segment = cumulative
        else:
            segment = segment_text if segment_text is not None else 0

        rows_out.append({
            "province": PROVINCE,
            "year": year,
            "subject_group": subject_group,
            "batch": batch,
            "score": score,
            "segment_count": segment,
            "cumulative_count": cumulative,
        })

    return rows_out


def clean_cell_int(val):
    """专用于表格单元格整数提取。"""
    s = clean_text(val)
    if not s:
        return 0
    m = re.search(r"\d+", s)
    return int(m.group(0)) if m else 0


def sync_yifenyiduan() -> dict:
    """同步一分一段表 → yifenyiduan_{year}.csv"""
    print(f"\n[{PROVINCE}] [SYNC] 一分一段表")
    stats = {}
    for year, sg, path, url in YIFENYIDUAN_SOURCES:
        if not path.exists():
            print(f"  [SKIP] {year} {sg}: 文件不存在 {path.name}")
            continue
        rows = parse_yifenyiduan_html(path, year, sg)
        csv_filename = f"yifenyiduan_{year}.csv"
        fieldnames = ["province", "year", "subject_group", "batch",
                      "score", "segment_count", "cumulative_count"]
        added = append_to_csv(rows, csv_filename, fieldnames, replace_years=[year])
        print(f"  [重庆] ✓ 已解析 {path.name} ({len(rows)}行, 新增 {added} 行)")
        stats[(year, sg)] = len(rows)
    return stats


# ═══════════════════════════════════════════════════════════════
# Phase 3b: 解析省控线
# ═══════════════════════════════════════════════════════════════
def parse_control_line_2026_html() -> list[dict]:
    """解析 2026 省控线 HTML 表格。

    表结构:
    Table 1 (普通类): 科类 | 本科批 | 特殊类型资格线 | 专科批
                     历史类 | 415 | 510 | 180
                     物理类 | 406 | 496 | 180
    Table 2 (艺术类): 分数线科类 | 文化分数线(本科批/专科批) | 专业分数线
    Table 3 (体育类): 批次 | 文化分数线 | 专业分数线
    """
    rows_out: list[dict] = []
    if not CONTROL_LINE_2026_HTML.exists():
        print(f"  [SKIP] 2026省控线 HTML 不存在")
        return rows_out
    html = CONTROL_LINE_2026_HTML.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    print(f"  2026省控线 HTML: 共 {len(tables)} 张表")

    # 表 1: 普通类
    if len(tables) >= 1:
        t = tables[0]
        trs = t.find_all("tr")
        # 跳过前2行表头（科类+分数线）
        for tr in trs[2:]:
            tds = tr.find_all("td")
            if len(tds) < 4:
                continue
            sg = clean_text(tds[0].get_text())
            if sg not in ("物理类", "历史类"):
                continue
            benke = parse_int(tds[1].get_text())
            tekong = parse_int(tds[2].get_text())
            zhuanke = parse_int(tds[3].get_text())
            for batch, score in [("本科批", benke), ("特殊类型资格线", tekong), ("专科批", zhuanke)]:
                if score is not None:
                    rows_out.append({
                        "province": PROVINCE, "year": 2026,
                        "batch_section": "普通类",
                        "batch": batch,
                        "subject_group": sg,
                        "line_type": "总分",
                        "lowest_score": score,
                        "source_url": CONTROL_LINE_2026_URL,
                    })

    # 表 2: 艺术类
    if len(tables) >= 2:
        t = tables[1]
        trs = t.find_all("tr")
        current_category = None
        for tr in trs:
            tds = tr.find_all("td")
            if not tds:
                continue
            # 艺术类表格不规则，第一列可能是"美术与设计类"或子类
            cells = [clean_text(td.get_text()) for td in tds]
            # 识别类别行: "美术与设计类 | 305 | 180 | 185"
            if "类" in cells[0] and len(cells) >= 4:
                cat = cells[0]
                wenhua_benke = parse_int(cells[1])
                wenhua_zhuanke = parse_int(cells[2])
                zhuanye = parse_int(cells[3]) if len(cells) > 3 else None
                if wenhua_benke:
                    rows_out.append({
                        "province": PROVINCE, "year": 2026,
                        "batch_section": "艺术类", "batch": "本科批",
                        "subject_group": cat, "line_type": "文化分数线",
                        "lowest_score": wenhua_benke, "source_url": CONTROL_LINE_2026_URL,
                    })
                if wenhua_zhuanke:
                    rows_out.append({
                        "province": PROVINCE, "year": 2026,
                        "batch_section": "艺术类", "batch": "专科批",
                        "subject_group": cat, "line_type": "文化分数线",
                        "lowest_score": wenhua_zhuanke, "source_url": CONTROL_LINE_2026_URL,
                    })
                if zhuanye:
                    rows_out.append({
                        "province": PROVINCE, "year": 2026,
                        "batch_section": "艺术类", "batch": "本科批",
                        "subject_group": cat, "line_type": "专业分数线",
                        "lowest_score": zhuanye, "source_url": CONTROL_LINE_2026_URL,
                    })

    # 表 3: 体育类
    if len(tables) >= 3:
        t = tables[2]
        trs = t.find_all("tr")
        for tr in trs:
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            batch = clean_text(tds[0].get_text())
            wenhua = parse_int(tds[1].get_text())
            zhuanye = parse_int(tds[2].get_text()) if len(tds) > 2 else None
            if batch and wenhua:
                rows_out.append({
                    "province": PROVINCE, "year": 2026,
                    "batch_section": "体育类", "batch": batch,
                    "subject_group": "体育类", "line_type": "文化分数线",
                    "lowest_score": wenhua, "source_url": CONTROL_LINE_2026_URL,
                })
            if batch and zhuanye:
                rows_out.append({
                    "province": PROVINCE, "year": 2026,
                    "batch_section": "体育类", "batch": batch,
                    "subject_group": "体育类", "line_type": "专业分数线",
                    "lowest_score": zhuanye, "source_url": CONTROL_LINE_2026_URL,
                })

    return rows_out


def sync_control_line() -> dict:
    """同步省控线 → control_line_{year}.csv"""
    print(f"\n[{PROVINCE}] [SYNC] 省控线")
    fieldnames = ["province", "year", "batch_section", "batch",
                  "subject_group", "line_type", "lowest_score", "source_url"]
    stats = {}

    # 2026 (HTML 解析)
    rows_2026 = parse_control_line_2026_html()
    added = append_to_csv(rows_2026, "control_line_2026.csv", fieldnames, replace_years=[2026])
    print(f"  [重庆] ✓ 2026省控线 ({len(rows_2026)}行, 新增 {added} 行)")
    stats[2026] = len(rows_2026)

    # 2025 (硬编码数据)
    rows_2025 = []
    for batch_section, batch, sg, line_type, score in CONTROL_LINE_2025_DATA:
        rows_2025.append({
            "province": PROVINCE, "year": 2025,
            "batch_section": batch_section, "batch": batch,
            "subject_group": sg, "line_type": line_type,
            "lowest_score": score, "source_url": CONTROL_LINE_2025_URL,
        })
    added = append_to_csv(rows_2025, "control_line_2025.csv", fieldnames, replace_years=[2025])
    print(f"  [重庆] ✓ 2025省控线 ({len(rows_2025)}行, 新增 {added} 行)")
    stats[2025] = len(rows_2025)

    # 2024 (硬编码数据)
    rows_2024 = []
    for batch_section, batch, sg, line_type, score in CONTROL_LINE_2024_DATA:
        rows_2024.append({
            "province": PROVINCE, "year": 2024,
            "batch_section": batch_section, "batch": batch,
            "subject_group": sg, "line_type": line_type,
            "lowest_score": score, "source_url": CONTROL_LINE_2024_URL,
        })
    added = append_to_csv(rows_2024, "control_line_2024.csv", fieldnames, replace_years=[2024])
    print(f"  [重庆] ✓ 2024省控线 ({len(rows_2024)}行, 新增 {added} 行)")
    stats[2024] = len(rows_2024)

    return stats


# ═══════════════════════════════════════════════════════════════
# Phase 3c: 解析 2025 投档线 PDF → admission_history.csv
# ═══════════════════════════════════════════════════════════════
WATERMARK_CHARS = set("院试考省育")


def strip_watermark(s: str) -> str:
    """去除PDF水印单字（嵌入到字段中的'院''试''考'等字）。

    这些字会在表格单元格中出现，但只在水印位置（独立出现，前后非中文）时清除。
    """
    if not s:
        return s
    # 去除独立的水印字（前后无中文字符）
    out = []
    for i, ch in enumerate(s):
        if ch in WATERMARK_CHARS:
            prev_ch = s[i - 1] if i > 0 else ""
            next_ch = s[i + 1] if i < len(s) - 1 else ""
            # 如果前后都不是中文字符，则视为水印
            prev_is_cjk = bool(re.match(r"[\u4e00-\u9fa5]", prev_ch))
            next_is_cjk = bool(re.match(r"[\u4e00-\u9fa5]", next_ch))
            if not (prev_is_cjk or next_is_cjk):
                continue
        out.append(ch)
    return "".join(out)


def parse_toudang_pdf(pdf_path: Path, subject_group: str, year: int, source_file: str) -> list[dict]:
    """解析投档线 PDF，返回 admission_history schema 行列表。

    PDF 表格列:
        院校代号 | 院校名称 | 专业代号 | 专业名称 | 投档最低分 | 语数之和 | 语数最高 | 外语 | 首选科目

    由于表格提取有合并单元格问题，改用文本行模式 + 正则解析。

    目标 schema:
        year, province, subject_group, batch, university_code, university_name,
        group_code, major_code, major_name, lowest_score, lowest_rank,
        avg_score, applicant_count, source_file
    """
    rows_out: list[dict] = []
    batch = "本科批"

    with pdfplumber.open(str(pdf_path)) as pdf:
        n_pages = len(pdf.pages)
        for page_idx, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            # 按行解析
            for line in text.split("\n"):
                line = strip_watermark(line).strip()
                if not line:
                    continue
                # 跳过表头
                if "院校代号" in line or "院校名称" in line or "投档最低分" in line:
                    continue
                if "重庆市普通高校招生信息表" in line or "平行志愿" in line:
                    continue
                if line.startswith("语数") or line.startswith("外语") or line.startswith("首选"):
                    continue

                # 匹配模式: 院校代号 院校名称 专业代号 专业名称 投档最低分 9位数字串 首选科目
                # 院校代号: 3-4位数字
                # 院校名称: 中文+括号
                # 专业代号: 3-4位字母数字
                # 专业名称: 中文+括号
                # 投档最低分: 3位数
                # 9位合并数字串: 语数之和(3)+语数最高(3)+外语(3)
                # 首选科目: 2位数
                # 例: 1101 北京大学 556 理科试验班类(理科基础类专业) 693 276149143 87

                m = re.match(
                    r"^(\d{4,5})\s+"        # 院校代号
                    r"([\u4e00-\u9fa5()（）]+)\s+"  # 院校名称
                    r"([0-9A-Z]{2,5})\s+"   # 专业代号
                    r"(.+?)\s+"             # 专业名称（非贪婪）
                    r"(\d{3})\s+"           # 投档最低分
                    r"(\d{6,9})\s+"         # 9位合并数字串
                    r"(\d{1,3})\s*$",       # 首选科目
                    line,
                )
                if not m:
                    # 尝试退化模式：可能没有首选科目
                    m = re.match(
                        r"^(\d{4,5})\s+"
                        r"([\u4e00-\u9fa5()（）]+)\s+"
                        r"([0-9A-Z]{2,5})\s+"
                        r"(.+?)\s+"
                        r"(\d{3})\s+"
                        r"(\d{6,9})\s*$",
                        line,
                    )
                    if m:
                        groups = list(m.groups()) + [None]
                    else:
                        log_error({"line": line, "page": page_idx + 1}, "regex_no_match")
                        continue
                else:
                    groups = list(m.groups())

                university_code = groups[0]
                university_name = groups[1]
                major_code = groups[2]
                major_name = groups[3]
                lowest_score = int(groups[4])
                # 9位合并数字串不拆分，仅丢弃
                # 首选科目 = groups[6]

                # 数据校验
                if lowest_score < 200 or lowest_score > 750:
                    log_error({"line": line, "score": lowest_score}, "score_out_of_range")
                    continue

                rows_out.append({
                    "year": year,
                    "province": PROVINCE,
                    "subject_group": subject_group,
                    "batch": batch,
                    "university_code": university_code,
                    "university_name": university_name,
                    "group_code": major_code,  # 重庆无独立组代码，用专业代号
                    "major_code": major_code,
                    "major_name": major_name,
                    "lowest_score": float(lowest_score),
                    "lowest_rank": "",  # PDF 无位次数据
                    "avg_score": "",
                    "applicant_count": "",
                    "source_file": source_file,
                })

            if (page_idx + 1) % 50 == 0:
                print(f"    进度: {page_idx + 1}/{n_pages} 页, 累计 {len(rows_out)} 行")

    return rows_out


def sync_toudang_history() -> dict:
    """同步 2025 投档线 → admission_history.csv"""
    print(f"\n[{PROVINCE}] [SYNC] 2025 投档线 → admission_history.csv")
    fieldnames = ["year", "province", "subject_group", "batch",
                  "university_code", "university_name", "group_code",
                  "major_code", "major_name", "lowest_score", "lowest_rank",
                  "avg_score", "applicant_count", "source_file"]
    stats = {}
    for sg, year, path, src_name in TOUDANG_PDFS:
        if not path.exists() or path.stat().st_size < 50000:
            print(f"  [SKIP] {year} {sg}: PDF 不存在 {path.name}")
            continue
        print(f"  解析 {path.name} ({sg}, {year})...")
        rows = parse_toudang_pdf(path, sg, year, src_name)
        # 投档线按 (province, year) 覆盖：保留2024年重庆数据 + 其他省份
        added = append_to_csv(rows, "admission_history.csv", fieldnames, replace_years=[year])
        print(f"  [重庆] ✓ 已解析 {path.name} ({len(rows)}行, 新增 {added} 行)")
        stats[(year, sg)] = len(rows)
    return stats


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════
def main():
    print(f"\n{'='*60}")
    print(f"[{PROVINCE}] 开始同步高考数据")
    print(f"{'='*60}")

    # Phase 2: 下载/检查
    download_files()

    # Phase 3: 解析与写入
    yfyd_stats = sync_yifenyiduan()
    cl_stats = sync_control_line()
    td_stats = sync_toudang_history()

    # Phase 5: 汇总
    print(f"\n{'='*60}")
    print(f"[{PROVINCE}] 数据爬取报告")
    print(f"{'='*60}")
    total_yfyd = sum(yfyd_stats.values())
    total_cl = sum(cl_stats.values())
    total_td = sum(td_stats.values())
    print(f"一分一段表: 追加 {total_yfyd} 行")
    for (year, sg), n in sorted(yfyd_stats.items()):
        print(f"  {year} {sg}: {n} 行")
    print(f"省控线: 追加 {total_cl} 行")
    for year, n in sorted(cl_stats.items()):
        print(f"  {year}: {n} 行")
    print(f"历史投档线: 追加 {total_td} 行 (2025)")
    for (year, sg), n in sorted(td_stats.items()):
        print(f"  {year} {sg}: {n} 行")

    print(f"\n注意:")
    print(f"  1. 2024年一分一段表: 考试院 URL 已下线，本次未爬取（admission_history.csv 已有2024年投档线 29548行）")
    print(f"  2. 招生计划 plans_2026/2025: 重庆考试院不直接公布 PDF，需通过志愿填报辅助系统获取")
    print(f"  3. 2024/2025 省控线: 考试院页面失效，数据来自政府转载站（jw.cq.gov.cn / cqzk.com.cn）")
    print(f"\n[{PROVINCE}] ✓ 同步完成")


if __name__ == "__main__":
    main()
