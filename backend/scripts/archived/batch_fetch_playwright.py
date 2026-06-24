#!/usr/bin/env python3
"""
Playwright 批量抓取 — 从各大学招生网站搜索2026章程

用法:
  python scripts/batch_fetch_playwright.py --limit 30
"""
import asyncio, re, time, json, argparse
from pathlib import Path
from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ZSZC_DIR = DATA_DIR / "zszc"
ZSZC_DIR.mkdir(parents=True, exist_ok=True)

# 大学名 → 官网域名
UNI_DOMAINS = {
    "复旦大学": "fudan.edu.cn",
    "浙江大学": "zju.edu.cn",
    "南京大学": "nju.edu.cn",
    "四川大学": "scu.edu.cn",
    "哈尔滨工业大学": "hit.edu.cn",
    "中国科学技术大学": "ustc.edu.cn",
    "中国人民大学": "ruc.edu.cn",
    "北京师范大学": "bnu.edu.cn",
    "天津大学": "tju.edu.cn",
    "东南大学": "seu.edu.cn",
    "山东大学": "sdu.edu.cn",
    "同济大学": "tongji.edu.cn",
    "北京航空航天大学": "buaa.edu.cn",
    "中国农业大学": "cau.edu.cn",
    "华东师范大学": "ecnu.edu.cn",
    "大连理工大学": "dlut.edu.cn",
    "中南大学": "csu.edu.cn",
    "西北工业大学": "nwpu.edu.cn",
    "重庆大学": "cqu.edu.cn",
    "兰州大学": "lzu.edu.cn",
    "南方科技大学": "sustech.edu.cn",
    "中央财经大学": "cufe.edu.cn",
    "对外经济贸易大学": "uibe.edu.cn",
    "北京交通大学": "bjtu.edu.cn",
    "北京科技大学": "ustb.edu.cn",
    "中国石油大学（华东）": "upc.edu.cn",
    "中国矿业大学": "cumt.edu.cn",
    "河海大学": "hhu.edu.cn",
    "江南大学": "jiangnan.edu.cn",
    "南京农业大学": "njau.edu.cn",
    "南京航空航天大学": "nuaa.edu.cn",
    "苏州大学": "suda.edu.cn",
    "上海大学": "shu.edu.cn",
    "华东理工大学": "ecust.edu.cn",
    "东华大学": "dhu.edu.cn",
    "上海外国语大学": "shisu.edu.cn",
    "上海财经大学": "sufe.edu.cn",
    "合肥工业大学": "hfut.edu.cn",
    "郑州大学": "zzu.edu.cn",
    "湖南大学": "hnu.edu.cn",
    "中南财经政法大学": "zuel.edu.cn",
    "西南交通大学": "swjtu.edu.cn",
    "西南大学": "swu.edu.cn",
    "云南大学": "ynu.edu.cn",
    "西北大学": "nwu.edu.cn",
    "陕西师范大学": "snnu.edu.cn",
    "长安大学": "chd.edu.cn",
    "西北农林科技大学": "nwafu.edu.cn",
    "南昌大学": "ncu.edu.cn",
    "广西大学": "gxu.edu.cn",
    "贵州大学": "gzu.edu.cn",
    "海南大学": "hainanu.edu.cn",
    "东北大学": "neu.edu.cn",
    "辽宁大学": "lnu.edu.cn",
    "大连海事大学": "dlmu.edu.cn",
    "东北师范大学": "nenu.edu.cn",
    "东北林业大学": "nefu.edu.cn",
    "东北农业大学": "neau.edu.cn",
    "哈尔滨工程大学": "hrbeu.edu.cn",
    "太原理工大学": "tyut.edu.cn",
    "内蒙古大学": "imu.edu.cn",
    "河北工业大学": "hebut.edu.cn",
    "华北电力大学": "ncepu.edu.cn",
    "北京工业大学": "bjut.edu.cn",
    "北京化工大学": "buct.edu.cn",
    "北京林业大学": "bjfu.edu.cn",
    "北京中医药大学": "bucm.edu.cn",
    "北京外国语大学": "bfsu.edu.cn",
    "中国传媒大学": "cuc.edu.cn",
    "中央民族大学": "muc.edu.cn",
    "北京体育大学": "bsu.edu.cn",
    "中国药科大学": "cpu.edu.cn",
    "中国石油大学（北京）": "cup.edu.cn",
    "中国地质大学（北京）": "cugb.edu.cn",
    "武汉理工大学": "whut.edu.cn",
    "湘潭大学": "xtu.edu.cn",
    "南京理工大学": "njust.edu.cn",
    "南京邮电大学": "njupt.edu.cn",
    "南京信息工程大学": "nuist.edu.cn",
    "南京医科大学": "njmu.edu.cn",
    "南京中医药大学": "njucm.edu.cn",
    "南京师范大学": "njnu.edu.cn",
    "扬州大学": "yzu.edu.cn",
    "杭州电子科技大学": "hdu.edu.cn",
    "浙江工业大学": "zjut.edu.cn",
    "宁波大学": "nbu.edu.cn",
    "安徽大学": "ahu.edu.cn",
    "福州大学": "fzu.edu.cn",
}


def safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', name)


async def find_and_download(name: str, domain: str, page) -> bool:
    """探测一个大学的招生网站并下载2026章程"""
    # 可能的招生网站URL
    zs_urls = [
        f"https://zsb.{domain}",
        f"https://zs.{domain}",
        f"https://zhaosheng.{domain}",
        f"https://admission.{domain}",
        f"https://bkzs.{domain}",
        f"https://www.{domain}/zs",
        f"https://www.{domain}/zhaosheng",
        f"https://www.{domain}/bkszs",
    ]

    found_url = None

    for zs_url in zs_urls:
        try:
            resp = await page.goto(zs_url, wait_until="domcontentloaded", timeout=12000)
            if resp and resp.status == 200:
                await page.wait_for_timeout(2000)

                # 找2026章程链接
                links = await page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('a')).map(a => ({
                        text: a.innerText.trim(),
                        href: a.href
                    }));
                }""")

                for l in links:
                    t = l["text"]
                    if ("2026" in t and ("章程" in t or "招生" in t)) or \
                       ("章程" in t and "2026" in l.get("href", "")):
                        # 优先选"招生章程"
                        if "招生章程" in t and "2026" in t:
                            found_url = l["href"]
                            break
                        elif found_url is None:
                            found_url = l["href"]

                if found_url:
                    break

                # 如果没找到直接链接，看看页面本身是不是章程页
                html = await page.content()
                if "2026" in html and "招生章程" in html and len(html) > 5000:
                    page_text = await page.evaluate("() => document.body.innerText")
                    if "招生章程" in page_text[:300] or "第一章" in page_text[:500]:
                        found_url = zs_url
                        break
        except Exception:
            continue

    if not found_url:
        # 尝试直接搜索首页
        try:
            await page.goto(f"https://www.{domain}", wait_until="domcontentloaded", timeout=12000)
            await page.wait_for_timeout(2000)
            links = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a')).map(a => ({
                    text: a.innerText.trim(),
                    href: a.href
                }));
            }""")
            for l in links:
                t = l["text"]
                if "招生" in t and ("章程" in t or "2026" in t):
                    found_url = l["href"]
                    break
        except Exception:
            pass

    if not found_url:
        return False

    # 下载章程内容
    try:
        await page.goto(found_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)

        text = await page.evaluate("() => document.body.innerText")
        text = re.sub(r"\s+", " ", text)

        if len(text) < 300:
            return False

        # 确认是章程
        if "招生章程" not in text[:1000] and "第一章" not in text[:500]:
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
                f.write(f"数据来源：{name}招生网站\n")
                f.write("=" * 60 + "\n\n" + seg)

        return True
    except Exception:
        return False


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", "-n", type=int, default=30, help="限制数量")
    args = parser.parse_args()

    # 获取已抓取大学
    existing = set()
    for f in ZSZC_DIR.glob("*招生章程_*.txt"):
        name = f.stem
        for s in ["_2026招生章程", "_2025招生章程"]:
            if s in name:
                name = name.replace(s, "")
                break
        name = re.sub(r"_第\d+段$", "", name)
        existing.add(name)

    targets = [(n, d) for n, d in UNI_DOMAINS.items() if safe_name(n) not in existing]
    if args.limit:
        targets = targets[:args.limit]

    print(f"已抓取: {len(existing)} 所")
    print(f"待抓取: {len(targets)} 所\n")

    stats = {"success": 0, "failed": 0, "total": len(targets)}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
            locale="zh-CN",
            ignore_https_errors=True,
        )
        page = await context.new_page()

        for i, (name, domain) in enumerate(targets):
            print(f"[{i+1}/{len(targets)}] {name} ({domain}) ...", end=" ", flush=True)

            try:
                ok = await find_and_download(name, domain, page)
                if ok:
                    stats["success"] += 1
                    print("✅")
                else:
                    stats["failed"] += 1
                    print("❌ 未找到")
            except Exception as e:
                stats["failed"] += 1
                print(f"❌ {type(e).__name__}")

            if (i + 1) % 10 == 0:
                print(f"  [进度] 成功{stats['success']}, 失败{stats['failed']}")

            await page.wait_for_timeout(2000)

        await browser.close()

    print(f"\n✅ 完成: 成功{stats['success']}, 失败{stats['failed']}")
    print(f"当前章程覆盖: {len(existing) + stats['success']} 所")


if __name__ == "__main__":
    asyncio.run(main())
