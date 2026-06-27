#!/usr/bin/env python3
"""陕西省教育考试院高考数据同步脚本。

数据源: https://www.sneac.com
覆盖数据:
  - 一分一段表 (yifenyiduan): 2024/2025/2026 三年
  - 省控线 (control_line): 2024/2025/2026 三年
  - 历史投档线 (admission_history): 2023/2024 两年 (2025未公开)

陕西2025年首改3+1+2，2024及之前为文/理科。
本脚本统一输出为 物理类/历史类:
  - 理工 → 物理类
  - 文史 → 历史类

用法:
    python scripts/sync_shaanxi_2026.py           # 全流程
    python scripts/sync_shaanxi_2026.py fetch      # 仅下载
    python scripts/sync_shaanxi_2026.py parse      # 仅解析并写入CSV
"""
from __future__ import annotations

import csv
import io
import os
import re
import sys
from pathlib import Path

import httpx
import pandas as pd

# ─────────────────────────────────────────────────────────────────
# 路径配置
# ─────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw" / "shaanxi_2026"

PROVINCE = "陕西"
BASE_URL = "https://www.sneac.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# ─────────────────────────────────────────────────────────────────
# 数据源配置
# ─────────────────────────────────────────────────────────────────
# 一分一段表: {年份: {科类: URL}}
# 2024年为文/理科，URL中标注文史/理工，统一映射为历史类/物理类
YIFENYIDUAN_SOURCES = {
    2024: {
        "历史类": f"{BASE_URL}/info/1019/17788.htm",   # 文史
        "物理类": f"{BASE_URL}/info/1019/17786.htm",   # 理工
    },
    2025: {
        "物理类": f"{BASE_URL}/info/1019/18391.htm",
        "历史类": f"{BASE_URL}/info/1019/18393.htm",
    },
    2026: {
        "物理类": f"{BASE_URL}/info/1019/18782.htm",
        "历史类": f"{BASE_URL}/info/1019/18783.htm",
    },
}

# 省控线: {年份: URL}
CONTROL_LINE_SOURCES = {
    2024: f"{BASE_URL}/info/1019/17777.htm",
    2025: f"{BASE_URL}/info/1019/18384.htm",
    2026: f"{BASE_URL}/info/1019/18765.htm",
}

# 历史投档线: {年份: {批次: {科类: URL}}}
# 2023/2024为文/理科，URL中-WS=文史→历史类，-LG=理工→物理类
ADMISSION_HISTORY_SOURCES = {
    2023: {
        "本科一批": {
            "历史类": f"{BASE_URL}/htm/2023/2023YBZS-WS.html",
            "物理类": f"{BASE_URL}/htm/2023/2023YBZS-LG.html",
        },
        "本科二批": {
            "历史类": f"{BASE_URL}/htm/2023/2023EBZS-WS.html",
            "物理类": f"{BASE_URL}/htm/2023/2023EBZS-LG.html",
        },
        "专科批": {
            "历史类": f"{BASE_URL}/htm/2023/2023GZZS-WS.html",
            "物理类": f"{BASE_URL}/htm/2023/2023GZZS-LG.html",
        },
    },
    2024: {
        "本科一批": {
            "历史类": f"{BASE_URL}/htm/2024/1BZS-WS.html",
            "物理类": f"{BASE_URL}/htm/2024/1BZS-LG.html",
        },
        "本科二批": {
            "历史类": f"{BASE_URL}/htm/2024/2024EBZS-WS.html",
            "物理类": f"{BASE_URL}/htm/2024/2024EBZS-LG.html",
        },
        "专科批": {
            "历史类": f"{BASE_URL}/htm/2024/2024GZZKZS-WS.html",
            "物理类": f"{BASE_URL}/htm/2024/2024GZZKZS-LG.html",
        },
    },
}


