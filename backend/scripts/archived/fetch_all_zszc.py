#!/usr/bin/env python3
"""
全国本科高校2026年招生章程全量抓取脚本 (V2增强版)

功能:
  Step 1: 从阳光高考平台获取全国本科高校列表 → school_list.json
  Step 2: 批量抓取每所高校的2026年招生章程全文 → zszc/*.txt

数据来源: 教育部阳光高考平台 (gaokao.chsi.com.cn)

用法:
  python scripts/fetch_all_zszc.py --step 1          # 仅获取高校列表
  python scripts/fetch_all_zszc.py --step 2          # 仅抓取章程
  python scripts/fetch_all_zszc.py --step 1 --step 2 # 全流程
  python scripts/fetch_all_zszc.py --resume          # 断点续传

"""
import requests
import re
import os
import sys
import time
import json
import argparse
from pathlib import Path
from urllib.parse import urljoin

# ── 配置 ───────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ZSZC_DIR = DATA_DIR / "zszc"
ZSZC_DIR.mkdir(parents=True, exist_ok=True)

MAX_SEGMENT_LENGTH = 1000
OVERLAP_LENGTH = 100
REQUEST_DELAY = 2.0  # 秒
MAX_RETRIES = 3
RETRY_WAIT = 30  # 403/503 时等待秒数
BATCH_SIZE = 200  # 每批请求数
BATCH_REST = 300  # 批次间休息秒数 (5分钟)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "Referer": "https://gaokao.chsi.com.cn/",
}

# URL 模板
INDEX_URL = "https://gaokao.chsi.com.cn/zsgs/zhangcheng/listVerifedZszc.do"
PAGE_URL = "https://gaokao.chsi.com.cn/zsgs/zhangcheng/listVerifedZszc.do?page={page}"
SCHOOL_ZC_LIST_URL = "https://gaokao.chsi.com.cn/zsgs/zhangcheng/listZszc--schId-{schId}.dhtml"
ZC_DETAIL_URL = "https://gaokao.chsi.com.cn/zsgs/zhangcheng/listVerifedZszc--method-view,schId-{schId},infoId-{infoId}.dhtml"


# ── 工具函数 ──────────────────────────────────────────────────

def safe_filename(name: str) -> str:
    """清理文件名中的非法字符，保留中文括号"""
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    return name


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
    """按句子分段，最大长度 max_len，重叠 overlap"""
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


def http_get(url: str, timeout: int = 30) -> requests.Response:
    """带重试的 HTTP GET 请求"""
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 200:
                resp.encoding = 'utf-8'
                return resp
            elif resp.status_code == 403:
                print(f"    ⚠️ 403 Forbidden, 等待 {RETRY_WAIT}s 后重试...")
                time.sleep(RETRY_WAIT)
            elif resp.status_code == 503:
                print(f"    ⚠️ 503 Service Unavailable, 等待 {RETRY_WAIT*2}s 后重试...")
                time.sleep(RETRY_WAIT * 2)
            else:
                print(f"    ⚠️ HTTP {resp.status_code}, 重试 {attempt+1}/{MAX_RETRIES}")
                time.sleep(5)
        except requests.Timeout:
            print(f"    ⚠️ 超时, 重试 {attempt+1}/{MAX_RETRIES}")
            time.sleep(10)
        except Exception as e:
            last_error = e
            print(f"    ⚠️ 请求异常: {e}, 重试 {attempt+1}/{MAX_RETRIES}")
            time.sleep(10)

    raise last_error or Exception(f"请求失败: {url}")


# ── Step 1: 获取全国高校列表 ─────────────────────────────────

