#!/usr/bin/env python3
"""用Vision OCR处理2026年一分一段表图片。"""
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

BACKEND = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND / "data"
OCR_BIN = BACKEND / "scripts" / "ocr_vision"
PROVINCE = "福建"

IMG_FILES = [
    (DATA_DIR / "raw" / "fujian_2026" / "yifenyiduan_2026_physics_p1.jpg", "物理类"),
    (DATA_DIR / "raw" / "fujian_2026" / "yifenyiduan_2026_physics_p2.jpg", "物理类"),
    (DATA_DIR / "raw" / "fujian_2026" / "yifenyiduan_2026_physics_p3.jpg", "物理类"),
    (DATA_DIR / "raw" / "fujian_2026" / "yifenyiduan_2026_physics_p4.jpg", "物理类"),
    (DATA_DIR / "raw" / "fujian_2026" / "yifenyiduan_2026_history_p1.jpg", "历史类"),
    (DATA_DIR / "raw" / "fujian_2026" / "yifenyiduan_2026_history_p2.jpg", "历史类"),
    (DATA_DIR / "raw" / "fujian_2026" / "yifenyiduan_2026_history_p3.jpg", "历史类"),
    (DATA_DIR / "raw" / "fujian_2026" / "yifenyiduan_2026_history_p4.jpg", "历史类"),
]


def ocr_vision(img_path):
    r = subprocess.run([str(OCR_BIN), str(img_path)], capture_output=True, text=True, timeout=120)
    items = []
    for ln in r.stdout.split("\n"):
        if not ln.strip():
            continue
        parts = ln.split("\t", 2)
        if len(parts) != 3:
            continue
        try:
            y, x = float(parts[0]), float(parts[1])
            items.append((y, x, parts[2].strip()))
        except ValueError:
            continue
    return items


def parse_items(items, subject_group):
    """3栏×3列格式: 每栏 分数|人数|累计。"""
    HEADER_TEXTS = {"分数", "人数", "累计", "科目组", "物理", "历史",
                    "高考考生成绩分布", "物理科目组", "历史科目组"}
    items = [(y, x, t) for y, x, t in items
             if t.strip() and t.strip() not in HEADER_TEXTS]

    num_items = []
    for y, x, text in items:
        cleaned = re.sub(r"[^\d]", "", text)
        if not cleaned:
            continue
        try:
            num_items.append((y, x, int(cleaned)))
        except ValueError:
            continue

    COLS = [
        [(y, x, v) for y, x, v in num_items if 0.10 <= x < 0.40],
        [(y, x, v) for y, x, v in num_items if 0.40 <= x < 0.62],
        [(y, x, v) for y, x, v in num_items if 0.62 <= x <= 0.85],
    ]

    rows_out = []
    for col_items in COLS:
        if not col_items:
            continue
        col_items.sort(key=lambda t: -t[0])
        rows = []
        for y, x, v in col_items:
            placed = False
            for row in rows:
                if abs(row[0] - y) < 0.008:
                    row[1].append((x, v))
                    placed = True
                    break
            if not placed:
                rows.append([y, [(x, v)]])

        for _, cells in rows:
            cells.sort(key=lambda c: c[0])
            vals = [v for _, v in cells]
            if len(vals) < 3:
                continue
            score, seg, cum = vals[0], vals[1], vals[2]
            if not (0 <= score <= 750):
                continue
            if seg < 0 or seg > 100000:
                continue
            if cum < 0 or cum > 1000000:
                continue
            if cum < seg:
                continue
            rows_out.append({
                "province": "福建", "year": 2026, "subject_group": subject_group,
                "batch": "本科批", "score": score,
                "segment_count": seg, "cumulative_count": cum,
            })
    return rows_out


def main():
    all_rows = []
    for img_path, sg in IMG_FILES:
        if not img_path.exists():
            print(f"  跳过 {img_path.name} (不存在)")
            continue
        items = ocr_vision(img_path)
        print(f"  [{sg} {img_path.name}] Vision OCR {len(items)} 项")
        rows = parse_items(items, sg)
        all_rows.extend(rows)
    
    # 去重
    seen = set()
    unique = []
    for r in all_rows:
        k = (r["batch"], r["score"], r["segment_count"], r["cumulative_count"])
        if k not in seen:
            seen.add(k)
            unique.append(r)
    unique.sort(key=lambda x: -x["score"])
    
    if unique:
        csv_path = DATA_DIR / "yifenyiduan_2026.csv"
        # #14 root fix: 重定向到 data/raw/{省}_{文件名}，禁止直接写主 CSV
        _raw_dir = DATA_DIR / "raw"
        _raw_dir.mkdir(exist_ok=True)
        csv_path = _raw_dir / f"{PROVINCE}_{csv_path.name}"
        if csv_path.exists():
            existing = pd.read_csv(csv_path, dtype=str)
            existing_no_fj = existing[existing["province"] != "福建"]
            new_df = pd.DataFrame(unique)
            merged = pd.concat([existing_no_fj, new_df], ignore_index=True)
        else:
            merged = pd.DataFrame(unique)
        merged = merged.fillna("")
        merged.to_csv(csv_path, index=False, encoding="utf-8")
        benke = [r for r in unique if r["batch"] == "本科批"]
        zhuanke = [r for r in unique if r["batch"] == "专科批"]
        print(f"\n[OK] 写入 {len(unique)} 行到 yifenyiduan_2026.csv")
        print(f"     本科批: {len(benke)} 行, 专科批: {len(zhuanke)} 行")


if __name__ == "__main__":
    main()
