#!/usr/bin/env python3
"""甘肃数据下载脚本 - 下载2025/2026一分一段表 + 控制线 + 探查投档线"""
import os
import re
import requests
from bs4 import BeautifulSoup

RAW_DIR = '/Users/sanzhaibanniang/Claude/Projects/gaokao/backend/data/raw/gansu_2026'
os.makedirs(RAW_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def download(url, filename):
    out = os.path.join(RAW_DIR, filename)
    if os.path.exists(out) and os.path.getsize(out) > 5000:
        print(f'[SKIP] {filename} 已存在 ({os.path.getsize(out)} bytes)')
        return out
    try:
        r = requests.get(url, headers=HEADERS, timeout=30, verify=False)
        r.raise_for_status()
        with open(out, 'wb') as f:
            f.write(r.content)
        print(f'[OK] {filename} ({len(r.content)} bytes) <- {url}')
        return out
    except Exception as e:
        print(f'[FAIL] {filename}: {e} <- {url}')
        return None


# === Step 1: 下载2025年一分一段表（eol.cn 历史类 + 物理类） ===
print('\n=== 下载2025年一分一段表 ===')
# eol.cn 历史类
download('https://gaokao.eol.cn/gan_su/dongtai/202507/t20250702_2678473.shtml', 'gansu_yifenyiduan_2025_eol_history.html')
# eol.cn 物理类 - 尝试相邻URL
download('https://gaokao.eol.cn/gan_su/dongtai/202507/t20250702_2678472.shtml', 'gansu_yifenyiduan_2025_eol_physics.html')
# hfplg.com 完整版（物理+历史）
download('https://m.hfplg.com/yfyd/35c7027890.html', 'gansu_yifenyiduan_2025_hfplg.html')

# === Step 2: 尝试ganseea 2026年一分一段表的可能URL（公告ID 1900-1920） ===
print('\n=== 尝试ganseea 2026年一分一段表可能URL ===')
for aid in range(1907, 1925):
    url = f'https://www.ganseea.cn/gaokaogaozhao/{aid}.html'
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False, allow_redirects=True)
        if r.status_code == 200 and ('分段' in r.text or '一分一段' in r.text or '成绩分段' in r.text):
            # 提取标题
            m = re.search(r'<title>([^<]+)</title>', r.text)
            title = m.group(1) if m else 'unknown'
            out = os.path.join(RAW_DIR, f'gansu_yifenyiduan_2026_aid{aid}.html')
            with open(out, 'wb') as f:
                f.write(r.content)
            print(f'[OK] aid={aid} {title} -> {out}')
            break
    except Exception as e:
        pass

# === Step 3: 尝试ganseea 2025年一分一段表的可能URL（公告ID 1400-1500） ===
print('\n=== 尝试ganseea 2025年一分一段表可能URL ===')
found_2025 = False
for aid in range(1400, 1500):
    url = f'https://www.ganseea.cn/gaokaogaozhao/{aid}.html'
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False, allow_redirects=True)
        if r.status_code == 200 and ('分段' in r.text or '一分一段' in r.text or '成绩分段' in r.text):
            m = re.search(r'<title>([^<]+)</title>', r.text)
            title = m.group(1) if m else 'unknown'
            out = os.path.join(RAW_DIR, f'gansu_yifenyiduan_2025_aid{aid}.html')
            with open(out, 'wb') as f:
                f.write(r.content)
            print(f'[OK] aid={aid} {title} -> {out}')
            found_2025 = True
            break
    except Exception as e:
        pass
    # 限制扫描数量，避免太慢
    if aid > 1420:
        break

# === Step 4: 解析已下载的2025年数据 ===
print('\n=== 解析2025年一分一段表 ===')
for fname in ['gansu_yifenyiduan_2025_eol_history.html', 'gansu_yifenyiduan_2025_eol_physics.html', 'gansu_yifenyiduan_2025_hfplg.html']:
    path = os.path.join(RAW_DIR, fname)
    if not os.path.exists(path):
        continue
    html = open(path, encoding='utf-8', errors='ignore').read()
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')
    print(f'\n{fname}: {len(tables)} tables')
    for i, t in enumerate(tables):
        rows = t.find_all('tr')
        print(f'  table {i}: {len(rows)} rows')
        for r in rows[:3]:
            cells = [td.get_text(strip=True) for td in r.find_all(['td', 'th'])][:6]
            print('   ', cells)
        if len(rows) > 2:
            last = rows[-1]
            cells = [td.get_text(strip=True) for td in last.find_all(['td', 'th'])][:6]
            print('   LAST:', cells)

print('\n=== 完成 ===')
print('已下载文件:')
for f in sorted(os.listdir(RAW_DIR)):
    print(f'  {f} ({os.path.getsize(os.path.join(RAW_DIR, f))} bytes)')
