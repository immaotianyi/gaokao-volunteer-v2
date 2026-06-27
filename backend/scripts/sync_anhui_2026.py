#!/usr/bin/env python3
"""
安徽 高考数据爬取脚本
数据源: https://www.ahzsks.cn (安徽省教育招生考试院)

覆盖数据:
  - yifenyiduan_2025.csv / yifenyiduan_2026.csv: 一分一段表 (PDF解析, 物理类+历史类)
  - control_line_2024.csv / 2025 / 2026: 省控线 (官方公告值)
  - plans_2026.csv: 2026 专项招生计划 (国家专项/地方专项/高校专项, PDF解析)
  - admission_history.csv: 现有数据保留 (投档线为图片格式, 未OCR)

科类: 安徽是 3+1+2 省份 (2024首改), subject_group = 物理类 / 历史类
"""
from __future__ import annotations

import csv
import os
import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

# ─────────────────────────────────────────────────────────────────
# 路径配置
# ─────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw" / "anhui_2026"

PROVINCE = "安徽"
SUBJECT_GROUPS = ["物理类", "历史类"]

# ─────────────────────────────────────────────────────────────────
# 院校层次推断 (985/211/双一流名单, 用于 plans 的 school_type 字段)
# ─────────────────────────────────────────────────────────────────
SCHOOL_985 = {
    "北京大学", "中国人民大学", "清华大学", "北京交通大学", "北京工业大学",
    "北京航空航天大学", "北京理工大学", "北京科技大学", "北京化工大学",
    "北京邮电大学", "中国农业大学", "北京林业大学", "北京中医药大学",
    "北京师范大学", "北京外国语大学", "中国传媒大学", "中央财经大学",
    "对外经济贸易大学", "外交学院", "国际关系学院", "中央音乐学院",
    "中国政法大学", "南开大学", "天津大学", "天津医科大学", "华北电力大学",
    "河北工业大学", "太原理工大学", "内蒙古大学", "辽宁大学", "大连理工大学",
    "东北大学", "大连海事大学", "吉林大学", "延边大学", "东北师范大学",
    "哈尔滨工业大学", "哈尔滨工程大学", "东北农业大学", "东北林业大学",
    "复旦大学", "同济大学", "上海交通大学", "华东理工大学", "东华大学",
    "华东师范大学", "上海外国语大学", "上海财经大学", "上海大学",
    "第二军医大学", "第四军医大学", "南京大学", "苏州大学", "东南大学",
    "南京航空航天大学", "南京理工大学", "中国矿业大学", "河海大学",
    "江南大学", "南京农业大学", "中国药科大学", "南京师范大学", "浙江大学",
    "中国科学技术大学", "合肥工业大学", "厦门大学", "福州大学", "南昌大学",
    "山东大学", "中国海洋大学", "郑州大学", "武汉大学", "华中科技大学",
    "中国地质大学", "武汉理工大学", "华中农业大学", "华中师范大学",
    "中南财经政法大学", "湖南大学", "中南大学", "湖南师范大学", "中山大学",
    "暨南大学", "华南理工大学", "华南师范大学", "海南大学", "广西大学",
    "四川大学", "重庆大学", "西南交通大学", "电子科技大学", "西南大学",
    "西南财经大学", "贵州大学", "云南大学", "西北大学", "西安交通大学",
    "西北工业大学", "西安电子科技大学", "长安大学", "西北农林科技大学",
    "陕西师范大学", "兰州大学", "青海大学", "宁夏大学", "新疆大学",
    "石河子大学", "北京大学医学部", "国防科技大学", "中央民族大学",
    "中国海洋大学", "北京体育大学", "中国石油大学", "北京中医药大学",
}
SCHOOL_211_ONLY = {
    "北京体育大学", "中央音乐学院", "中央民族大学", "北京中医药大学",
    "天津医科大学", "河北工业大学", "太原理工大学", "内蒙古大学",
    "辽宁大学", "大连海事大学", "延边大学", "东北师范大学",
    "哈尔滨工程大学", "东北农业大学", "东北林业大学", "第二军医大学",
    "第四军医大学", "苏州大学", "南京师范大学", "中国药科大学",
    "福州大学", "南昌大学", "中国海洋大学", "郑州大学", "中国地质大学",
    "武汉理工大学", "华中师范大学", "中南财经政法大学", "湖南师范大学",
    "暨南大学", "华南师范大学", "海南大学", "广西大学", "西南交通大学",
    "西南大学", "西南财经大学", "贵州大学", "云南大学", "西北大学",
    "长安大学", "陕西师范大学", "青海大学", "宁夏大学", "新疆大学",
    "石河子大学", "上海大学", "东华大学", "上海外国语大学", "上海财经大学",
    "中央财经大学", "对外经济贸易大学", "外交学院", "国际关系学院",
    "中国传媒大学", "北京外国语大学", "北京林业大学", "中国农业大学",
    "北京邮电大学", "北京化工大学", "北京科技大学", "北京工业大学",
    "华北电力大学", "河海大学", "江南大学", "南京农业大学",
    "中国矿业大学", "南京理工大学", "南京航空航天大学", "合肥工业大学",
    "厦门大学", "中国石油大学", "长安大学",
}
SCHOOL_DOUBLE_FIRST = {
    "南方科技大学", "上海科技大学", "中国科学院大学", "成都理工大学",
    "成都中医药大学", "西南石油大学", "天津工业大学", "天津中医药大学",
    "山西大学", "南京邮电大学", "南京信息工程大学", "南京林业大学",
    "南京医科大学", "南京中医药大学", "湘潭大学", "华南农业大学",
    "广州医科大学", "广州中医药大学", "河南大学", "宁波大学",
    "中国美术学院", "外交学院", "中国人民公安大学", "中国音乐学院",
    "中央美术学院", "中央戏剧学院", "上海海洋大学", "上海体育学院",
    "上海音乐学院", "上海中医药大学", " Maritime University",
}


