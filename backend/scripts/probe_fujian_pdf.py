#!/usr/bin/env python3
"""福建招生计划 PDF 解析器 v2 - 用 extract_chars 按字符 height 过滤水印。"""
import pdfplumber
from pathlib import Path
from collections import defaultdict

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "fujian_2026"

# 列区间
COL_RANGES = {
    "left": (60, 100),          # 院校名 / 专业组代号(4位)
    "major_code": (100, 130),   # 专业代号(3位)
    "name": (130, 270),         # 专业名/选科/章程
    "xuezhi": (270, 300),       # 学制
    "plan": (300, 330),         # 计划人数
    "tuition": (330, 370),      # 学费
    "note": (370, 495),         # 备注
}


def assign_column(x0):
    for col, (lo, hi) in COL_RANGES.items():
        if lo <= x0 < hi:
            return col
    return None


def parse_page_chars(page):
    """用 extract_chars，按 height 过滤水印，重组行。"""
    chars = page.chars  # pdfplumber 0.11: page.chars 属性
    # 正常字符 height ≈ 8-9，水印字符 height ≈ 60-70（旋转90度）
    # 过滤掉 height > 15 的字符
    normal_chars = [c for c in chars if (c["bottom"] - c["top"]) <= 15]
    print(f"  字符总数: {len(chars)}, 正常字符: {len(normal_chars)}, 过滤水印: {len(chars)-len(normal_chars)}")

    # 按 (top 取整, x0) 分组组装 words
    # 先按 row（top/5 取整）分组
    rows_dict = defaultdict(list)
    for c in normal_chars:
        row_idx = round(c["top"] / 5)
        rows_dict[row_idx].append(c)

    # 合并相邻行（top 差 ≤ 8），按列分桶
    sorted_keys = sorted(rows_dict.keys())
    merged_rows = []
    for k in sorted_keys:
        chars_in_row = rows_dict[k]
        if not chars_in_row:
            continue
        cur_top = min(c["top"] for c in chars_in_row)
        # 尝试合并到上一行
        if merged_rows:
            last_row, last_top = merged_rows[-1]
            if abs(cur_top - last_top) <= 8:
                last_row.extend(chars_in_row)
                continue
        merged_rows.append((chars_in_row, cur_top))

    # 对每行，按列分桶 + 按 x0 排序组装文本
    result = []
    for chars_in_row, _ in merged_rows:
        col_buckets = defaultdict(list)
        for c in chars_in_row:
            col = assign_column(c["x0"])
            if col is None:
                continue
            col_buckets[col].append(c)
        # 每列按 x0 排序，拼接文本
        row_data = {}
        for col, chars_list in col_buckets.items():
            chars_list.sort(key=lambda c: c["x0"])
            # 合并相邻字符（x0 间距 ≤ 3 视为同一 word）
            text_parts = []
            prev_x1 = None
            for c in chars_list:
                if prev_x1 is not None and c["x0"] - prev_x1 > 3:
                    text_parts.append(" ")
                text_parts.append(c["text"])
                prev_x1 = c["x1"]
            row_data[col] = "".join(text_parts).strip()
        if row_data:
            result.append(row_data)
    return result


def classify_row(row):
    """识别行类型。"""
    left = row.get("left", "")
    major_code = row.get("major_code", "")
    name = row.get("name", "")

    # 跳过表头/标题
    if any(kw in (left + name) for kw in ["年福建省", "普通高校招生计划", "招生计划", "收费标准",
                                            "院校代号", "专业代号", "代号", "专业名称", "学制",
                                            "计划人数", "备注", "普通类", "物理科目组", "历史科目组",
                                            "本科批", "专科批", "本科提前批"]):
        return "header", "", ""

    # 专业组行：left 有4位数字 + (name 含":(" 或 "选考" 或 "不限" 或 "专业组")
    if left and len(left) >= 4 and left[:4].isdigit():
        if any(kw in name for kw in [":(", "选考", "不限", "专业组", ":999", ":500", ":600"]):
            return "group", left[:4], name
        # 也可能 name 区有 "专业组"
        if "专业组" in (name + major_code):
            return "group", left[:4], name

    # 院校行：left 是中文 + 含"大学/学院/学校"
    if left and any(kw in left for kw in ["大学", "学院", "学校"]):
        return "university", "", left

    # 专业行：major_code 有3位代号
    if major_code and 2 <= len(major_code) <= 3:
        # 数字或字母+数字
        cleaned = major_code.replace(" ", "")
        if cleaned and (cleaned[0].isalpha() or cleaned.isdigit()):
            return "major", cleaned, name

    return "other", "", ""


def main():
    pdf_path = RAW / "plans_physics" / "4本科批.pdf"
    print(f"解析: {pdf_path.name}")
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[0]
        rows = parse_page_chars(page)
        print(f"\n第1页解析行数: {len(rows)}")
        for i, row in enumerate(rows[:40]):
            rtype, code, name = classify_row(row)
            line = " | ".join(f"{col}={row[col]}" for col in
                              ["left", "major_code", "name", "xuezhi", "plan", "tuition", "note"]
                              if col in row and row[col])
            print(f"  [{i:>2}] {rtype:10s} code={code:6s}  {line[:140]}")


if __name__ == "__main__":
    main()
