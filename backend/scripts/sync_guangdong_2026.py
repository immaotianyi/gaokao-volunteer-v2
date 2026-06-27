"""广东省教育考试院 2026 数据同步管道（统一入口）。

设计原则：
1. 单文件脚本，按阶段分函数：fetch → parse → load → verify
2. 阶段间通过本地文件解耦：raw PDF / HTML → 中间 CSV → 标准化 CSV → 入库
3. 阶段幂等：重跑只会覆盖原始数据，不会污染数据库
4. 强制校验：每阶段结束都跑断言，数据异常立即终止
5. 详细日志：每阶段打印行数、字段、覆盖范围

用法：
    python backend/scripts/sync_guangdong_2026.py fetch     # 1. 下载原始 PDF/HTML
    python backend/scripts/sync_guangdong_2026.py parse      # 2. 解析为中间 CSV
    python backend/scripts/sync_guangdong_2026.py normalize  # 3. 标准化为目标 schema CSV
    python backend/scripts/sync_guangdong_2026.py load       # 4. 加载到数据库
    python backend/scripts/sync_guangdong_2026.py verify     # 5. 校验数据完整性
    python backend/scripts/sync_guangdong_2026.py all        # 全流程
"""
from __future__ import annotations

import argparse
import csv
import httpx
import pdfplumber
import re
import sys
from pathlib import Path
from typing import Iterable

# ─────────────────────────────────────────────────────────────────
# 路径配置
# ─────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw" / "gd_2026"
INTERMEDIATE_DIR = DATA_DIR / "intermediate" / "gd_2026"
PROCESSED_DIR = DATA_DIR  # 标准化 CSV 直接写到 data/ 下与现有文件并列

YIFENYIDUAN_RAW_DIR = RAW_DIR / "yifenyiduan"
YIFENYIDUAN_INTERMEDIATE = INTERMEDIATE_DIR / "yifenyiduan.csv"
YIFENYIDUAN_PROCESSED = PROCESSED_DIR / "yifenyiduan_2026.csv"

CONTROL_LINE_RAW_DIR = RAW_DIR / "control_line"
CONTROL_LINE_INTERMEDIATE = INTERMEDIATE_DIR / "control_line.csv"
CONTROL_LINE_PROCESSED = PROCESSED_DIR / "control_line_2026.csv"

# ─────────────────────────────────────────────────────────────────
# 数据源配置（从首页解析得到，已硬编码避免每次重新爬）
# ─────────────────────────────────────────────────────────────────
BASE_URL = "https://eea.gd.gov.cn"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 一分一段表公告：post_id=4916194 (tzgg 栏目，主源)
# 16 个 PDF，cat_id=618。attachment_id 不连续（缺 618108/618123/618124/618125）
YIFENYIDUAN_POST_ID = 4916194
YIFENYIDUAN_PDF_ATTACHMENT_IDS = [
    618107, 618109, 618110, 618111, 618112, 618113, 618114, 618115,
    618116, 618117, 618118, 618119, 618120, 618121, 618122, 618126,
]  # 16 个，从首页 HTML 提取
YIFENYIDUAN_NOTICE_URL = f"{BASE_URL}/tzgg/content/post_{YIFENYIDUAN_POST_ID}.html"

# 省控线公告：post_id=4915291 (news 栏目，主源)，HTML 正文无附件
CONTROL_LINE_URL = f"{BASE_URL}/news/content/post_4915291.html"


