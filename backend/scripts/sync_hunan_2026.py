#!/usr/bin/env python3
"""湖南省高考数据爬取与同步脚本（覆盖 2024/2025/2026 三年）。

数据源:
  - 湖南省教育厅 jyt.hunan.gov.cn (2026 一分一段表 HTML)
  - 湖南招生考试信息港 hneeb.cn (2024/2025 一分一段表 HTML + 投档线 Excel)
  - 湖南省官方新闻发布会公告 (省控线数值，硬编码)

目标 CSV (追加模式，字段顺序见 _common_spec.md):
  - yifenyiduan_2024/2025/2026.csv
  - control_line_2024/2025/2026.csv
  - admission_history.csv (本科批投档线 2024/2025)

特点:
  - 一分一段表 HTML 表格: 2024 年 5 列(含全国性加分+地方加分)，2025/2026 年 3 列
  - 投档线 Excel 16 列，header=2，科类"普通类(首选历史/物理)"→"历史类/物理类"
  - 追加去重策略：按 province+year+key_cols 覆盖式更新当年湖南数据
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import pandas as pd
import requests

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_2026 = DATA_DIR / "raw" / "hunan_2026"
RAW_2025 = DATA_DIR / "raw" / "hunan_2025"
RAW_2024 = DATA_DIR / "raw" / "hunan_2024"

PROVINCE = "湖南"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# ═══════════════════════════════════════════════════════════════
# 数据源 URL
# ═══════════════════════════════════════════════════════════════
URLS_2026 = {
    "yifenyiduan_physics": "https://jyt.hunan.gov.cn/jyt/sjyt/hnsjyksy/web/ksyzkzx/202606/t20260625_34013125.html",
    "yifenyiduan_history": "https://jyt.hunan.gov.cn/jyt/sjyt/hnsjyksy/web/ksyzkzx/202606/t20260625_34013108.html",
    "control_line": "https://jyt.hunan.gov.cn/jyt/sjyt/hnsjyksy/web/ksyzkzx/202606/t20260625_34011553.html",
}
URLS_2025 = {
    "yifenyiduan_physics": "https://www.hneeb.cn/hnxxg/741/742/content_4434.html",
    "yifenyiduan_history": "https://www.hneeb.cn/hnxxg/741/742/content_4433.html",
    "toudang_benke": "https://jyt.hunan.gov.cn/jyt/sjyt/hnsjyksy/web/ksyzkzx/202507/33744762/files/b3230b1d6d374bc6858030c97267374b.xlsx",
}
URLS_2024 = {
    "yifenyiduan_physics": "https://www.hneeb.cn/hnxxg/741/742/content_4207.html",
    "yifenyiduan_history": "https://www.hneeb.cn/hnxxg/741/742/content_4206.html",
    "toudang_benke": "https://www.hneeb.cn/hnxxg/741/742/2024072001.xlsx",
}

# ═══════════════════════════════════════════════════════════════
# 省控线（官方新闻发布会公告数值，硬编码）
# ═══════════════════════════════════════════════════════════════
CONTROL_LINE_2026_URL = URLS_2026["control_line"]
CONTROL_LINE_2025_URL = "https://jyt.hunan.gov.cn/jyt/sjyt/hnsjyksy/web/ksyzkzx/202506/t20250624_33698897.html"
CONTROL_LINE_2024_URL = "https://jyt.hunan.gov.cn/jyt/sjyt/hnsjyksy/web/ksyzkzx/202406/t20240625_33333291.html"

# 格式: (batch_section, batch, subject_group, line_type, lowest_score)
CONTROL_LINE_2026 = [
    ("本科院校", "本科", "历史类", "总分", 446),
    ("本科院校", "本科", "物理类", "总分", 400),
    ("特殊类型招生", "特控线", "历史类", "总分", 494),
    ("特殊类型招生", "特控线", "物理类", "总分", 481),
    ("专科院校", "专科", "历史类", "总分", 200),
    ("专科院校", "专科", "物理类", "总分", 200),
    # 体育类
    ("本科院校", "本科", "体育类(历史)", "文化科总分", 349),
    ("本科院校", "本科", "体育类(历史)", "专业省统考", 257),
    ("本科院校", "本科", "体育类(物理)", "文化科总分", 310),
    ("本科院校", "本科", "体育类(物理)", "专业省统考", 257),
    # 艺术类平行组
    ("本科院校", "本科", "音乐类", "文化科总分", 320),
    ("本科院校", "本科", "音乐类", "专业省统考", 209),
    ("本科院校", "本科", "舞蹈类", "文化科总分", 300),
    ("本科院校", "本科", "舞蹈类", "专业省统考", 174),
    ("本科院校", "本科", "播音与主持类", "文化科总分", 400),
    ("本科院校", "本科", "播音与主持类", "专业省统考", 189),
    ("本科院校", "本科", "美术与设计类", "文化科总分", 320),
    ("本科院校", "本科", "美术与设计类", "专业省统考", 197),
    ("本科院校", "本科", "书法类", "文化科总分", 320),
    ("本科院校", "本科", "书法类", "专业省统考", 222),
    ("本科院校", "本科", "表(导)演类(服装表演)", "文化科总分", 300),
    ("本科院校", "本科", "表(导)演类(服装表演)", "专业省统考", 221),
    ("本科院校", "本科", "表(导)演类(戏剧表演)", "文化科总分", 300),
    ("本科院校", "本科", "表(导)演类(戏剧表演)", "专业省统考", 231),
    ("本科院校", "本科", "表(导)演类(戏剧影视导演)", "文化科总分", 300),
    ("本科院校", "本科", "表(导)演类(戏剧影视导演)", "专业省统考", 233),
    # 高职专科艺术体育
    ("专科院校", "专科", "艺术类", "文化科总分", 160),
    ("专科院校", "专科", "艺术类", "专业省统考", 155),
    ("专科院校", "专科", "体育类", "文化科总分", 160),
    ("专科院校", "专科", "体育类", "专业省统考", 155),
]

CONTROL_LINE_2025 = [
    # 普通类
    ("本科院校", "本科", "历史类", "总分", 446),
    ("本科院校", "本科", "物理类", "总分", 405),
    ("特殊类型招生", "特控线", "历史类", "总分", 503),
    ("特殊类型招生", "特控线", "物理类", "总分", 476),
    ("专科院校", "专科", "历史类", "总分", 200),
    ("专科院校", "专科", "物理类", "总分", 200),
    # 体育类
    ("本科院校", "本科", "体育类(历史)", "文化科总分", 357),
    ("本科院校", "本科", "体育类(历史)", "专业省统考", 259),
    ("本科院校", "本科", "体育类(物理)", "文化科总分", 311),
    ("本科院校", "本科", "体育类(物理)", "专业省统考", 259),
    # 艺术类平行组（本科）
    ("本科院校", "本科", "音乐类", "文化科总分", 320),
    ("本科院校", "本科", "音乐类", "专业省统考", 205),
    ("本科院校", "本科", "舞蹈类", "文化科总分", 300),
    ("本科院校", "本科", "舞蹈类", "专业省统考", 175),
    ("本科院校", "本科", "播音与主持类", "文化科总分", 400),
    ("本科院校", "本科", "播音与主持类", "专业省统考", 188),
    ("本科院校", "本科", "美术与设计类", "文化科总分", 320),
    ("本科院校", "本科", "美术与设计类", "专业省统考", 200),
    ("本科院校", "本科", "书法类", "文化科总分", 320),
    ("本科院校", "本科", "书法类", "专业省统考", 222),
    ("本科院校", "本科", "表(导)演类(服装表演)", "文化科总分", 300),
    ("本科院校", "本科", "表(导)演类(服装表演)", "专业省统考", 218),
    ("本科院校", "本科", "表(导)演类(戏剧表演)", "文化科总分", 300),
    ("本科院校", "本科", "表(导)演类(戏剧表演)", "专业省统考", 230),
    ("本科院校", "本科", "表(导)演类(戏剧影视导演)", "文化科总分", 300),
    ("本科院校", "本科", "表(导)演类(戏剧影视导演)", "专业省统考", 235),
    # 高职专科艺术体育
    ("专科院校", "专科", "艺术类", "文化科总分", 160),
    ("专科院校", "专科", "艺术类", "专业省统考", 155),
    ("专科院校", "专科", "体育类", "文化科总分", 160),
    ("专科院校", "专科", "体育类", "专业省统考", 155),
]

CONTROL_LINE_2024 = [
    # 普通类
    ("本科院校", "本科", "历史类", "总分", 438),
    ("本科院校", "本科", "物理类", "总分", 422),
    ("特殊类型招生", "特控线", "历史类", "总分", 496),
    ("特殊类型招生", "特控线", "物理类", "总分", 481),
    ("专科院校", "专科", "历史类", "总分", 200),
    ("专科院校", "专科", "物理类", "总分", 200),
    # 体育类
    ("本科院校", "本科", "体育类(历史)", "文化科总分", 342),
    ("本科院校", "本科", "体育类(历史)", "专业省统考", 258),
    ("本科院校", "本科", "体育类(物理)", "文化科总分", 307),
    ("本科院校", "本科", "体育类(物理)", "专业省统考", 258),
    # 艺术类平行组（本科）
    ("本科院校", "本科", "音乐类", "文化科总分", 316),
    ("本科院校", "本科", "音乐类", "专业省统考", 203),
    ("本科院校", "本科", "舞蹈类", "文化科总分", 297),
    ("本科院校", "本科", "舞蹈类", "专业省统考", 173),
    ("本科院校", "本科", "播音与主持类", "文化科总分", 397),
    ("本科院校", "本科", "播音与主持类", "专业省统考", 188),
    ("本科院校", "本科", "美术与设计类", "文化科总分", 316),
    ("本科院校", "本科", "美术与设计类", "专业省统考", 201),
    ("本科院校", "本科", "书法类", "文化科总分", 316),
    ("本科院校", "本科", "书法类", "专业省统考", 221),
    ("本科院校", "本科", "表(导)演类(服装表演)", "文化科总分", 297),
    ("本科院校", "本科", "表(导)演类(服装表演)", "专业省统考", 219),
    ("本科院校", "本科", "表(导)演类(戏剧表演)", "文化科总分", 297),
    ("本科院校", "本科", "表(导)演类(戏剧表演)", "专业省统考", 230),
    ("本科院校", "本科", "表(导)演类(戏剧影视导演)", "文化科总分", 297),
    ("本科院校", "本科", "表(导)演类(戏剧影视导演)", "专业省统考", 233),
    # 高职专科艺术体育
    ("专科院校", "专科", "艺术类", "文化科总分", 160),
    ("专科院校", "专科", "艺术类", "专业省统考", 155),
    ("专科院校", "专科", "体育类", "文化科总分", 160),
    ("专科院校", "专科", "体育类", "专业省统考", 155),
]


# ═══════════════════════════════════════════════════════════════
# 阶段 1: FETCH - 下载原始 HTML/Excel
# ═══════════════════════════════════════════════════════════════
def fetch_html(url: str, out_path: Path, timeout: int = 30) -> bool:
    if out_path.exists() and out_path.stat().st_size > 1000:
        print(f"  [SKIP] {out_path.name} 已存在")
        return True
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code != 200:
            print(f"  [FAIL] {url} status={r.status_code}")
            return False
        r.encoding = r.apparent_encoding or "utf-8"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(r.text, encoding="utf-8")
        print(f"  [OK] {out_path.name} ({out_path.stat().st_size} bytes)")
        return True
    except Exception as e:
        print(f"  [FAIL] {url}: {e}")
        return False


def fetch_binary(url: str, out_path: Path, timeout: int = 60) -> bool:
    if out_path.exists() and out_path.stat().st_size > 1000:
        print(f"  [SKIP] {out_path.name} 已存在")
        return True
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
        if r.status_code != 200:
            print(f"  [FAIL] {url} status={r.status_code}")
            return False
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"  [OK] {out_path.name} ({out_path.stat().st_size} bytes)")
        return True
    except Exception as e:
        print(f"  [FAIL] {url}: {e}")
        return False


def fetch_year(year: int, urls: dict, raw_dir: Path):
    print(f"\n[FETCH {year}] 一分一段表 + 投档线")
    raw_dir.mkdir(parents=True, exist_ok=True)
    for key, url in urls.items():
        out = raw_dir / f"{key}.html" if "yifenyiduan" in key or "control" in key else raw_dir / f"{key}.xlsx"
        if "yifenyiduan" in key or "control" in key:
            fetch_html(url, out)
        else:
            fetch_binary(url, out)
        time.sleep(0.5)


# ═══════════════════════════════════════════════════════════════
# 阶段 2: PARSE - 解析为标准 CSV 行
# ═══════════════════════════════════════════════════════════════
def parse_yifenyiduan_html(html_path: Path, subject_group: str, year: int) -> list[dict]:
    """解析一分一段表 HTML 表格。

    支持两种格式:
      - 3 列 (2025/2026): 档分 | 本段人数 | 累计人数
      - 5 列 (2024): 档分 | 本段(全国性加分) | 累计(全国性加分) | 本段(全国+地方) | 累计(全国+地方)
                     统一使用列 0,1,2（含全国性加分的本段/累计）

    首行 "X分含以上" cumulative 为该分及以上总人数；末行 "100以下" 跳过。
    """
    tables = pd.read_html(str(html_path), encoding="utf-8")
    if not tables:
        print(f"  [WARN] {html_path.name} 未找到表格")
        return []
    df = tables[0]
    rows = []
    for _, r in df.iterrows():
        raw_score = str(r.iloc[0]).strip()
        # 跳过标题/表头/含优惠加分/100以下
        if any(kw in raw_score for kw in ["统计表", "档分", "含优惠加分", "含全国性加分", "以下"]):
            continue
        try:
            score = int(float(raw_score))
        except (ValueError, TypeError):
            continue
        if score < 0 or score > 750:
            continue
        try:
            segment = int(float(str(r.iloc[1]).replace(",", "")))
            cumulative = int(float(str(r.iloc[2]).replace(",", "")))
        except (ValueError, TypeError):
            continue
        rows.append({
            "province": PROVINCE,
            "year": year,
            "subject_group": subject_group,
            "batch": "本科批",
            "score": score,
            "segment_count": segment,
            "cumulative_count": cumulative,
        })
    score_range = f"{rows[-1]['score']}-{rows[0]['score']}" if rows else "N/A"
    print(f"  [{subject_group} {year}] {html_path.name} → {len(rows)} 行 (分数 {score_range}, 表格列数 {df.shape[1]})")
    return rows


def parse_control_line(year: int) -> list[dict]:
    """省控线（来自官方发布会公告数值，已硬编码）。"""
    data = {2024: (CONTROL_LINE_2024, CONTROL_LINE_2024_URL),
            2025: (CONTROL_LINE_2025, CONTROL_LINE_2025_URL),
            2026: (CONTROL_LINE_2026, CONTROL_LINE_2026_URL)}[year]
    lines, url = data
    rows = []
    for batch_section, batch, sg, line_type, score in lines:
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
    print(f"  [省控线 {year}] → {len(rows)} 行")
    return rows


# 科类映射: 湖南2024/2025 投档线 Excel 中的"科类"字段值
SUBJECT_GROUP_MAP = {
    "普通类(首选历史)": "历史类",
    "普通类(首选物理)": "物理类",
}


def parse_toudang_excel(xlsx_path: Path, year: int) -> list[dict]:
    """解析本科批投档线 Excel → admission_history 标准行。

    Excel 表结构 (header=2, 16 列):
        批次 | 计划类别 | 科类 | 院校代号 | 院校名称 | 专业组编号 | 专业组名称 |
        投档线 | 语数之和 | 语数最高 | 外语 | 首选科目 | 再选最高 | 再选次高 | 志愿序号 | 备注

    字段映射:
      - subject_group: 普通类(首选历史)→历史类 / 普通类(首选物理)→物理类
      - batch: 提取"本科批(普通)" → "本科批"
      - university_code: 院校代号
      - university_name: 院校名称
      - group_code: 专业组编号
      - major_code: = group_code（投档线是专业组级，无具体专业代码）
      - major_name: 专业组名称
      - lowest_score: 投档线
      - 其余字段: 空
    """
    df = pd.read_excel(xlsx_path, sheet_name=0, header=2)
    rows = []
    skipped = 0
    for _, r in df.iterrows():
        # 科类映射
        raw_sg = str(r.get("科类", "")).strip()
        sg = SUBJECT_GROUP_MAP.get(raw_sg)
        if not sg:
            skipped += 1
            continue
        # 批次标准化: "本科批(普通)" → "本科批"
        raw_batch = str(r.get("批次", "")).strip()
        batch = "本科批" if raw_batch.startswith("本科批") else raw_batch
        # 院校代号
        code = str(r.get("院校代号", "")).strip()
        if not code or code == "nan":
            skipped += 1
            continue
        # 院校名称
        name = str(r.get("院校名称", "")).strip()
        if name == "nan":
            name = ""
        # 专业组编号
        group_code = str(r.get("专业组编号", "")).strip()
        if group_code == "nan":
            group_code = ""
        # 专业组名称
        group_name = str(r.get("专业组名称", "")).strip()
        if group_name == "nan":
            group_name = ""
        # 投档线（必须为 0-750 整数）
        score_val = r.get("投档线")
        try:
            score = int(float(score_val)) if pd.notna(score_val) else None
        except (ValueError, TypeError):
            score = None
        if score is None or score < 0 or score > 750:
            score = ""
        rows.append({
            "year": year,
            "province": PROVINCE,
            "subject_group": sg,
            "batch": batch,
            "university_code": code,
            "university_name": name,
            "group_code": group_code,
            "major_code": group_code,  # 投档线是专业组级
            "major_name": group_name,
            "lowest_score": score,
            "lowest_rank": "",
            "avg_score": "",
            "applicant_count": "",
            "source_file": xlsx_path.name,
        })
    print(f"  [投档线 {year}] {xlsx_path.name} → {len(rows)} 行 (跳过 {skipped})")
    return rows


# ═══════════════════════════════════════════════════════════════
# 阶段 3: LOAD - 安全追加到 CSV（去重）
# ═══════════════════════════════════════════════════════════════
def append_to_csv(new_rows: list[dict], csv_filename: str, key_cols: list[str]) -> int:
    """安全追加数据到 CSV，按 key_cols 去重。

    只删除新数据覆盖范围内(同省份+同年份+同key)的旧行，再追加新数据，
    避免重复但不破坏其他省份数据。
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
        # 删除与新数据同 province+year+key 的旧行（覆盖式更新当年数据）
        new_keys = set()
        for r in new_rows:
            key = tuple(str(r.get(c, "")) for c in key_cols)
            new_keys.add(key)
        mask_keep = []
        for _, r in existing.iterrows():
            key = tuple(str(r.get(c, "")) for c in key_cols)
            if str(r.get("province", "")) == PROVINCE and key in new_keys:
                mask_keep.append(False)
            else:
                mask_keep.append(True)
        existing = existing[mask_keep]
        merged = pd.concat([existing, new_df], ignore_index=True)
    else:
        merged = new_df
    merged = merged.fillna("")
    merged.to_csv(csv_path, index=False, encoding="utf-8")
    print(f"  [写入] {csv_filename}: +{len(new_df)} 行 (总计 {len(merged)} 行)")
    return len(new_df)