# ═══════════════════════════════════════════════════════════════
# 通用工具函数
# ═══════════════════════════════════════════════════════════════
def fetch_html(url: str, cache_name: str) -> str:
    """下载HTML页面，带本地缓存。"""
    cache_path = RAW_DIR / cache_name
    if cache_path.exists() and cache_path.stat().st_size > 500:
        return cache_path.read_text(encoding="utf-8", errors="replace")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  [下载] {url}")
    r = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
    if r.status_code != 200:
        raise RuntimeError(f"下载失败 {url} status={r.status_code}")
    # 确保UTF-8编码
    r.encoding = r.charset_encoding or "utf-8"
    html = r.text
    cache_path.write_text(html, encoding="utf-8")
    print(f"  [OK] {cache_name} ({len(html)} chars)")
    return html


def clean_cell(val) -> str:
    """清洗单元格文本。"""
    if val is None:
        return ""
    s = str(val).strip()
    s = re.sub(r"\s+", "", s)
    if s in ("", "-", "—", "null", "None", "NA", "nan"):
        return ""
    return s


def to_int(val) -> int | None:
    """安全转整数。"""
    s = clean_cell(val)
    if not s:
        return None
    s = s.replace(",", "")
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def append_to_csv(new_df: pd.DataFrame, csv_filename: str) -> int:
    """安全追加数据到CSV（去重，不覆盖其他省份数据）。

    Returns: 实际新增的行数
    """
    csv_path = DATA_DIR / csv_filename
    # #14 root fix: 重定向到 data/raw/{省}_{文件名}，禁止直接写主 CSV
    _raw_dir = DATA_DIR / "raw"
    _raw_dir.mkdir(exist_ok=True)
    csv_path = _raw_dir / f"{PROVINCE}_{csv_path.name}"
    if csv_path.exists():
        existing = pd.read_csv(csv_path, dtype=str)
        # 去除可能的陕西旧数据（幂等：重跑只覆盖陕西数据）
        existing_no_sx = existing[existing["province"] != PROVINCE]
        merged = pd.concat([existing_no_sx, new_df], ignore_index=True)
    else:
        merged = new_df
    # 去完全重复行
    merged = merged.drop_duplicates()
    merged.to_csv(csv_path, index=False, encoding="utf-8")
    return len(new_df)


