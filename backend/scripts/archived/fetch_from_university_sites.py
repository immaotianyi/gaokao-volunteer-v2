#!/usr/bin/env python3
"""
从各大学官方网站抓取 2026 年招生章程

策略:
  1. 从 school_list.json 读取高校列表
  2. 对每所高校，尝试搜索其官网的招生章程页面
  3. 搜索关键词: "2026年招生章程" "2026招生章程" site:{大学域名}
  4. 下载章程全文，分段存储到 zszc/

用法:
  python scripts/fetch_from_university_sites.py --limit 20
"""
import os
import re
import sys
import json
import time
import argparse
from pathlib import Path
from urllib.parse import urljoin, quote

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ZSZC_DIR = DATA_DIR / "zszc"
ZSZC_DIR.mkdir(parents=True, exist_ok=True)

MAX_SEGMENT_LENGTH = 1000
OVERLAP_LENGTH = 100
REQUEST_DELAY = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 大学名称 → 官网域名映射
UNI_DOMAINS = {
    "北京大学": "pku.edu.cn",
    "清华大学": "tsinghua.edu.cn",
    "复旦大学": "fudan.edu.cn",
    "上海交通大学": "sjtu.edu.cn",
    "浙江大学": "zju.edu.cn",
    "南京大学": "nju.edu.cn",
    "武汉大学": "whu.edu.cn",
    "华中科技大学": "hust.edu.cn",
    "中山大学": "sysu.edu.cn",
    "华南理工大学": "scut.edu.cn",
    "四川大学": "scu.edu.cn",
    "西安交通大学": "xjtu.edu.cn",
    "哈尔滨工业大学": "hit.edu.cn",
    "中国科学技术大学": "ustc.edu.cn",
    "中国人民大学": "ruc.edu.cn",
    "北京师范大学": "bnu.edu.cn",
    "南开大学": "nankai.edu.cn",
    "天津大学": "tju.edu.cn",
    "东南大学": "seu.edu.cn",
    "厦门大学": "xmu.edu.cn",
    "山东大学": "sdu.edu.cn",
    "吉林大学": "jlu.edu.cn",
    "同济大学": "tongji.edu.cn",
    "北京航空航天大学": "buaa.edu.cn",
    "北京理工大学": "bit.edu.cn",
    "中国农业大学": "cau.edu.cn",
    "华东师范大学": "ecnu.edu.cn",
    "大连理工大学": "dlut.edu.cn",
    "电子科技大学": "uestc.edu.cn",
    "中南大学": "csu.edu.cn",
    "西北工业大学": "nwpu.edu.cn",
    "重庆大学": "cqu.edu.cn",
    "兰州大学": "lzu.edu.cn",
    "华南师范大学": "scnu.edu.cn",
    "暨南大学": "jnu.edu.cn",
    "深圳大学": "szu.edu.cn",
    "南方科技大学": "sustech.edu.cn",
    "华南农业大学": "scau.edu.cn",
    "广东工业大学": "gdut.edu.cn",
    "广州大学": "gzhu.edu.cn",
    "南方医科大学": "smu.edu.cn",
    "广州中医药大学": "gzucm.edu.cn",
    "广东外语外贸大学": "gdufs.edu.cn",
    "广东财经大学": "gdufe.edu.cn",
    "广东海洋大学": "gdou.edu.cn",
    "汕头大学": "stu.edu.cn",
    "五邑大学": "wyu.edu.cn",
    "中国政法大学": "cupl.edu.cn",
    "中央财经大学": "cufe.edu.cn",
    "对外经济贸易大学": "uibe.edu.cn",
    "北京邮电大学": "bupt.edu.cn",
    "北京交通大学": "bjtu.edu.cn",
    "北京科技大学": "ustb.edu.cn",
    "中国地质大学（武汉）": "cug.edu.cn",
    "中国石油大学（华东）": "upc.edu.cn",
    "中国矿业大学": "cumt.edu.cn",
    "河海大学": "hhu.edu.cn",
    "江南大学": "jiangnan.edu.cn",
    "南京农业大学": "njau.edu.cn",
    "南京理工大学": "njust.edu.cn",
    "南京航空航天大学": "nuaa.edu.cn",
    "苏州大学": "suda.edu.cn",
    "上海大学": "shu.edu.cn",
    "华东理工大学": "ecust.edu.cn",
    "东华大学": "dhu.edu.cn",
    "上海外国语大学": "shisu.edu.cn",
    "上海财经大学": "sufe.edu.cn",
    "合肥工业大学": "hfut.edu.cn",
    "福州大学": "fzu.edu.cn",
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
    "宁夏大学": "nxu.edu.cn",
    "青海大学": "qhu.edu.cn",
    "新疆大学": "xju.edu.cn",
    "石河子大学": "shzu.edu.cn",
    "西藏大学": "utibet.edu.cn",
    "延边大学": "ybu.edu.cn",
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
    "中央音乐学院": "ccom.edu.cn",
    "中央美术学院": "cafa.edu.cn",
    "北京体育大学": "bsu.edu.cn",
    "中国药科大学": "cpu.edu.cn",
    "中国石油大学（北京）": "cup.edu.cn",
    "中国地质大学（北京）": "cugb.edu.cn",
    "中国矿业大学（北京）": "cumtb.edu.cn",
    "华北电力大学（保定）": "ncepu.edu.cn",
    "华中农业大学": "hzau.edu.cn",
    "华中师范大学": "ccnu.edu.cn",
    "武汉理工大学": "whut.edu.cn",
    "湖北大学": "hubu.edu.cn",
    "武汉科技大学": "wust.edu.cn",
    "武汉工程大学": "wit.edu.cn",
    "三峡大学": "ctgu.edu.cn",
    "长江大学": "yangtzeu.edu.cn",
    "西南石油大学": "swpu.edu.cn",
    "成都理工大学": "cdut.edu.cn",
    "西南财经大学": "swufe.edu.cn",
    "四川农业大学": "sicau.edu.cn",
    "华侨大学": "hqu.edu.cn",
    "集美大学": "jmu.edu.cn",
    "湘潭大学": "xtu.edu.cn",
}