def load_yifenyiduan(year: int, raw_dir: Path):
    print(f"\n[LOAD] 一分一段表 {year} → yifenyiduan_{year}.csv")
    all_rows = []
    for key, sg in [("yifenyiduan_physics", "物理类"), ("yifenyiduan_history", "历史类")]:
        html_path = raw_dir / f"{key}.html"
        if not html_path.exists():
            print(f"  [SKIP] {html_path.name} 不存在")
            continue
        rows = parse_yifenyiduan_html(html_path, sg, year)
        all_rows.extend(rows)
    n = append_to_csv(all_rows, f"yifenyiduan_{year}.csv",
                      key_cols=["province", "year", "subject_group", "batch", "score"])
    return n


def load_control_line(year: int):
    print(f"\n[LOAD] 省控线 {year} → control_line_{year}.csv")
    rows = parse_control_line(year)
    n = append_to_csv(rows, f"control_line_{year}.csv",
                      key_cols=["province", "year", "batch", "subject_group", "line_type"])
    return n


def load_toudang(year: int, raw_dir: Path):
    print(f"\n[LOAD] 投档线 {year} → admission_history.csv")
    xlsx_path = raw_dir / "toudang_benke.xlsx"
    if not xlsx_path.exists():
        print(f"  [SKIP] {xlsx_path.name} 不存在")
        return 0
    rows = parse_toudang_excel(xlsx_path, year)
    n = append_to_csv(rows, "admission_history.csv",
                      key_cols=["year", "province", "subject_group", "batch",
                                "university_code", "group_code"])
    return n


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════
def main():
    print(f"[{PROVINCE}] 开始爬取 2024/2025/2026 数据...")

    # FETCH
    fetch_year(2026, URLS_2026, RAW_2026)
    fetch_year(2025, URLS_2025, RAW_2025)
    fetch_year(2024, URLS_2024, RAW_2024)

    # LOAD 一分一段表
    n_yfd_2026 = load_yifenyiduan(2026, RAW_2026)
    n_yfd_2025 = load_yifenyiduan(2025, RAW_2025)
    n_yfd_2024 = load_yifenyiduan(2024, RAW_2024)

    # LOAD 省控线
    n_cl_2026 = load_control_line(2026)
    n_cl_2025 = load_control_line(2025)
    n_cl_2024 = load_control_line(2024)

    # LOAD 投档线
    n_td_2025 = load_toudang(2025, RAW_2025)
    n_td_2024 = load_toudang(2024, RAW_2024)

    # 统计报告
    print(f"\n{'=' * 50}")
    print(f"[{PROVINCE}] ✓ 全部完成")
    print(f"  一分一段表: 2024={n_yfd_2024}, 2025={n_yfd_2025}, 2026={n_yfd_2026}")
    print(f"  省控线:     2024={n_cl_2024}, 2025={n_cl_2025}, 2026={n_cl_2026}")
    print(f"  投档线:     2024={n_td_2024}, 2025={n_td_2025}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
