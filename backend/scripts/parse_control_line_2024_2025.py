#!/usr/bin/env python3
"""
解析广东省 2024/2025 年省控线 HTML → control_line_{year}.csv

复用 2026 的章节状态机逻辑：
  一、本科院校 → batch=本科
  二、专科院校 → batch=专科
  （二）特殊类型招生录取控制线 → batch=特控线
  （三）地方专项 → batch=地方专项
  三、军队本科 → batch=军队本科
  四、消防 → batch=消防本科
  五、教师专项 → batch=教师专项
  六、卫生专项 → batch=卫生专项（本科/专科子节）
  七、少数民族班 → batch=少数民族班
  八、预科班 → batch=预科班

输出 schema: province, year, batch_section, batch, subject_group, line_type, lowest_score, source_url
"""
import re
import csv
from pathlib import Path
from html import unescape

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

SOURCES = {
    2024: {
        "html": DATA_DIR / "raw" / "gd_2024" / "control_line" / "post_4444840.html",
        "url": "https://eea.gd.gov.cn/zwgk/sjfb/tjsj/content/post_4444840.html",
        "output": DATA_DIR / "control_line_2024.csv",
    },
    2025: {
        "html": DATA_DIR / "raw" / "gd_2025" / "control_line" / "post_4733327.html",
        "url": "https://eea.gd.gov.cn/gkmlpt/content/4/4733/mpost_4733327.html",
        "output": DATA_DIR / "control_line_2025.csv",
    },
}


def extract_paragraphs(html: str) -> list[str]:
    """从 HTML 中提取 <p> 段落纯文本"""
    # 去 HTML 标签内的 style 等属性，提取 <p...>内容</p>
    paras = re.findall(r"<p[^>]*>(.*?)</p>", html, re.S)
    texts = []
    for p in paras:
        # 去 inner HTML 标签
        t = re.sub(r"<[^>]+>", "", p)
        t = unescape(t).strip()
        # 去除首尾全角空格
        t = t.replace("\u3000", "").strip()
        if t:
            texts.append(t)
    return texts


def parse_control_line(paras: list[str], year: int, source_url: str) -> list[dict]:
    """章节状态机解析省控线段落 → 行列表"""
    rows = []
    current_section = ""   # 一、二、三...
    current_subsection = ""  # （一）（二）...
    current_batch = ""

    SECTION_MAP = {
        "一": "本科",
        "二": "专科",
        "三": "军队本科",
        "四": "消防本科",
        "五": "教师专项",
        "六": "卫生专项",
        "七": "少数民族班",
        "八": "预科班",
    }
    SUBSECTION_MAP = {
        "（一）": "本科各科类",   # 本科
        "（二）": "特控线",
        "（三）": "地方专项",
        "（四）": "军队提前本科",
    }

    for text in paras:
        # 识别章节 "一、本科院校..."
        m_sec = re.match(r"([一二三四五六七八九十])、", text)
        if m_sec:
            current_section = m_sec.group(1)
            current_subsection = ""
            current_batch = SECTION_MAP.get(current_section, "")
            # 卫生专项有本专科子节，先不设 batch
            if current_section == "六":
                current_batch = "卫生专项"

        # 识别子节 "（一）" "（二）"
        m_sub = re.match(r"（([一二三四五六])）", text)
        if m_sub:
            current_subsection = f"（{m_sub.group(1)}）"

        # 卫生专项的子节区分本科/专科
        if current_section == "六":
            if current_subsection == "（一）":
                current_batch = "卫生专项(本科)"
            elif current_subsection == "（二）":
                current_batch = "卫生专项(专科)"

        # 特控线
        if "特殊类型" in text and "控制线" in text:
            current_batch = "特控线"

        # 地方专项
        if "地方专项" in text:
            current_batch = "地方专项"

        # 匹配 "普通类（历史）：总分XXX分"
        m_score = re.search(r"普通类（历史）：总分(\d+)分", text)
        if m_score and current_batch:
            rows.append(_row(year, current_batch, "历史类", "总分", int(m_score.group(1)), source_url))
            continue
        m_score = re.search(r"普通类（物理）：总分(\d+)分", text)
        if m_score and current_batch:
            rows.append(_row(year, current_batch, "物理类", "总分", int(m_score.group(1)), source_url))
            continue

        # 匹配艺体类 "体育类：文化科总分365分，体育类专业省统考210分"
        m_art = re.match(r"(体育类|音乐类.*?|舞蹈类|表.*?演类.*?|播音.*?|美术.*?|书法类|戏曲类)[：:]", text)
        if m_art and current_batch:
            subject = m_art.group(1).split("（")[0].split("(")[0]
            # 文化科总分
            m_culture = re.search(r"文化科总分(\d+)分", text)
            if m_culture:
                rows.append(_row(year, current_batch, subject, "文化科总分", int(m_culture.group(1)), source_url))
            # 专业省统考
            m_major = re.search(r"专业省统考(\d+)分", text)
            if m_major:
                rows.append(_row(year, current_batch, subject, "专业省统考", int(m_major.group(1)), source_url))
            # 戏曲类 "专业省际联考须合格" 无数字
            continue

    return rows


def _row(year, batch, subject, line_type, score, url) -> dict:
    return {
        "province": "广东",
        "year": year,
        "batch_section": batch,
        "batch": batch,
        "subject_group": subject,
        "line_type": line_type,
        "lowest_score": score,
        "source_url": url,
    }


def main():
    for year, cfg in SOURCES.items():
        print(f"\n{'='*50}")
        print(f"解析 {year} 年省控线")
        print(f"{'='*50}")

        html_path = cfg["html"]
        if not html_path.exists():
            print(f"❌ HTML 不存在: {html_path}")
            continue

        html = html_path.read_text(encoding="utf-8", errors="ignore")
        paras = extract_paragraphs(html)
        print(f"  提取段落: {len(paras)} 个")

        rows = parse_control_line(paras, year, cfg["url"])
        print(f"  解析出行: {len(rows)} 行")

        # 去重
        seen = set()
        deduped = []
        for r in rows:
            key = (r["batch"], r["subject_group"], r["line_type"])
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        if len(deduped) != len(rows):
            print(f"  去重: {len(rows)} → {len(deduped)}")
        rows = deduped

        # 写 CSV
        out = cfg["output"]
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "province", "year", "batch_section", "batch",
                "subject_group", "line_type", "lowest_score", "source_url"
            ])
            writer.writeheader()
            writer.writerows(rows)
        print(f"  ✅ 已写入 {out.name} ({len(rows)} 行)")

        # 打印关键数据校验
        print(f"\n  关键分数线校验:")
        for r in rows:
            if r["subject_group"] in ("历史类", "物理类") and r["line_type"] == "总分":
                if r["batch"] in ("本科", "专科", "特控线", "地方专项"):
                    print(f"    {r['batch']:8s} {r['subject_group']}: {r['lowest_score']}分")


if __name__ == "__main__":
    main()
