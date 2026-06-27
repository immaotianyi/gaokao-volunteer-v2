#!/usr/bin/env python3
"""下载甘肃2024本科批C段投档最低分 XLS（历史类+物理类）。"""
import urllib3
import requests
from pathlib import Path

urllib3.disable_warnings()

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "gansu_2026"
RAW.mkdir(parents=True, exist_ok=True)

FILES = {
    "gansu_toudang_2024_history.xls": "https://www.ganseea.cn/uploads/allimg/20240719/11-240G911340H24.xls",
    "gansu_toudang_2024_physics.xls": "https://www.ganseea.cn/uploads/allimg/20240719/11-240G9113416231.xls",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.ganseea.cn/",
}

for name, url in FILES.items():
    out = RAW / name
    if out.exists() and out.stat().st_size > 1000:
        print(f"[SKIP] {name} ({out.stat().st_size} bytes)")
        continue
    try:
        r = requests.get(url, headers=HEADERS, verify=False, timeout=30)
        print(f"  status={r.status_code} len={len(r.content)} ct={r.headers.get('content-type')}")
        if r.status_code == 200 and len(r.content) > 1000:
            out.write_bytes(r.content)
            print(f"[OK] {name} ({out.stat().st_size} bytes)")
        else:
            print(f"[FAIL] {name}: {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"[ERR] {name}: {e}")
