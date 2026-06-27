#!/usr/bin/env python3
"""河南 高考数据爬取脚本（2024-2026）

数据源:
- 一分一段表: eol.cn 网页表格 (2025/2026 物理+历史, 2024 文+理)
- 省控线: 河南省教育考试院公告 (硬编码已核实数据)
- 招生计划: 已有 plans_2026.csv 数据 (291行)
- 历史投档线: 待补充

输出:
- data/yifenyiduan_2024.csv (追加)
- data/yifenyiduan_2025.csv (追加)
- data/yifenyiduan_2026.csv (追加)
- data/control_line_2024.csv (追加)
- data/control_line_2025.csv (追加)
- data/control_line_2026.csv (追加)

字段顺序严格遵循 /backend/prompts/_common_spec.md
"""
from __future__ import annotations
import os
import sys
import re
import time
import requests
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path

# ─────────────────────────────────────────────────────────────────
# 路径配置
# ─────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw" / "henan_2026"

PROVINCE = "河南"
SUBJECT_GROUPS_NEW = ["物理类", "历史类"]  # 2025起 3+1+2
SUBJECT_GROUPS_OLD = {"理科": "物理类", "文科": "历史类"}  # 2024及之前 老高考

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# ─────────────────────────────────────────────────────────────────
# 一分一段表数据源URL（已验证可访问，HTML表格格式）
# ─────────────────────────────────────────────────────────────────
# 2025 eol.cn: 3列 分数|人数|累计人数
# 2024 eol.cn: 3列 分数|人数|累计人数 (老高考文/理，分别在不同URL)
# 2026 6617.com: 4列 分数|人数|累计人数|首选科目 (物理类+历史类在同一页面)
YIFENYIDUAN_URLS = {
    # 2025 新高考 3+1+2 (eol.cn 移动版)
    (2025, "物理类"): "http://www.eol.cn/m/gaokao/202506/t20250625_2676859.shtml",
    (2025, "历史类"): "http://www.eol.cn/m/gaokao/202506/t20250625_2676858.shtml",
    # 2026 新高考 3+1+2 (6617.com，物理+历史同一页面，由parser按"首选科目"列拆分)
    # p_2196990150.html 同时含2个表格: 表1物理(608行), 表2历史(588行)
    (2026, "物理类"): "https://m.6617.com/p_2196990150.html",
    (2026, "历史类"): "https://m.6617.com/p_2196990150.html",
    # 2024 老高考 文/理 → 转 物理类(理)/历史类(文)
    (2024, "物理类"): "http://www.eol.cn/m/gaokao/202406/t20240625_2619212_1.shtml",  # 理科
    (2024, "历史类"): "http://www.eol.cn/m/gaokao/202406/t20240625_2619212.shtml",    # 文科
}