def fetch_school_list_from_index() -> list[dict]:
    """从阳光高考首页分页获取全部高校列表"""
    schools = []
    seen_names = set()

    # 先获取第一页，确认分页机制
    print("[Step 1] 获取高校列表首页...")
    try:
        resp = http_get(INDEX_URL, timeout=30)
    except Exception as e:
        print(f"[Step 1] ❌ 无法访问首页: {e}")
        print("[Step 1] 尝试备用方案：手动 schId 范围扫描...")
        return _fallback_school_list()

    html = resp.text

    # 提取总页数
    total_pages = 1
    page_patterns = [
        r'共\s*(\d+)\s*页',
        r'/(\d+)\s*页',
        r'pageCount["\']?\s*[:=]\s*(\d+)',
        r'pagecount\s*=\s*(\d+)',
        r'totalPages["\']?\s*[:=]\s*(\d+)',
        r'共(\d+)页',
        r'pageno=(\d+)[^>]*>末页',
    ]
    for pattern in page_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            total_pages = int(match.group(1))
            print(f"[Step 1] 检测到总页数: {total_pages}")
            break

    if total_pages == 1:
        # 检查是否有翻页链接
        page_links = re.findall(r'[?&]page=(\d+)', html)
        if page_links:
            total_pages = max(int(p) for p in page_links)
            print(f"[Step 1] 从翻页链接推断总页数: {total_pages}")

    # 如果还是1页，尝试手动翻页探测
    if total_pages == 1:
        for test_page in [2, 3]:
            try:
                test_url = PAGE_URL.format(page=test_page)
                resp_test = http_get(test_url, timeout=30)
                if resp_test.status_code == 200 and len(resp_test.text) > 500:
                    # 有内容，继续探测
                    print(f"[Step 1] 第{test_page}页有内容，继续探测...")
                else:
                    total_pages = test_page - 1
                    break
            except Exception:
                total_pages = test_page - 1
                break
        else:
            # 探测到至少3页以上
            total_pages = 999  # 标记未知，后续动态判断

    print(f"[Step 1] 开始遍历 {total_pages if total_pages < 999 else '未知'} 页...")

    page = 1
    empty_pages = 0
    while page <= (total_pages if total_pages < 999 else 1000):
        if page == 1:
            page_html = html
        else:
            url = PAGE_URL.format(page=page)
            try:
                resp = http_get(url, timeout=30)
                page_html = resp.text
            except Exception as e:
                print(f"[Step 1] 第{page}页获取失败: {e}, 跳过")
                page += 1
                continue

        # 提取 schId 和学校名称
        patterns = [
            r'schId-(\d+)\.dhtml[^>]*>([^<]+)</a>',
            r'viewZszc[^>]*schId=(\d+)[^>]*>([^<]+)</a>',
            r'schId["\']?\s*[:=]\s*(\d+)[^>]*>([^<]+)</a>',
        ]
        found_any = False
        for pattern in patterns:
            matches = re.findall(pattern, page_html)
            if matches:
                for sch_id, name in matches:
                    name = name.strip()
                    if name and name not in seen_names:
                        seen_names.add(name)
                        schools.append({"schId": sch_id, "name": name})
                        found_any = True
                if found_any:
                    break

        if not found_any:
            empty_pages += 1
            if empty_pages >= 3:
                print(f"[Step 1] 连续{empty_pages}页无内容，停止翻页")
                break
        else:
            empty_pages = 0
            print(f"[Step 1] 第{page}页: 获取到 {len(schools)} 所高校 (累计)")

        page += 1
        time.sleep(REQUEST_DELAY / 2)  # 列表页间隔短一点

    print(f"[Step 1] ✅ 共获取 {len(schools)} 所高校")

    # 保存
    output_path = DATA_DIR / "school_list.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schools, f, ensure_ascii=False, indent=2)
    print(f"[Step 1] 已保存到: {output_path}")

    return schools


def _fallback_school_list() -> list[dict]:
    """备用方案：手动扫描 schId 范围"""
    print("[备用] 扫描 schId 1-3000...")
    schools = []
    seen = set()

    for sch_id in range(1, 3001):
        try:
            url = SCHOOL_ZC_LIST_URL.format(schId=sch_id)
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                # 尝试提取学校名称
                title_match = re.search(r'<title>([^-]+)', resp.text)
                if title_match:
                    name = title_match.group(1).strip()
                    # 过滤明显非学校名称
                    if len(name) >= 4 and '大学' in name or '学院' in name:
                        if name not in seen:
                            seen.add(name)
                            schools.append({"schId": str(sch_id), "name": name})
                            if len(schools) % 100 == 0:
                                print(f"  [备用] 已发现 {len(schools)} 所高校 (schId={sch_id})")
        except Exception:
            pass

        if sch_id % 50 == 0:
            time.sleep(REQUEST_DELAY)

    print(f"[备用] ✅ 共获取 {len(schools)} 所高校")
    output_path = DATA_DIR / "school_list.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schools, f, ensure_ascii=False, indent=2)
    return schools


