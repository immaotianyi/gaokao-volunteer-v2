#!/usr/bin/env python3
"""福建投档线图片下载 + Vision OCR + 写入admission_history.csv。

投档线表格格式：院校代号 | 院校名称 | 专业组代号 | 投档最低分
"""
import csv
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pandas as pd

BACKEND = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND / "data"
RAW_DIR = DATA_DIR / "raw" / "fujian_history"
OCR_BIN = BACKEND / "scripts" / "ocr_vision"
PROVINCE = "福建"

HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "http://www.eeafj.cn/"}

# 投档线图片URL（从WebFetch获取）
TOUDANG_URLS = {
    2025: {
        ("本科批", "物理类"): [
            "https://aka.doubaocdn.com/s/U6Rb1wfqHj", "https://aka.doubaocdn.com/s/go4d1wfqHj",
            "https://aka.doubaocdn.com/s/NibE1wfqHj", "https://aka.doubaocdn.com/s/DVpC1wfqHj",
            "https://aka.doubaocdn.com/s/LXL51wfqHj", "https://aka.doubaocdn.com/s/WssF1wfqHj",
            "https://aka.doubaocdn.com/s/WzIi1wfqHj", "https://aka.doubaocdn.com/s/MaCP1wfqHj",
            "https://aka.doubaocdn.com/s/dtKd1wfqHj", "https://aka.doubaocdn.com/s/7nxT1wfqHj",
            "https://aka.doubaocdn.com/s/e9051wfqHj", "https://aka.doubaocdn.com/s/h21B1wfqHj",
            "https://aka.doubaocdn.com/s/nrlc1wfqHj", "https://aka.doubaocdn.com/s/HCfY1wfqHj",
            "https://aka.doubaocdn.com/s/SuNZ1wfqHj", "https://aka.doubaocdn.com/s/d2ow1wfqHj",
            "https://aka.doubaocdn.com/s/p5M41wfqHj", "https://aka.doubaocdn.com/s/HEkW1wfqHj",
            "https://aka.doubaocdn.com/s/Cbiz1wfqHj", "https://aka.doubaocdn.com/s/Qby41wfqHj",
            "https://aka.doubaocdn.com/s/g7eH1wfqHj", "https://aka.doubaocdn.com/s/nb1O1wfqHj",
            "https://aka.doubaocdn.com/s/sFpV1wfqHj", "https://aka.doubaocdn.com/s/eV4s1wfqHj",
            "https://aka.doubaocdn.com/s/UAhC1wfqHj", "https://aka.doubaocdn.com/s/yV7b1wfqHj",
            "https://aka.doubaocdn.com/s/vP0f1wfqHj", "https://aka.doubaocdn.com/s/Deew1wfqHj",
            "https://aka.doubaocdn.com/s/NP7S1wfqHj", "https://aka.doubaocdn.com/s/cVGZ1wfqHj",
            "https://aka.doubaocdn.com/s/H4Y91wfqHj", "https://aka.doubaocdn.com/s/GedF1wfqHj",
            "https://aka.doubaocdn.com/s/JWVM1wfqHj", "https://aka.doubaocdn.com/s/aAfz1wfqHj",
            "https://aka.doubaocdn.com/s/Kcf31wfqHj", "https://aka.doubaocdn.com/s/OBF91wfqHj",
            "https://aka.doubaocdn.com/s/9n2t1wfqHj", "https://aka.doubaocdn.com/s/IrUR1wfqHj",
            "https://aka.doubaocdn.com/s/K9Dx1wfqHj", "https://aka.doubaocdn.com/s/UDyC1wfqHj",
            "https://aka.doubaocdn.com/s/Joe31wfqHj", "https://aka.doubaocdn.com/s/bkpj1wfqHj",
            "https://aka.doubaocdn.com/s/RJ131wfqHj", "https://aka.doubaocdn.com/s/gjQn1wfqHj",
            "https://aka.doubaocdn.com/s/3e9n1wfqHj", "https://aka.doubaocdn.com/s/HU1v1wfqHj",
            "https://aka.doubaocdn.com/s/gnYC1wfqHj", "https://aka.doubaocdn.com/s/W38J1wfqHj",
            "https://aka.doubaocdn.com/s/t9Xw1wfqHj", "https://aka.doubaocdn.com/s/mVF81wfqHj",
            "https://aka.doubaocdn.com/s/81TB1wfqHj", "https://aka.doubaocdn.com/s/f2Ph1wfqHj",
            "https://aka.doubaocdn.com/s/HYFB1wfqHj", "https://aka.doubaocdn.com/s/h4Yv1wfqHj",
            "https://aka.doubaocdn.com/s/qEru1wfqHj", "https://aka.doubaocdn.com/s/xdt01wfqHj",
            "https://aka.doubaocdn.com/s/A15w1wfqHj", "https://aka.doubaocdn.com/s/O57f1wfqHj",
            "https://aka.doubaocdn.com/s/TiUc1wfqHj", "https://aka.doubaocdn.com/s/cfGo1wfqHj",
            "https://aka.doubaocdn.com/s/etbm1wfqHj",
        ],
        ("本科批", "历史类"): [
            "https://aka.doubaocdn.com/s/9Ao51wfqNc", "https://aka.doubaocdn.com/s/zlU91wfqNc",
            "https://aka.doubaocdn.com/s/MDku1wfqNc", "https://aka.doubaocdn.com/s/XOkU1wfqNc",
            "https://aka.doubaocdn.com/s/WXHG1wfqNc", "https://aka.doubaocdn.com/s/kzYA1wfqNc",
            "https://aka.doubaocdn.com/s/poLx1wfqNc", "https://aka.doubaocdn.com/s/IFhI1wfqNc",
            "https://aka.doubaocdn.com/s/WTVb1wfqNc", "https://aka.doubaocdn.com/s/V7mW1wfqNc",
            "https://aka.doubaocdn.com/s/LxpZ1wfqNc", "https://aka.doubaocdn.com/s/RI7i1wfqNc",
            "https://aka.doubaocdn.com/s/7j2h1wfqNc", "https://aka.doubaocdn.com/s/Wp6s1wfqNc",
            "https://aka.doubaocdn.com/s/TIsB1wfqNc", "https://aka.doubaocdn.com/s/QlsD1wfqNc",
            "https://aka.doubaocdn.com/s/CvJU1wfqNc", "https://aka.doubaocdn.com/s/s8Go1wfqNc",
            "https://aka.doubaocdn.com/s/JYRR1wfqNc", "https://aka.doubaocdn.com/s/4ovm1wfqNc",
            "https://aka.doubaocdn.com/s/UKGy1wfqNc", "https://aka.doubaocdn.com/s/hAAx1wfqNc",
            "https://aka.doubaocdn.com/s/V2L21wfqNc", "https://aka.doubaocdn.com/s/i6671wfqNc",
            "https://aka.doubaocdn.com/s/pC3W1wfqNc", "https://aka.doubaocdn.com/s/Z6fg1wfqNc",
            "https://aka.doubaocdn.com/s/ZA7h1wfqNc", "https://aka.doubaocdn.com/s/aAi71wfqNc",
            "https://aka.doubaocdn.com/s/lvV21wfqNc", "https://aka.doubaocdn.com/s/jAuU1wfqNc",
            "https://aka.doubaocdn.com/s/Bic01wfqNc", "https://aka.doubaocdn.com/s/mgIN1wfqNc",
            "https://aka.doubaocdn.com/s/cNJm1wfqNc", "https://aka.doubaocdn.com/s/zST51wfqNc",
            "https://aka.doubaocdn.com/s/lKAP1wfqNc", "https://aka.doubaocdn.com/s/Dbo41wfqNc",
            "https://aka.doubaocdn.com/s/3gLU1wfqNc", "https://aka.doubaocdn.com/s/jUS21wfqNc",
            "https://aka.doubaocdn.com/s/gDj71wfqNc", "https://aka.doubaocdn.com/s/iVZo1wfqNc",
            "https://aka.doubaocdn.com/s/C30t1wfqNc",
        ],
    },
}