# ─────────────────────────────────────────────────────────────────
# 省控线数据（已从河南省教育考试院公告核实）
# 来源: m.henan.gov.cn 河南省政府公告
# ─────────────────────────────────────────────────────────────────
CONTROL_LINE_DATA = [
    # 2026 新高考 3+1+2 (来源: https://m.henan.gov.cn/2026/06-25/3368880.html)
    # 普通本科批: 历史类459, 物理类419
    # 特殊类型: 历史类534, 物理类513
    # 普通高职(专科)批: 历史类179, 物理类179
    {"year": 2026, "batch_section": "普通本科批", "batch": "本科", "subject_group": "历史类", "line_type": "总分", "lowest_score": 459, "source_url": "https://m.henan.gov.cn/2026/06-25/3368880.html"},
    {"year": 2026, "batch_section": "普通本科批", "batch": "本科", "subject_group": "物理类", "line_type": "总分", "lowest_score": 419, "source_url": "https://m.henan.gov.cn/2026/06-25/3368880.html"},
    {"year": 2026, "batch_section": "特殊类型招生", "batch": "特控线", "subject_group": "历史类", "line_type": "总分", "lowest_score": 534, "source_url": "https://m.henan.gov.cn/2026/06-25/3368880.html"},
    {"year": 2026, "batch_section": "特殊类型招生", "batch": "特控线", "subject_group": "物理类", "line_type": "总分", "lowest_score": 513, "source_url": "https://m.henan.gov.cn/2026/06-25/3368880.html"},
    {"year": 2026, "batch_section": "普通高职(专科)批", "batch": "专科", "subject_group": "历史类", "line_type": "总分", "lowest_score": 179, "source_url": "https://m.henan.gov.cn/2026/06-25/3368880.html"},
    {"year": 2026, "batch_section": "普通高职(专科)批", "batch": "专科", "subject_group": "物理类", "line_type": "总分", "lowest_score": 179, "source_url": "https://m.henan.gov.cn/2026/06-25/3368880.html"},

    # 2025 新高考 3+1+2 首年 (来源: https://m.henan.gov.cn/2025/06-25/3173563.html)
    # 特殊类型: 历史类552, 物理类535
    # 本科批: 历史类471, 物理类427
    # 专科批: 历史类185, 物理类185
    {"year": 2025, "batch_section": "特殊类型招生", "batch": "特控线", "subject_group": "历史类", "line_type": "总分", "lowest_score": 552, "source_url": "https://m.henan.gov.cn/2025/06-25/3173563.html"},
    {"year": 2025, "batch_section": "特殊类型招生", "batch": "特控线", "subject_group": "物理类", "line_type": "总分", "lowest_score": 535, "source_url": "https://m.henan.gov.cn/2025/06-25/3173563.html"},
    {"year": 2025, "batch_section": "普通本科批", "batch": "本科", "subject_group": "历史类", "line_type": "总分", "lowest_score": 471, "source_url": "https://m.henan.gov.cn/2025/06-25/3173563.html"},
    {"year": 2025, "batch_section": "普通本科批", "batch": "本科", "subject_group": "物理类", "line_type": "总分", "lowest_score": 427, "source_url": "https://m.henan.gov.cn/2025/06-25/3173563.html"},
    {"year": 2025, "batch_section": "普通高职(专科)批", "batch": "专科", "subject_group": "历史类", "line_type": "总分", "lowest_score": 185, "source_url": "https://m.henan.gov.cn/2025/06-25/3173563.html"},
    {"year": 2025, "batch_section": "普通高职(专科)批", "batch": "专科", "subject_group": "物理类", "line_type": "总分", "lowest_score": 185, "source_url": "https://m.henan.gov.cn/2025/06-25/3173563.html"},

    # 2024 老高考 文/理 (来源: https://m.henan.gov.cn/2024/06-24/3012218.html)
    # 本科一批: 文科521, 理科511
    # 本科二批: 文科428, 理科396
    # 高职高专批: 文科185, 理科185
    # 注: 2024及之前为文/理科，按规范统一转为 物理类(理)/历史类(文)
    {"year": 2024, "batch_section": "本科一批", "batch": "本科", "subject_group": "历史类", "line_type": "总分", "lowest_score": 521, "source_url": "https://m.henan.gov.cn/2024/06-24/3012218.html"},
    {"year": 2024, "batch_section": "本科一批", "batch": "本科", "subject_group": "物理类", "line_type": "总分", "lowest_score": 511, "source_url": "https://m.henan.gov.cn/2024/06-24/3012218.html"},
    {"year": 2024, "batch_section": "本科二批", "batch": "本科", "subject_group": "历史类", "line_type": "总分", "lowest_score": 428, "source_url": "https://m.henan.gov.cn/2024/06-24/3012218.html"},
    {"year": 2024, "batch_section": "本科二批", "batch": "本科", "subject_group": "物理类", "line_type": "总分", "lowest_score": 396, "source_url": "https://m.henan.gov.cn/2024/06-24/3012218.html"},
    {"year": 2024, "batch_section": "高职高专批", "batch": "专科", "subject_group": "历史类", "line_type": "总分", "lowest_score": 185, "source_url": "https://m.henan.gov.cn/2024/06-24/3012218.html"},
    {"year": 2024, "batch_section": "高职高专批", "batch": "专科", "subject_group": "物理类", "line_type": "总分", "lowest_score": 185, "source_url": "https://m.henan.gov.cn/2024/06-24/3012218.html"},

    # 2023 老高考 文/理 (来源: https://m.henan.gov.cn/2023/06-24/2765644.html)
    # 本科一批: 文科547, 理科514
    # 本科二批: 文科465, 理科409
    # 高职高专批: 文科185, 理科185
    {"year": 2023, "batch_section": "本科一批", "batch": "本科", "subject_group": "历史类", "line_type": "总分", "lowest_score": 547, "source_url": "https://m.henan.gov.cn/2023/06-24/2765644.html"},
    {"year": 2023, "batch_section": "本科一批", "batch": "本科", "subject_group": "物理类", "line_type": "总分", "lowest_score": 514, "source_url": "https://m.henan.gov.cn/2023/06-24/2765644.html"},
    {"year": 2023, "batch_section": "本科二批", "batch": "本科", "subject_group": "历史类", "line_type": "总分", "lowest_score": 465, "source_url": "https://m.henan.gov.cn/2023/06-24/2765644.html"},
    {"year": 2023, "batch_section": "本科二批", "batch": "本科", "subject_group": "物理类", "line_type": "总分", "lowest_score": 409, "source_url": "https://m.henan.gov.cn/2023/06-24/2765644.html"},
    {"year": 2023, "batch_section": "高职高专批", "batch": "专科", "subject_group": "历史类", "line_type": "总分", "lowest_score": 185, "source_url": "https://m.henan.gov.cn/2023/06-24/2765644.html"},
    {"year": 2023, "batch_section": "高职高专批", "batch": "专科", "subject_group": "物理类", "line_type": "总分", "lowest_score": 185, "source_url": "https://m.henan.gov.cn/2023/06-24/2765644.html"},
]


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════
def append_to_csv(new_df: pd.DataFrame, csv_filename: str, dedup_cols: list[str] | None = None) -> int:
    """安全追加数据到CSV（去重），返回新增行数

    关键: 把 new_df 转为 str 再与 existing(str) 合并，避免 dtype 不一致导致去重失败。
    """
    csv_path = DATA_DIR / csv_filename
    # #14 root fix: 重定向到 data/raw/{省}_{文件名}，禁止直接写主 CSV
    _raw_dir = DATA_DIR / "raw"
    _raw_dir.mkdir(exist_ok=True)
    csv_path = _raw_dir / f"{PROVINCE}_{csv_path.name}"
    new_df_str = new_df.astype(str).fillna("")
    if csv_path.exists():
        existing = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        before = len(existing)
        merged = pd.concat([existing, new_df_str], ignore_index=True)
        if dedup_cols:
            merged = merged.drop_duplicates(subset=dedup_cols, keep="last")
        else:
            merged = merged.drop_duplicates(keep="last")
        merged.to_csv(csv_path, index=False, encoding="utf-8")
        return len(merged) - before
    else:
        new_df_str.to_csv(csv_path, index=False, encoding="utf-8")
        return len(new_df_str)