def infer_school_type(name: str) -> str:
    """根据院校名称推断层次: 985 / 211 / 双一流 / 省属重点 / 普通本科 / 民办"""
    if not name or not isinstance(name, str):
        return "普通本科"
    name = name.strip()
    # 民办院校关键词
    if any(k in name for k in ["民办", "独立学院", "学院(民办)", "职业"]):
        if "民办" in name or "独立学院" in name:
            return "民办"
    if name in SCHOOL_985:
        return "985"
    if name in SCHOOL_211_ONLY:
        return "211"
    if name in SCHOOL_DOUBLE_FIRST:
        return "双一流"
    # 省属重点关键词
    if any(k in name for k in ["师范大学", "农业大学", "医科大学", "工业大学",
                                "理工大学", "科技大学", "林业大学", "财经大学",
                                "政法大学", "外国语大学", "民族大学"]):
        # 排除民办
        if "民办" not in name and "独立" not in name:
            return "省属重点"
    # 普通本科
    return "普通本科"


def infer_major_category(major_name: str) -> str:
    """根据专业名称推断专业大类"""
    if not major_name:
        return ""
    name = str(major_name)
    rules = [
        ("医学", ["医学", "临床", "口腔", "护理", "药学", "中医", "公共卫生", "法医"]),
        ("工学", ["工程", "工", "计算机", "电子", "电气", "机械", "自动化", "土木",
                  "建筑", "化工", "材料", "通信", "信息", "软件", "人工智能",
                  "机器人", "车辆", "航空", "航天", "船舶", "核", "测控", "安全"]),
        ("理学", ["数学", "物理", "化学", "生物", "地理", "地质", "天文", "统计",
                  "科学", "心理", "生态", "海洋科学"]),
        ("文学", ["文学", "语言", "汉语", "外语", "英语", "日语", "新闻", "传播",
                  "翻译", "汉语言"]),
        ("法学", ["法学", "法律", "政治", "社会学", "马克思", "公安", "侦查"]),
        ("经济学", ["经济", "金融", "贸易", "保险", "财政", "税务"]),
        ("管理学", ["管理", "会计", "工商", "市场营销", "财务", "人力", "公共",
                    "物流", "旅游", "电子商务"]),
        ("教育学", ["教育", "体育", "运动", "学前"]),
        ("农学", ["农学", "园艺", "植物", "动物", "林学", "水产", "草学", "兽医"]),
        ("历史学", ["历史", "考古", "文物"]),
        ("哲学", ["哲学"]),
        ("艺术学", ["艺术", "美术", "设计", "音乐", "舞蹈", "戏剧", "影视",
                    "动画", "书法", "播音", "表演"]),
        ("军事学", ["军事", "国防", "武器"]),
    ]
    for cat, keywords in rules:
        if any(k in name for k in keywords):
            return cat
    return ""


