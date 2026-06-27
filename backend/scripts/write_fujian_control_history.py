#!/usr/bin/env python3
"""写入福建2024/2025省控线数据（来自WebSearch确认的官方数据）。"""
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROVINCE = "福建"

# 2024年福建高考分数线（来源：福建省教育考试院）
DATA_2024 = [
    # (batch_section, batch, subject_group, score)
    ("本科院校", "本科", "物理类", 449),
    ("专科院校", "专科", "物理类", 220),
    ("特殊类型招生", "提前", "物理类", 538),
    ("本科院校", "本科", "历史类", 431),
    ("专科院校", "专科", "历史类", 220),
    ("特殊类型招生", "提前", "历史类", 519),
]
SOURCE_2024 = "http://www.eeafj.cn/gkptgkgsgg/20240624/13465.html"

# 2025年福建高考分数线（来源：福建省教育考试院）
DATA_2025 = [
    ("本科院校", "本科", "物理类", 441),
    ("专科院校", "专科", "物理类", 235),
    ("特殊类型招生", "提前", "物理类", 520),
    ("本科院校", "本科", "历史类", 450),
    ("专科院校", "专科", "历史类", 235),
    ("特殊类型招生", "提前", "历史类", 531),
]
SOURCE_2025 = "http://www.eeafj.cn/gkptgkgsgg/20250624/14072.html"


def write_year(year, data, source_url, csv_name):
    csv_path = DATA_DIR / csv_name
    # #14 root fix: 重定向到 data/raw/{省}_{文件名}，禁止直接写主 CSV
    _raw_dir = DATA_DIR / "raw"
    _raw_dir.mkdir(exist_ok=True)
    csv_path = _raw_dir / f"{PROVINCE}_{csv_path.name}"
    rows = [
        {
            "province": "福建",
            "year": year,
            "batch_section": bs,
            "batch": b,
            "subject_group": sg,
            "line_type": "总分",
            "lowest_score": s,
            "source_url": source_url,
        }
        for bs, b, sg, s in data
    ]
    if csv_path.exists():
        existing = pd.read_csv(csv_path, dtype=str)
        existing_no_fj = existing[existing["province"] != "福建"]
        new_df = pd.DataFrame(rows)
        merged = pd.concat([existing_no_fj, new_df], ignore_index=True)
    else:
        merged = pd.DataFrame(rows)
    merged = merged.fillna("")
    merged.to_csv(csv_path, index=False, encoding="utf-8")
    print(f"[OK] {year} 省控线写入 {len(rows)} 行到 {csv_name} (总{len(merged)}行)")


write_year(2024, DATA_2024, SOURCE_2024, "control_line_2024.csv")
write_year(2025, DATA_2025, SOURCE_2025, "control_line_2025.csv")
