#!/usr/bin/env python3
"""福建历史数据（2023/2024/2025）下载 + OCR 解析。

数据类型：
  - 省控线 control_line（图片格式，OCR）
  - 一分一段表 yifenyiduan（图片格式，OCR）
  - 投档线 toudang（图片格式，OCR）
  - 招生计划 plans（PDF格式，pdfplumber）

输出：
  - 追加到 data/control_line_{year}.csv
  - 追加到 data/yifenyiduan_{year}.csv
  - 追加到 data/admission_history.csv
  - 追加到 data/plans_2025.csv (仅 2025)
"""
from __future__ import annotations

import csv
import os
import re
import sys
import time
from pathlib import Path
from io import BytesIO

import httpx
from PIL import Image, ImageOps, ImageFilter
import pytesseract

BACKEND = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND / "data"
RAW_DIR = DATA_DIR / "raw" / "fujian_history"
PROVINCE = "福建"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "http://www.eeafj.cn/",
}

# ─────────────────────────────────────────────────────────────────
# 公告 URL 清单（从 history_log.txt 提取的关键公告）
# ─────────────────────────────────────────────────────────────────
URLS = {
    2025: {
        "control_line": "http://www.eeafj.cn/gkptgkgsgg/20250624/14072.html",
        "yifenyiduan_physics": "http://www.eeafj.cn/gkptgkgsgg/20250625/14056.html",
        "yifenyiduan_history": "http://www.eeafj.cn/gkptgkgsgg/20250625/14055.html",
        "plans": "http://www.eeafj.cn/gkptgkgsgg/20250626/14057.html",
        "toudang_benke_physics": "http://www.eeafj.cn/gkptgkgsgg/20250726/14165.html",
        "toudang_benke_history": "http://www.eeafj.cn/gkptgkgsgg/20250726/14164.html",
        "toudang_zhuanke_physics": "http://www.eeafj.cn/gkptgkgsgg/20250818/14226.html",
        "toudang_zhuanke_history": "http://www.eeafj.cn/gkptgkgsgg/20250818/14227.html",
    },
    2024: {
        "control_line": "http://www.eeafj.cn/gkptgkgsgg/20240624/13465.html",
        "yifenyiduan_physics": "http://www.eeafj.cn/gkptgkgsgg/20240625/13485.html",
        "yifenyiduan_history": "http://www.eeafj.cn/gkptgkgsgg/20240625/13486.html",
        "plans": "http://www.eeafj.cn/gkptgkgsgg/20240626/13466.html",
        "toudang_benke_physics": "http://www.eeafj.cn/gkptgkgsgg/20240726/13557.html",
        "toudang_benke_history": "http://www.eeafj.cn/gkptgkgsgg/20240726/13541.html",
        "toudang_zhuanke_physics": "http://www.eeafj.cn/gkptgkgsgg/20240819/13650.html",
        "toudang_zhuanke_history": "http://www.eeafj.cn/gkptgkgsgg/20240819/13649.html",
    },
    2023: {
        "control_line": "http://www.eeafj.cn/gkptgkgsgg/20230624/12910.html",
        "yifenyiduan_physics": "http://www.eeafj.cn/gkptgkgsgg/20230625/12913.html",
        "yifenyiduan_history": "http://www.eeafj.cn/gkptgkgsgg/20230625/12898.html",
        "plans": "http://www.eeafj.cn/gkptgkgsgg/20230626/12914.html",
        "toudang_benke_physics": "http://www.eeafj.cn/gkptgkgsgg/20230728/12994.html",
        "toudang_benke_history": "http://www.eeafj.cn/gkptgkgsgg/20230728/13021.html",
        "toudang_zhuanke_physics": "http://www.eeafj.cn/gkptgkgsgg/20230818/13038.html",
        "toudang_zhuanke_history": "http://www.eeafj.cn/gkptgkgsgg/20230818/13045.html",
    },
}


# ─────────────────────────────────────────────────────────────────
# 下载工具
# ─────────────────────────────────────────────────────────────────
def fetch_html(url: str, cache_path: Path) -> str:
    """下载 HTML 并缓存。"""
    if cache_path.exists() and cache_path.stat().st_size > 1000:
        return cache_path.read_text(encoding="utf-8", errors="ignore")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
        if r.status_code != 200:
            print(f"  [FAIL] {url} status={r.status_code}")
            return ""
        cache_path.write_text(r.text, encoding="utf-8")
        print(f"  [OK] HTML {cache_path.name} ({cache_path.stat().st_size} bytes)")
        return r.text
    except Exception as e:
        print(f"  [FAIL] {url}: {e}")
        return ""