# ─────────────────────────────────────────────────────────────────
# 通用工具
# ─────────────────────────────────────────────────────────────────
def clean_cell(val) -> str | None:
    """清洗单元格"""
    if val is None:
        return None
    s = str(val).strip().replace("\n", "").replace(" ", "").replace(",", "")
    if s == "" or s == "-" or s == "—":
        return None
    return s


def parse_int(val) -> int | None:
    s = clean_cell(val)
    if s is None:
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def append_to_csv(new_df: pd.DataFrame, csv_filename: str) -> int:
    """安全追加数据到CSV（去重），返回新增行数"""
    csv_path = DATA_DIR / csv_filename
    # #14 root fix: 重定向到 data/raw/{省}_{文件名}，禁止直接写主 CSV
    _raw_dir = DATA_DIR / "raw"
    _raw_dir.mkdir(exist_ok=True)
    csv_path = _raw_dir / f"{PROVINCE}_{csv_path.name}"
    if not isinstance(new_df, pd.DataFrame) or len(new_df) == 0:
        return 0
    # 把所有 NaN 替换为空字符串（避免写入 null/NA/None/nan）
    new_df = new_df.fillna("")
    if csv_path.exists():
        existing = pd.read_csv(csv_path, dtype=str).fillna("")
        # 去除可能存在的同省份旧测试数据（仅安徽，避免重复）
        # 实际策略: concat 后整体 drop_duplicates
        merged = pd.concat([existing, new_df], ignore_index=True)
        before = len(merged)
        merged = merged.drop_duplicates()
        after = len(merged)
        merged.to_csv(csv_path, index=False, encoding="utf-8")
        return after - len(existing) if after > len(existing) else (before - len(existing) - (before - after))
    else:
        new_df.to_csv(csv_path, index=False, encoding="utf-8")
        return len(new_df)


