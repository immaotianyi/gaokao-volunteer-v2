#!/usr/bin/env python3
"""湖南省教育考试院 2026 数据下载脚本。

数据源: 湖南省教育厅 (jyt.hunan.gov.cn) 考试院招考资讯栏目
特点: 数据以 HTML 表格形式发布，比 PDF 易解析。
"""
import os
import re
import sys
import time
from pathlib import Path

import requests

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_2026 = DATA_DIR / "raw" / "hunan_2026"
RAW_2025 = DATA_DIR / "raw" / "hunan_2025"
RAW_2024 = DATA_DIR / "raw" / "hunan_2024"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 2026 年已确认 URL（来自 web 搜索）
URLS_2026 = {
    "yifenyiduan_physics": "https://jyt.hunan.gov.cn/jyt/sjyt/hnsjyksy/web/ksyzkzx/202606/t20260625_34013125.html",
    "yifenyiduan_history": "https://jyt.hunan.gov.cn/jyt/sjyt/hnsjyksy/web/ksyzkzx/202606/t20260625_34013108.html",
    "control_line": "https://jyt.hunan.gov.cn/jyt/sjyt/hnsjyksy/web/ksyzkzx/202606/t20260625_34011553.html",
}


def fetch_html(url: str, out_path: Path, timeout: int = 30) -> bool:
    """下载 HTML 页面并保存。返回是否成功。"""
    if out_path.exists() and out_path.stat().st_size > 1000:
        print(f"  [SKIP] {out_path.name} 已存在 ({out_path.stat().st_size} bytes)")
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


def fetch_2026():
    """下载 2026 年一分一段表 + 省控线 HTML。"""
    print("\n[FETCH 2026] 一分一段表 + 省控线")
    RAW_2026.mkdir(parents=True, exist_ok=True)
    ok = True
    for key, url in URLS_2026.items():
        out = RAW_2026 / f"{key}.html"
        if not fetch_html(url, out):
            ok = False
        time.sleep(0.5)
    return ok


if __name__ == "__main__":
    fetch_2026()