def fetch_image(url: str, cache_path: Path) -> Path | None:
    """下载图片并缓存。"""
    if cache_path.exists() and cache_path.stat().st_size > 1000:
        return cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = httpx.get(url, headers=HEADERS, timeout=60, follow_redirects=True)
        if r.status_code != 200:
            print(f"    [FAIL IMG] {url} status={r.status_code}")
            return None
        cache_path.write_bytes(r.content)
        print(f"    [OK IMG] {cache_path.name} ({cache_path.stat().st_size} bytes)")
        time.sleep(0.3)
        return cache_path
    except Exception as e:
        print(f"    [FAIL IMG] {url}: {e}")
        return None


def extract_image_urls(html: str) -> list[str]:
    """从 HTML 中提取所有图片 URL。"""
    # 匹配 <img src="...">
    urls = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.I)
    # 过滤掉 logo/icon 等小图
    filtered = []
    for u in urls:
        if any(kw in u.lower() for kw in ["logo", "icon", "banner", "code_", "wechat", "qrcode"]):
            continue
        # 补全协议
        if u.startswith("//"):
            u = "http:" + u
        elif u.startswith("/"):
            u = "http://www.eeafj.cn" + u
        filtered.append(u)
    return filtered


# ─────────────────────────────────────────────────────────────────
# OCR 工具
# ─────────────────────────────────────────────────────────────────
def preprocess_image(img: Image.Image, scale: int = 3) -> Image.Image:
    """图像预处理：灰度 + 放大 + 锐化 + 二值化。"""
    if img.mode != "L":
        img = img.convert("L")
    w, h = img.size
    img = img.resize((w * scale, h * scale), Image.LANCZOS)
    img = img.filter(ImageFilter.SHARPEN)
    # 二值化（提升对比度）
    img = img.point(lambda p: 0 if p < 140 else 255)
    return img


def ocr_image(img_path: Path, psm: int = 6, lang: str = "chi_sim+eng") -> str:
    """OCR 单张图片。"""
    try:
        img = Image.open(img_path)
        img = preprocess_image(img)
        config = f"--psm {psm} -c tessedit_char_whitelist=0123456789物理历史类本科专科特殊类型招生控制分数线总分年福建,"
        text = pytesseract.image_to_string(img, lang=lang, config=config)
        return text
    except Exception as e:
        print(f"    [OCR FAIL] {img_path.name}: {e}")
        return ""


def ocr_image_table(img_path: Path, psm: int = 6) -> list[str]:
    """OCR 表格图片，返回行列表。"""
    try:
        img = Image.open(img_path)
        img = preprocess_image(img)
        text = pytesseract.image_to_string(img, lang="chi_sim+eng", config=f"--psm {psm}")
        return [ln.strip() for ln in text.split("\n") if ln.strip()]
    except Exception as e:
        print(f"    [OCR FAIL] {img_path.name}: {e}")
        return []


# ─────────────────────────────────────────────────────────────────
# 省控线解析（2024/2025 复用 2026 已知结构）
# ─────────────────────────────────────────────────────────────────
def parse_control_line_ocr(text: str, year: int, source_url: str) -> list[dict]:
    """从 OCR 文本中提取省控线。
    
    格式（2024/2025/2026 一致）：
      物理类 本科 446 专科 239 特殊类型 528
      历史类 本科 458 专科 239 特殊类型 533
    """
    rows = []
    # 整体清洗
    text = text.replace(" ", "").replace("\u3000", "")
    lines = [ln for ln in text.split("\n") if ln.strip()]
    
    current_subject = None
    for ln in lines:
        # 识别科类
        if "物理" in ln and ("类" in ln or "科目组" in ln):
            current_subject = "物理类"
        elif "历史" in ln and ("类" in ln or "科目组" in ln):
            current_subject = "历史类"
        
        if current_subject is None:
            continue
        
        # 提取分数：本科/专科/特殊类型
        # OCR 文本可能是 "物理类本科446专科239特殊类型528" 或分多行
        m_benke = re.search(r"本科[\s:：]*(\d{3})", ln)
        m_zhuanke = re.search(r"专科[\s:：]*(\d{3})", ln)
        m_tekong = re.search(r"特殊[类型]*[\s:：]*(\d{3})", ln)
        
        # 一行可能含多个分数
        for label, m, batch_section, batch in [
            ("本科", m_benke, "本科院校", "本科"),
            ("专科", m_zhuanke, "专科院校", "专科"),
            ("特控", m_tekong, "特殊类型招生", "提前"),
        ]:
            if m:
                score = int(m.group(1))
                if 100 <= score <= 750:
                    rows.append({
                        "province": "福建",
                        "year": year,
                        "batch_section": batch_section,
                        "batch": batch,
                        "subject_group": current_subject,
                        "line_type": "总分",
                        "lowest_score": score,
                        "source_url": source_url,
                    })
    
    return rows