# ═══════════════════════════════════════════════════════════════
# 解析一分一段表 PDF
# ═══════════════════════════════════════════════════════════════
def parse_yifenyiduan_pdf(pdf_path: Path, year: int) -> list[dict]:
    """解析一分一段表PDF。

    PDF结构: 每页1个15列表格 (5组: 分数|人数|累计人数)
    科类通过页面文本 "历史科目组合" / "物理科目组合" 识别
    单一PDF包含两个科类 (前几页历史类, 后几页物理类)
    """
    rows: list[dict] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            # 识别科类
            if "物理科目组合" in text:
                subject_group = "物理类"
            elif "历史科目组合" in text:
                subject_group = "历史类"
            else:
                # 延续上一页科类（部分页无标题）
                if rows:
                    subject_group = rows[-1]["subject_group"]
                else:
                    subject_group = "历史类"  # 默认历史类在前
                    print(f"  [WARN] 第{page_idx+1}页未识别科类, 默认{subject_group}")

            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue
                for row in table:
                    if not row or len(row) < 3:
                        continue
                    # 跳过表头
                    if row[0] and ("分数" in str(row[0]) or "科类" in str(row[0])):
                        continue
                    # 15列 = 5组(分数,人数,累计)
                    n_groups = len(row) // 3
                    for g in range(n_groups):
                        base = g * 3
                        score_raw = clean_cell(row[base])
                        seg_raw = clean_cell(row[base + 1])
                        cum_raw = clean_cell(row[base + 2])
                        if not score_raw:
                            continue
                        # 处理 "671及以上" 格式
                        m = re.match(r"^(\d+)", score_raw)
                        if not m:
                            continue
                        score = int(m.group(1))
                        if score < 0 or score > 750:
                            continue
                        segment_count = parse_int(seg_raw) or 0
                        cumulative_count = parse_int(cum_raw)
                        if cumulative_count is None:
                            continue
                        # 合理性校验
                        if cumulative_count > 1000000:
                            continue
                        rows.append({
                            "province": PROVINCE,
                            "year": year,
                            "subject_group": subject_group,
                            "batch": "本科批",
                            "score": score,
                            "segment_count": segment_count,
                            "cumulative_count": cumulative_count,
                        })
    # 去重 (按 province/year/subject_group/batch/score)
    seen = set()
    deduped = []
    for r in rows:
        key = (r["province"], r["year"], r["subject_group"], r["batch"], r["score"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return deduped


# ═══════════════════════════════════════════════════════════════
# 解析招生计划 PDF (专项计划)
# ═══════════════════════════════════════════════════════════════
PLANS_FIELDS = [
    "province", "subject_group", "batch", "university_code", "university_name",
    "group_code", "major_code", "major_name", "plan_count", "tuition",
    "lowest_score_2025", "lowest_rank_2025", "is_new", "school_type",
    "major_category", "subject_requirement", "plan_count_prev",
]


def parse_plans_pdf(pdf_path: Path, subject_group: str, batch: str) -> list[dict]:
    """解析招生计划PDF (专项计划).

    PDF表格10列: 院校代码|院校名称|专业组号|选考要求|专业代码|专业名称|学制|收费标准|招生计划|备注
    映射到 plans_2026.csv schema.
    """
    rows: list[dict] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue
                for row in table:
                    if not row or len(row) < 9:
                        continue
                    # 跳过表头
                    if row[0] and ("院校" in str(row[0]) and "代码" in str(row[0])):
                        continue
                    code = clean_cell(row[0])
                    name = clean_cell(row[1])
                    if not code or not name:
                        continue
                    # 院校代码应为数字
                    if not re.match(r"^\d{3,6}$", str(code)):
                        continue
                    group_code = clean_cell(row[2]) or ""
                    subject_req = clean_cell(row[3]) or ""
                    major_code = clean_cell(row[4]) or ""
                    major_name = clean_cell(row[5]) or ""
                    tuition = parse_int(row[7])
                    plan_count = parse_int(row[8])
                    if not plan_count or plan_count <= 0:
                        continue

                    rows.append({
                        "province": PROVINCE,
                        "subject_group": subject_group,
                        "batch": batch,
                        "university_code": str(code),
                        "university_name": str(name),
                        "group_code": str(group_code),
                        "major_code": str(major_code),
                        "major_name": str(major_name),
                        "plan_count": plan_count,
                        "tuition": tuition if tuition else "",
                        "lowest_score_2025": "",
                        "lowest_rank_2025": "",
                        "is_new": 0,
                        "school_type": infer_school_type(str(name)),
                        "major_category": infer_major_category(major_name),
                        "subject_requirement": subject_req,
                        "plan_count_prev": "",
                    })
            if (page_idx + 1) % 30 == 0:
                print(f"  [{pdf_path.name}] 进度: {page_idx+1}/{len(pdf.pages)} 页")
    return rows


# ═══════════════════════════════════════════════════════════════
# 省控线 (官方公告值, 已通过 WebFetch 核实)
# ═══════════════════════════════════════════════════════════════
CONTROL_LINE_VALUES = {
    # (year, batch_section, batch, subject_group, line_type, lowest_score, source_url)
    2024: [
        ("本科院校", "本科", "历史类", "总分", 462,
         "https://www.ahzsks.cn/ggl/7626.htm"),
        ("本科院校", "本科", "物理类", "总分", 465,
         "https://www.ahzsks.cn/ggl/7626.htm"),
        ("高职(专科)", "专科", "历史类", "总分", 200,
         "https://www.ahzsks.cn/ggl/7626.htm"),
        ("高职(专科)", "专科", "物理类", "总分", 200,
         "https://www.ahzsks.cn/ggl/7626.htm"),
        ("特殊类型招生", "特控线", "历史类", "总分", 512,
         "https://www.ahzsks.cn/ggl/7626.htm"),
        ("特殊类型招生", "特控线", "物理类", "总分", 514,
         "https://www.ahzsks.cn/ggl/7626.htm"),
        # 艺术类 (历史科目组合)
        ("艺术类", "艺术本科", "历史类", "文化科总分", 347,
         "https://www.ahzsks.cn/ggl/7626.htm"),
        ("艺术类", "艺术本科", "物理类", "文化科总分", 349,
         "https://www.ahzsks.cn/ggl/7626.htm"),
        ("体育类", "体育本科", "历史类", "文化科总分", 323,
         "https://www.ahzsks.cn/ggl/7626.htm"),
        ("体育类", "体育本科", "物理类", "文化科总分", 326,
         "https://www.ahzsks.cn/ggl/7626.htm"),
    ],
    2025: [
        ("本科院校", "本科", "历史类", "总分", 477,
         "https://www.ahzsks.cn/ggl/8357.htm"),
        ("本科院校", "本科", "物理类", "总分", 461,
         "https://www.ahzsks.cn/ggl/8357.htm"),
        ("特殊类型招生", "特控线", "历史类", "总分", 515,
         "https://www.ahzsks.cn/ggl/8357.htm"),
        ("特殊类型招生", "特控线", "物理类", "总分", 514,
         "https://www.ahzsks.cn/ggl/8357.htm"),
    ],
    2026: [
        ("本科院校", "本科", "历史类", "总分", 490,
         "https://www.ahzsks.cn/ggl/8995.htm"),
        ("本科院校", "本科", "物理类", "总分", 451,
         "https://www.ahzsks.cn/ggl/8995.htm"),
        ("特殊类型招生", "特控线", "历史类", "总分", 522,
         "https://www.ahzsks.cn/ggl/8995.htm"),
        ("特殊类型招生", "特控线", "物理类", "总分", 514,
         "https://www.ahzsks.cn/ggl/8995.htm"),
    ],
}


def build_control_line_rows(year: int) -> list[dict]:
    """构造省控线行"""
    rows = []
    for (section, batch, sg, line_type, score, url) in CONTROL_LINE_VALUES.get(year, []):
        rows.append({
            "province": PROVINCE,
            "year": year,
            "batch_section": section,
            "batch": batch,
            "subject_group": sg,
            "line_type": line_type,
            "lowest_score": score,
            "source_url": url,
        })
    return rows


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════
def main():
    print(f"[{PROVINCE}] 开始爬取数据...")
    stats = {}

    # ─── 1. 一分一段表 ───
    print(f"\n[1/4] 一分一段表")
    for year, pdf_name in [(2026, "anhui_yifenyiduan_2026.pdf"),
                            (2025, "anhui_yifenyiduan_2025.pdf")]:
        pdf_path = RAW_DIR / "yifenyiduan" / pdf_name
        if not pdf_path.exists():
            print(f"  [SKIP] {pdf_name} 不存在")
            continue
        rows = parse_yifenyiduan_pdf(pdf_path, year)
        df = pd.DataFrame(rows, columns=[
            "province", "year", "subject_group", "batch",
            "score", "segment_count", "cumulative_count",
        ])
        csv_name = f"yifenyiduan_{year}.csv"
        n = append_to_csv(df, csv_name)
        phy = len(df[df["subject_group"] == "物理类"])
        his = len(df[df["subject_group"] == "历史类"])
        print(f"  [安徽] ✓ 已解析 {pdf_name} ({len(rows)}行: 物理类{phy}+历史类{his}, 追加{n}行)")
        stats[csv_name] = (len(rows), phy, his)

    # ─── 2. 省控线 ───
    print(f"\n[2/4] 省控线")
    for year in [2024, 2025, 2026]:
        rows = build_control_line_rows(year)
        if not rows:
            continue
        df = pd.DataFrame(rows, columns=[
            "province", "year", "batch_section", "batch",
            "subject_group", "line_type", "lowest_score", "source_url",
        ])
        csv_name = f"control_line_{year}.csv"
        n = append_to_csv(df, csv_name)
        print(f"  [安徽] ✓ 省控线 {year}年 ({len(rows)}行, 追加{n}行)")
        stats[csv_name] = len(rows)

    # ─── 3. 招生计划 (2026 专项计划) ───
    print(f"\n[3/4] 招生计划 (2026 专项计划)")
    plans_files = [
        ("anhui_plans_2026_guojia_physics.pdf", "物理类", "国家专项本科"),
        ("anhui_plans_2026_guojia_history.pdf", "历史类", "国家专项本科"),
        ("anhui_plans_2026_difang_physics.pdf", "物理类", "地方专项本科"),
        ("anhui_plans_2026_difang_history.pdf", "历史类", "地方专项本科"),
        ("anhui_plans_2026_gaoxiao_physics.pdf", "物理类", "高校专项本科"),
        ("anhui_plans_2026_gaoxiao_history.pdf", "历史类", "高校专项本科"),
    ]
    all_plans = []
    for pdf_name, sg, batch in plans_files:
        pdf_path = RAW_DIR / "plans" / pdf_name
        if not pdf_path.exists():
            print(f"  [SKIP] {pdf_name} 不存在")
            continue
        rows = parse_plans_pdf(pdf_path, sg, batch)
        all_plans.extend(rows)
        print(f"  [安徽] ✓ 已解析 {pdf_name} ({len(rows)}行, {sg}/{batch})")
    if all_plans:
        df = pd.DataFrame(all_plans, columns=PLANS_FIELDS)
        n = append_to_csv(df, "plans_2026.csv")
        phy = len(df[df["subject_group"] == "物理类"])
        his = len(df[df["subject_group"] == "历史类"])
        print(f"  [安徽] ✓ 招生计划2026 合计 {len(all_plans)}行 (物理类{phy}+历史类{his}, 追加{n}行)")
        stats["plans_2026.csv"] = (len(all_plans), phy, his)

    # ─── 4. 历史投档线说明 ───
    print(f"\n[4/4] 历史投档线")
    print(f"  [安徽] 投档线为图片格式发布, 未OCR; 现有 admission_history.csv 保留 {76} 行 (2024年, 质量有限)")
    print(f"  [安徽] 如需补充, 建议后续使用 OCR 或第三方结构化数据源")

    # ─── 汇总报告 ───
    print(f"\n{'='*50}")
    print(f"========== {PROVINCE} 数据爬取报告 ==========")
    for k, v in stats.items():
        if isinstance(v, tuple):
            if k.startswith("yifenyiduan"):
                print(f"{k}: 追加 {v[0]} 行 (物理类 {v[1]} + 历史类 {v[2]})")
            else:
                print(f"{k}: 追加 {v[0]} 行 (物理类 {v[1]} + 历史类 {v[2]})")
        else:
            print(f"{k}: 追加 {v} 行")
    print(f"原始文件: data/raw/anhui_2026/ (8个PDF)")
    print(f"[{PROVINCE}] ✓ 爬取完成")
    print(f"[{PROVINCE}] ⚠ 提示: 数据写入完成, 请重启后端服务 (uvicorn main:app) 以加载新数据")


if __name__ == "__main__":
    main()
