#!/usr/bin/env python3
"""
使用 Playwright + Stealth 绕过反爬，从阳光高考平台抓取全国高校列表和章程

用法:
  python scripts/fetch_via_playwright.py --step 1          # 仅获取高校列表
  python scripts/fetch_via_playwright.py --step 2          # 仅抓取章程
  python scripts/fetch_via_playwright.py --limit 50        # 限制抓取数量
"""
import asyncio
import json
import re
import sys
import time
import argparse
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("请先安装: pip install playwright && playwright install chromium")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ZSZC_DIR = DATA_DIR / "zszc"
ZSZC_DIR.mkdir(parents=True, exist_ok=True)

MAX_SEGMENT_LENGTH = 1000
OVERLAP_LENGTH = 100

# URL 模板
INDEX_URL = "https://gaokao.chsi.com.cn/zsgs/zhangcheng/listVerifedZszc.do"
SCHOOL_ZC_LIST_URL = "https://gaokao.chsi.com.cn/zsgs/zhangcheng/listZszc--schId-{schId}.dhtml"
ZC_DETAIL_URL = "https://gaokao.chsi.com.cn/zsgs/zhangcheng/listVerifedZszc--method-view,schId-{schId},infoId-{infoId}.dhtml"


def clean_html(html_text: str) -> str:
    """清理HTML标签，提取纯文本"""
    text = re.sub(r'<script[^>]*>.*?</script>', '', html_text,
                  flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text,
                  flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
    text = text.replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'")
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()


def segment_text(text: str, max_len: int = MAX_SEGMENT_LENGTH,
                 overlap: int = OVERLAP_LENGTH) -> list:
    """按句子分段"""
    segments = []
    if not text:
        return segments
    split_pattern = r'([。！？\n]+)'
    parts = re.split(split_pattern, text)
    sentences = []
    current = ""
    for part in parts:
        current += part
        if re.search(r'[。！？\n]', part):
            sentences.append(current)
            current = ""
    if current.strip():
        sentences.append(current)
    i = 0
    while i < len(sentences):
        segment = ""
        j = i
        while j < len(sentences) and len(segment) + len(sentences[j]) <= max_len:
            segment += sentences[j]
            j += 1
        if not segment:
            sentence = sentences[i]
            for k in range(0, len(sentence), max_len - overlap):
                chunk = sentence[k:k + max_len]
                if chunk.strip():
                    segments.append(chunk.strip())
            i += 1
            continue
        segments.append(segment.strip())
        if j > i + 1:
            overlap_chars = 0
            new_i = j - 1
            while new_i > i and overlap_chars < overlap:
                overlap_chars += len(sentences[new_i])
                new_i -= 1
            i = new_i + 1 if new_i > i else i + 1
        else:
            i = j
    return segments


def safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', name)


# ── Step 1: 获取高校列表 ──────────────────────────────────────

async def fetch_school_list() -> list[dict]:
    """使用 Playwright 从阳光高考平台获取全国高校列表"""
    schools = []
    seen_names = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
        )

        page = await context.new_page()

        # Stealth 注入
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN','zh','en'] });
            window.chrome = { runtime: {} };
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({state: Notification.permission}) :
                    originalQuery(parameters)
            );
        """)

        print("[Step 1] 访问首页...")
        try:
            await page.goto(INDEX_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"[Step 1] 首页加载异常: {e}")

        # 检查是否被屏蔽
        body_text = await page.evaluate("() => document.body?.innerText || ''")
        if not body_text or len(body_text) < 50:
            # 尝试截图看页面状态
            await page.screenshot(path=str(DATA_DIR / "debug_screenshot.png"))
            print(f"[Step 1] ⚠️ 页面内容为空或太少 ({len(body_text)} 字符), 可能被WAF拦截")
            print(f"[Step 1] 截图已保存: {DATA_DIR}/debug_screenshot.png")

        html = await page.content()
        print(f"[Step 1] 页面长度: {len(html)} 字符")

        # 提取学校链接
        links = await page.evaluate("""() => {
            const links = document.querySelectorAll('a[href*="schId"]');
            return Array.from(links).map(a => ({
                href: a.href,
                text: a.innerText.trim()
            }));
        }""")
        print(f"[Step 1] 找到 {len(links)} 个链接")

        for link in links:
            # 从 href 提取 schId
            sch_match = re.search(r'schId[=-](\d+)', link.get("href", ""))
            name = link.get("text", "").strip()
            if sch_match and name and name not in seen_names:
                seen_names.add(name)
                schools.append({"schId": sch_match.group(1), "name": name})

        # 尝试翻页
        page_num = 1
        while page_num < 100:  # 最多100页
            page_num += 1
            # 查找下一页按钮
            next_exists = await page.evaluate("""() => {
                const nextLinks = document.querySelectorAll('a');
                for (const a of nextLinks) {
                    if (a.innerText.includes('下一页') || a.innerText.includes('>')) {
                        return true;
                    }
                }
                return false;
            }""")

            if not next_exists:
                print(f"[Step 1] 第{page_num}页: 无下一页，停止")
                break

            # 构造下一页URL或点击
            next_url = f"{INDEX_URL}?page={page_num}"
            try:
                await page.goto(next_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
            except Exception:
                break

            links = await page.evaluate("""() => {
                const links = document.querySelectorAll('a[href*="schId"]');
                return Array.from(links).map(a => ({
                    href: a.href,
                    text: a.innerText.trim()
                }));
            }""")

            new_count = 0
            for link in links:
                sch_match = re.search(r'schId[=-](\d+)', link.get("href", ""))
                name = link.get("text", "").strip()
                if sch_match and name and name not in seen_names:
                    seen_names.add(name)
                    schools.append({"schId": sch_match.group(1), "name": name})
                    new_count += 1

            if new_count == 0:
                print(f"[Step 1] 第{page_num}页: 无新学校，停止")
                break
            print(f"[Step 1] 第{page_num}页: +{new_count} 所 (累计 {len(schools)})")

            await page.wait_for_timeout(2000)

        await browser.close()

    # 保存
    output_path = DATA_DIR / "school_list.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schools, f, ensure_ascii=False, indent=2)
    print(f"[Step 1] ✅ 共 {len(schools)} 所高校 → {output_path}")

    return schools


# ── Step 2: 批量抓取章程 ──────────────────────────────────────

async def fetch_charters(schools: list[dict], limit: int = 0):
    """批量抓取高校章程"""
    if limit > 0:
        schools = schools[:limit]

    stats = {"total": len(schools), "success": 0, "failed": 0,
             "no_2026": 0, "segments": 0}
    skipped = []
    failed = []

    # 断点续传
    existing = set()
    for f in ZSZC_DIR.glob("*_2026招生章程_*.txt"):
        name = f.stem.split('_2026')[0]
        existing.add(name)
    if existing:
        print(f"[Step 2] 断点续传: 已抓取 {len(existing)} 所")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
        )
        page = await context.new_page()

        # Stealth
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            window.chrome = { runtime: {} };
        """)

        for i, school in enumerate(schools):
            sch_id = school.get("schId", "")
            name = school.get("name", f"schId_{sch_id}")

            # 断点续传
            safe = safe_filename(name)
            if safe in existing:
                if (i + 1) % 50 == 0:
                    print(f"  [{i+1}/{len(schools)}] 跳过: {name}")
                continue

            try:
                print(f"\n[{i+1}/{len(schools)}] {name} (schId={sch_id})")

                # 获取章程列表
                list_url = SCHOOL_ZC_LIST_URL.format(schId=sch_id)
                await page.goto(list_url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(2000)

                list_html = await page.content()

                # 提取 infoId
                info_matches = re.findall(
                    r'infoId[=-](\d+)\.dhtml[^>]*>([^<]*)',
                    list_html
                )

                zc_2026 = []
                for info_id, title in info_matches:
                    year_match = re.search(r'(20\d{2})', title)
                    year = year_match.group(1) if year_match else "unknown"
                    if year == "2026":
                        zc_2026.append({"infoId": info_id, "title": title.strip()})

                if not zc_2026:
                    stats["no_2026"] += 1
                    skipped.append({"schId": sch_id, "name": name, "reason": "无2026年章程"})
                    continue

                # 抓取章程内容
                uni_segments = 0
                for zc in zc_2026:
                    info_id = zc["infoId"]
                    detail_url = ZC_DETAIL_URL.format(schId=sch_id, infoId=info_id)

                    await page.goto(detail_url, wait_until="domcontentloaded", timeout=20000)
                    await page.wait_for_timeout(1500)

                    detail_html = await page.content()
                    text = clean_html(detail_html)

                    # 找正文起始
                    for marker in ["招生章程", "第一章", "第一条", "总则"]:
                        idx = text.find(marker)
                        if idx != -1:
                            text = text[idx:]
                            break

                    if len(text) < 100:
                        continue

                    # 分段并保存
                    segments = segment_text(text)
                    safe_name = safe_filename(name)

                    for j, segment in enumerate(segments):
                        filename = f"{safe_name}_2026招生章程_第{j+1}段.txt"
                        filepath = ZSZC_DIR / filename
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(f"大学名称：{name}\n")
                            f.write(f"年份：2026年\n")
                            f.write(f"段落编号：{j+1}/{len(segments)}\n")
                            f.write(f"数据来源：教育部阳光高考平台 (gaokao.chsi.com.cn)\n")
                            f.write("=" * 60 + "\n\n")
                            f.write(segment)

                    uni_segments += len(segments)
                    print(f"    已保存 {len(segments)} 段 ({len(text)} 字符)")

                if uni_segments > 0:
                    stats["success"] += 1
                    stats["segments"] += uni_segments
                    existing.add(safe)
                else:
                    stats["failed"] += 1
                    failed.append({"schId": sch_id, "name": name, "reason": "无有效内容"})

            except Exception as e:
                stats["failed"] += 1
                failed.append({"schId": sch_id, "name": name, "reason": str(e)})
                print(f"  ❌ {e}")

            # 进度
            if (i + 1) % 10 == 0:
                print(f"\n[进度] {i+1}/{len(schools)}: 成功{stats['success']}, "
                      f"跳过{stats['no_2026']}, 失败{stats['failed']}")

            await page.wait_for_timeout(2000)

        await browser.close()

    # 保存清单
    for filename, data in [("skipped_schools.json", skipped),
                            ("failed_schools.json", failed)]:
        path = DATA_DIR / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 抓取完成: 成功{stats['success']}, 跳过{stats['no_2026']}, "
          f"失败{stats['failed']}, 总段数{stats['segments']}")


# ── Main ───────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Playwright 章程抓取")
    parser.add_argument("--step", type=int, action="append",
                        choices=[1, 2], help="执行步骤")
    parser.add_argument("--limit", type=int, default=0, help="限制抓取数量")
    args = parser.parse_args()

    if not args.step:
        args.step = [1]

    if 1 in args.step:
        schools = await fetch_school_list()
    else:
        list_path = DATA_DIR / "school_list.json"
        if list_path.exists():
            with open(list_path, "r", encoding="utf-8") as f:
                schools = json.load(f)
            print(f"[Step 2] 加载 {len(schools)} 所高校")
        else:
            print("❌ school_list.json 不存在")
            return

    if 2 in args.step:
        await fetch_charters(schools, limit=args.limit)


if __name__ == "__main__":
    asyncio.run(main())