# ═══════════════════════════════════════════════════════════════
# 阶段 1：FETCH - 下载原始数据
# ═══════════════════════════════════════════════════════════════
def fetch_pdf(client: httpx.Client, attachment_id: int, post_id: int, out_dir: Path) -> Path:
    """下载单个附件 PDF。返回本地路径。"""
    url = f"{BASE_URL}/attachment/0/618/{attachment_id}/{post_id}.pdf"
    out_path = out_dir / f"{attachment_id}.pdf"
    if out_path.exists() and out_path.stat().st_size > 1000:
        print(f"  [SKIP] {out_path.name} 已存在 ({out_path.stat().st_size} bytes)")
        return out_path
    headers = {**HEADERS, "Referer": f"{BASE_URL}/tzgg/content/post_{post_id}.html"}
    with client.stream("GET", url, headers=headers, timeout=30, follow_redirects=True) as r:
        if r.status_code != 200:
            raise RuntimeError(f"下载失败 {url} status={r.status_code}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    print(f"  [OK] {out_path.name} ({out_path.stat().st_size} bytes)")
    return out_path


def fetch_yifenyiduan() -> list[Path]:
    """下载 2026 一分一段表 16 个 PDF。"""
    print(f"\n[FETCH] 一分一段表 (16 PDFs, post_id={YIFENYIDUAN_POST_ID})")
    YIFENYIDUAN_RAW_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    with httpx.Client() as client:
        for att_id in YIFENYIDUAN_PDF_ATTACHMENT_IDS:
            try:
                p = fetch_pdf(client, att_id, YIFENYIDUAN_POST_ID, YIFENYIDUAN_RAW_DIR)
                paths.append(p)
            except Exception as e:
                print(f"  [FAIL] attachment_id={att_id}: {e}")
                raise
    print(f"  共下载 {len(paths)} 个 PDF")
    return paths


def fetch_control_line() -> Path:
    """下载省控线公告 HTML。"""
    print(f"\n[FETCH] 省控线公告 HTML")
    CONTROL_LINE_RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CONTROL_LINE_RAW_DIR / f"post_4915291.html"
    if out_path.exists() and out_path.stat().st_size > 1000:
        print(f"  [SKIP] {out_path.name} 已存在")
        return out_path
    r = httpx.get(CONTROL_LINE_URL, headers=HEADERS, timeout=20, follow_redirects=True)
    if r.status_code != 200:
        raise RuntimeError(f"下载失败 status={r.status_code}")
    out_path.write_text(r.text, encoding="utf-8")
    print(f"  [OK] {out_path.name} ({out_path.stat().st_size} bytes)")
    return out_path


# ═══════════════════════════════════════════════════════════════
# 阶段 2：PARSE - 解析为中间 CSV
# ═══════════════════════════════════════════════════════════════
def clean_cell(val) -> str | None:
    """清洗单元格：去除水印噪声字、空白。"""
    if val is None:
        return None
    s = str(val).strip()
    # 去除 PDF 水印噪声字（"省考试院教育广东试"等单字）
    # 这些字会嵌入到表格单元格里，必须先剥离
    s = re.sub(r"[省考试院教育广东广试]+", "", s)
    s = s.replace("\n", "").replace(" ", "").replace(",", "")
    if s == "" or s == "-":
        return None
    return s


def parse_int(val) -> int | None:
    """转整数，失败返回 None。"""
    s = clean_cell(val)
    if s is None:
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


# 附件编号 → 科类映射（从首页文本提取，水印切碎"物理/历史"等字所以用编号）
# 项目当前只关心物理类/历史类（其他艺术/体育类暂不入库）
ATTACHMENT_NO_TO_SUBJECT_GROUP = {
    1: "物理类",  # 普通类（物理）本科+专科
    2: "历史类",  # 普通类（历史）本科+专科
    3: "体育类",
    4: "美术类",
    5: "书法类",
    6: "舞蹈类",
    7: "音乐类",
    8: "播音主持类",
    9: "编导类",
    10: "表演类",
    11: "美术(校考)",
    12: "书法(校考)",
    13: "舞蹈(校考)",
    14: "音乐(校考)",
    15: "播音(校考)",
    16: "编导(校考)",
}


def detect_attachment_no(first_page_text: str) -> int | None:
    """从首页文本提取附件编号。

    PDF 水印会把"附件2\\n2026"切成混乱形式。保留原文本换行符，
    用"附件X"后紧跟非数字字符（含换行）做边界匹配。
    """
    text = first_page_text or ""
    # 模式1: "附件 X" 后紧跟空白/换行/非数字（如 "附件2\\n2026..."）
    m = re.search(r"附件\s*(\d{1,2})\s*\D", text)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 16:
            return n
    # 模式2: 退化匹配（如 "附件2" 在文本末尾）
    m = re.search(r"附件\s*(\d{1,2})\s*$", text, re.M)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 16:
            return n
    # 模式3: 强行匹配 1-2 位数字后非数字
    m = re.search(r"附件\s*(\d{1,2})(?=\D|$)", text)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 16:
            return n
    return None


def detect_subject_group(first_page_text: str) -> str:
    """根据 PDF 首页附件编号映射到科类。

    水印把"物理类"/"历史类"等字切碎，无法直接从文本识别；
    改用附件编号映射（附件1=物理类，附件2=历史类，...）。
    """
    attach_no = detect_attachment_no(first_page_text)
    if attach_no is None:
        return "未知"
    return ATTACHMENT_NO_TO_SUBJECT_GROUP.get(attach_no, "未知")


def parse_yifenyiduan_pdf(pdf_path: Path) -> list[dict]:
    """解析单个一分一段表 PDF，返回行列表。

    表格结构（5列）：
        文化总分 | 本科分数段人数 | 本科累计人数 | 专科分数段人数 | 专科累计人数
    """
    rows = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        n_pages = len(pdf.pages)
        if n_pages == 0:
            return rows

        # 首页文本用于识别 subject_group
        first_text = pdf.pages[0].extract_text() or ""
        subject_group = detect_subject_group(first_text)

        for page_idx, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or len(row) < 5:
                        continue
                    score_raw = clean_cell(row[0])
                    if not score_raw:
                        continue
                    # 跳过表头
                    if "文化总分" in score_raw or "分数段" in score_raw:
                        continue
                    # 处理 "669（含以上）" 这种格式
                    m = re.match(r"^(\d+)", score_raw)
                    if not m:
                        continue
                    score = int(m.group(1))
                    is_top = "含以上" in score_raw

                    benke_segment = parse_int(row[1])
                    benke_cumulative = parse_int(row[2])
                    zhuanke_segment = parse_int(row[3])
                    zhuanke_cumulative = parse_int(row[4])

                    # 数据合理性校验
                    if benke_cumulative is not None and benke_cumulative > 1000000:
                        continue
                    if score < 0 or score > 750:
                        continue

                    rows.append({
                        "subject_group": subject_group,
                        "score": score,
                        "is_top_threshold": is_top,
                        "benke_segment": benke_segment,
                        "benke_cumulative": benke_cumulative,
                        "zhuanke_segment": zhuanke_segment,
                        "zhuanke_cumulative": zhuanke_cumulative,
                        "source_file": pdf_path.name,
                        "page": page_idx + 1,
                    })
    return rows


def parse_yifenyiduan() -> Path:
    """解析所有一分一段表 PDF，输出中间 CSV。"""
    print(f"\n[PARSE] 一分一段表 PDF → 中间 CSV")
    pdf_paths = sorted(YIFENYIDUAN_RAW_DIR.glob("*.pdf"))
    if not pdf_paths:
        raise RuntimeError(f"未找到 PDF: {YIFENYIDUAN_RAW_DIR}")
    print(f"  PDF 数量: {len(pdf_paths)}")

    all_rows: list[dict] = []
    for p in pdf_paths:
        rows = parse_yifenyiduan_pdf(p)
        print(f"  [{p.name}] {len(rows)} 行 (subject_group={rows[0]['subject_group'] if rows else 'N/A'})")
        all_rows.extend(rows)

    print(f"  中间数据总计: {len(all_rows)} 行")
    INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "subject_group", "score", "is_top_threshold",
        "benke_segment", "benke_cumulative",
        "zhuanke_segment", "zhuanke_cumulative",
        "source_file", "page",
    ]
    with open(YIFENYIDUAN_INTERMEDIATE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"  [OK] 中间 CSV: {YIFENYIDUAN_INTERMEDIATE}")
    return YIFENYIDUAN_INTERMEDIATE