# ─────────────────────────────────────────────────────────────────
# 一分一段表解析
# ─────────────────────────────────────────────────────────────────
def parse_yifenyiduan_ocr(lines: list[str], year: int, subject_group: str) -> list[dict]:
    """从 OCR 行列表中提取一分一段表数据。
    
    格式：分数 | 人数 | 累计人数
    OCR 可能识别为 "690 12 12" 或 "690 12 12" 等
    """
    rows = []
    for ln in lines:
        # 提取所有数字
        nums = re.findall(r"\d+", ln)
        if len(nums) < 3:
            continue
        try:
            score = int(nums[0])
            seg = int(nums[1])
            cum = int(nums[2])
        except (ValueError, IndexError):
            continue
        if not (0 <= score <= 750):
            continue
        if seg < 0 or seg > 100000:
            continue
        if cum < 0 or cum > 1000000:
            continue
        rows.append({
            "province": "福建",
            "year": year,
            "subject_group": subject_group,
            "batch": "本科批",
            "score": score,
            "segment_count": seg,
            "cumulative_count": cum,
        })
    return rows


# ─────────────────────────────────────────────────────────────────
# 投档线解析
# ─────────────────────────────────────────────────────────────────
def parse_toudang_ocr(lines: list[str], year: int, subject_group: str, batch: str) -> list[dict]:
    """从 OCR 行列表中提取投档线数据。
    
    格式：院校代号 | 院校名称 | 专业组代号 | 投档最低分
    OCR 难以精确分列，采用宽松匹配。
    """
    rows = []
    for ln in lines:
        # 提取所有数字
        nums = re.findall(r"\d+", ln)
        if len(nums) < 2:
            continue
        # 找院校代号（4位）和分数（3位）
        univ_code = None
        score = None
        for n in nums:
            v = int(n)
            if 1000 <= v <= 9999 and univ_code is None:
                univ_code = str(v)
            elif 200 <= v <= 750 and score is None:
                score = v
        if not univ_code or not score:
            continue
        # 提取院校名（去除数字后的中文部分）
        name = re.sub(r"\d+", "", ln).strip()
        if not name or len(name) < 4:
            continue
        rows.append({
            "year": year,
            "province": "福建",
            "subject_group": subject_group,
            "batch": batch,
            "university_code": univ_code,
            "university_name": name,
            "group_code": univ_code,  # 简化：用院校代号
            "major_code": univ_code,
            "major_name": f"第{univ_code}组",
            "lowest_score": float(score),
            "lowest_rank": "",
            "avg_score": "",
            "applicant_count": "",
            "source_file": f"fujian_{year}_{subject_group}_{batch}.jpg",
        })
    return rows


# ─────────────────────────────────────────────────────────────────
# 写入 CSV（追加模式）
# ─────────────────────────────────────────────────────────────────
def append_rows_to_csv(rows: list[dict], csv_path: Path, fieldnames: list[str]) -> int:
    """追加行到 CSV（去除福建旧数据后追加新数据）。"""
    # #14 root fix: 重定向到 data/raw/{省}_{文件名}，禁止直接写主 CSV
    _raw_dir = DATA_DIR / "raw"
    _raw_dir.mkdir(exist_ok=True)
    csv_path = _raw_dir / f"{PROVINCE}_{csv_path.name}"
    if not rows:
        return 0
    import pandas as pd
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