def clean_html(html_text: str) -> str:
    text = re.sub(r'<script[^>]*>.*?</script>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
    text = text.replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'")
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()


def segment_text(text: str) -> list:
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
        while j < len(sentences) and len(segment) + len(sentences[j]) <= MAX_SEGMENT_LENGTH:
            segment += sentences[j]
            j += 1
        if not segment:
            sentence = sentences[i]
            for k in range(0, len(sentence), MAX_SEGMENT_LENGTH - OVERLAP_LENGTH):
                chunk = sentence[k:k + MAX_SEGMENT_LENGTH]
                if chunk.strip():
                    segments.append(chunk.strip())
            i += 1
            continue
        segments.append(segment.strip())
        if j > i + 1:
            overlap_chars = 0
            new_i = j - 1
            while new_i > i and overlap_chars < OVERLAP_LENGTH:
                overlap_chars += len(sentences[new_i])
                new_i -= 1
            i = new_i + 1 if new_i > i else i + 1
        else:
            i = j
    return segments


def safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', name)


def search_university_zszc(name: str, domain: str) -> str | None:
    """搜索某大学官网的 2026 招生章程"""
    # 尝试常见的招生章程 URL 模式（按优先级排序）
    patterns = [
        f"https://zsb.{domain}",       # 招生办子域名
        f"https://zhaosheng.{domain}",
        f"https://admission.{domain}",
        f"https://zs.{domain}",
        f"https://www.{domain}/zs",
        f"https://www.{domain}/zhaosheng",
        f"https://www.{domain}/bkszs",
        f"https://www.{domain}/zsb",
    ]

    for base_url in patterns:
        try:
            resp = requests.get(base_url, headers=HEADERS, timeout=15, allow_redirects=True)
            if resp.status_code == 200:
                html = resp.text
                soup = BeautifulSoup(html, 'html.parser')
                
                # 搜索包含 "2026"+"招生章程" 的链接
                for a in soup.find_all('a', href=True):
                    text = a.get_text(strip=True)
                    if re.search(r'2026.*招生章程|招生章程.*2026', text):
                        href = a['href']
                        full_url = urljoin(resp.url, href)
                        return full_url
                
                # 宽松匹配: 标题中包含 "招生章程" 且页面有 "2026"
                for a in soup.find_all('a', href=True):
                    text = a.get_text(strip=True)
                    href = a.get('href', '')
                    if '招生章程' in text and '2026' in (text + href):
                        full_url = urljoin(resp.url, href)
                        return full_url

                # 检查当前页面是否就是章程页
                if '2026' in html and '招生章程' in html and len(html) > 5000:
                    # 可能是章程详情页
                    page_text = clean_html(html)
                    if '招生章程' in page_text[:200] or '第一章' in page_text[:500]:
                        return resp.url

        except Exception:
            continue

    # 最后尝试：直接搜索首页
    try:
        home_url = f"https://www.{domain}"
        resp = requests.get(home_url, headers=HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                text = a.get_text(strip=True)
                href = a.get('href', '')
                if ('招生' in text or '招生' in href) and ('章程' in text or '章程' in href):
                    full_url = urljoin(resp.url, href)
                    return full_url
    except Exception:
        pass

    return None


def download_chapter(url: str, university_name: str) -> int:
    """下载章程全文并分段保存"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            return 0

        # 自动检测编码
        resp.encoding = resp.apparent_encoding or 'utf-8'

        text = clean_html(resp.text)
        if len(text) < 200:
            return 0

        # 找正文起始
        for marker in ["招生章程", "第一章", "第一条", "总则"]:
            idx = text.find(marker)
            if idx != -1:
                text = text[idx:]
                break

        segments = segment_text(text)
        safe_name = safe_filename(university_name)

        for i, segment in enumerate(segments):
            filename = f"{safe_name}_2026招生章程_第{i+1}段.txt"
            filepath = ZSZC_DIR / filename
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"大学名称：{university_name}\n")
                f.write(f"年份：2026年\n")
                f.write(f"段落编号：{i+1}/{len(segments)}\n")
                f.write(f"数据来源：{university_name}官方网站\n")
                f.write("=" * 60 + "\n\n")
                f.write(segment)

        return len(segments)

    except Exception as e:
        print(f"    下载失败: {e}")
        return 0


def main():
    parser = argparse.ArgumentParser(description="从大学官网抓取招生章程")
    parser.add_argument("--limit", "-n", type=int, default=0, help="限制数量")
    parser.add_argument("--university", "-u", help="指定大学名称")
    args = parser.parse_args()

    # 获取已抓取大学
    existing = set()
    for f in ZSZC_DIR.glob("*_2026招生章程_*.txt"):
        name = f.stem.split('_2026')[0]
        existing.add(name)

    print(f"已抓取: {len(existing)} 所")

    # 确定目标大学
    if args.university:
        targets = [(args.university, UNI_DOMAINS.get(args.university, ""))]
    else:
        targets = [(name, domain) for name, domain in UNI_DOMAINS.items()
                   if safe_filename(name) not in existing]

    if args.limit > 0:
        targets = targets[:args.limit]

    print(f"待抓取: {len(targets)} 所")

    stats = {"total": len(targets), "success": 0, "failed": 0, "segments": 0}

    for i, (name, domain) in enumerate(targets):
        if not domain:
            continue

        print(f"\n[{i+1}/{len(targets)}] {name} ({domain})")

        try:
            url = search_university_zszc(name, domain)
            if not url:
                print(f"  ⚠️ 未找到章程URL")
                stats["failed"] += 1
                continue

            print(f"  找到: {url[:80]}...")
            segments = download_chapter(url, name)

            if segments > 0:
                stats["success"] += 1
                stats["segments"] += segments
                print(f"  ✅ 保存 {segments} 段")
            else:
                stats["failed"] += 1
                print(f"  ❌ 下载失败")

        except Exception as e:
            stats["failed"] += 1
            print(f"  ❌ {e}")

        time.sleep(REQUEST_DELAY)

    print(f"\n✅ 完成: 成功{stats['success']}, 失败{stats['failed']}, "
          f"总段数{stats['segments']}")


if __name__ == "__main__":
    main()
