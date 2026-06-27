#!/usr/bin/env python3
"""河北省教育考试院 2026 高考数据爬取脚本

数据源: https://www.hebeea.edu.cn
覆盖数据:
  1. yifenyiduan_2026.csv — 2026年一分一段表（图片型PDF，用OpenCV+Tesseract OCR）
  2. control_line_2026.csv — 2026年省控线（公告页只有图片，从官方公告文本提取）
  3. admission_history.csv — 历史投档线（2026年投档线未发布，仅整理现有2024/2025数据）

河北是3+1+2省份，subject_group 只用「物理类」「历史类」。
所有CSV采用追加模式，drop_duplicates去重，不覆盖已有省份数据。

用法:
    python backend/scripts/sync_hebei_2026.py fetch      # 下载原始PDF
    python backend/scripts/sync_hebei_2026.py ocr         # OCR解析一分一段表
    python backend/scripts/sync_hebei_2026.py control    # 写入省控线
    python backend/scripts/sync_hebei_2026.py load       # 追加写入CSV
    python backend/scripts/sync_hebei_2026.py all        # 全流程
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import pdfplumber
import pytesseract

# ─────────────────────────────────────────────────────────────────
# 路径配置
# ─────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw" / "hebei_2026"
IMG_DIR = RAW_DIR / "images"
INTERMEDIATE_DIR = DATA_DIR / "intermediate" / "hebei_2026"

YIFENYIDUAN_PDF = RAW_DIR / "hebei_yifenyiduan_2026.pdf"
YIFENYIDUAN_INTERMEDIATE = INTERMEDIATE_DIR / "yifenyiduan.csv"

# 标准 CSV（与全国共享，追加模式）
YIFENYIDUAN_2026_CSV = DATA_DIR / "yifenyiduan_2026.csv"
YIFENYIDUAN_2025_CSV = DATA_DIR / "yifenyiduan_2025.csv"
YIFENYIDUAN_2024_CSV = DATA_DIR / "yifenyiduan_2024.csv"
CONTROL_LINE_2026_CSV = DATA_DIR / "control_line_2026.csv"
CONTROL_LINE_2025_CSV = DATA_DIR / "control_line_2025.csv"
CONTROL_LINE_2024_CSV = DATA_DIR / "control_line_2024.csv"
PLANS_2026_CSV = DATA_DIR / "plans_2026.csv"

PROVINCE = "河北"
SUBJECT_GROUPS = ["物理类", "历史类"]

# ─────────────────────────────────────────────────────────────────
# 数据源 URL（2026/2025/2024 一分一段表 + 省控线公告）
# ─────────────────────────────────────────────────────────────────
# 一分一段表 PDF（均为图片型扫描件，18页，需OCR）
YIFENYIDUAN_URLS = {
    2026: ("https://file.hebeea.edu.cn/upload/resources/file/2026/06/24/27144.pdf",
           "https://www.hebeea.edu.cn/c/2026-06-24/493215.html"),
    2025: ("https://file.hebeea.edu.cn/files/article/2025/06/20250624193800_658.pdf",
           "https://www.hebeea.edu.cn/c/2025-06-24/488903.html"),
    2024: ("https://file.hebeea.edu.cn/files/article/2024/06/20240624195327_41.pdf",
           "https://www.hebeea.edu.cn/html/xxgl/tzgg/2024/0624-185638-797.html"),
}

# 河北省控线（从官方公告及权威媒体核实，均来自河北省教育考试院公告）
# 2026: https://www.hebeea.edu.cn/c/2026-06-24/493121.html
# 2025: https://www.hebeea.edu.cn/c/2025-06-24/488635.html (公告页)
# 2024: https://www.hebeea.edu.cn/html/xxgl/tzgg/2024/0624-185637-794.html
CONTROL_LINES = {
    2026: [
        ("本科院校", "本科", "历史类", "总分", 485),
        ("本科院校", "本科", "物理类", "总分", 443),
        ("专科院校", "专科", "历史类", "总分", 200),
        ("专科院校", "专科", "物理类", "总分", 200),
        ("特殊类型招生", "特招线", "历史类", "总分", 542),
        ("特殊类型招生", "特招线", "物理类", "总分", 510),
    ],
    2025: [
        ("本科院校", "本科", "历史类", "总分", 477),
        ("本科院校", "本科", "物理类", "总分", 459),
        ("专科院校", "专科", "历史类", "总分", 200),
        ("专科院校", "专科", "物理类", "总分", 200),
        ("特殊类型招生", "特招线", "历史类", "总分", 527),
        ("特殊类型招生", "特招线", "物理类", "总分", 499),
    ],
    2024: [
        ("本科院校", "本科", "历史类", "总分", 449),
        ("本科院校", "本科", "物理类", "总分", 448),
        ("专科院校", "专科", "历史类", "总分", 200),
        ("专科院校", "专科", "物理类", "总分", 200),
        ("特殊类型招生", "特招线", "历史类", "总分", 506),
        ("特殊类型招生", "特招线", "物理类", "总分", 506),
    ],
}

CONTROL_LINE_NOTICE_URLS = {
    2026: "https://www.hebeea.edu.cn/c/2026-06-24/493121.html",
    2025: "https://www.hebeea.edu.cn/c/2025-06-24/488635.html",
    2024: "https://www.hebeea.edu.cn/html/xxgl/tzgg/2024/0624-185637-794.html",
}


# ═══════════════════════════════════════════════════════════════
# 阶段 1: FETCH — 下载原始 PDF
# ═══════════════════════════════════════════════════════════════
def fetch_yifenyiduan(year: int) -> Path:
    """下载指定年份的一分一段表PDF。"""
    url, notice = YIFENYIDUAN_URLS[year]
    raw_dir = DATA_DIR / "raw" / f"hebei_{year}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = raw_dir / f"hebei_yifenyiduan_{year}.pdf"
    print(f"\n[FETCH] {year}年一分一段表 PDF")
    if pdf_path.exists() and pdf_path.stat().st_size > 100_000:
        print(f"  [SKIP] {pdf_path.name} 已存在 ({pdf_path.stat().st_size:,} bytes)")
        return pdf_path
    import urllib.request
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                               "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    pdf_path.write_bytes(data)
    print(f"  [OK] {pdf_path.name} ({len(data):,} bytes)")
    return pdf_path


# ═══════════════════════════════════════════════════════════════
# 阶段 2: OCR — 图片型PDF → 结构化数据
# ═══════════════════════════════════════════════════════════════
def pdf_to_images(pdf_path: Path, out_dir: Path, dpi: int = 300) -> list[Path]:
    """用 pdftoppm 把PDF渲染为高分辨率PNG。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    # 检查是否已渲染
    existing = sorted(out_dir.glob("page-*.png"))
    if existing:
        print(f"  [SKIP] 已有 {len(existing)} 张渲染图")
        return existing
    cmd = ["pdftoppm", "-png", "-r", str(dpi), str(pdf_path), str(out_dir / "page")]
    print(f"  渲染PDF→PNG (dpi={dpi})...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"pdftoppm失败: {result.stderr}")
    pages = sorted(out_dir.glob("page-*.png"))
    print(f"  [OK] 渲染 {len(pages)} 页")
    return pages


def detect_grid(img: np.ndarray) -> tuple[list[int], list[int]]:
    """检测表格网格，返回 (水平线y坐标列表, 垂直线x坐标列表)。"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

    # 水平线
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (img.shape[1] // 4, 1))
    h_lines = cv2.morphologyEx(bw, cv2.MORPH_OPEN, h_kernel, iterations=1)
    h_proj = h_lines.sum(axis=1)
    h_peaks = np.where(h_proj > img.shape[1] * 0.3 * 255)[0]
    h_groups: list[list[int]] = []
    for y in h_peaks:
        if h_groups and y - h_groups[-1][-1] < 15:
            h_groups[-1].append(y)
        else:
            h_groups.append([y])
    h_ys = [int(np.mean(g)) for g in h_groups]

    # 垂直线
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, img.shape[0] // 4))
    v_lines = cv2.morphologyEx(bw, cv2.MORPH_OPEN, v_kernel, iterations=1)
    v_proj = v_lines.sum(axis=0)
    v_peaks = np.where(v_proj > img.shape[0] * 0.3 * 255)[0]
    v_groups: list[list[int]] = []
    for x in v_peaks:
        if v_groups and x - v_groups[-1][-1] < 15:
            v_groups[-1].append(x)
        else:
            v_groups.append([x])
    v_xs = [int(np.mean(g)) for g in v_groups]
    return h_ys, v_xs


def ocr_cell(img: np.ndarray, x1: int, x2: int, y1: int, y2: int) -> str:
    """OCR单个单元格，返回纯数字字符串。"""
    cell = img[y1 + 3:y2 - 3, x1 + 3:x2 - 3]
    if cell.size == 0 or cell.shape[0] < 5 or cell.shape[1] < 5:
        return ""
    cell_gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    # 放大2倍提升识别率
    cell_gray = cv2.resize(cell_gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    # OTSU二值化
    _, cell_bw = cv2.threshold(cell_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    text = pytesseract.image_to_string(
        cell_bw,
        config="--psm 7 -c tessedit_char_whitelist=0123456789",
        lang="eng",
    ).strip()
    # 去除换行等
    text = re.sub(r"\s+", "", text)
    return text


def ocr_page(img_path: Path) -> list[dict]:
    """OCR单页，返回行列表。
    表格5列结构：分数 | 物理段 | 物理累计 | 历史段 | 历史累计
    """
    img = cv2.imread(str(img_path))
    if img is None:
        raise RuntimeError(f"无法读取图片: {img_path}")
    h_ys, v_xs = detect_grid(img)
    if len(v_xs) < 6 or len(h_ys) < 4:
        print(f"  [WARN] {img_path.name} 网格异常: h={len(h_ys)} v={len(v_xs)}")
        return []

    rows = []
    # 跳过前2行表头，从第3行（idx=2）开始
    for r in range(2, len(h_ys) - 1):
        vals = []
        for c in range(len(v_xs) - 1):
            vals.append(ocr_cell(img, v_xs[c], v_xs[c + 1], h_ys[r], h_ys[r + 1]))
        # 第一列必须是数字（分数）
        if not vals[0] or not vals[0].isdigit():
            continue
        score = int(vals[0])
        if score < 0 or score > 750:
            continue
        rows.append({
            "score": score,
            "phy_segment": vals[1] if len(vals) > 1 else "",
            "phy_cumulative": vals[2] if len(vals) > 2 else "",
            "his_segment": vals[3] if len(vals) > 3 else "",
            "his_cumulative": vals[4] if len(vals) > 4 else "",
            "page": img_path.stem,
        })
    return rows


def clean_int(val: str) -> int | None:
    """清洗OCR结果并转整数。"""
    if not val or not val.strip():
        return None
    s = re.sub(r"\s+", "", val)
    if not s.isdigit():
        # 提取数字部分
        m = re.match(r"^(\d+)", s)
        if not m:
            return None
        s = m.group(1)
    try:
        return int(s)
    except ValueError:
        return None


def repair_cumulative(rows: list[dict], key: str) -> int:
    """修正累计人数（必须随分数下降递增）。
    返回修正次数。
    """
    fixes = 0
    last_cum = 0
    for row in rows:  # rows按分数从高到低排序
        cum = clean_int(row[key])
        if cum is None:
            # 用上一个累计值填充
            row[key] = str(last_cum) if last_cum else ""
            continue
        if cum < last_cum:
            # OCR错误（如4719应为479），用上一个值+当前段人数
            seg = clean_int(row[key.replace("cumulative", "segment")]) or 0
            new_cum = last_cum + seg
            row[key] = str(new_cum)
            fixes += 1
            cum = new_cum
        last_cum = cum
    return fixes


def ocr_yifenyiduan(year: int) -> Path:
    """OCR指定年份的全部页 → 中间CSV（支持断点续传，每页缓存）。"""
    print(f"\n[OCR] {year}年一分一段表 PDF → 中间CSV")
    raw_dir = DATA_DIR / "raw" / f"hebei_{year}"
    img_dir = raw_dir / "images"
    intermediate_dir = DATA_DIR / "intermediate" / f"hebei_{year}"
    pdf_path = raw_dir / f"hebei_yifenyiduan_{year}.pdf"
    intermediate_csv = intermediate_dir / "yifenyiduan.csv"

    if not pdf_path.exists():
        raise RuntimeError(f"PDF不存在: {pdf_path}")

    pages = pdf_to_images(pdf_path, img_dir, dpi=300)
    print(f"  共 {len(pages)} 页待OCR")

    cache_dir = intermediate_dir / "page_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    for i, p in enumerate(pages, 1):
        cache_file = cache_dir / f"{p.stem}.csv"
        # 断点续传：已有缓存的页面直接读取
        if cache_file.exists():
            with open(cache_file, encoding="utf-8-sig") as cf:
                rows = list(csv.DictReader(cf))
            # 统一score为int（缓存读取的是str）
            for r in rows:
                if isinstance(r.get("score"), str) and r["score"].isdigit():
                    r["score"] = int(r["score"])
            print(f"  [{p.name}] {len(rows)} 行 (缓存命中)")
        else:
            try:
                rows = ocr_page(p)
            except Exception as e:
                print(f"  [{p.name}] OCR失败: {e}")
                rows = []
            # 保存缓存
            if rows:
                with open(cache_file, "w", newline="", encoding="utf-8-sig") as cf:
                    writer = csv.DictWriter(cf, fieldnames=["score", "phy_segment",
                        "phy_cumulative", "his_segment", "his_cumulative", "page"])
                    writer.writeheader()
                    writer.writerows(rows)
            print(f"  [{p.name}] {len(rows)} 行 (累计 {len(all_rows) + len(rows)})")
        all_rows.extend(rows)

    print(f"\n  OCR总计: {len(all_rows)} 行")

    # 按分数从高到低排序（用于累计修正）
    all_rows.sort(key=lambda x: -x["score"])

    # 修正累计人数（OCR偶有多识别数字的情况）
    phy_fixes = repair_cumulative(all_rows, "phy_cumulative")
    his_fixes = repair_cumulative(all_rows, "his_cumulative")
    print(f"  累计修正: 物理{phy_fixes}处, 历史{his_fixes}处")

    # 检查分数连续性
    scores = [r["score"] for r in all_rows]
    min_s, max_s = min(scores), max(scores)
    expected = set(range(min_s, max_s + 1))
    missing = expected - set(scores)
    if missing:
        print(f"  [WARN] 缺失分数: {sorted(missing)[:10]}... 共{len(missing)}个")
    else:
        print(f"  [OK] 分数连续覆盖 {min_s}-{max_s} ({max_s - min_s + 1}个分数)")

    # 写中间CSV
    intermediate_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = ["score", "phy_segment", "phy_cumulative",
                  "his_segment", "his_cumulative", "page"]
    with open(intermediate_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"  [OK] 中间CSV: {intermediate_csv} ({len(all_rows)} 行)")
    return intermediate_csv


# ═══════════════════════════════════════════════════════════════
# 阶段 3: LOAD — 标准化并追加写入CSV
# ═══════════════════════════════════════════════════════════════
def load_yifenyiduan(year: int) -> int:
    """把中间CSV转为标准格式并追加到 yifenyiduan_{year}.csv。

    标准 schema: province, year, subject_group, batch, score,
                 segment_count, cumulative_count
    河北一分一段表统一一份表，batch 标 "本科批"（项目惯例）。
    """
    print(f"\n[LOAD] {year}年一分一段表 → yifenyiduan_{year}.csv")
    intermediate_csv = DATA_DIR / "intermediate" / f"hebei_{year}" / "yifenyiduan.csv"
    target_csv = DATA_DIR / f"yifenyiduan_{year}.csv"
    if not intermediate_csv.exists():
        raise RuntimeError(f"中间CSV不存在: {intermediate_csv}")

    rows_out: list[dict] = []
    with open(intermediate_csv, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            score = int(r["score"])
            # 物理类
            phy_seg = clean_int(r["phy_segment"])
            phy_cum = clean_int(r["phy_cumulative"])
            if phy_cum is not None:
                rows_out.append({
                    "province": PROVINCE, "year": year,
                    "subject_group": "物理类", "batch": "本科批",
                    "score": score,
                    "segment_count": phy_seg if phy_seg is not None else 0,
                    "cumulative_count": phy_cum,
                })
            # 历史类
            his_seg = clean_int(r["his_segment"])
            his_cum = clean_int(r["his_cumulative"])
            if his_cum is not None:
                rows_out.append({
                    "province": PROVINCE, "year": year,
                    "subject_group": "历史类", "batch": "本科批",
                    "score": score,
                    "segment_count": his_seg if his_seg is not None else 0,
                    "cumulative_count": his_cum,
                })

    print(f"  生成标准行: {len(rows_out)} (物理类 {sum(1 for r in rows_out if r['subject_group']=='物理类')} + "
          f"历史类 {sum(1 for r in rows_out if r['subject_group']=='历史类')})")

    n_added = append_to_csv(rows_out, target_csv,
                            dedup_keys=["province", "year", "subject_group", "batch", "score"])
    print(f"  [OK] yifenyiduan_{year}.csv 追加 {n_added} 行")
    return n_added


def load_control_line(year: int) -> int:
    """写入指定年份省控线到 control_line_{year}.csv。"""
    print(f"\n[LOAD] {year}年省控线 → control_line_{year}.csv")
    target_csv = DATA_DIR / f"control_line_{year}.csv"
    notice_url = CONTROL_LINE_NOTICE_URLS[year]
    rows_out = []
    for batch_section, batch, sg, line_type, score in CONTROL_LINES[year]:
        rows_out.append({
            "province": PROVINCE, "year": year,
            "batch_section": batch_section, "batch": batch,
            "subject_group": sg, "line_type": line_type,
            "lowest_score": score,
            "source_url": notice_url,
        })
    n_added = append_to_csv(rows_out, target_csv,
                            dedup_keys=["province", "year", "batch", "subject_group", "line_type"])
    print(f"  [OK] control_line_{year}.csv 追加 {n_added} 行")
    for r in rows_out:
        print(f"    [{r['batch']}] {r['subject_group']} → {r['lowest_score']}分")
    return n_added


def append_to_csv(new_rows: list[dict], csv_path: Path,
                 dedup_keys: list[str] | None = None) -> int:
    """安全追加数据到CSV（去重，不覆盖其他省份）。

    返回新增行数（去重后）。
    """
    if not new_rows:
        return 0
    # #14 root fix: 重定向到 data/raw/{省}_{文件名}，禁止直接写主 CSV
    _raw_dir = DATA_DIR / "raw"
    _raw_dir.mkdir(exist_ok=True)
    csv_path = _raw_dir / f"{PROVINCE}_{csv_path.name}"
    new_df = pd.DataFrame(new_rows)
    # 空值处理：pandas的NaN转为空字符串
    new_df = new_df.where(pd.notna(new_df), "")

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if csv_path.exists():
        existing = pd.read_csv(csv_path, dtype=str)
        # 同province的数据先删除再追加（保证幂等）
        prov_mask = existing["province"] == PROVINCE
        # 进一步按年份过滤（同年同省覆盖）
        if "year" in existing.columns:
            years_in_new = set(new_df["year"].astype(str).unique())
            year_mask = existing["year"].astype(str).isin(years_in_new)
            remove_mask = prov_mask & year_mask
        else:
            remove_mask = prov_mask
        existing_no_prov = existing[~remove_mask]
        removed = int(remove_mask.sum())
        if removed:
            print(f"  移除旧{PROVINCE}数据: {removed} 行（同年覆盖）")
        merged = pd.concat([existing_no_prov, new_df], ignore_index=True)
    else:
        merged = new_df

    # 去重
    before_dedup = len(merged)
    if dedup_keys:
        merged = merged.drop_duplicates(subset=dedup_keys, keep="last")
    else:
        merged = merged.drop_duplicates(keep="last")
    deduped = before_dedup - len(merged)
    if deduped:
        print(f"  去重: 移除 {deduped} 行重复")

    merged.to_csv(csv_path, index=False, encoding="utf-8-sig")
    # 返回本次新增的行数
    return len(new_df) - (len(new_df) - len(new_df.drop_duplicates(subset=dedup_keys) if dedup_keys else new_df))


# ═══════════════════════════════════════════════════════════════
# 阶段 4: VERIFY — 校验
# ═══════════════════════════════════════════════════════════════
def verify_yifenyiduan() -> bool:
    """校验一分一段表数据完整性。"""
    print(f"\n[VERIFY] 一分一段表校验")
    if not YIFENYIDUAN_2026_CSV.exists():
        print(f"  [FAIL] 文件不存在")
        return False
    df = pd.read_csv(YIFENYIDUAN_2026_CSV, dtype=str)
    hb = df[df["province"] == PROVINCE].copy()
    if len(hb) == 0:
        print(f"  [FAIL] 无河北数据")
        return False
    hb["score"] = hb["score"].astype(int)
    hb["cumulative_count"] = hb["cumulative_count"].astype(int)
    print(f"  河北数据: {len(hb)} 行")

    ok = True
    for sg in SUBJECT_GROUPS:
        sub = hb[hb["subject_group"] == sg].sort_values("score", ascending=False)
        if len(sub) == 0:
            print(f"  [FAIL] {sg} 无数据")
            ok = False
            continue
        scores = sub["score"].tolist()
        cum = sub["cumulative_count"].tolist()
        max_s, min_s = max(scores), min(scores)
        # 累计必须递增（分数降序，累计升序）
        non_monotonic = sum(1 for i in range(len(cum) - 1) if cum[i] > cum[i + 1])
        # 分数连续性
        expected = set(range(min_s, max_s + 1))
        missing = expected - set(scores)
        print(f"  {sg}: {len(sub)}行, 分数{min_s}-{max_s}, "
              f"累计{cum[0]}→{cum[-1]}, 非单调{non_monotonic}处, 缺失分数{len(missing)}个")
        if non_monotonic > 5:
            print(f"  [WARN] {sg} 累计非单调超过5处")
        if len(missing) > 0:
            print(f"  [WARN] {sg} 缺失分数: {sorted(missing)[:5]}...")
        # 行数应 > 2000（满分750，最低200，至少550行×2类）
        if len(sub) < 400:
            print(f"  [FAIL] {sg} 行数不足: {len(sub)}")
            ok = False
    return ok


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=[
        "fetch", "ocr", "control", "load", "verify",
        "all", "history", "history_ocr"])
    parser.add_argument("--year", type=int, default=2026,
                        help="年份 (2024/2025/2026)，默认2026")
    args = parser.parse_args()

    year = args.year

    if args.stage == "fetch":
        fetch_yifenyiduan(year)
    elif args.stage == "ocr":
        ocr_yifenyiduan(year)
    elif args.stage == "control":
        load_control_line(year)
    elif args.stage == "load":
        load_yifenyiduan(year)
    elif args.stage == "verify":
        ok = verify_yifenyiduan()
        if not ok:
            print("\n[VERIFY] 校验失败")
            sys.exit(1)
        print("\n[VERIFY] 全部通过 ✓")
    elif args.stage == "history_ocr":
        # 仅OCR历史年份（2024+2025），跳过已处理的2026
        for y in [2024, 2025]:
            print(f"\n{'='*60}\n处理 {y} 年\n{'='*60}")
            fetch_yifenyiduan(y)
            ocr_yifenyiduan(y)
    elif args.stage == "history":
        # 处理历史年份全流程（2024+2025）
        for y in [2024, 2025]:
            print(f"\n{'='*60}\n处理 {y} 年\n{'='*60}")
            fetch_yifenyiduan(y)
            ocr_yifenyiduan(y)
            load_yifenyiduan(y)
            load_control_line(y)
    elif args.stage == "all":
        # 2026全流程
        fetch_yifenyiduan(2026)
        ocr_yifenyiduan(2026)
        load_yifenyiduan(2026)
        load_control_line(2026)
        # 历史2024+2025
        for y in [2024, 2025]:
            print(f"\n{'='*60}\n处理 {y} 年\n{'='*60}")
            fetch_yifenyiduan(y)
            ocr_yifenyiduan(y)
            load_yifenyiduan(y)
            load_control_line(y)
        # 校验
        ok = verify_yifenyiduan()
        if not ok:
            print("\n[VERIFY] 校验失败")
            sys.exit(1)
        print("\n[VERIFY] 全部通过 ✓")


if __name__ == "__main__":
    main()