def fetch_html(url: str, retries: int = 3, timeout: int = 20) -> str | None:
    """带重试的HTML获取"""
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, verify=False)
            if r.status_code == 200:
                r.encoding = r.apparent_encoding or "utf-8"
                return r.text
            print(f"  [WARN] {url} 状态={r.status_code} (attempt {attempt+1})")
        except Exception as e:
            print(f"  [WARN] {url} 异常={e} (attempt {attempt+1})")
        time.sleep(1.5 * (attempt + 1))
    return None


# ═══════════════════════════════════════════════════════════════
# 一分一段表爬取（从网页表格）
# ═══════════════════════════════════════════════════════════════
def parse_yifenyiduan_html(html: str, year: int, subject_group: str) -> pd.DataFrame:
    """从HTML解析一分一段表

    支持两种表格结构:
    - 3列: 分数 | 人数 | 累计人数  (eol.cn 2024/2025)
    - 4列: 分数 | 人数 | 累计人数 | 首选科目  (6617.com 2026, 物理类+历史类同页面)

    当4列时，根据"首选科目"列过滤出目标科类。
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        print(f"  [FAIL] 页面无表格")
        return pd.DataFrame()

    data = []
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if not cells:
                continue
            # 跳过表头
            joined = "".join(cells)
            if any(kw in joined for kw in ["分数", "人数", "累计", "考生人数", "首选"]):
                continue

            # 4列: 分数|人数|累计人数|首选科目 (2026 6617.com)
            row_sg = None
            if len(cells) >= 4:
                score_str, seg_str, cum_str, sg_str = cells[0], cells[1], cells[2], cells[3]
                if "物理" in sg_str:
                    row_sg = "物理类"
                elif "历史" in sg_str:
                    row_sg = "历史类"
            # 3列: 分数|人数|累计人数
            elif len(cells) >= 3:
                score_str, seg_str, cum_str = cells[0], cells[1], cells[2]
            # 2列: 分数|累计人数
            elif len(cells) == 2:
                score_str, cum_str = cells[0], cells[1]
                seg_str = ""
            else:
                continue

            # 4列模式：只保留目标科类
            if row_sg is not None and row_sg != subject_group:
                continue

            # 解析分数（可能是 "710-750" 或 "709" 或 "709（含以上）"）
            m = re.match(r"(\d{2,3})", score_str)
            if not m:
                continue
            score = int(m.group(1))
            if not (0 <= score <= 750):
                continue

            # 解析累计人数
            cum_str_clean = re.sub(r"[^\d]", "", cum_str)
            if not cum_str_clean:
                continue
            cumulative = int(cum_str_clean)
            if cumulative > 1000000:
                continue

            # 解析段人数
            seg_str_clean = re.sub(r"[^\d]", "", seg_str) if seg_str else ""
            segment = int(seg_str_clean) if seg_str_clean else 0

            data.append({
                "province": PROVINCE,
                "year": year,
                "subject_group": subject_group,
                "batch": "本科",  # 河南一分一段表累计含全部考生
                "score": score,
                "segment_count": segment,
                "cumulative_count": cumulative,
            })

    # 去重（同分数可能多次出现）
    if data:
        seen = set()
        deduped = []
        for r in data:
            key = (r["score"], r["subject_group"])
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        data = deduped

    print(f"  [OK] 解析 {len(data)} 行")
    return pd.DataFrame(data)


def fetch_yifenyiduan_all() -> dict[str, pd.DataFrame]:
    """爬取所有一分一段表，返回 {csv文件名: DataFrame}

    优化: 2026年物理类和历史类用同一URL，只下载一次HTML，分别解析两个科类。
    """
    print(f"\n{'='*60}\n[一分一段表] 开始爬取\n{'='*60}")
    results = {}
    html_cache = {}  # url -> html (避免同URL重复下载)

    for (year, sg), url in YIFENYIDUAN_URLS.items():
        print(f"\n[{year} {sg}]")
        if url in html_cache:
            print(f"  [CACHE] 复用已下载HTML")
            html = html_cache[url]
        else:
            print(f"  [FETCH] {url}")
            html = fetch_html(url)
            if not html:
                print(f"  [FAIL] 无法获取页面")
                continue
            html_cache[url] = html

        df = parse_yifenyiduan_html(html, year, sg)
        if len(df) > 0:
            csv_name = f"yifenyiduan_{year}.csv"
            if csv_name in results:
                results[csv_name] = pd.concat([results[csv_name], df], ignore_index=True)
            else:
                results[csv_name] = df
    return results


# ═══════════════════════════════════════════════════════════════
# 省控线写入
# ═══════════════════════════════════════════════════════════════
def write_control_lines() -> dict[str, int]:
    """写入省控线数据，返回 {csv文件名: 新增行数}"""
    print(f"\n{'='*60}\n[省控线] 写入数据\n{'='*60}")
    results = {}
    df_all = pd.DataFrame(CONTROL_LINE_DATA)
    df_all.insert(0, "province", PROVINCE)
    for year in [2024, 2025, 2026]:  # 规范要求3年，2023保留在数据中但不写入CSV
        df_year = df_all[df_all["year"] == year].copy()
        if len(df_year) == 0:
            continue
        # 字段顺序: province,year,batch_section,batch,subject_group,line_type,lowest_score,source_url
        df_year = df_year[["province", "year", "batch_section", "batch",
                           "subject_group", "line_type", "lowest_score", "source_url"]]
        csv_name = f"control_line_{year}.csv"
        n = append_to_csv(df_year, csv_name,
                          dedup_cols=["province", "year", "batch_section", "subject_group", "line_type"])
        print(f"  {csv_name}: +{n} 行 (总{len(df_year)}条)")
        results[csv_name] = n
    return results


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════
def main():
    print(f"\n{'#'*60}")
    print(f"# 河南 高考数据爬取 (2024-2026)")
    print(f"{'#'*60}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 省控线（已硬编码，直接写入）
    cl_results = write_control_lines()

    # 2. 一分一段表（从网页爬取）
    yyd_results = fetch_yifenyiduan_all()
    yyd_write = {}
    for csv_name, df in yyd_results.items():
        if len(df) == 0:
            continue
        n = append_to_csv(df, csv_name,
                          dedup_cols=["province", "year", "subject_group", "batch", "score"])
        print(f"  {csv_name}: +{n} 行")
        yyd_write[csv_name] = n

    # 3. 汇总报告
    print(f"\n{'='*60}")
    print(f"========== 河南 数据爬取报告 ==========")
    print(f"{'='*60}")
    print(f"省控线:")
    for k, v in cl_results.items():
        print(f"  {k}: +{v} 行")
    print(f"一分一段表:")
    for k, v in yyd_write.items():
        print(f"  {k}: +{v} 行")
    print(f"\nplans_2026.csv: 已有 291 行 (保留)")
    print(f"plans_2025.csv: 待补充 (需招生计划PDF)")
    print(f"admission_history.csv: 待补充 (需投档线PDF)")
    print(f"\n[完成] 请重启后端服务 (uvicorn main:app) 加载新数据")


if __name__ == "__main__":
    main()
