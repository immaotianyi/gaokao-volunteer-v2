#!/usr/bin/env python3
"""下载安徽省考试院原始PDF/HTML（临时下载脚本）"""
import httpx
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "data" / "raw" / "anhui_2026"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

FILES = [
    ("yifenyiduan", "anhui_yifenyiduan_2026.pdf",
     "https://www.ahzsks.cn/pic/file/20260625/20260625153758_335.pdf"),
    ("yifenyiduan", "anhui_yifenyiduan_2025.pdf",
     "https://www.ahzsks.cn/pic/file/20250625/20250625150831_928.pdf"),
    ("plans", "anhui_plans_2026_guojia_physics.pdf",
     "https://www.ahzsks.cn/pic/file/20260621/20260621134118_822.pdf"),
    ("plans", "anhui_plans_2026_guojia_history.pdf",
     "https://www.ahzsks.cn/pic/file/20260621/20260621134105_608.pdf"),
    ("plans", "anhui_plans_2026_difang_physics.pdf",
     "https://www.ahzsks.cn/pic/file/20260621/20260621134146_545.pdf"),
    ("plans", "anhui_plans_2026_difang_history.pdf",
     "https://www.ahzsks.cn/pic/file/20260621/20260621134132_771.pdf"),
    ("plans", "anhui_plans_2026_gaoxiao_physics.pdf",
     "https://www.ahzsks.cn/pic/file/20260621/20260621134226_374.pdf"),
    ("plans", "anhui_plans_2026_gaoxiao_history.pdf",
     "https://www.ahzsks.cn/pic/file/20260621/20260621134158_510.pdf"),
    ("control_line", "anhui_control_line_2024.html",
     "https://www.ahzsks.cn/ggl/7626.htm"),
    ("yifenyiduan", "anhui_yifenyiduan_2024.html",
     "https://www.ahzsks.cn/ggl/7625.htm"),
]

ok, fail = 0, 0
with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=60) as cli:
    for sub, name, url in FILES:
        out = BASE / sub / name
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists() and out.stat().st_size > 1000:
            print(f"[SKIP] {sub}/{name} ({out.stat().st_size} bytes)")
            ok += 1
            continue
        try:
            r = cli.get(url)
            if r.status_code == 200 and len(r.content) > 1000:
                out.write_bytes(r.content)
                print(f"[OK] {sub}/{name} ({len(r.content)} bytes)")
                ok += 1
            else:
                print(f"[FAIL] {sub}/{name} status={r.status_code} size={len(r.content)}")
                fail += 1
        except Exception as e:
            print(f"[ERR] {sub}/{name}: {e}")
            fail += 1

print(f"\n下载完成: 成功 {ok}, 失败 {fail}")