# ── Step 2: 批量抓取章程 ──────────────────────────────────────

def fetch_zc_info_ids(sch_id: str) -> list[dict]:
    """获取某大学的招生章程 infoId 列表"""
    results = []
    try:
        url = SCHOOL_ZC_LIST_URL.format(schId=sch_id)
        resp = http_get(url, timeout=30)
        html = resp.text

        patterns = [
            r'infoId-(\d+)\.dhtml[^>]*>([^<]*招生章程[^<]*)</a>',
            r'infoId=(\d+)[^>]*>([^<]*章程[^<]*)</a>',
            r'view[^>]*infoId=(\d+)[^>]*>([^<]*章程[^<]*)</a>',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, html)
            if matches:
                for info_id, title in matches:
                    year_match = re.search(r'(20\d{2})', title)
                    year = year_match.group(1) if year_match else "unknown"
                    results.append({
                        "infoId": info_id,
                        "year": year,
                        "title": title.strip()
                    })
                break

    except Exception as e:
        print(f"  ⚠️ 获取 schId={sch_id} 章程列表失败: {e}")

    return results


def fetch_zc_content(sch_id: str, info_id: str) -> str:
    """获取招生章程详细内容"""
    try:
        url = ZC_DETAIL_URL.format(schId=sch_id, infoId=info_id)
        resp = http_get(url, timeout=30)
        html = resp.text
        text = clean_html(html)

        # 找到章程正文起始位置
        for marker in ["招生章程", "第一章", "第一条", "总则"]:
            idx = text.find(marker)
            if idx != -1:
                text = text[idx:]
                break

        return text
    except Exception as e:
        print(f"  ⚠️ 获取 schId={sch_id}, infoId={info_id} 内容失败: {e}")
        return None


def save_segments(university_name: str, year: str,
                  segments: list, output_dir: Path) -> int:
    """保存分段文本"""
    safe_name = safe_filename(university_name)

    for i, segment in enumerate(segments):
        filename = f"{safe_name}_{year}招生章程_第{i+1}段.txt"
        filepath = output_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"大学名称：{university_name}\n")
            f.write(f"年份：{year}年\n")
            f.write(f"段落编号：{i+1}/{len(segments)}\n")
            f.write(f"数据来源：教育部阳光高考平台 (gaokao.chsi.com.cn)\n")
            f.write("=" * 60 + "\n\n")
            f.write(segment)

    return len(segments)


def get_existing_universities(zszc_dir: Path) -> set:
    """获取已抓取的大学名称集合（断点续传）"""
    existing = set()
    if not zszc_dir.exists():
        return existing
    for f in zszc_dir.glob("*_2026招生章程_*.txt"):
        name = f.stem.split('_2026')[0]
        if name:
            existing.add(name)
    return existing