def download_image(url, cache_path):
    if cache_path.exists() and cache_path.stat().st_size > 1000:
        return cache_path
    try:
        r = httpx.get(url, headers=HEADERS, timeout=60, follow_redirects=True)
        if r.status_code != 200:
            return None
        cache_path.write_bytes(r.content)
        time.sleep(0.2)
        return cache_path
    except Exception:
        return None


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


def parse_toudang_items(items, year, subject_group, batch):
    """解析投档线表格（6列单页布局）：
    批次 | 科类 | 院校代号 | 院校名称 | 专业组(代号+选科) | 投档最低分 | 备注(可选)
    """
    rows_out = []

    # 过滤表头/页眉文字
    HEADER_TEXTS = {"批次", "科类", "科目组", "院校", "代号", "院校名称",
                    "专业组", "投档", "最低分", "备注", "普通类", "普週类",
                    "物理", "历史", "本科批", "专科批", "院校代号", "投档最低分"}
    items = [(y, x, t) for y, x, t in items
             if t.strip() and t.strip() not in HEADER_TEXTS]

    # 按y聚合行（y从大到小排序，容差0.012）
    items_sorted = sorted(items, key=lambda t: -t[0])
    rows = []
    for y, x, text in items_sorted:
        if rows and abs(rows[-1][0] - y) < 0.012:
            rows[-1][1].append((x, text))
        else:
            rows.append([y, [(x, text)]])

    for _, cells in rows:
        cells.sort(key=lambda c: c[0])  # 按x排序

        # 按6列分桶（基于x坐标）
        col_batch = [t for x, t in cells if 0.08 <= x < 0.21]      # 批次/科类
        col_univ_code = [t for x, t in cells if 0.21 <= x < 0.28]  # 院校代号
        col_univ_name = [t for x, t in cells if 0.28 <= x < 0.50]  # 院校名称
        col_group = [t for x, t in cells if 0.50 <= x < 0.72]      # 专业组代号+选科
        col_score = [t for x, t in cells if 0.78 <= x < 0.88]      # 投档最低分
        col_note = [t for x, t in cells if x >= 0.88]              # 备注

        # 必须有院校代号（4位数字）
        univ_code_text = " ".join(col_univ_code)
        univ_code_match = re.search(r"\b(\d{4})\b", univ_code_text)
        if not univ_code_match:
            continue
        univ_code = univ_code_match.group(1)

        # 必须有投档最低分（3位数字）
        score_text = " ".join(col_score)
        score_match = re.search(r"\b(\d{3})\b", score_text)
        if not score_match:
            continue
        score = int(score_match.group(1))
        if not (200 <= score <= 750):
            continue

        # 提取院校名称（中文，清洗OCR错字）
        name_text = "".join(col_univ_name)
        # 去掉数字和标点
        name_text = re.sub(r"[^\u4e00-\u9fa5（）()·]+", "", name_text)
        if not name_text:
            name_text = f"院校{univ_code}"

        # 提取专业组代号（3位数字，福建实际格式）
        group_text = " ".join(col_group)
        group_match = re.search(r"\b(\d{3,4})\b", group_text)
        group_code = group_match.group(1) if group_match else univ_code

        # 提取选科要求（专业组列中的中文部分）
        subj_match = re.search(r"[\u4e00-\u9fa5（）()]+", group_text)
        subj_req = subj_match.group(0) if subj_match else ""

        # 备注列（如果有）
        note_text = " ".join(col_note).strip()

        rows_out.append({
            "year": year,
            "province": "福建",
            "subject_group": subject_group,
            "batch": batch,
            "university_code": univ_code,
            "university_name": name_text,
            "group_code": group_code,
            "major_code": group_code,
            "major_name": f"第{group_code}组({subj_req})" if subj_req else f"第{group_code}组",
            "lowest_score": float(score),
            "lowest_rank": "",
            "avg_score": "",
            "applicant_count": "",
            "source_file": f"fujian_{year}_{subject_group}_{batch}.jpg",
        })

    return rows_out


