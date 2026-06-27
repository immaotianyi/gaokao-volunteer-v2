#!/usr/bin/env python3
"""下载福建省2026原始数据：招生计划ZIP、一分一段表图片、省控线图片。"""
import httpx
import os
from pathlib import Path
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.eeafj.cn/gkptgkgsgg/",
}
BASE = "https://www.eeafj.cn"
BACKEND = Path(__file__).resolve().parent.parent
RAW_DIR = BACKEND / "data" / "raw" / "fujian_2026"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# 2026 数据清单
FILES_2026 = [
    # 招生计划 ZIP
    ("plans_2026_physics.zip", "https://www.eeafj.cn/u/cms/default/202606/20260624081923_43.zip",
     "https://www.eeafj.cn/gkptgkgsgg/20260624/14715.html"),
    ("plans_2026_history.zip", "https://www.eeafj.cn/u/cms/default/202606/20260624081933_648.zip",
     "https://www.eeafj.cn/gkptgkgsgg/20260624/14715.html"),
    # 省控线图片（2026）
    ("control_line_2026.jpg", "https://www.eeafj.cn/u/cms/default/202606/20260624151636_4.jpg",
     "https://www.eeafj.cn/gkptgkgsgg/20260624/14697.html"),
    # 一分一段表-历史类 图片
    ("yifenyiduan_2026_history_p1.jpg", "https://www.eeafj.cn/u/cms/default/202606/20260625091641_469.jpg",
     "https://www.eeafj.cn/gkptgkgsgg/20260625/14698.html"),
    ("yifenyiduan_2026_history_p2.jpg", "https://www.eeafj.cn/u/cms/default/202606/20260625091642_980.jpg",
     "https://www.eeafj.cn/gkptgkgsgg/20260625/14698.html"),
    ("yifenyiduan_2026_history_p3.jpg", "https://www.eeafj.cn/u/cms/default/202606/20260625091642_682.jpg",
     "https://www.eeafj.cn/gkptgkgsgg/20260625/14698.html"),
    ("yifenyiduan_2026_history_p4.jpg", "https://www.eeafj.cn/u/cms/default/202606/20260625091642_527.jpg",
     "https://www.eeafj.cn/gkptgkgsgg/20260625/14698.html"),
    # 一分一段表-物理类 图片
    ("yifenyiduan_2026_physics_p1.jpg", "https://www.eeafj.cn/u/cms/default/202606/20260625091744_154.jpg",
     "https://www.eeafj.cn/gkptgkgsgg/20260625/14699.html"),
    ("yifenyiduan_2026_physics_p2.jpg", "https://www.eeafj.cn/u/cms/default/202606/20260625091744_318.jpg",
     "https://www.eeafj.cn/gkptgkgsgg/20260625/14699.html"),
    ("yifenyiduan_2026_physics_p3.jpg", "https://www.eeafj.cn/u/cms/default/202606/20260625091744_501.jpg",
     "https://www.eeafj.cn/gkptgkgsgg/20260625/14699.html"),
    ("yifenyiduan_2026_physics_p4.jpg", "https://www.eeafj.cn/u/cms/default/202606/20260625091744_834.jpg",
     "https://www.eeafj.cn/gkptgkgsgg/20260625/14699.html"),
]


def download(url, out_path, referer):
    if out_path.exists() and out_path.stat().st_size > 1000:
        print(f"  [SKIP] {out_path.name} 已存在 ({out_path.stat().st_size} bytes)")
        return True
    headers = {**HEADERS, "Referer": referer}
    try:
        with httpx.Client() as client:
            with client.stream("GET", url, headers=headers, timeout=60, follow_redirects=True) as r:
                if r.status_code != 200:
                    print(f"  [FAIL] {out_path.name} status={r.status_code}")
                    return False
                with open(out_path, "wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
        size = out_path.stat().st_size
        print(f"  [OK] {out_path.name} ({size} bytes)")
        return True
    except Exception as e:
        print(f"  [ERR] {out_path.name}: {type(e).__name__} {e}")
        return False


def main():
    print(f"下载目录: {RAW_DIR}")
    ok = 0
    for fname, url, referer in FILES_2026:
        print(f"\n下载 {fname}")
        if download(url, RAW_DIR / fname, referer):
            ok += 1
    print(f"\n=== 完成: {ok}/{len(FILES_2026)} 个文件下载成功 ===")

    # 列出所有文件
    print(f"\n目录内容:")
    for p in sorted(RAW_DIR.iterdir()):
        print(f"  {p.name:50s} {p.stat().st_size:>10} bytes")


if __name__ == "__main__":
    main()
