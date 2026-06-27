#!/usr/bin/env python3
"""福建一分一段表图片下载 + OCR + 写入CSV。

图片URL来自WebFetch获取的页面渲染结果。
"""
import csv
import re
import sys
import time
from pathlib import Path

import httpx
import pandas as pd
import pytesseract
from PIL import Image, ImageOps, ImageFilter

BACKEND = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND / "data"
RAW_DIR = DATA_DIR / "raw" / "fujian_history"
PROVINCE = "福建"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "http://www.eeafj.cn/",
}

# 一分一段表图片URL（WebFetch获取）
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


def download_image(url: str, cache_path: Path) -> Path | None:
    if cache_path.exists() and cache_path.stat().st_size > 1000:
        return cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = httpx.get(url, headers=HEADERS, timeout=60, follow_redirects=True)
        if r.status_code != 200:
            print(f"    [FAIL] {url} status={r.status_code}")
            return None
        cache_path.write_bytes(r.content)
        print(f"    [OK] {cache_path.name} ({cache_path.stat().st_size} bytes)")
        time.sleep(0.3)
        return cache_path
    except Exception as e:
        print(f"    [FAIL] {url}: {e}")
        return None


def preprocess(img: Image.Image, scale: int = 3) -> Image.Image:
    if img.mode != "L":
        img = img.convert("L")
    w, h = img.size
    img = img.resize((w * scale, h * scale), Image.LANCZOS)
    img = img.filter(ImageFilter.SHARPEN)
    # 自适应二值化
    img = img.point(lambda p: 0 if p < 150 else 255)
    return img


def ocr_table(img_path: Path) -> list[str]:
    """OCR表格图片，返回行列表。"""
    try:
        img = Image.open(img_path)
        img = preprocess(img)
        # PSM 6 = 假设单一统一文本块
        text = pytesseract.image_to_string(img, lang="chi_sim+eng", config="--psm 6")
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        return lines
    except Exception as e:
        print(f"    [OCR FAIL] {img_path.name}: {e}")
        return []


def parse_yfd_lines(lines: list[str], year: int, subject_group: str) -> list[dict]:
    """从OCR行列表中解析一分一段表数据。
    
    福建一分一段表格式：分数 | 本科人数 | 本科累计 | 专科人数 | 专科累计
    OCR可能识别为各种格式，宽松匹配。
    """
    rows = []
    for ln in lines:
        # 提取所有数字
        nums = re.findall(r"\d+", ln)
        if len(nums) < 3:
            continue
        try:
            score = int(nums[0])
            # 尝试不同列数：3列(分数|人数|累计) 或 5列(分数|本人数|本累计|专人数|专累计)
            if len(nums) >= 5:
                score = int(nums[0])
                benke_seg = int(nums[1])
                benke_cum = int(nums[2])
                zhuanke_seg = int(nums[3])
                zhuanke_cum = int(nums[4])
            elif len(nums) >= 3:
                score = int(nums[0])
                benke_seg = int(nums[1])
                benke_cum = int(nums[2])
                zhuanke_seg = None
                zhuanke_cum = None
            else:
                continue
        except (ValueError, IndexError):
            continue
        
        if not (0 <= score <= 750):
            continue
        if benke_seg < 0 or benke_seg > 100000:
            continue
        if benke_cum < 0 or benke_cum > 1000000:
            continue
        
        # 本科批
        rows.append({
            "province": "福建",
            "year": year,
            "subject_group": subject_group,
            "batch": "本科批",
            "score": score,
            "segment_count": benke_seg,
            "cumulative_count": benke_cum,
        })
        # 专科批（如果有）
        if zhuanke_seg is not None and zhuanke_cum is not None:
            if zhuanke_seg >= 0 and zhuanke_cum >= 0:
                rows.append({
                    "province": "福建",
                    "year": year,
                    "subject_group": subject_group,
                    "batch": "专科批",
                    "score": score,
                    "segment_count": zhuanke_seg,
                    "cumulative_count": zhuanke_cum,
                })
    return rows


def append_to_csv(rows: list[dict], csv_path: Path, fieldnames: list[str]) -> int:
    # #14 root fix: 重定向到 data/raw/{省}_{文件名}，禁止直接写主 CSV
    _raw_dir = DATA_DIR / "raw"
    _raw_dir.mkdir(exist_ok=True)
    csv_path = _raw_dir / f"{PROVINCE}_{csv_path.name}"
    if not rows:
        return 0
    new_df = pd.DataFrame(rows)
    if csv_path.exists():
        existing = pd.read_csv(csv_path, dtype=str)
        existing_no_fj = existing[existing["province"] != "福建"]
        merged = pd.concat([existing_no_fj, new_df], ignore_index=True)
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
        p = download_image(url, img_path)
        if not p:
            continue
        lines = ocr_table(p)
        print(f"    [p{i+1}] OCR {len(lines)} 行")
        if lines:
            print(f"    样本: {lines[0][:80]}")
        rows = parse_yfd_lines(lines, year, subject_group)
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
        n = append_to_csv(unique, csv_path,
            ["province","year","subject_group","batch","score","segment_count","cumulative_count"])
        print(f"  [OK] {subject_group} 写入 {n} 行到 {csv_path.name}")
        # 统计
        benke = [r for r in unique if r["batch"] == "本科批"]
        zhuanke = [r for r in unique if r["batch"] == "专科批"]
        print(f"       本科批: {len(benke)} 行, 专科批: {len(zhuanke)} 行")
        if benke:
            print(f"       分数范围: {benke[-1]['score']}-{benke[0]['score']}")
    else:
        print(f"  [WARN] {subject_group} 无有效数据")


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    years = [int(y) for y in sys.argv[1:]] if len(sys.argv) > 1 else [2025, 2024]
    
    for year in years:
        if year not in YFD_IMAGES:
            print(f"无 {year} 年图片URL配置")
            continue
        for subject_group, urls in YFD_IMAGES[year].items():
            try:
                process_year_subject(year, subject_group, urls)
            except Exception as e:
                print(f"  [ERROR] {year} {subject_group}: {e}")
                import traceback
                traceback.print_exc()
    
    print(f"\n{'='*60}")
    print("一分一段表处理完成")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
