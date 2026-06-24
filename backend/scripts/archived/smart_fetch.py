#!/usr/bin/env python3
"""
智能批量抓取 — 用 DuckDuckGo 搜索 + Playwright 下载章程

两步走：
1. DuckDuckGo 搜索 "{校名} 2026年 招生章程" → 找到章程URL
2. Playwright 下载页面 → 分段保存

用法:
  python scripts/smart_fetch.py --limit 50
"""
import asyncio, re, time, json, argparse, requests
from pathlib import Path
from urllib.parse import unquote
from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ZSZC_DIR = DATA_DIR / "zszc"
ZSZC_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', name)


def search_chapter_url(university_name: str) -> str | None:
    """DuckDuckGo 搜索章程URL"""
    query = f"{university_name} 2026年 招生章程"
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=HEADERS,
            timeout=15,
        )
        if resp.status_code == 200:
            urls = re.findall(r'uddg=([^"&]+)', resp.text)
            decoded = [unquote(u) for u in urls]
            for u in decoded:
                if '.edu.cn' in u:
                    return u
            for u in decoded:
                if any(k in u.lower() for k in ['zhaosheng','zsb','bkzs','admission']):
                    return u
            if decoded:
                return decoded[0]
    except Exception:
        pass
    return None


async def download_chapter(name: str, url: str, page) -> bool:
    """Playwright 下载章程页面"""
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        if not resp or resp.status != 200:
            return False
        await page.wait_for_timeout(3000)

        text = await page.evaluate("() => document.body.innerText")
        text = re.sub(r"\s+", " ", text)

        if len(text) < 300:
            return False

        # 确认是章程
        has_chapter = "招生章程" in text[:2000] or "第一章" in text[:1000]
        has_2026 = "2026" in text[:2000]
        if not has_chapter or not has_2026:
            return False

        # 找正文起始
        for marker in ["招生章程", "第一章", "第一条", "总则"]:
            idx = text.find(marker)
            if idx != -1:
                text = text[idx:]
                break

        # 分段保存
        MAX_LEN, OVERLAP = 1000, 100
        segments = []
        i = 0
        while i < len(text):
            segments.append(text[i:i + MAX_LEN].strip())
            i += MAX_LEN - OVERLAP

        sn = safe_name(name)
        for j, seg in enumerate(segments):
            if not seg.strip():
                continue
            fp = ZSZC_DIR / f"{sn}_2026招生章程_第{j+1}段.txt"
            with open(fp, "w", encoding="utf-8") as f:
                f.write(f"大学名称：{name}\n年份：2026年\n")
                f.write(f"段落编号：{j+1}/{len(segments)}\n")
                f.write(f"数据来源：{url}\n")
                f.write("=" * 60 + "\n\n" + seg)

        return True
    except Exception:
        return False


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", "-n", type=int, default=50)
    args = parser.parse_args()

    # 获取已抓取
    existing = set()
    for f in ZSZC_DIR.glob("*招生章程_*.txt"):
        name = f.stem
        for s in ["_2026招生章程", "_2025招生章程"]:
            if s in name:
                name = name.replace(s, "")
                break
        name = re.sub(r"_第\d+段$", "", name)
        existing.add(name)

    # 加载缺失的985/211/双一流
    with open(DATA_DIR / "school_list.json") as f:
        all_schools = json.load(f)

    # 优先级: 985 > 211 > 双一流 > 省属重点
    priority_order = {"985": 0, "211": 1, "双一流": 2, "省属重点": 3, "普通本科": 4}
    targets = []
    for s in all_schools:
        if s["name"] not in covered and safe_name(s["name"]) not in existing:
            targets.append(s)
    targets.sort(key=lambda x: priority_order.get(x["type"], 9))

    if args.limit:
        targets = targets[:args.limit]

    print(f"已抓取: {len(existing)} 所")
    print(f"待抓取: {len(targets)} 所")
    types = {}
    for t in targets:
        types[t["type"]] = types.get(t["type"], 0) + 1
    for t, c in sorted(types.items(), key=lambda x: priority_order.get(x[0], 9)):
        print(f"  {t}: {c}所")

    stats = {"success": 0, "failed": 0, "no_url": 0}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
            locale="zh-CN",
            ignore_https_errors=True,
        )
        page = await context.new_page()

        for i, s in enumerate(targets):
            name = s["name"]
            print(f"[{i+1}/{len(targets)}] {name} ({s['type']}) ...", end=" ", flush=True)

            # 1. 搜索
            url = search_chapter_url(name)
            if not url:
                stats["no_url"] += 1
                print("❌ 搜索无结果")
                time.sleep(1)
                continue

            # 2. 下载
            ok = await download_chapter(name, url, page)
            if ok:
                stats["success"] += 1
                print(f"✅")
            else:
                stats["failed"] += 1
                print(f"❌ 下载失败")

            if (i + 1) % 10 == 0:
                new_total = len(existing) + stats["success"]
                print(f"  [进度] 成功{stats['success']} 失败{stats['failed']} 无结果{stats['no_url']} → 累计{new_total}所")

            time.sleep(2)

        await browser.close()

    new_total = len(existing) + stats["success"]
    print(f"\n✅ 完成: 成功{stats['success']} 失败{stats['failed']} 无结果{stats['no_url']}")
    print(f"累计章程覆盖: {new_total} 所")


if __name__ == "__main__":
    # 更新 covered 集合
    with open(DATA_DIR / "enrollment_rules.json") as f:
        rules = json.load(f)["rules"]
    covered = {r["university"] for r in rules}
    asyncio.run(main())
