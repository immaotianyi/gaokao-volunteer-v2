#!/usr/bin/env python3
"""检查湖南HTML文件结构。"""
import re
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "hunan_2026"

for name in ["control_line.html", "yifenyiduan_physics.html"]:
    p = RAW / name
    if not p.exists():
        print(f"{name}: 不存在")
        continue
    html = p.read_text(encoding="utf-8")
    print(f"\n{'='*60}\n{name} (总长 {len(html)})\n{'='*60}")

    # 关键词位置
    for kw in ["446", "400", "控制分数线", "main_con_zw", "TRS_Editor",
               "class=\"article\"", "本科", "历史类", "物理类", "<table", "<img"]:
        idx = html.find(kw)
        print(f"  {kw:20s}: 位置={idx}")

    # 找正文区
    print("\n--- 正文区内容 ---")
    # 多种正文容器匹配
    patterns = [
        r'class="main_con_zw">(.*?)</div>\s*<div[^>]*class="main_con_fj',
        r'class="main_con_zw">(.*?)</div>\s*<!--',
        r'class="TRS_Editor">(.*?)<div[^>]*class="con_share',
        r'class="article">(.*?)<div[^>]*class="article_fj',
    ]
    body = None
    for pat in patterns:
        m = re.search(pat, html, re.S)
        if m:
            body = m.group(1)
            print(f"  [匹配模式] {pat[:40]}... 长度={len(body)}")
            break
    if not body:
        # 找 main_con_zw 第二次出现后的内容
        idx = html.find('class="main_con_zw"')
        if idx > 0:
            # 找对应的 > 然后截取
            gt = html.find(">", idx)
            if gt > 0:
                body = html[gt+1:gt+5000]
                print(f"  [退化匹配] main_con_zw 后5000字")
    if body:
        text = re.sub(r"<[^>]+>", "\n", body)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"\n+", "\n", text).strip()
        print(text[:1500])