def process_batch(year, subject_group, batch, img_urls):
    print(f"\n[{year} {batch} {subject_group}] {len(img_urls)} 张图片")
    batch_dir = RAW_DIR / str(year) / f"toudang_{batch}_{subject_group}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    
    all_rows = []
    for i, url in enumerate(img_urls):
        img_path = batch_dir / f"p{i+1:02d}.jpg"
        p = download_image(url, img_path)
        if not p:
            continue
        items = ocr_vision(p)
        rows = parse_toudang_items(items, year, subject_group, batch)
        all_rows.extend(rows)
        if (i + 1) % 10 == 0:
            print(f"  进度: {i+1}/{len(img_urls)}, 累计 {len(all_rows)} 行")
    
    # 去重
    seen = set()
    unique = []
    for r in all_rows:
        k = (r["university_code"], r["group_code"], r["lowest_score"])
        if k not in seen:
            seen.add(k)
            unique.append(r)
    
    print(f"  [OK] {batch}/{subject_group} 提取 {len(unique)} 行 (去重后)")
    return unique


def main():
    all_rows = []
    for year, batches in TOUDANG_URLS.items():
        for (batch, sg), urls in batches.items():
            try:
                rows = process_batch(year, sg, batch, urls)
                all_rows.extend(rows)
            except Exception as e:
                print(f"  [ERROR] {year} {batch} {sg}: {e}")
    
    if all_rows:
        csv_path = DATA_DIR / "admission_history.csv"
        # #14 root fix: 重定向到 data/raw/{省}_{文件名}，禁止直接写主 CSV
        _raw_dir = DATA_DIR / "raw"
        _raw_dir.mkdir(exist_ok=True)
        csv_path = _raw_dir / f"{PROVINCE}_{csv_path.name}"
        if csv_path.exists():
            existing = pd.read_csv(csv_path, dtype=str)
            existing_no_fj = existing[existing["province"] != "福建"]
            new_df = pd.DataFrame(all_rows)
            merged = pd.concat([existing_no_fj, new_df], ignore_index=True)
        else:
            merged = pd.DataFrame(all_rows)
        merged = merged.fillna("")
        merged.to_csv(csv_path, index=False, encoding="utf-8")
        print(f"\n[OK] 投档线写入 {len(all_rows)} 行到 admission_history.csv")
        print(f"     总行数: {len(merged)}")
    
    print(f"\n{'='*60}")
    print("投档线处理完成")


if __name__ == "__main__":
    main()
