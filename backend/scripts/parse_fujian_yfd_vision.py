#!/usr/bin/env python3
"""用macOS Vision API OCR福建一分一段表图片，解析并写入CSV。"""
import csv
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

BACKEND = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND / "data"
RAW_DIR = DATA_DIR / "raw" / "fujian_history"
OCR_BIN = BACKEND / "scripts" / "ocr_vision"
PROVINCE = "福建"

# 一分一段表图片URL
YFD_IMAGES = {
    2025: {
        "物理类": [
            "https://aka.doubaocdn.com/s/kVEl1wfqGb",
            "https://aka.doubaocdn.com/s/YRKZ1wfqGb",
            "https://aka.doubaocdn.com/s/RX8H1wfqGb",
            "https://aka.doubaocdn.com/s/aDGn1wfqGb",
        ],
        "历史类": [
            "https://aka.doubaocdn.com/s/AQUg1wfqIR",
            "https://aka.doubaocdn.com/s/XrRH1wfqIR",
            "https://aka.doubaocdn.com/s/XG8T1wfqIR",
            "https://aka.doubaocdn.com/s/UEtL1wfqIR",
        ],
    },
    2024: {
        "物理类": [
            "https://aka.doubaocdn.com/s/suWO1wfqHi",
            "https://aka.doubaocdn.com/s/Yd5X1wfqHi",
            "https://aka.doubaocdn.com/s/bjBH1wfqHi",
            "https://aka.doubaocdn.com/s/2YbG1wfqHi",
            "https://aka.doubaocdn.com/s/xUX11wfqHi",
        ],
        "历史类": [
            "https://aka.doubaocdn.com/s/g1E21wfqIR",
            "https://aka.doubaocdn.com/s/N9i31wfqIR",
            "https://aka.doubaocdn.com/s/ByhC1wfqIR",
            "https://aka.doubaocdn.com/s/Urcw1wfqIR",
        ],
    },
}


