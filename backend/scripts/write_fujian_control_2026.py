#!/usr/bin/env python3
"""把已 OCR 的 2026 福建省控线数据写入 control_line_2026.csv。"""
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROVINCE = "福建"
# #14 root fix: 重定向到 data/raw/{省}_{文件名}，禁止直接写主 CSV
_raw_dir = DATA_DIR / "raw"
_raw_dir.mkdir(exist_ok=True)
CSV_PATH = _raw_dir / f"{PROVINCE}_control_line_2026.csv"
SOURCE_URL = "http://www.eeafj.cn/gkptgkgsgg/20260624/14697.html"

# 2026 福建省控线（已 OCR 得到）
ROWS = [
    # 物理类
    ("本科院校", "本科", "物理类", 446),
    ("专科院校", "专科", "物理类", 239),
    ("特殊类型招生", "提前", "物理类", 528),
    # 历史类
    ("本科院校", "本科", "历史类", 458),
    ("专科院校", "专科", "历史类", 239),
    ("特殊类型招生", "提前", "历史类", 533),
]

new_rows = [
    {
        "province": "福建",
        "year": 2026,
        "batch_section": bs,
        "batch": b,
        "subject_group": sg,
        "line_type": "总分",
        "lowest_score": s,
        "source_url": SOURCE_URL,
    }
    for bs, b, sg, s in ROWS
]

if CSV_PATH.exists():
    existing = pd.read_csv(CSV_PATH, dtype=str)
    existing_no_fj = existing[existing["province"] != "福建"]
    new_df = pd.DataFrame(new_rows)
    merged = pd.concat([existing_no_fj, new_df], ignore_index=True)
else:
    merged = pd.DataFrame(new_rows)

merged = merged.fillna("")
merged.to_csv(CSV_PATH, index=False, encoding="utf-8")
print(f"[OK] 写入 {len(new_rows)} 行福建2026省控线到 {CSV_PATH.name}")
print(f"     当前文件总行数: {len(merged)}")
