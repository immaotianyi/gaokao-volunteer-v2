#!/usr/bin/env python3
"""
中国大学招生章程批量抓取与分段处理脚本
数据来源：教育部阳光高考平台 (gaokao.chsi.com.cn)
"""

import requests
import re
import os
import time
import json
from pathlib import Path

# 配置
OUTPUT_DIR = Path("/Users/sanzhaibanniang/Desktop/zszc_output")
MAX_SEGMENT_LENGTH = 1000  # 每段最大字符数
OVERLAP_LENGTH = 100       # 段落重叠字符数
REQUEST_DELAY = 1.5        # 请求间隔（秒）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 所有已知的大学 schId 映射（从阳光高考获取）
# 阳光高考平台 schId 范围大约从 1 到 3000+
SCHOOL_LIST_URL = "https://gaokao.chsi.com.cn/zsgs/zhangcheng/listVerifedZszc.do"
SCHOOL_ZC_LIST_URL = "https://gaokao.chsi.com.cn/zsgs/zhangcheng/listZszc--schId-{schId}.dhtml"
ZC_DETAIL_URL = "https://gaokao.chsi.com.cn/zsgs/zhangcheng/listVerifedZszc--method-view,schId-{schId},infoId-{infoId}.dhtml"


def clean_html(html_text):
    """清理HTML标签，提取纯文本"""
    # 移除script和style标签
    text = re.sub(r'<script[^>]*>.*?</script>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # 移除HTML标签
    text = re.sub(r'<[^>]+>', '', text)
    # 替换HTML实体
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    # 清理多余空白
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()


def segment_text(text, max_len=MAX_SEGMENT_LENGTH, overlap=OVERLAP_LENGTH):
    """按符号分段，最大长度max_len，重叠overlap"""
    segments = []
    if not text:
        return segments
    
    # 按段落分隔符（句号、换行等）初步分割
    # 使用句号、感叹号、问号、换行等作为分隔点
    split_pattern = r'([。！？\n]+)'
    parts = re.split(split_pattern, text)
    
    # 合并为完整句子
    sentences = []
    current = ""
    for part in parts:
        current += part
        if re.search(r'[。！？\n]', part):
            sentences.append(current)
            current = ""
    if current.strip():
        sentences.append(current)
    
    # 按最大长度组装段落
    segments = []
    i = 0
    while i < len(sentences):
        segment = ""
        j = i
        while j < len(sentences) and len(segment) + len(sentences[j]) <= max_len:
            segment += sentences[j]
            j += 1
        
        if not segment:
            # 单个句子超过最大长度，强制截断
            sentence = sentences[i]
            for k in range(0, len(sentence), max_len - overlap):
                chunk = sentence[k:k + max_len]
                if chunk.strip():
                    segments.append(chunk.strip())
            i += 1
            continue
        
        segments.append(segment.strip())
        
        # 计算重叠部分开始位置
        if j > i + 1:
            # 找到overlap字符前的句子边界
            overlap_chars = 0
            new_i = j - 1
            while new_i > i and overlap_chars < overlap:
                overlap_chars += len(sentences[new_i])
                new_i -= 1
            i = new_i + 1 if new_i > i else i + 1
        else:
            i = j
    
    return segments


def fetch_school_list_from_index():
    """从阳光高考首页获取大学列表"""
    schools = []
    try:
        resp = requests.get(
            "https://gaokao.chsi.com.cn/zsgs/zhangcheng/listVerifedZszc.do",
            headers=HEADERS,
            timeout=30
        )
        resp.encoding = 'utf-8'
        html = resp.text
        
        # 提取 schId 和学校名称
        pattern = r'schId-(\d+)\.dhtml[^>]*>([^<]+)</a>'
        matches = re.findall(pattern, html)
        
        seen = set()
        for sch_id, name in matches:
            name = name.strip()
            if name and name not in seen:
                seen.add(name)
                schools.append({"schId": sch_id, "name": name})
        
        print(f"从首页获取到 {len(schools)} 所大学")
    except Exception as e:
        print(f"获取大学列表失败: {e}")
    
    return schools


def fetch_zc_info_ids(sch_id):
    """获取某所大学的招生章程 infoId 列表"""
    results = []
    try:
        url = SCHOOL_ZC_LIST_URL.format(schId=sch_id)
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.encoding = 'utf-8'
        html = resp.text
        
        # 提取章程链接和年份
        # 模式: infoId-(\d+).dhtml 附近有年份信息
        pattern = r'infoId-(\d+)\.dhtml[^>]*>([^<]*招生章程[^<]*)</a>'
        matches = re.findall(pattern, html)
        
        for info_id, title in matches:
            # 从标题提取年份
            year_match = re.search(r'(20\d{2})', title)
            year = year_match.group(1) if year_match else "unknown"
            results.append({"infoId": info_id, "year": year, "title": title.strip()})
        
    except Exception as e:
        print(f"  获取 schId={sch_id} 章程列表失败: {e}")
    
    return results


def fetch_zc_content(sch_id, info_id):
    """获取招生章程详细内容"""
    try:
        url = ZC_DETAIL_URL.format(schId=sch_id, infoId=info_id)
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.encoding = 'utf-8'
        html = resp.text
        
        # 提取正文内容（在 "招生章程" 之后的文本）
        text = clean_html(html)
        
        # 找到 "招生章程" 标题后的内容
        idx = text.find("招生章程")
        if idx != -1:
            text = text[idx:]
        
        return text
    except Exception as e:
        print(f"  获取 schId={sch_id}, infoId={info_id} 内容失败: {e}")
        return None


def save_segments(university_name, year, segments, output_dir):
    """保存分段文本"""
    # 清理文件名中的非法字符
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', university_name)
    
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


def fetch_university_zc(sch_id, name, output_dir):
    """获取单个大学的所有招生章程"""
    print(f"\n处理: {name} (schId={sch_id})")
    
    zc_list = fetch_zc_info_ids(sch_id)
    
    if not zc_list:
        print(f"  {name}: 未找到招生章程")
        return 0
    
    total_segments = 0
    for zc in zc_list:
        year = zc['year']
        info_id = zc['infoId']
        print(f"  获取 {year}年 章程 (infoId={info_id})...")
        
        content = fetch_zc_content(sch_id, info_id)
        if not content:
            print(f"    内容为空")
            continue
        
        # 分段处理
        segments = segment_text(content)
        print(f"    内容长度: {len(content)} 字符, 分为 {len(segments)} 段")
        
        # 保存
        count = save_segments(name, year, segments, output_dir)
        total_segments += count
        print(f"    已保存 {count} 个分段文件")
        
        time.sleep(REQUEST_DELAY)
    
    return total_segments


def main():
    """主函数"""
    print("=" * 60)
    print("中国大学招生章程批量抓取与分段处理工具")
    print("数据来源：教育部阳光高考平台 (gaokao.chsi.com.cn)")
    print("=" * 60)
    
    # 创建输出目录
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 获取大学列表
    print("\n[步骤1] 获取大学列表...")
    schools = fetch_school_list_from_index()
    
    if not schools:
        print("未获取到大学列表，使用备用 schId 扫描模式...")
        # 备用方案：扫描 schId 范围
        schools = [{"schId": str(i), "name": f"schId_{i}"} for i in range(1, 200)]
    
    print(f"共获取 {len(schools)} 所大学")
    
    # 如果数量太多，可以分批处理
    # 这里处理前 N 所
    MAX_SCHOOLS = 500  # 可根据需要调整
    schools_to_process = schools[:MAX_SCHOOLS]
    
    print(f"\n[步骤2] 开始处理 {len(schools_to_process)} 所大学...")
    
    stats = {
        "total": 0,
        "success_2025": 0,
        "success_2026": 0,
        "failed": 0,
        "segments": 0
    }
    
    for i, school in enumerate(schools_to_process):
        sch_id = school['schId']
        name = school.get('name', f'schId_{sch_id}')
        
        try:
            segments = fetch_university_zc(sch_id, name, OUTPUT_DIR)
            stats["total"] += 1
            stats["segments"] += segments
            if segments > 0:
                print(f"  [{i+1}/{len(schools_to_process)}] {name}: 完成 ({segments}段)")
            else:
                stats["failed"] += 1
                print(f"  [{i+1}/{len(schools_to_process)}] {name}: 无数据")
        except Exception as e:
            stats["failed"] += 1
            print(f"  [{i+1}/{len(schools_to_process)}] {name}: 出错 - {e}")
        
        time.sleep(REQUEST_DELAY)
    
    # 输出统计
    print("\n" + "=" * 60)
    print("处理完成！统计信息：")
    print(f"  处理大学数: {stats['total']}")
    print(f"  成功: {stats['total'] - stats['failed']}")
    print(f"  失败: {stats['failed']}")
    print(f"  总分段数: {stats['segments']}")
    print(f"  输出目录: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()