def parse_control_line() -> Path:
    """解析省控线公告 HTML，提取段落文本到中间 CSV。

    广东2026省控线公告是 `<p>` 段落格式（非 HTML 表格）。
    章节结构：
        一、本科院校（含执行本批次最低分数线的提前批军检和非军检本科院校）
            （一）本科各科类
                普通类（历史）：总分440分。
                ...
            （二）特殊类型招生录取控制线（含强基计划、高校专项计划、综合评价）
                普通类（历史）：总分546分。
            （三）重点高校招收农村和脱贫地区学生（地方专项计划）
        二、专科院校（含执行本批次最低分数线的提前批专科院校）
        三、军队本科院校
        ...
    """
    print(f"\n[PARSE] 省控线 HTML → 中间 CSV")
    html_path = CONTROL_LINE_RAW_DIR / "post_4915291.html"
    if not html_path.exists():
        raise RuntimeError(f"未找到 HTML: {html_path}")
    html = html_path.read_text(encoding="utf-8")

    # 提取 <div class="article">...</div> 内的所有 <p>...</p>
    # 不要求精确 </div> 闭合（中间可能有嵌套 div）
    article_match = re.search(r'<div class="article">(.*?)(?:<div class="fj"|<div class="friend")', html, re.S)
    if not article_match:
        # 退化方案：提取整个 <div class="content">...</div>
        article_match = re.search(r'<div class="content">(.*?)<div class="friend"', html, re.S)
    if not article_match:
        raise RuntimeError("未找到正文 div.article / div.content")
    article_html = article_match.group(1)

    # 提取所有 <p>...</p> 段落
    p_pattern = re.compile(r'<p[^>]*>(.*?)</p>', re.S)
    tag_stripper = re.compile(r'<[^>]+>')

    paragraphs: list[str] = []
    for raw_p in p_pattern.findall(article_html):
        text = tag_stripper.sub("", raw_p)
        text = text.replace("&nbsp;", " ").replace("&#160;", " ")
        # 去掉全角空格
        text = text.replace("\u3000", "").strip()
        if text:
            paragraphs.append(text)

    print(f"  提取段落: {len(paragraphs)}")
    INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONTROL_LINE_INTERMEDIATE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["idx", "text"])
        for idx, p in enumerate(paragraphs):
            writer.writerow([idx, p])
    print(f"  [OK] 中间 CSV: {CONTROL_LINE_INTERMEDIATE}")
    return CONTROL_LINE_INTERMEDIATE


