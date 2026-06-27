#!/usr/bin/env python3
"""
湖北省教育考试院 PDF/图片 解析工具

支持3类数据：
1. 投档线 PDF（pdfplumber 解析12列表格）
2. 一分一段表图片（rapidocr_onnxruntime OCR）
3. 省控线图片（rapidocr_onnxruntime OCR）

字段顺序严格遵循 backend/prompts/_common_spec.md
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pdfplumber
import pandas as pd

# OCR 懒加载（首次调用才初始化，避免无 OCR 任务时也加载模型）
_RAPIDOCR = None


def _get_ocr():
    global _RAPIDOCR
    if _RAPIDOCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _RAPIDOCR = RapidOCR()
    return _RAPIDOCR


# ═══════════════════════════════════════════════════════════════
# 通用清洗
# ═══════════════════════════════════════════════════════════════
def _clean_int(val):
    """转整数；失败返回 None。"""
    if val is None:
        return None
    s = str(val).strip().replace(",", "").replace(" ", "")
    if s in ("", "-", "—", "nan", "None"):
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _clean_str(val):
    """清洗字符串：去换行/空白。"""
    if val is None:
        return ""
    s = str(val).replace("\n", "").strip()
    return "" if s in ("-", "—", "nan", "None") else s


# ═══════════════════════════════════════════════════════════════
# 1. 投档线 PDF 解析 → admission_history.csv
# ═══════════════════════════════════════════════════════════════
# 湖北 PDF 表格结构（12列，前2行是合并表头）：
#   col0: 院校专业组代号 (如 A00105)
#   col1: 院校专业组名称 (如 北京大学第05组)
#   col2: 再选科目要求 (如 不限/化/政)
#   col3: 投档线 (如 693)
#   col4-10: 末位投档考生同分排序项（语数之和/语数最高/外语/物理或历史/再选最高/再选次高/志愿号）
#   col11: 备注
#
# 字段映射到 admission_history.csv：
#   year = PDF年份
#   province = "湖北"
#   subject_group = "物理类" 或 "历史类"（按 PDF 标题"首选物理"/"首选历史"判定）
#   batch = "本科批"
#   university_code = group_code 前4位 (如 A001)
#   university_name = 从"北京大学第05组"提取"北京大学"
#   group_code = A00105 (完整代号)
#   major_code = A00105 (专业组级数据，同 group_code)
#   major_name = "第05组"
#   lowest_score = 投档线
#   lowest_rank = None（湖北PDF不公布位次）
#   avg_score = None
#   applicant_count = None
#   source_file = PDF文件名

_GROUP_NAME_RE = re.compile(r"^(.+?)第(\d+)组$")


def _split_group_name(full_name: str) -> tuple[str, str]:
    """从'北京大学第05组'提取 ('北京大学', '第05组')。匹配失败返回 (full_name, '')."""
    full_name = _clean_str(full_name)
    m = _GROUP_NAME_RE.match(full_name)
    if m:
        return m.group(1), f"第{m.group(2)}组"
    return full_name, ""


def parse_toudang_pdf(pdf_path: Path, year: int, subject_group: str) -> pd.DataFrame:
    """解析湖北投档线 PDF，返回 admission_history schema 的 DataFrame。

    Args:
        pdf_path: PDF 文件路径
        year: 录取年份（如 2024）
        subject_group: "物理类" 或 "历史类"
    """
    rows = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or len(row) < 4:
                        continue
                    code = _clean_str(row[0])
                    # 跳过表头行
                    if not code or "代号" in code or "院校" in code:
                        continue
                    # 校验：必须是字母+数字开头的代号
                    if not re.match(r"^[A-Za-z]\d", code):
                        continue
                    group_name_full = _clean_str(row[1])
                    score = _clean_int(row[3]) if len(row) > 3 else None
                    # 分数范围校验
                    if score is not None and not (200 <= score <= 750):
                        score = None

                    uni_name, major_name = _split_group_name(group_name_full)
                    # university_code = group_code 前4位（A00105 → A001）
                    uni_code = code[:4] if len(code) >= 5 else code

                    rows.append({
                        "year": year,
                        "province": "湖北",
                        "subject_group": subject_group,
                        "batch": "本科批",
                        "university_code": uni_code,
                        "university_name": uni_name,
                        "group_code": code,
                        "major_code": code,  # 专业组级数据
                        "major_name": major_name or f"第{code[-2:]}组",
                        "lowest_score": score,
                        "lowest_rank": None,  # 湖北 PDF 不公布位次
                        "avg_score": None,
                        "applicant_count": None,
                        "source_file": pdf_path.name,
                    })
            if (page_idx + 1) % 20 == 0:
                print(f"  [{pdf_path.name}] 解析进度: {page_idx+1}/{len(pdf.pages)} 页")

    df = pd.DataFrame(rows, columns=[
        "year", "province", "subject_group", "batch", "university_code",
        "university_name", "group_code", "major_code", "major_name",
        "lowest_score", "lowest_rank", "avg_score", "applicant_count", "source_file",
    ])
    return df


# ═══════════════════════════════════════════════════════════════
# 2. 一分一段表 图片 OCR 解析 → yifenyiduan_*.csv
# ═══════════════════════════════════════════════════════════════
# 图片结构（hbea.edu.cn）：每张图3列「分数|人数|累计人数」
# OCR 返回 [(box, text, score), ...]，box 为4角坐标
# 解析步骤：
#   1. 从标题判断科类（首选物理→物理类，首选历史→历史类）
#   2. 过滤纯数字文本框
#   3. 按 y 坐标聚类成行（容差 ±15px）
#   4. 行内按 x 坐标排序，9 个数字一组（3列×3字段）
#   5. 输出 (score, segment_count, cumulative_count)


def _cluster_by_y(items: list, y_tol: int = 15) -> list[list]:
    """按 y 坐标聚类。items: [(box, text, score), ...]"""
    if not items:
        return []
    # 按 y 排序
    sorted_items = sorted(items, key=lambda x: x[0][0][1])
    clusters = []
    cur = [sorted_items[0]]
    cur_y = sorted_items[0][0][0][1]
    for it in sorted_items[1:]:
        y = it[0][0][1]
        if abs(y - cur_y) <= y_tol:
            cur.append(it)
            cur_y = (cur_y * (len(cur) - 1) + y) / len(cur)
        else:
            clusters.append(cur)
            cur = [it]
            cur_y = y
    clusters.append(cur)
    return clusters


def _cluster_x_into_columns(items: list, img_width: int = 1080) -> list[list]:
    """把同一行的数字按 x 坐标分3列。

    使用图片宽度的0.36和0.60作为分界点（基于湖北一分一段表图片的OCR经验值）。
    列1: 分数 | 人数 | 累计人数  (x < 0.36*w)
    列2: 分数 | 人数 | 累计人数  (0.36*w <= x < 0.60*w)
    列3: 分数 | 人数 | 累计人数  (x >= 0.60*w)
    """
    if not items:
        return []
    bound1 = img_width * 0.36
    bound2 = img_width * 0.60
    col1_items = sorted([(box, n) for box, n in items if box[0][0] < bound1], key=lambda x: x[0][0][0])
    col2_items = sorted([(box, n) for box, n in items if bound1 <= box[0][0] < bound2], key=lambda x: x[0][0][0])
    col3_items = sorted([(box, n) for box, n in items if box[0][0] >= bound2], key=lambda x: x[0][0][0])
    return [[n for _, n in col1_items], [n for _, n in col2_items], [n for _, n in col3_items]]


def parse_yifenyiduan_image(img_path: Path, year: int) -> pd.DataFrame:
    """OCR 一张一分一段表图片，返回 yifenyiduan schema 的 DataFrame。

    科类从图片标题自动判定（含"首选物理"→物理类，"首选历史"→历史类）。
    图片结构：每张图含3列「分数|人数|累计人数」，按 x 间隙分列。
    """
    ocr = _get_ocr()
    result, _ = ocr(str(img_path))
    if not result:
        return pd.DataFrame(columns=[
            "province", "year", "subject_group", "batch",
            "score", "segment_count", "cumulative_count",
        ])

    # 获取图片宽度用于分列
    from PIL import Image
    try:
        with Image.open(img_path) as img:
            img_width = img.width
    except Exception:
        img_width = 1080  # 默认值

    # 1. 从标题判断科类
    subject_group = None
    for box, text, _ in result:
        if "首选物理" in text or "物理类" in text:
            subject_group = "物理类"
            break
        if "首选历史" in text or "历史类" in text:
            subject_group = "历史类"
            break
    if subject_group is None:
        print(f"  ⚠ {img_path.name}: 未识别科类，跳过")
        return pd.DataFrame()

    # 2. 过滤纯数字文本框
    numeric_items = []
    for box, text, _ in result:
        text = text.strip().replace(",", "").replace(" ", "")
        if text.isdigit():
            num = int(text)
            # 排除年份
            if num in (2023, 2024, 2025, 2026):
                continue
            numeric_items.append((box, num))

    # 3. 按 y 聚类成行
    clusters = _cluster_by_y(numeric_items, y_tol=15)

    # 4. 行内按 x 间隙分列，每列3个数字 (score, segment, cumulative)
    rows = []
    for cluster in clusters:
        columns = _cluster_x_into_columns(cluster, img_width=img_width)
        for col in columns:
            # 每列应有3个数字
            if len(col) < 3:
                continue
            # 取前3个（避免OCR多识别）
            score, seg, cum = col[0], col[1], col[2]
            # 校验
            if not (0 <= score <= 750):
                continue
            if seg < 0 or cum < 0:
                continue
            if cum < seg:
                continue
            # 累计人数应 >= 1（除非分数为0）
            if cum < 1 and score > 0:
                continue
            rows.append({
                "province": "湖北",
                "year": year,
                "subject_group": subject_group,
                "batch": "本科批",
                "score": score,
                "segment_count": seg,
                "cumulative_count": cum,
            })

    df = pd.DataFrame(rows, columns=[
        "province", "year", "subject_group", "batch",
        "score", "segment_count", "cumulative_count",
    ])
    if len(df) == 0:
        return df
    # 去重（同一 score 可能跨图重复），保留累计人数最大的（更可靠）
    df = df.sort_values("cumulative_count", ascending=False).drop_duplicates(
        subset=["year", "subject_group", "score"]
    )
    # 后处理：按 score 降序排序，剔除累计人数不递增的行（OCR错误）
    df = df.sort_values(["subject_group", "score"], ascending=[True, False]).reset_index(drop=True)
    kept = []
    prev_cum = 0
    for _, r in df.iterrows():
        # 累计人数必须 >= 前一行（更高分）的累计人数
        if r["cumulative_count"] >= prev_cum and r["cumulative_count"] >= r["segment_count"]:
            kept.append(r)
            prev_cum = r["cumulative_count"]
    df = pd.DataFrame(kept, columns=df.columns).reset_index(drop=True)
    return df


# ═══════════════════════════════════════════════════════════════
# 3. 省控线 图片 OCR 解析 → control_line_*.csv
# ═══════════════════════════════════════════════════════════════
# 省控线图片含批次(本科/专科/特殊类型) + 科类(物理类/历史类/艺术/体育) + 分数
# OCR 后按行解析：每个关键词附近找3位数字


def parse_control_line_image(img_path: Path, year: int, source_url: str = "") -> pd.DataFrame:
    """OCR 省控线图片，返回 control_line schema 的 DataFrame。

    湖北省控线为通知文字格式（非表格），OCR 后用正则匹配：
    - "首选物理(\\d+)分" → 物理类分数线
    - "首选历史(\\d+)分" → 历史类分数线
    - 上下文含"本科"/"高职高专"/"特殊" → 切换批次
    """
    ocr = _get_ocr()
    result, _ = ocr(str(img_path))
    if not result:
        return pd.DataFrame()

    # 按 y 坐标排序后按行聚合（同 y 容差 25px 视为同行）
    sorted_result = sorted(result, key=lambda x: x[0][0][1])
    rows_text = []
    clusters = _cluster_by_y([(b, t, s) for b, t, s in sorted_result], y_tol=25)
    for cluster in clusters:
        cluster.sort(key=lambda x: x[0][0][0])
        rows_text.append(" ".join(t for _, t, _ in cluster))

    records = []
    cur_batch = "本科"
    cur_batch_section = "本科院校"

    for line in rows_text:
        # 切换批次段（注意"高职高专"含"专科"二字）
        if "高职高专" in line or ("专科" in line and "本科" not in line):
            cur_batch = "专科"
            cur_batch_section = "专科院校"
        elif "特殊" in line and ("招生" in line or "线" in line):
            cur_batch = "提前"
            cur_batch_section = "特殊类型招生"
        elif "本科" in line and "高职" not in line and "特殊" not in line:
            cur_batch = "本科"
            cur_batch_section = "本科院校"

        # 匹配"首选物理XXX分"和"首选历史XXX分"
        # 注意：一行可能同时含两个科类（如"本科：首选物理435分，首选历史443分。"）
        m_phy = re.search(r"首选物理[^\d]{0,5}(\d{3})\s*分", line)
        m_his = re.search(r"首选历史[^\d]{0,5}(\d{3})\s*分", line)

        # 特殊情况："首选物理、历史均为200分"
        m_both = re.search(r"首选物理[、，和与].{0,5}历史[均为]{0,3}(\d{3})\s*分", line)
        if m_both:
            score = int(m_both.group(1))
            if 100 <= score <= 750:
                records.append({
                    "province": "湖北", "year": year,
                    "batch_section": cur_batch_section, "batch": cur_batch,
                    "subject_group": "物理类", "line_type": "总分",
                    "lowest_score": score, "source_url": source_url,
                })
                records.append({
                    "province": "湖北", "year": year,
                    "batch_section": cur_batch_section, "batch": cur_batch,
                    "subject_group": "历史类", "line_type": "总分",
                    "lowest_score": score, "source_url": source_url,
                })
        else:
            if m_phy:
                score = int(m_phy.group(1))
                if 100 <= score <= 750:
                    records.append({
                        "province": "湖北", "year": year,
                        "batch_section": cur_batch_section, "batch": cur_batch,
                        "subject_group": "物理类", "line_type": "总分",
                        "lowest_score": score, "source_url": source_url,
                    })
            if m_his:
                score = int(m_his.group(1))
                if 100 <= score <= 750:
                    records.append({
                        "province": "湖北", "year": year,
                        "batch_section": cur_batch_section, "batch": cur_batch,
                        "subject_group": "历史类", "line_type": "总分",
                        "lowest_score": score, "source_url": source_url,
                    })

    df = pd.DataFrame(records, columns=[
        "province", "year", "batch_section", "batch",
        "subject_group", "line_type", "lowest_score", "source_url",
    ])
    df = df.drop_duplicates().reset_index(drop=True)
    return df


# ═══════════════════════════════════════════════════════════════
# 主入口（自测）
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python parse_hubei_pdf.py <pdf_or_image_path>")
        sys.exit(1)
    p = Path(sys.argv[1])
    if not p.exists():
        print(f"文件不存在: {p}")
        sys.exit(1)
    if p.suffix.lower() == ".pdf":
        # 默认按物理类 2024 解析（测试用）
        df = parse_toudang_pdf(p, year=2024, subject_group="物理类")
        print(df.head(10))
        print(f"\n共 {len(df)} 行")
    elif p.suffix.lower() in (".png", ".jpg", ".jpeg"):
        df = parse_yifenyiduan_image(p, year=2026)
        print(df.head(10))
        print(f"\n共 {len(df)} 行")