# ─────────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────────
def process_year(year: int):
    """处理单年所有数据。"""
    print(f"\n{'='*60}")
    print(f"处理 {year} 年数据")
    print(f"{'='*60}")
    
    year_urls = URLS.get(year, {})
    if not year_urls:
        print(f"  无 {year} 年 URL 配置")
        return
    
    year_dir = RAW_DIR / str(year)
    year_dir.mkdir(parents=True, exist_ok=True)
    
    # ────── 1. 省控线 ──────
    print(f"\n[1/4] 省控线")
    cl_url = year_urls.get("control_line")
    if cl_url:
        html = fetch_html(cl_url, year_dir / "control_line.html")
        if html:
            img_urls = extract_image_urls(html)
            print(f"  找到 {len(img_urls)} 张图片")
            for i, iu in enumerate(img_urls[:3]):  # 省控线通常1张图
                img_path = year_dir / f"control_line_p{i+1}.jpg"
                p = fetch_image(iu, img_path)
                if p:
                    text = ocr_image(p, psm=6)
                    print(f"  [OCR] 原始: {text[:200]}")
                    rows = parse_control_line_ocr(text, year, cl_url)
                    if rows:
                        n = append_rows_to_csv(rows, DATA_DIR / f"control_line_{year}.csv",
                            ["province","year","batch_section","batch","subject_group","line_type","lowest_score","source_url"])
                        print(f"  [OK] 省控线写入 {n} 行到 control_line_{year}.csv")
                        break
    
    # ────── 2. 一分一段表 ──────
    print(f"\n[2/4] 一分一段表")
    for sg_key, sg_name in [("physics", "物理类"), ("history", "历史类")]:
        url_key = f"yifenyiduan_{sg_key}"
        yfd_url = year_urls.get(url_key)
        if not yfd_url:
            continue
        print(f"  [{sg_name}] {yfd_url}")
        html = fetch_html(yfd_url, year_dir / f"yfd_{sg_key}.html")
        if not html:
            continue
        img_urls = extract_image_urls(html)
        print(f"    找到 {len(img_urls)} 张图片")
        all_rows = []
        for i, iu in enumerate(img_urls[:6]):  # 一分一段表通常2-4张图
            img_path = year_dir / f"yfd_{sg_key}_p{i+1}.jpg"
            p = fetch_image(iu, img_path)
            if p:
                lines = ocr_image_table(p, psm=6)
                print(f"    [p{i+1}] OCR 得到 {len(lines)} 行")
                rows = parse_yifenyiduan_ocr(lines, year, sg_name)
                all_rows.extend(rows)
        if all_rows:
            # 去重
            seen = set()
            unique = []
            for r in all_rows:
                k = (r["score"], r["segment_count"], r["cumulative_count"])
                if k not in seen:
                    seen.add(k)
                    unique.append(r)
            # 按分数降序
            unique.sort(key=lambda x: -x["score"])
            n = append_rows_to_csv(unique, DATA_DIR / f"yifenyiduan_{year}.csv",
                ["province","year","subject_group","batch","score","segment_count","cumulative_count"])
            print(f"    [OK] {sg_name} 一分一段表写入 {n} 行到 yifenyiduan_{year}.csv")
    
    # ────── 3. 投档线 ──────
    print(f"\n[3/4] 投档线")
    toudang_rows = []
    for batch_key, batch_name, sg_key, sg_name in [
        ("toudang_benke_physics", "本科批", "physics", "物理类"),
        ("toudang_benke_history", "本科批", "history", "历史类"),
        ("toudang_zhuanke_physics", "专科批", "physics", "物理类"),
        ("toudang_zhuanke_history", "专科批", "history", "历史类"),
    ]:
        td_url = year_urls.get(batch_key)
        if not td_url:
            continue
        print(f"  [{batch_name}/{sg_name}] {td_url}")
        html = fetch_html(td_url, year_dir / f"{batch_key}.html")
        if not html:
            continue
        img_urls = extract_image_urls(html)
        print(f"    找到 {len(img_urls)} 张图片")
        for i, iu in enumerate(img_urls[:8]):
            img_path = year_dir / f"{batch_key}_p{i+1}.jpg"
            p = fetch_image(iu, img_path)
            if p:
                lines = ocr_image_table(p, psm=6)
                rows = parse_toudang_ocr(lines, year, sg_name, batch_name)
                toudang_rows.extend(rows)
    
    if toudang_rows:
        n = append_rows_to_csv(toudang_rows, DATA_DIR / "admission_history.csv",
            ["year","province","subject_group","batch","university_code","university_name",
             "group_code","major_code","major_name","lowest_score","lowest_rank","avg_score","applicant_count","source_file"])
        print(f"  [OK] 投档线写入 {n} 行到 admission_history.csv")
    
    # ────── 4. 招生计划（仅 2025，PDF 格式） ──────
    if year == 2025:
        print(f"\n[4/4] 招生计划 (2025)")
        plans_url = year_urls.get("plans")
        if plans_url:
            html = fetch_html(plans_url, year_dir / "plans.html")
            if html:
                # 提取附件链接（PDF）
                pdf_urls = re.findall(r'href=["\']([^"\']+\.pdf)["\']', html, re.I)
                print(f"    找到 {len(pdf_urls)} 个 PDF 附件")
                for i, pu in enumerate(pdf_urls[:4]):
                    if pu.startswith("/"):
                        pu = "http://www.eeafj.cn" + pu
                    elif not pu.startswith("http"):
                        pu = "http://www.eeafj.cn/" + pu
                    pdf_path = year_dir / f"plans_2025_{i+1}.pdf"
                    p = fetch_image(pu, pdf_path)
                    if p:
                        print(f"    [OK] 下载 {pdf_path.name}")
    else:
        print(f"\n[4/4] 招生计划 (跳过 {year})")


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    # 默认处理 2024/2025（2023 数据可能不全，可选）
    years = [int(y) for y in sys.argv[1:]] if len(sys.argv) > 1 else [2025, 2024]
    
    for year in years:
        try:
            process_year(year)
        except Exception as e:
            print(f"\n[ERROR] {year} 年处理失败: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*60}")
    print(f"全部完成")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