# ═══════════════════════════════════════════════════════════════
# 阶段1: 一分一段表
# ═══════════════════════════════════════════════════════════════
def parse_yifenyiduan_html(html: str, year: int, subject_group: str) -> list[dict]:
    """解析一分一段表HTML，返回行列表。

    表格结构: 分数 | 人数 | 累计人数
    特殊行: "709及以上" → score=709
    """
    rows = []
    # 尝试用pandas解析HTML表格
    try:
        tables = pd.read_html(io.StringIO(html))
        for df in tables:
            if len(df.columns) >= 3:
                for _, row in df.iterrows():
                    score_raw = clean_cell(row.iloc[0])
                    if not score_raw or "分数" in score_raw:
                        continue
                    # 提取分数: "709及以上" → 709
                    m = re.match(r"(\d+)", score_raw)
                    if not m:
                        continue
                    score = int(m.group(1))
                    if score < 0 or score > 750:
                        continue
                    segment = to_int(row.iloc[1])
                    cumulative = to_int(row.iloc[2])
                    if cumulative is None or cumulative < 0:
                        continue
                    rows.append({
                        "province": PROVINCE,
                        "year": year,
                        "subject_group": subject_group,
                        "batch": "本科批",
                        "score": score,
                        "segment_count": segment if segment is not None else 0,
                        "cumulative_count": cumulative,
                    })
                break
    except Exception as e:
        print(f"  [WARN] pandas.read_html失败，尝试正则解析: {e}")
        # 正则回退方案
        row_pattern = re.compile(
            r"<tr[^>]*>\s*<td[^>]*>([^<]+)</td>\s*<td[^>]*>([^<]+)</td>\s*<td[^>]*>([^<]+)</td>",
            re.I,
        )
        for m in row_pattern.finditer(html):
            score_raw = clean_cell(m.group(1))
            if not score_raw or "分数" in score_raw:
                continue
            sm = re.match(r"(\d+)", score_raw)
            if not sm:
                continue
            score = int(sm.group(1))
            if score < 0 or score > 750:
                continue
            segment = to_int(m.group(2))
            cumulative = to_int(m.group(3))
            if cumulative is None or cumulative < 0:
                continue
            rows.append({
                "province": PROVINCE,
                "year": year,
                "subject_group": subject_group,
                "batch": "本科批",
                "score": score,
                "segment_count": segment if segment is not None else 0,
                "cumulative_count": cumulative,
            })

    # 去重（同分数取第一次出现）
    seen = set()
    deduped = []
    for r in rows:
        key = (r["year"], r["subject_group"], r["batch"], r["score"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped


def sync_yifenyiduan() -> dict:
    """同步所有年份的一分一段表。"""
    print(f"\n{'='*60}")
    print(f"[一分一段表] 开始同步")
    print(f"{'='*60}")
    stats = {}
    all_rows = []

    for year, subjects in YIFENYIDUAN_SOURCES.items():
        for sg, url in subjects.items():
            cache_name = f"yifenyiduan_{year}_{sg}.html"
            try:
                html = fetch_html(url, cache_name)
                rows = parse_yifenyiduan_html(html, year, sg)
                print(f"  [陕西] ✓ 一分一段 {year} {sg}: {len(rows)}行")
                stats[f"{year}_{sg}"] = len(rows)
                all_rows.extend(rows)
            except Exception as e:
                print(f"  [陕西] ✗ 一分一段 {year} {sg} 失败: {e}")
                stats[f"{year}_{sg}"] = 0

    if not all_rows:
        print("  [WARN] 未提取到任何一分一段数据")
        return stats

    df = pd.DataFrame(all_rows)
    # 按年份写入对应CSV
    for year in YIFENYIDUAN_SOURCES:
        year_df = df[df["year"] == year].copy()
        if year_df.empty:
            continue
        csv_file = f"yifenyiduan_{year}.csv"
        n = append_to_csv(year_df, csv_file)
        print(f"  [陕西] ✓ 写入 {csv_file}: {n}行")

    return stats


# ═══════════════════════════════════════════════════════════════
# 阶段2: 省控线
# ═══════════════════════════════════════════════════════════════
def parse_control_line_html(html: str, year: int) -> list[dict]:
    """解析省控线HTML文本，返回行列表。

    支持两种格式:
    - 2024 (老高考): "本科一批：文史类 488 分，理工类 475 分。"
    - 2025/2026 (3+1+2): "普通类（历史）414分，普通类（物理）394分。"
    """
    # 提取纯文本
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&nbsp;", " ").replace("&#160;", " ")
    text = re.sub(r"\s+", " ", text)

    source_url = ""
    rows = []

    if year <= 2024:
        # 老高考格式: 文史类/理工类
        # 本科一批：文史类 488 分，理工类 475 分
        # 本科二批：文史类 397 分，理工类 372 分
        # 高职（专科）：文史类 150 分，理工类 150 分
        patterns = [
            (r"本科一批[：:]\s*文史类\s*(\d+)\s*分[，,]?\s*理工类\s*(\d+)\s*分",
             "本科一批", "本科一批"),
            (r"本科二批[：:]\s*文史类\s*(\d+)\s*分[，,]?\s*理工类\s*(\d+)\s*分",
             "本科二批", "本科二批"),
            (r"高职[（(]专科[)）][：:]\s*文史类\s*(\d+)\s*分[，,]?\s*理工类\s*(\d+)\s*分",
             "高职（专科）", "专科"),
        ]
        for pat, section, batch in patterns:
            m = re.search(pat, text)
            if m:
                wen = int(m.group(1))
                li = int(m.group(2))
                rows.append({
                    "province": PROVINCE, "year": year,
                    "batch_section": section, "batch": batch,
                    "subject_group": "历史类", "line_type": "总分",
                    "lowest_score": wen, "source_url": "",
                })
                rows.append({
                    "province": PROVINCE, "year": year,
                    "batch_section": section, "batch": batch,
                    "subject_group": "物理类", "line_type": "总分",
                    "lowest_score": li, "source_url": "",
                })
        # 特殊类型 (2024可能没有单独列出)
        m = re.search(r"特殊类型[^\d]*(?:文史类|文科)\s*(\d+)\s*分[，,]?\s*(?:理工类|理科)\s*(\d+)\s*分", text)
        if m:
            rows.append({
                "province": PROVINCE, "year": year,
                "batch_section": "特殊类型", "batch": "特控线",
                "subject_group": "历史类", "line_type": "总分",
                "lowest_score": int(m.group(1)), "source_url": "",
            })
            rows.append({
                "province": PROVINCE, "year": year,
                "batch_section": "特殊类型", "batch": "特控线",
                "subject_group": "物理类", "line_type": "总分",
                "lowest_score": int(m.group(2)), "source_url": "",
            })
    else:
        # 3+1+2格式: 普通类（历史）XXX分，普通类（物理）YYY分
        # 注意：HTML标签剥离后括号内可能有空格，如"普通类（ 历史 ） 385 分"
        # 策略：直接找所有"普通类（历史）XXX分，普通类（物理）YYY分"匹配，按顺序分配批次
        all_matches = list(re.finditer(
            r"普通类[（(]\s*历史\s*[)）]\s*(\d+)\s*分[，,]?\s*普通类[（(]\s*物理\s*[)）]\s*(\d+)\s*分",
            text,
        ))
        sections = [
            ("本科批次", "本科"),
            ("特殊类型", "特控线"),
            ("高职（专科）", "专科"),
        ]
        for i, m in enumerate(all_matches[:3]):
            section, batch = sections[i] if i < len(sections) else (f"批次{i+1}", f"批次{i+1}")
            rows.append({
                "province": PROVINCE, "year": year,
                "batch_section": section, "batch": batch,
                "subject_group": "历史类", "line_type": "总分",
                "lowest_score": int(m.group(1)), "source_url": "",
            })
            rows.append({
                "province": PROVINCE, "year": year,
                "batch_section": section, "batch": batch,
                "subject_group": "物理类", "line_type": "总分",
                "lowest_score": int(m.group(2)), "source_url": "",
            })

    # 填充source_url
    for r in rows:
        r["source_url"] = CONTROL_LINE_SOURCES.get(year, "")

    return rows


def sync_control_line() -> dict:
    """同步所有年份的省控线。"""
    print(f"\n{'='*60}")
    print(f"[省控线] 开始同步")
    print(f"{'='*60}")
    stats = {}
    all_rows = []

    for year, url in CONTROL_LINE_SOURCES.items():
        cache_name = f"control_line_{year}.html"
        try:
            html = fetch_html(url, cache_name)
            rows = parse_control_line_html(html, year)
            print(f"  [陕西] ✓ 省控线 {year}: {len(rows)}行")
            for r in rows:
                if r["subject_group"] in ("物理类", "历史类"):
                    print(f"    {r['batch_section']}/{r['batch']} {r['subject_group']}: {r['lowest_score']}分")
            stats[year] = len(rows)
            all_rows.extend(rows)
        except Exception as e:
            print(f"  [陕西] ✗ 省控线 {year} 失败: {e}")
            stats[year] = 0

    if not all_rows:
        print("  [WARN] 未提取到任何省控线数据")
        return stats

    df = pd.DataFrame(all_rows)
    for year in CONTROL_LINE_SOURCES:
        year_df = df[df["year"] == year].copy()
        if year_df.empty:
            continue
        csv_file = f"control_line_{year}.csv"
        n = append_to_csv(year_df, csv_file)
        print(f"  [陕西] ✓ 写入 {csv_file}: {n}行")

    return stats


# ═══════════════════════════════════════════════════════════════
# 阶段3: 历史投档线
# ═══════════════════════════════════════════════════════════════
def parse_admission_html(html: str, year: int, subject_group: str, batch: str) -> list[dict]:
    """解析投档线HTML表格，返回行列表。

    表格结构: 序号 | 科类 | 院校代号 | 院校名称 | 计划数 | 投档人数 | 最低分 | 最低位次
    """
    rows = []
    source_file = f"{year}年陕西省普通高校招生{batch}正式投档情况统计表"

    try:
        tables = pd.read_html(io.StringIO(html))
        for df in tables:
            if len(df.columns) < 6:
                continue
            for _, row in df.iterrows():
                # 跳过表头
                first_val = clean_cell(row.iloc[0])
                if not first_val or "序号" in first_val:
                    continue
                # 院校代号在第3列(index 2)，院校名称在第4列(index 3)
                # 但有些表格可能列数不同，做适配
                code_idx, name_idx, score_idx, rank_idx = 2, 3, 6, 7
                if len(df.columns) == 8:
                    code_idx, name_idx, score_idx, rank_idx = 2, 3, 6, 7
                elif len(df.columns) == 7:
                    code_idx, name_idx, score_idx, rank_idx = 1, 2, 5, 6
                else:
                    # 尝试按列名匹配
                    cols_lower = [str(c).lower() for c in df.columns]
                    for i, c in enumerate(cols_lower):
                        if "代号" in c or "代码" in c:
                            code_idx = i
                        elif "名称" in c:
                            name_idx = i
                        elif "最低分" in c or "分数" in c:
                            score_idx = i
                        elif "位次" in c or "排位" in c:
                            rank_idx = i

                code = clean_cell(row.iloc[code_idx]) if code_idx < len(df.columns) else ""
                name = clean_cell(row.iloc[name_idx]) if name_idx < len(df.columns) else ""
                if not code or not name:
                    continue
                # 跳过科类为空或非文/理/物理/历史的行
                score = to_int(row.iloc[score_idx]) if score_idx < len(df.columns) else None
                rank = to_int(row.iloc[rank_idx]) if rank_idx < len(df.columns) else None

                # 分数合理性校验
                if score is None or score < 0 or score > 750:
                    score = None
                if rank is not None and rank <= 0:
                    rank = None

                # 计划数和投档人数
                plan_count = to_int(row.iloc[4]) if len(df.columns) > 4 else None
                admit_count = to_int(row.iloc[5]) if len(df.columns) > 5 else None

                rows.append({
                    "year": year,
                    "province": PROVINCE,
                    "subject_group": subject_group,
                    "batch": batch,
                    "university_code": code,
                    "university_name": name,
                    "group_code": code,       # 老高考无专业组，用院校代号
                    "major_code": code,       # 无专业级数据，填代号
                    "major_name": f"第{code}组",
                    "lowest_score": score,
                    "lowest_rank": rank,
                    "avg_score": None,
                    "applicant_count": admit_count if admit_count else plan_count,
                    "source_file": source_file,
                })
    except Exception as e:
        print(f"  [WARN] pandas.read_html失败，尝试正则解析: {e}")
        # 正则回退: 匹配 <tr><td>...</td>...</tr>
        td_pattern = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
        tr_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
        for tr_match in tr_pattern.finditer(html):
            tds = td_pattern.findall(tr_match.group(1))
            if len(tds) < 6:
                continue
            cells = [clean_cell(td) for td in tds]
            if not cells[0] or "序号" in cells[0]:
                continue
            # 找到院校代号列
            code = ""
            name = ""
            score = None
            rank = None
            if len(cells) >= 8:
                code, name = cells[2], cells[3]
                score = to_int(cells[6])
                rank = to_int(cells[7])
            elif len(cells) >= 7:
                code, name = cells[1], cells[2]
                score = to_int(cells[5])
                rank = to_int(cells[6])
            if not code or not name:
                continue
            if score is not None and (score < 0 or score > 750):
                score = None
            rows.append({
                "year": year,
                "province": PROVINCE,
                "subject_group": subject_group,
                "batch": batch,
                "university_code": code,
                "university_name": name,
                "group_code": code,
                "major_code": code,
                "major_name": f"第{code}组",
                "lowest_score": score,
                "lowest_rank": rank,
                "avg_score": None,
                "applicant_count": None,
                "source_file": source_file,
            })

    # 去重
    seen = set()
    deduped = []
    for r in rows:
        key = (r["year"], r["subject_group"], r["batch"], r["university_code"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped


def sync_admission_history() -> dict:
    """同步历史投档线。"""
    print(f"\n{'='*60}")
    print(f"[历史投档线] 开始同步")
    print(f"{'='*60}")
    stats = {}
    all_rows = []

    for year, batches in ADMISSION_HISTORY_SOURCES.items():
        for batch, subjects in batches.items():
            for sg, url in subjects.items():
                cache_name = f"toudang_{year}_{batch}_{sg}.html"
                try:
                    html = fetch_html(url, cache_name)
                    rows = parse_admission_html(html, year, sg, batch)
                    print(f"  [陕西] ✓ 投档线 {year} {batch} {sg}: {len(rows)}行")
                    stats[f"{year}_{batch}_{sg}"] = len(rows)
                    all_rows.extend(rows)
                except Exception as e:
                    print(f"  [陕西] ✗ 投档线 {year} {batch} {sg} 失败: {e}")
                    stats[f"{year}_{batch}_{sg}"] = 0

    if not all_rows:
        print("  [WARN] 未提取到任何投档线数据")
        return stats

    df = pd.DataFrame(all_rows)
    # 写入admission_history.csv
    n = append_to_csv(df, "admission_history.csv")
    print(f"  [陕西] ✓ 写入 admission_history.csv: {n}行")

    # 统计
    for year in ADMISSION_HISTORY_SOURCES:
        year_count = len(df[df["year"] == year])
        print(f"  [统计] {year}年: {year_count}行")

    return stats


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════
def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    print(f"\n{'='*60}")
    print(f"[{PROVINCE}] 开始同步高考数据 (stage={stage})")
    print(f"{'='*60}")

    if stage in ("fetch", "all"):
        # fetch阶段内嵌在各sync函数中（带缓存）
        pass

    stats = {}
    if stage in ("yifenyiduan", "all"):
        stats["yifenyiduan"] = sync_yifenyiduan()

    if stage in ("control_line", "all"):
        stats["control_line"] = sync_control_line()

    if stage in ("admission", "all"):
        stats["admission"] = sync_admission_history()

    # 汇总报告
    print(f"\n{'='*60}")
    print(f"[{PROVINCE}] 数据同步完成")
    print(f"{'='*60}")

    if "yifenyiduan" in stats:
        yd = stats["yifenyiduan"]
        total_yd = sum(yd.values())
        print(f"\n一分一段表: 共 {total_yd} 行")
        for k, v in yd.items():
            print(f"  {k}: {v}行")

    if "control_line" in stats:
        cl = stats["control_line"]
        total_cl = sum(cl.values())
        print(f"\n省控线: 共 {total_cl} 行")
        for k, v in cl.items():
            print(f"  {k}年: {v}行")

    if "admission" in stats:
        ah = stats["admission"]
        total_ah = sum(ah.values())
        print(f"\n历史投档线: 共 {total_ah} 行")
        for k, v in ah.items():
            print(f"  {k}: {v}行")

    print(f"\n[注意] 招生计划(plans)数据陕西省不公开发布，仅通过印刷书籍和志愿填报系统提供")
    print(f"[注意] 2025年投档线数据陕西省未公开发布")
    print(f"\n[完成] 请重启后端服务 (uvicorn main:app) 以加载新数据")


if __name__ == "__main__":
    main()
