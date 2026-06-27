#!/usr/bin/env python3
"""翻福建考试院公示公告栏目，找 2024/2025 年的一分一段表、省控线、招生计划、投档线公告。"""
import httpx
import re
import time
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
BASE = "https://www.eeafj.cn"

# 目标关键词
TARGET_KEYWORDS = [
    "一分一段", "成绩分布", "成绩分段", "分数段",
    "录取控制分数线", "控制分数线", "省控线", "切线",
    "招生计划",
    "投档线", "投档分数", "投档情况", "录取结果", "常规志愿",
    "本科批", "专科批",
]


def fetch(url):
    try:
        r = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        return r
    except Exception as e:
        return None


def parse_column_page(url):
    """解析栏目页，返回 [(href, title, date)]。"""
    r = fetch(url)
    if not r or r.status_code != 200:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "gkptgkgsgg/" not in href or not href.endswith(".html"):
            continue
        # 文字可能不在 a 里，找父级 li
        text = a.get_text(strip=True)
        if not text:
            li = a.find_parent("li") or a.find_parent("div")
            if li:
                text = li.get_text(" ", strip=True)
        # 提取日期 [MM-DD]
        date_m = re.search(r"\[(\d{2}-\d{2})\]", text)
        date = date_m.group(1) if date_m else ""
        # 清洗标题
        title = re.sub(r"\[\d{2}-\d{2}\]\s*", "", text).strip()
        # 完整 URL
        if href.startswith("http"):
            full_url = href
        else:
            full_url = BASE + href if href.startswith("/") else BASE + "/" + href
        items.append((full_url, title, date))
    # 去重
    seen = set()
    unique = []
    for item in items:
        if item[0] in seen:
            continue
        seen.add(item[0])
        unique.append(item)
    return unique


def main():
    print("="*60)
    print("福建考试院 公示公告栏目 - 翻页找历史数据")
    print("="*60)

    all_items = []
    # 翻页 1..100（首页是 index.html, 后续是 index_2.jhtml .. index_100.jhtml）
    urls_to_fetch = ["https://www.eeafj.cn/gkptgkgsgg/"]
    for i in range(2, 101):
        urls_to_fetch.append(f"https://www.eeafj.cn/ffcms/gkptgkgsgg/index_{i}.jhtml")

    # 先翻前 30 页（覆盖最近 1-2 年）
    for idx, url in enumerate(urls_to_fetch[:30]):
        items = parse_column_page(url)
        if not items:
            print(f"  [{idx+1}/30] {url} - 无数据")
            continue
        # 过滤目标关键词
        for href, title, date in items:
            for kw in TARGET_KEYWORDS:
                if kw in title:
                    all_items.append((href, title, date))
                    break
        print(f"  [{idx+1}/30] {url} - {len(items)} 条, 累计目标 {len(all_items)}")
        time.sleep(0.3)  # 礼貌延迟

    print(f"\n=== 找到 {len(all_items)} 条目标公告 ===")
    # 按日期排序
    for href, title, date in all_items:
        print(f"  [{date}] {title[:60]}")
        print(f"       {href}")


if __name__ == "__main__":
    main()