def ocr_image_vision(img_path: Path) -> list[tuple[float, float, str]]:
    """用Vision API OCR图片，返回 [(y, x, text)]。"""
    try:
        result = subprocess.run(
            [str(OCR_BIN), str(img_path)],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            print(f"    [OCR ERROR] {img_path.name}: {result.stderr[:200]}")
            return []
        items = []
        for ln in result.stdout.split("\n"):
            if not ln.strip():
                continue
            parts = ln.split("\t", 2)
            if len(parts) != 3:
                continue
            try:
                y = float(parts[0])
                x = float(parts[1])
                text = parts[2].strip()
                items.append((y, x, text))
            except ValueError:
                continue
        return items
    except Exception as e:
        print(f"    [OCR FAIL] {img_path.name}: {e}")
        return []


def parse_yfd_items(items: list[tuple[float, float, str]], year: int, subject_group: str) -> list[dict]:
    """解析一分一段表OCR结果。

    实际表格结构：3栏 × 3列
    每栏: 分数 | 人数 | 累计
    Vision输出: (y, x, text)
    - y从1.0(顶部)到0.0(底部)
    - x从0.0(左)到1.0(右)

    3栏x范围：
    - 第1栏: 0.10 ≤ x < 0.40
    - 第2栏: 0.40 ≤ x < 0.62
    - 第3栏: 0.62 ≤ x ≤ 0.85
    """
    # 过滤表头文字
    HEADER_TEXTS = {"分数", "人数", "累计", "科目组", "物理", "历史",
                    "高考考生成绩分布", "物理科目组", "历史科目组"}
    items = [(y, x, t) for y, x, t in items
             if t.strip() and t.strip() not in HEADER_TEXTS]

    # 清洗：只保留数字
    num_items = []
    for y, x, text in items:
        cleaned = re.sub(r"[^\d]", "", text)
        if not cleaned:
            continue
        try:
            val = int(cleaned)
            num_items.append((y, x, val))
        except ValueError:
            continue

    if not num_items:
        return []

    # 按 x 分3栏
    COLS = [
        [(y, x, v) for y, x, v in num_items if 0.10 <= x < 0.40],
        [(y, x, v) for y, x, v in num_items if 0.40 <= x < 0.62],
        [(y, x, v) for y, x, v in num_items if 0.62 <= x <= 0.85],
    ]

    rows_out = []

    for col_idx, col_items in enumerate(COLS):
        if not col_items:
            continue
        # 按y从大到小排序
        col_items.sort(key=lambda t: -t[0])

        # 按y聚合行（容差0.008）
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
            cells.sort(key=lambda c: c[0])  # 按x排序
            vals = [v for _, v in cells]

            # 每行3个数字：分数|人数|累计
            if len(vals) < 3:
                continue
            # 取前3个
            score, seg, cum = vals[0], vals[1], vals[2]

            # 校验
            if not (0 <= score <= 750):
                continue
            if seg < 0 or seg > 100000:
                continue
            if cum < 0 or cum > 1000000:
                continue
            # 累计应大于等于人数
            if cum < seg:
                continue

            rows_out.append({
                "province": "福建",
                "year": year,
                "subject_group": subject_group,
                "batch": "本科批",
                "score": score,
                "segment_count": seg,
                "cumulative_count": cum,
            })

    return rows_out


def append_to_csv(rows: list[dict], csv_path: Path) -> int:
    # #14 root fix: 重定向到 data/raw/{省}_{文件名}，禁止直接写主 CSV
    _raw_dir = DATA_DIR / "raw"
    _raw_dir.mkdir(exist_ok=True)
    csv_path = _raw_dir / f"{PROVINCE}_{csv_path.name}"
    if not rows:
        return 0
    new_df = pd.DataFrame(rows)
    # 提取本次写入的 (year, subject_group) 组合
    keys_set = {(str(y), str(sg))
                for y, sg in new_df[["year", "subject_group"]].drop_duplicates().itertuples(index=False, name=None)}
    if csv_path.exists():
        existing = pd.read_csv(csv_path, dtype=str)
        # 保留：非福建行 + 福建行中(year,subject_group)不在本次keys_set的
        is_fj = existing["province"] == "福建"
        fj_keys = list(zip(existing.loc[is_fj, "year"].astype(str),
                           existing.loc[is_fj, "subject_group"].astype(str)))
        fj_keep = pd.Series([k not in keys_set for k in fj_keys], index=existing.index[is_fj])
        keep_mask = ~is_fj
        keep_mask.loc[is_fj] = fj_keep
        existing_keep = existing[keep_mask]
        merged = pd.concat([existing_keep, new_df], ignore_index=True)
    else:
        merged = new_df
    merged = merged.fillna("")
    merged.to_csv(csv_path, index=False, encoding="utf-8")
    return len(new_df)


def process_year_subject(year: int, subject_group: str, img_urls: list[str]):
    print(f"\n[{year} {subject_group}] {len(img_urls)} 张图片")
    year_dir = RAW_DIR / str(year)
    year_dir.mkdir(parents=True, exist_ok=True)
    
    all_rows = []
    for i, url in enumerate(img_urls):
        img_path = year_dir / f"yfd_{year}_{subject_group}_p{i+1}.jpg"
        if not img_path.exists():
            # 下载图片
            import httpx
            try:
                r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60, follow_redirects=True)
                if r.status_code == 200:
                    img_path.write_bytes(r.content)
                    print(f"    [OK] 下载 {img_path.name}")
            except Exception as e:
                print(f"    [FAIL] 下载 {url}: {e}")
                continue
        
        # OCR
        items = ocr_image_vision(img_path)
        print(f"    [p{i+1}] Vision OCR {len(items)} 项")
        rows = parse_yfd_items(items, year, subject_group)
        all_rows.extend(rows)
    
    # 去重
    seen = set()
    unique = []
    for r in all_rows:
        k = (r["batch"], r["score"], r["segment_count"], r["cumulative_count"])
        if k not in seen:
            seen.add(k)
            unique.append(r)
    # 按分数降序
    unique.sort(key=lambda x: -x["score"])
    
    if unique:
        csv_path = DATA_DIR / f"yifenyiduan_{year}.csv"
        n = append_to_csv(unique, csv_path)
        benke = [r for r in unique if r["batch"] == "本科批"]
        zhuanke = [r for r in unique if r["batch"] == "专科批"]
        print(f"  [OK] {subject_group} 写入 {n} 行到 {csv_path.name}")
        print(f"       本科批: {len(benke)} 行, 专科批: {len(zhuanke)} 行")
        if benke:
            print(f"       本科分数范围: {benke[-1]['score']}-{benke[0]['score']}")
    else:
        print(f"  [WARN] {subject_group} 无有效数据")


def main():
    years = [int(y) for y in sys.argv[1:]] if len(sys.argv) > 1 else [2025, 2024]
    for year in years:
        if year not in YFD_IMAGES:
            continue
        for sg, urls in YFD_IMAGES[year].items():
            try:
                process_year_subject(year, sg, urls)
            except Exception as e:
                print(f"  [ERROR] {year} {sg}: {e}")
                import traceback
                traceback.print_exc()
    print(f"\n{'='*60}")
    print("一分一段表处理完成")


if __name__ == "__main__":
    main()
