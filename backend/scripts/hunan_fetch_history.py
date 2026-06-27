#!/usr/bin/env python3
"""湖南历史数据下载：2024/2025 一分一段表、省控线、投档线。"""
import time
from pathlib import Path
import requests

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_2025 = DATA_DIR / "raw" / "hunan_2025"
RAW_2024 = DATA_DIR / "raw" / "hunan_2024"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 2025 数据 URL
URLS_2025 = {
    "yifenyiduan_physics": "https://www.hneeb.cn/hnxxg/741/742/content_4434.html",
    "yifenyiduan_history": "https://www.hneeb.cn/hnxxg/741/742/content_4433.html",
    "toudang_benke": "https://jyt.hunan.gov.cn/jyt/sjyt/hnsjyksy/web/ksyzkzx/202507/33744762/files/b3230b1d6d374bc6858030c97267374b.xlsx",
}

# 2024 数据 URL
URLS_2024 = {
    # 一分一段表（2024 有两套列：含全国性加分 / 含全国性和地方性加分）
    "yifenyiduan_physics": "https://www.hneeb.cn/hnxxg/741/742/content_4207.html",
    "yifenyiduan_history": "https://www.hneeb.cn/hnxxg/741/742/content_4206.html",
    # 投档线 Excel（本科批普通类第一次）
    "toudang_benke": "https://www.hneeb.cn/hnxxg/741/742/2024072001.xlsx",
}


def fetch(url, out_path, timeout=60):
    if out_path.exists() and out_path.stat().st_size > 1000:
        print(f"  [SKIP] {out_path.name} 已存在 ({out_path.stat().st_size} bytes)")
        return True
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
        if r.status_code != 200:
            print(f"  [FAIL] {url} status={r.status_code}")
            return False
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        print(f"  [OK] {out_path.name} ({out_path.stat().st_size} bytes)")
        return True
    except Exception as e:
        print(f"  [FAIL] {url}: {e}")
        return False


def main():
    for year, urls, raw_dir in [("2025", URLS_2025, RAW_2025), ("2024", URLS_2024, RAW_2024)]:
        print(f"\n[FETCH {year}] 一分一段表 + 投档线")
        raw_dir.mkdir(parents=True, exist_ok=True)
        for key, url in urls.items():
            ext = ".xlsx" if url.endswith(".xlsx") else ".html"
            out = raw_dir / f"{key}{ext}"
            fetch(url, out)
            time.sleep(0.5)


if __name__ == "__main__":
    main()