def fetch_all_charters(schools: list[dict], resume: bool = True):
    """批量抓取所有高校的2026年招生章程"""
    zszc_dir = ZSZC_DIR
    skipped = []
    failed = []
    stats = {"total": len(schools), "success": 0, "skipped": 0,
             "failed": 0, "no_2026": 0, "segments": 0}

    existing_unis = get_existing_universities(zszc_dir) if resume else set()
    if existing_unis:
        print(f"[Step 2] 断点续传: 已抓取 {len(existing_unis)} 所大学")

    batch_count = 0

    for i, school in enumerate(schools):
        sch_id = school.get("schId", "")
        name = school.get("name", f"schId_{sch_id}")

        # 断点续传：跳过已抓取的
        if resume and name in existing_unis:
            if (i + 1) % 100 == 0:
                print(f"  [{i+1}/{stats['total']}] 跳过已抓取: {name}")
            continue

        # 速率控制
        batch_count += 1
        if batch_count >= BATCH_SIZE:
            print(f"\n[Step 2] 已处理 {batch_count} 个请求，休眠 {BATCH_REST}s...")
            time.sleep(BATCH_REST)
            batch_count = 0

        try:
            print(f"\n[{i+1}/{stats['total']}] 处理: {name} (schId={sch_id})")

            # 获取章程列表
            zc_list = fetch_zc_info_ids(sch_id)
            time.sleep(REQUEST_DELAY)

            if not zc_list:
                stats["no_2026"] += 1
                skipped.append({"schId": sch_id, "name": name, "reason": "无章程"})
                continue

            # 筛选 2026 年章程
            zc_2026 = [z for z in zc_list if z["year"] == "2026"]
            if not zc_2026:
                stats["no_2026"] += 1
                skipped.append({"schId": sch_id, "name": name, "reason": "无2026年章程"})
                if (i + 1) % 50 == 0:
                    print(f"  [{i+1}/{stats['total']}] {name}: 无2026年章程，跳过")
                continue

            # 抓取每个2026年章程
            uni_segments = 0
            for zc in zc_2026:
                info_id = zc["infoId"]
                content = fetch_zc_content(sch_id, info_id)
                time.sleep(REQUEST_DELAY)

                if not content:
                    continue

                if len(content) < 100:  # 太短可能是空内容
                    print(f"    内容过短 ({len(content)} 字符), 跳过")
                    continue

                segments = segment_text(content)
                count = save_segments(name, "2026", segments, zszc_dir)
                uni_segments += count
                print(f"    已保存 {count} 段 ({len(content)} 字符)")

            if uni_segments > 0:
                stats["success"] += 1
                stats["segments"] += uni_segments
                existing_unis.add(name)
            else:
                stats["failed"] += 1
                failed.append({"schId": sch_id, "name": name, "reason": "无有效内容"})

        except Exception as e:
            stats["failed"] += 1
            failed.append({"schId": sch_id, "name": name, "reason": str(e)})
            print(f"  ❌ 失败: {e}")

        # 进度日志
        if (i + 1) % 10 == 0:
            print(f"\n[Step 2 进度] 已处理 {i+1}/{stats['total']}: "
                  f"成功 {stats['success']}, 跳过 {stats['no_2026']}, "
                  f"失败 {stats['failed']}")

    # 保存跳过和失败清单
    for filename, data in [("skipped_schools.json", skipped),
                            ("failed_schools.json", failed)]:
        path = DATA_DIR / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[Step 2] {filename}: {len(data)} 条")

    # 汇总
    print(f"\n[Step 2] ✅ 抓取完成!")
    print(f"  总计: {stats['total']}")
    print(f"  成功: {stats['success']}")
    print(f"  跳过(无2026章程): {stats['no_2026']}")
    print(f"  失败: {stats['failed']}")
    print(f"  总分段数: {stats['segments']}")

    return stats


# ── Main ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="全国本科高校2026招生章程全量抓取")
    parser.add_argument("--step", type=int, action="append",
                        choices=[1, 2], help="执行步骤 (可多次指定)")
    parser.add_argument("--resume", action="store_true", default=True,
                        help="启用断点续传 (默认)")
    parser.add_argument("--no-resume", action="store_true",
                        help="禁用断点续传, 从头开始")
    args = parser.parse_args()

    if not args.step:
        args.step = [1, 2]  # 默认全流程

    resume = not args.no_resume

    # Step 1: 获取高校列表
    schools = None
    if 1 in args.step:
        schools = fetch_school_list_from_index()

    # Step 2: 批量抓取章程
    if 2 in args.step:
        if schools is None:
            # 从已保存的列表加载
            list_path = DATA_DIR / "school_list.json"
            if list_path.exists():
                with open(list_path, "r", encoding="utf-8") as f:
                    schools = json.load(f)
                print(f"[Step 2] 从 {list_path} 加载 {len(schools)} 所高校")
            else:
                print("[Step 2] ❌ school_list.json 不存在，请先运行 Step 1")
                sys.exit(1)

        fetch_all_charters(schools, resume=resume)


if __name__ == "__main__":
    main()