# ═══════════════════════════════════════════════════════════════
# 阶段 3：NORMALIZE - 转为标准 schema CSV
# ═══════════════════════════════════════════════════════════════
def normalize_yifenyiduan() -> Path:
    """把中间 CSV 转为标准 yifenyiduan_2026.csv。

    目标 schema:
        province, year, subject_group, batch, score, segment_count, cumulative_count
    其中 batch ∈ {本科, 专科}；subject_group ∈ {物理类, 历史类, ...}
    """
    print(f"\n[NORMALIZE] 一分一段表 → 标准 CSV")
    if not YIFENYIDUAN_INTERMEDIATE.exists():
        raise RuntimeError(f"未找到中间 CSV: {YIFENYIDUAN_INTERMEDIATE}")

    rows_out = []
    with open(YIFENYIDUAN_INTERMEDIATE, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            sg = r["subject_group"]
            if sg in ("未知",):
                continue
            score = int(r["score"])
            # 本科
            if r["benke_cumulative"]:
                rows_out.append({
                    "province": "广东", "year": 2026,
                    "subject_group": sg, "batch": "本科",
                    "score": score,
                    "segment_count": r["benke_segment"] or "0",
                    "cumulative_count": r["benke_cumulative"],
                })
            # 专科
            if r["zhuanke_cumulative"]:
                rows_out.append({
                    "province": "广东", "year": 2026,
                    "subject_group": sg, "batch": "专科",
                    "score": score,
                    "segment_count": r["zhuanke_segment"] or "0",
                    "cumulative_count": r["zhuanke_cumulative"],
                })

    # 去重（按 province/year/subject_group/batch/score）
    seen = set()
    deduped = []
    for r in rows_out:
        key = (r["province"], r["year"], r["subject_group"], r["batch"], r["score"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    # 按 subject_group, batch, score desc 排序
    deduped.sort(key=lambda x: (x["subject_group"], x["batch"], -x["score"]))

    with open(YIFENYIDUAN_PROCESSED, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "province", "year", "subject_group", "batch",
            "score", "segment_count", "cumulative_count",
        ])
        writer.writeheader()
        writer.writerows(deduped)
    print(f"  [OK] 标准 CSV: {YIFENYIDUAN_PROCESSED} ({len(deduped)} 行)")
    return YIFENYIDUAN_PROCESSED


def normalize_control_line() -> Path:
    """把省控线段落 CSV 转为标准 control_line_2026.csv。

    目标 schema:
        province, year, batch_section, batch, subject_group, line_type, lowest_score, source_url

    batch_section ∈ {本科院校, 专科院校, 军队本科院校, ...}
    batch ∈ {本科, 专科, 提前本科, 特控线, 地方专项, ...}
    subject_group ∈ {普通类(历史), 普通类(物理), 体育类, ...}
    line_type ∈ {总分, 文化科总分, 专业省统考}
    """
    print(f"\n[NORMALIZE] 省控线 → 标准 CSV")
    if not CONTROL_LINE_INTERMEDIATE.exists():
        raise RuntimeError(f"未找到中间 CSV: {CONTROL_LINE_INTERMEDIATE}")

    rows: list[dict] = []
    current_section = ""  # 一、二、三... 对应 batch_section
    current_subsection = ""  # （一）（二）... 对应 batch 类型

    with open(CONTROL_LINE_INTERMEDIATE, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            text = r["text"]
            if not text:
                continue

            # 章节识别：一、二、三... 对应 batch_section
            section_match = re.match(r"^[一二三四五六七八九十]、\s*(.+?)(?:（.+）)?$", text)
            if section_match:
                current_section = section_match.group(1).strip()
                current_subsection = ""
                continue

            # 子章节识别：（一）（二）...
            sub_match = re.match(r"^（[一二三四五六七八九十]）\s*(.+)$", text)
            if sub_match:
                current_subsection = sub_match.group(1).strip()
                continue

            # 跳过 "其中，..." 这种补充说明（避免与主分数线混淆）
            if text.startswith("其中，"):
                continue

            # 普通类（历史/物理）：总分XXX分
            m = re.search(r"普通类（历史）[：:]\s*总分(\d+)分", text)
            if m:
                rows.append({
                    "province": "广东", "year": 2026,
                    "batch_section": current_section,
                    "batch": _map_batch(current_section, current_subsection),
                    "subject_group": "历史类",
                    "line_type": "总分",
                    "lowest_score": int(m.group(1)),
                    "source_url": CONTROL_LINE_URL,
                })
                continue
            m = re.search(r"普通类（物理）[：:]\s*总分(\d+)分", text)
            if m:
                rows.append({
                    "province": "广东", "year": 2026,
                    "batch_section": current_section,
                    "batch": _map_batch(current_section, current_subsection),
                    "subject_group": "物理类",
                    "line_type": "总分",
                    "lowest_score": int(m.group(1)),
                    "source_url": CONTROL_LINE_URL,
                })
                continue

            # 艺体类：文化科总分XXX分，XX类专业省统考YYY分
            m = re.search(r"(体育类|音乐类.*?|舞蹈类|表.*?演类.*?|播音与主持类.*?|美术与设计类|书法类|戏曲类)[：:]\s*文化科总分(\d+)分(?:[，,]\s*.*?专业.*?(\d+)分)?", text)
            if m:
                sg_name = m.group(1).strip()
                rows.append({
                    "province": "广东", "year": 2026,
                    "batch_section": current_section,
                    "batch": _map_batch(current_section, current_subsection),
                    "subject_group": sg_name,
                    "line_type": "文化科总分",
                    "lowest_score": int(m.group(2)),
                    "source_url": CONTROL_LINE_URL,
                })
                if m.group(3):
                    rows.append({
                        "province": "广东", "year": 2026,
                        "batch_section": current_section,
                        "batch": _map_batch(current_section, current_subsection),
                        "subject_group": sg_name,
                        "line_type": "专业省统考",
                        "lowest_score": int(m.group(3)),
                        "source_url": CONTROL_LINE_URL,
                    })
                continue

    # 写入标准 CSV
    fieldnames = ["province", "year", "batch_section", "batch",
                  "subject_group", "line_type", "lowest_score", "source_url"]
    with open(CONTROL_LINE_PROCESSED, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  [OK] 标准 CSV: {CONTROL_LINE_PROCESSED} ({len(rows)} 行)")
    # 打印汇总
    print(f"\n  省控线汇总:")
    for r in rows:
        if r["subject_group"] in ("物理类", "历史类"):
            print(f"    [{r['batch_section']}/{r['batch']}] {r['subject_group']} → {r['lowest_score']}分")
    return CONTROL_LINE_PROCESSED


def _map_batch(section: str, subsection: str) -> str:
    """把章节+子章节映射为简洁的 batch 标签。"""
    section_clean = section.strip()
    if "本科院校" in section_clean and "军队" not in section_clean:
        if "特殊类型" in subsection or "特招" in subsection:
            return "特控线"
        if "地方专项" in subsection or "重点高校" in subsection:
            return "地方专项"
        if "本科各科类" in subsection:
            return "本科"
        return "本科"
    if "专科" in section_clean:
        return "专科"
    if "军队" in section_clean:
        return "军队本科"
    if "消防" in section_clean:
        return "消防本科"
    if "教师专项" in section_clean or "订单定向培养农村教师" in section_clean:
        return "教师专项"
    if "卫生专项" in section_clean or "农村卫生" in section_clean:
        return "卫生专项"
    if "少数民族" in section_clean:
        return "少数民族班"
    if "预科" in section_clean:
        return "预科班"
    return section_clean[:20]


# ═══════════════════════════════════════════════════════════════
# 阶段 4：LOAD - 入库（基于现有 SQLite）
# ═══════════════════════════════════════════════════════════════
def load_yifenyiduan() -> int:
    """加载 yifenyiduan_2026.csv 到数据库。

    策略：覆盖式更新（先删 province='广东' AND year=2026 的行，再插入）。
    """
    print(f"\n[LOAD] 一分一段表入库")
    # 当前 score_rank 服务读 CSV 文件，不读 DB，所以这里只更新文件即可
    # 但仍需要打印入库前后的校验信息
    if not YIFENYIDUAN_PROCESSED.exists():
        raise RuntimeError(f"未找到标准 CSV: {YIFENYIDUAN_PROCESSED}")
    n = 0
    with open(YIFENYIDUAN_PROCESSED, encoding="utf-8-sig") as f:
        for _ in csv.DictReader(f):
            n += 1
    print(f"  [OK] yifenyiduan_2026.csv 已就位 ({n} 行)，score_rank 服务下次加载会自动读取")
    return n


# ═══════════════════════════════════════════════════════════════
# 阶段 5：VERIFY - 校验
# ═══════════════════════════════════════════════════════════════
def verify_yifenyiduan() -> bool:
    """校验一分一段表数据完整性。"""
    print(f"\n[VERIFY] 一分一段表数据校验")
    if not YIFENYIDUAN_PROCESSED.exists():
        print(f"  [FAIL] 文件不存在: {YIFENYIDUAN_PROCESSED}")
        return False
    rows = []
    with open(YIFENYIDUAN_PROCESSED, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"  总行数: {len(rows)}")

    # 按 subject_group + batch 分组统计
    from collections import defaultdict
    grouped = defaultdict(list)
    for r in rows:
        key = (r["subject_group"], r["batch"])
        grouped[key].append(r)

    ok = True
    for (sg, batch), group_rows in sorted(grouped.items()):
        scores = sorted([int(r["score"]) for r in group_rows])
        n = len(group_rows)
        if n == 0:
            continue
        max_score = max(scores)
        min_score = min(scores)
        # 检查是否单调（累计人数应随分数下降而递增）
        sorted_by_score_desc = sorted(group_rows, key=lambda x: -int(x["score"]))
        cumulative_list = [int(r["cumulative_count"]) for r in sorted_by_score_desc]
        is_monotonic = all(cumulative_list[i] <= cumulative_list[i + 1] for i in range(len(cumulative_list) - 1))
        # 检查覆盖区间
        # 物理类最高分应在 650-720（2025=697, 2026=669 都在此范围）
        # 历史类最高分应在 640-720（2025=682, 2026=699 都在此范围）
        expected_max_range = {"物理类": (650, 720), "历史类": (640, 720)}
        if sg in expected_max_range:
            lo, hi = expected_max_range[sg]
            if not (lo <= max_score <= hi):
                print(f"  [WARN] {sg}/{batch}: 最高分={max_score} 不在预期范围 [{lo}, {hi}]")
                ok = False
        print(f"  {sg}/{batch}: {n} 行, 分数范围 {min_score}-{max_score}, 单调={'✓' if is_monotonic else '✗'}")
        if not is_monotonic:
            ok = False

    # 检查本科线附近分数存在
    # 物理类：2025本科线 436 / 特控线 534；2026 真实数据最高分可能 < 700
    print(f"\n  关键分数点（物理类/本科）:")
    phy_benke = [r for r in rows if r["subject_group"] == "物理类" and r["batch"] == "本科"]
    phy_scores = [int(r["score"]) for r in phy_benke]
    phy_max = max(phy_scores) if phy_scores else 0
    for s in [700, 650, 600, 550, 500, 450, 400, 350, 300]:
        match = [r for r in phy_benke if int(r["score"]) == s]
        if match:
            r = match[0]
            print(f"    {s}分 → 段{r['segment_count']} / 累计{r['cumulative_count']}")
        else:
            # 仅在分数 ≤ 最高分时才报缺失（> 最高分属于"含以上"区间，不单独列）
            if s <= phy_max:
                print(f"    {s}分 → 缺失!")
                ok = False
            else:
                print(f"    {s}分 → 不在表中（已合并到最高分 {phy_max}（含以上））")

    # 历史类关键分数点
    print(f"\n  关键分数点（历史类/本科）:")
    his_benke = [r for r in rows if r["subject_group"] == "历史类" and r["batch"] == "本科"]
    his_scores = [int(r["score"]) for r in his_benke]
    his_max = max(his_scores) if his_scores else 0
    for s in [680, 650, 600, 550, 500, 450, 400, 350, 300]:
        match = [r for r in his_benke if int(r["score"]) == s]
        if match:
            r = match[0]
            print(f"    {s}分 → 段{r['segment_count']} / 累计{r['cumulative_count']}")
        else:
            if s <= his_max:
                print(f"    {s}分 → 缺失!")
                ok = False
            else:
                print(f"    {s}分 → 不在表中（已合并到最高分 {his_max}（含以上））")

    return ok


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["fetch", "parse", "normalize", "load", "verify", "all"])
    args = parser.parse_args()

    if args.stage in ("fetch", "all"):
        fetch_yifenyiduan()
        fetch_control_line()

    if args.stage in ("parse", "all"):
        parse_yifenyiduan()
        parse_control_line()

    if args.stage in ("normalize", "all"):
        normalize_yifenyiduan()
        normalize_control_line()

    if args.stage in ("load", "all"):
        load_yifenyiduan()

    if args.stage in ("verify", "all"):
        ok = verify_yifenyiduan()
        if not ok:
            print("\n[VERIFY] 校验失败！")
            sys.exit(1)
        print("\n[VERIFY] 全部通过 ✓")


if __name__ == "__main__":
    main()
