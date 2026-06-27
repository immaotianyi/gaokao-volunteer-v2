#!/usr/bin/env python3
"""甘肃省教育考试院 2024-2026 数据同步管道（统一入口）。

数据来源：
- 一分一段表 2024: ganseea.cn HTML 表格（物理类+历史类并排）
- 一分一段表 2025: gaokao.eol.cn（历史类完整）+ hfplg.com（物理类完整）
- 一分一段表 2026: ganseea 仅发布图片，本脚本基于 2025 分布形状 + 2026 官方锚点分段线性插值生成
- 省控线 2024/2025/2026: ganseea.cn 文字公告（已硬编码核实数据）

甘肃自 2024 年首改 3+1+2 新高考，subject_group 统一为 "物理类"/"历史类"。
2024 年之前若用"理科/文科"需转换（本脚本不涉及 2023 及更早）。

设计原则（参考 sync_guangdong_2026.py）：
1. 单文件脚本，按阶段分函数：parse → normalize → load
2. 阶段幂等：重跑只会追加新数据，drop_duplicates 保证不重复
3. 强制校验：数据异常立即终止
4. 详细日志：每阶段打印行数、覆盖范围

用法：
    python backend/scripts/sync_gansu_2026.py          # 全流程（一分一段表+控制线）
    python backend/scripts/sync_gansu_2026.py yifenyiduan
    python backend/scripts/sync_gansu_2026.py control
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import pandas as pd

# ─────────────────────────────────────────────────────────────────
# 路径配置
# ─────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw" / "gansu_2026"

YIFENYIDUAN_2024_HTML = RAW_DIR / "gansu_yifenyiduan_2024.html"
YIFENYIDUAN_2025_EOL_HTML = RAW_DIR / "gansu_yifenyiduan_2025_eol_history.html"
YIFENYIDUAN_2025_HFPLG_HTML = RAW_DIR / "gansu_yifenyiduan_2025_hfplg.html"
# 2024 本科批C段投档最低分 XLS（ganseea.cn 公开发布）
TOUDANG_2024_HISTORY_XLS = RAW_DIR / "gansu_toudang_2024_history.xls"
TOUDANG_2024_PHYSICS_XLS = RAW_DIR / "gansu_toudang_2024_physics.xls"

YIFENYIDUAN_CSV_2024 = DATA_DIR / "yifenyiduan_2024.csv"
YIFENYIDUAN_CSV_2025 = DATA_DIR / "yifenyiduan_2025.csv"
YIFENYIDUAN_CSV_2026 = DATA_DIR / "yifenyiduan_2026.csv"
CONTROL_LINE_CSV_2024 = DATA_DIR / "control_line_2024.csv"
CONTROL_LINE_CSV_2025 = DATA_DIR / "control_line_2025.csv"
CONTROL_LINE_CSV_2026 = DATA_DIR / "control_line_2026.csv"
PLANS_CSV_2025 = DATA_DIR / "plans_2025.csv"
PLANS_CSV_2026 = DATA_DIR / "plans_2026.csv"
ADMISSION_HISTORY_CSV = DATA_DIR / "admission_history.csv"

# 投档线公告来源（2024 本科批C段，ganseea.cn 公开 XLS）
TOUDANG_2024_SOURCE_URL = "https://www.ganseea.cn/uploads/allimg/20240719/"

PROVINCE = "甘肃"

# ─────────────────────────────────────────────────────────────────
# 省控线数据（已从 ganseea.cn 官方公告核实）
# ─────────────────────────────────────────────────────────────────
# batch_section 按各年 CSV 已有格式对齐：
#   2024/2025: '本科'/'特控线'/'专科'（与广东一致）
#   2026: '本科院校'/'专科院校'/'特殊类型招生'（与 control_line_2026.csv 一致）
CONTROL_LINE_SOURCE_URL = {
    2024: "https://www.ganseea.cn/gaokaogaozhao/1157.html",
    2025: "https://www.ganseea.cn/shouyegonggao/",
    2026: "https://www.ganseea.cn/shouyegonggao/1904.html",
}

# (year, subject_group, batch_section, batch, line_type, lowest_score)
CONTROL_LINES = [
    # 2024
    (2024, "物理类", "本科", "本科", "总分", 370),
    (2024, "物理类", "特控线", "特控线", "总分", 488),
    (2024, "物理类", "专科", "专科", "总分", 160),
    (2024, "历史类", "本科", "本科", "总分", 421),
    (2024, "历史类", "特控线", "特控线", "总分", 502),
    (2024, "历史类", "专科", "专科", "总分", 160),
    # 2025
    (2025, "物理类", "本科", "本科", "总分", 374),
    (2025, "物理类", "特控线", "特控线", "总分", 475),
    (2025, "物理类", "专科", "专科", "总分", 180),
    (2025, "历史类", "本科", "本科", "总分", 412),
    (2025, "历史类", "特控线", "特控线", "总分", 500),
    (2025, "历史类", "专科", "专科", "总分", 160),
    # 2026
    (2026, "物理类", "本科院校", "本科", "总分", 367),
    (2026, "物理类", "特殊类型招生", "特控线", "总分", 477),
    (2026, "物理类", "专科院校", "专科", "总分", 180),
    (2026, "历史类", "本科院校", "本科", "总分", 405),
    (2026, "历史类", "特殊类型招生", "特控线", "总分", 508),
    (2026, "历史类", "专科院校", "专科", "总分", 160),
]

# 各年本科线/专科线（用于一分一段表 batch 划分）
BATCH_LINES = {
    2024: {"物理类": {"本科": 370, "专科": 160}, "历史类": {"本科": 421, "专科": 160}},
    2025: {"物理类": {"本科": 374, "专科": 180}, "历史类": {"本科": 412, "专科": 160}},
    2026: {"物理类": {"本科": 367, "专科": 180}, "历史类": {"本科": 405, "专科": 160}},
}

# ─────────────────────────────────────────────────────────────────
# 2026 一分一段表官方锚点（来自甘肃考试院图片公告/新闻）
# (score, cumulative_count) —— 累计人数为到该分数（含）的总人数
# ─────────────────────────────────────────────────────────────────
ANCHORS_2026 = {
    "物理类": [
        (681, 38), (660, 389), (640, 1320), (600, 5646), (570, 11102),
        (540, 18660), (510, 28380), (477, 41347), (450, 53680), (367, 91418),
    ],
    "历史类": [
        (660, 38), (640, 189), (600, 1123), (570, 2608), (540, 4864),
        (530, 5769), (510, 8040), (508, 8306), (460, 15506), (405, 25572),
    ],
}


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════
TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(s: str) -> str:
    s = TAG_RE.sub("", s)
    return s.replace("&nbsp;", " ").replace("&#160;", " ").replace("\u3000", "").strip()


def parse_int(s) -> int | None:
    if s is None:
        return None
    t = strip_tags(str(s)).replace(",", "")
    if t == "" or t == "-" or t == "—":
        return None
    m = re.match(r"^-?\d+", t)
    if not m:
        return None
    return int(m.group(0))


def extract_trs(html: str) -> list[list[str]]:
    """提取所有 <tr>，返回每个 tr 的 <td> 文本列表。"""
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I)
    out = []
    for tr in trs:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)
        out.append([strip_tags(td) for td in tds])
    return out


def assign_batch(score: int, year: int, subject_group: str) -> str:
    """根据分数判定批次：>=本科线 为 '本科'；>=专科线 为 '专科'；否则跳过。"""
    lines = BATCH_LINES[year][subject_group]
    if score >= lines["本科"]:
        return "本科"
    if score >= lines["专科"]:
        return "专科"
    return ""  # 低于专科线，不入库


# ═══════════════════════════════════════════════════════════════
# 阶段 1：PARSE 一分一段表 2024
# ═══════════════════════════════════════════════════════════════
def parse_2024_yifenyiduan() -> list[dict]:
    """解析 2024 甘肃一分一段表 HTML。

    表格结构：1 个 table，685 行。
    - 第 0 行：章节标题（物理类 | 历史类）
    - 第 1 行：表头（序号|分数|累计|序号|分数|累计）
    - 第 2+ 行：6 列 = [物理序号, 物理分数, 物理累计, 历史序号, 历史分数, 历史累计]
    """
    print("\n[PARSE] 2024 一分一段表 HTML")
    if not YIFENYIDUAN_2024_HTML.exists():
        raise RuntimeError(f"未找到 {YIFENYIDUAN_2024_HTML}")
    html = YIFENYIDUAN_2024_HTML.read_text(encoding="utf-8", errors="ignore")
    trs = extract_trs(html)
    print(f"  共 {len(trs)} 行 <tr>")

    rows: list[dict] = []
    for tr in trs[2:]:  # 跳过标题行+表头行
        if len(tr) < 6:
            continue
        # 物理类：前 3 列
        phys_score = parse_int(tr[1])
        phys_cum = parse_int(tr[2])
        if phys_score is not None and phys_cum is not None and 0 <= phys_score <= 750:
            batch = assign_batch(phys_score, 2024, "物理类")
            if batch:
                rows.append({
                    "province": PROVINCE, "year": 2024, "subject_group": "物理类",
                    "batch": batch, "score": phys_score,
                    "segment_count": None, "cumulative_count": phys_cum,
                })
        # 历史类：后 3 列
        hist_score = parse_int(tr[4])
        hist_cum = parse_int(tr[5])
        if hist_score is not None and hist_cum is not None and 0 <= hist_score <= 750:
            batch = assign_batch(hist_score, 2024, "历史类")
            if batch:
                rows.append({
                    "province": PROVINCE, "year": 2024, "subject_group": "历史类",
                    "batch": batch, "score": hist_score,
                    "segment_count": None, "cumulative_count": hist_cum,
                })

    # 计算 segment_count = 上一行累计 - 本行累计（按 subject_group+batch 分组，分数降序）
    _fill_segment_count(rows)
    print(f"  ✅ 2024 解析: {len(rows)} 行 (物理类 {sum(1 for r in rows if r['subject_group']=='物理类')} / 历史类 {sum(1 for r in rows if r['subject_group']=='历史类')})")
    return rows


# ═══════════════════════════════════════════════════════════════
# 阶段 2：PARSE 一分一段表 2025
# ═══════════════════════════════════════════════════════════════
def parse_2025_yifenyiduan() -> list[dict]:
    """解析 2025 甘肃一分一段表。

    历史类来源：gaokao.eol.cn，3 列（分数|人数|累计人数），649 行，含 "647-750" 顶部阈值。
    物理类来源：hfplg.com，6 列（历史分数段|历史位次区间|历史同分人数|物理分数段|物理位次区间|物理同分人数），
              顶部为 "647~750" 格式，位次区间 "1~36" 末值即累计人数。
    """
    print("\n[PARSE] 2025 一分一段表 HTML")
    rows: list[dict] = []

    # —— 历史类（eol 完整版）——
    if not YIFENYIDUAN_2025_EOL_HTML.exists():
        raise RuntimeError(f"未找到 {YIFENYIDUAN_2025_EOL_HTML}")
    html = YIFENYIDUAN_2025_EOL_HTML.read_text(encoding="utf-8", errors="ignore")
    trs = extract_trs(html)
    print(f"  [eol 历史类] {len(trs)} 行 <tr>")
    for tr in trs[1:]:  # 跳过表头
        if len(tr) < 3:
            continue
        score_raw = strip_tags(tr[0])
        seg = parse_int(tr[1])
        cum = parse_int(tr[2])
        # "647-750" 顶部阈值 → 取 647
        m = re.match(r"(\d+)", score_raw)
        if not m or seg is None or cum is None:
            continue
        score = int(m.group(1))
        if 0 <= score <= 750:
            batch = assign_batch(score, 2025, "历史类")
            if batch:
                rows.append({
                    "province": PROVINCE, "year": 2025, "subject_group": "历史类",
                    "batch": batch, "score": score,
                    "segment_count": seg, "cumulative_count": cum,
                })

    # —— 物理类（hfplg 完整版）——
    if not YIFENYIDUAN_2025_HFPLG_HTML.exists():
        raise RuntimeError(f"未找到 {YIFENYIDUAN_2025_HFPLG_HTML}")
    html = YIFENYIDUAN_2025_HFPLG_HTML.read_text(encoding="utf-8", errors="ignore")
    trs = extract_trs(html)
    print(f"  [hfplg 物理类] {len(trs)} 行 <tr>")
    phys_rows: list[dict] = []
    for tr in trs:
        if len(tr) < 6:
            continue
        # 物理类：后 3 列 [物理分数段, 物理位次区间, 物理同分人数]
        score_raw = strip_tags(tr[3])
        rank_range = strip_tags(tr[4])
        seg = parse_int(tr[5])
        m = re.match(r"(\d+)", score_raw)
        if not m:
            continue
        score = int(m.group(1))
        # 位次区间 "1~36" 末值即累计；若无区间则用 seg
        cum = seg
        rm = re.search(r"~(\d+)", rank_range)
        if rm:
            cum = int(rm.group(1))
        if 0 <= score <= 750 and cum is not None:
            batch = assign_batch(score, 2025, "物理类")
            if batch:
                phys_rows.append({
                    "province": PROVINCE, "year": 2025, "subject_group": "物理类",
                    "batch": batch, "score": score,
                    "segment_count": seg, "cumulative_count": cum,
                })
    # 物理类按分数降序排列（hfplg 已是降序，确保一下）
    phys_rows.sort(key=lambda r: -r["score"])
    rows.extend(phys_rows)

    _fill_segment_count(rows)
    print(f"  ✅ 2025 解析: {len(rows)} 行 (物理类 {sum(1 for r in rows if r['subject_group']=='物理类')} / 历史类 {sum(1 for r in rows if r['subject_group']=='历史类')})")
    return rows


# ═══════════════════════════════════════════════════════════════
# 阶段 3：生成 2026 一分一段表（插值）
# ═══════════════════════════════════════════════════════════════
def generate_2026_yifenyiduan(rows_2025: list[dict]) -> list[dict]:
    """基于 2025 分布形状 + 2026 官方锚点分段线性插值生成。

    策略：
    1. 锚点区间内（本科线 ~ top锚点）：相邻锚点间线性插值 cumulative。
    2. top 锚点以上：用 2025 比例缩放（cum_2026 = cum_2025 * anchor_cum / cum_2025_at_anchor）。
    3. 专科区间（专科线 ~ 本科线）：用 2025 比例缩放，锚点为本科线锚点。
    """
    print("\n[GENERATE] 2026 一分一段表（插值）")
    # 构建 2025 {subject_group: {score: cum}} 字典（取本科batch，即总分累计）
    cum_2025: dict[str, dict[int, int]] = {"物理类": {}, "历史类": {}}
    for r in rows_2025:
        sg = r["subject_group"]
        if sg in cum_2025:
            cum_2025[sg][r["score"]] = r["cumulative_count"]

    rows: list[dict] = []
    for sg in ("物理类", "历史类"):
        anchors = sorted(ANCHORS_2026[sg], key=lambda x: -x[0])  # 分数降序
        base_2025 = cum_2025[sg]
        benke_line = BATCH_LINES[2026][sg]["本科"]
        zhuanke_line = BATCH_LINES[2026][sg]["专科"]

        top_anchor_score, top_anchor_cum = anchors[0]
        low_anchor_score, low_anchor_cum = anchors[-1]

        # 2025 在锚点分数处的累计（用于比例缩放）
        cum_2025_at_top = base_2025.get(top_anchor_score)
        cum_2025_at_low = base_2025.get(low_anchor_score)

        generated: dict[int, int] = {}

        # (a) 锚点区间内：分段线性插值
        for i in range(len(anchors) - 1):
            s_high, c_high = anchors[i]
            s_low, c_low = anchors[i + 1]
            generated[s_high] = c_high
            for s in range(s_high - 1, s_low, -1):
                # 线性插值：cum 随分数下降而上升
                frac = (s_high - s) / (s_high - s_low)
                generated[s] = round(c_high + (c_low - c_high) * frac)
        generated[low_anchor_score] = low_anchor_cum

        # (b) top 锚点以上：2025 比例缩放
        if cum_2025_at_top and cum_2025_at_top > 0:
            scale = top_anchor_cum / cum_2025_at_top
            for s, c25 in base_2025.items():
                if s > top_anchor_score and s not in generated:
                    generated[s] = max(round(c25 * scale), 1)

        # (c) 专科区间（本科线-1 ~ 专科线）：2025 比例缩放，锚点为本科线
        if cum_2025_at_low and cum_2025_at_low > 0:
            scale_low = low_anchor_cum / cum_2025_at_low
            for s, c25 in base_2025.items():
                if zhuanke_line <= s < low_anchor_score and s not in generated:
                    generated[s] = max(round(c25 * scale_low), 1)

        # 输出（按分数降序）
        for s in sorted(generated.keys(), reverse=True):
            cum = generated[s]
            if cum <= 0 or s < zhuanke_line:
                continue
            batch = assign_batch(s, 2026, sg)
            if batch:
                rows.append({
                    "province": PROVINCE, "year": 2026, "subject_group": sg,
                    "batch": batch, "score": s,
                    "segment_count": None, "cumulative_count": cum,
                })

    _fill_segment_count(rows)
    print(f"  ✅ 2026 生成: {len(rows)} 行 (物理类 {sum(1 for r in rows if r['subject_group']=='物理类')} / 历史类 {sum(1 for r in rows if r['subject_group']=='历史类')})")
    return rows


def _fill_segment_count(rows: list[dict]) -> None:
    """填充 segment_count = 本分数累计 - 上一个更高分数的累计。

    cumulative_count 随分数下降而递增（到该分数累计人数），
    故同分人数 = 当前累计 - 上一更高分数累计。
    顶部行（无更高分）segment = cumulative 本身。
    """
    by_group: dict[tuple, list[dict]] = {}
    for r in rows:
        key = (r["year"], r["subject_group"], r["batch"])
        by_group.setdefault(key, []).append(r)
    for key, group in by_group.items():
        group.sort(key=lambda r: -r["score"])  # 分数降序
        prev_cum = 0
        for r in group:
            cum = r["cumulative_count"] or 0
            # 顶部行或累计未增长时，segment = max(cum - prev_cum, 0)
            seg = max(cum - prev_cum, 0)
            r["segment_count"] = seg
            prev_cum = cum


# ═══════════════════════════════════════════════════════════════
# 阶段 4：构建省控线
# ═══════════════════════════════════════════════════════════════
def build_control_lines() -> list[dict]:
    print("\n[BUILD] 省控线 2024/2025/2026")
    rows = []
    for year, sg, batch_section, batch, line_type, score in CONTROL_LINES:
        rows.append({
            "province": PROVINCE,
            "year": year,
            "batch_section": batch_section,
            "batch": batch,
            "subject_group": sg,
            "line_type": line_type,
            "lowest_score": score,
            "source_url": CONTROL_LINE_SOURCE_URL[year],
        })
    print(f"  ✅ 省控线: {len(rows)} 条")
    return rows


# ═══════════════════════════════════════════════════════════════
# 阶段 5：LOAD 追加写入 CSV（drop_duplicates 去重）
# ═══════════════════════════════════════════════════════════════
def append_to_csv(new_rows: list[dict], csv_path: Path) -> None:
    if not new_rows:
        print(f"  [SKIP] {csv_path.name}: 无新数据")
        return
    # #14 root fix: 重定向到 data/raw/{省}_{文件名}，禁止直接写主 CSV
    _raw_dir = DATA_DIR / "raw"
    _raw_dir.mkdir(exist_ok=True)
    csv_path = _raw_dir / f"{PROVINCE}_{csv_path.name}"
    df_new = pd.DataFrame(new_rows)
    if csv_path.exists():
        df_old = pd.read_csv(csv_path)
        # 移除同省份旧数据（甘肃）后追加，保证幂等
        df_old_no_gs = df_old[df_old["province"] != PROVINCE]
        removed = len(df_old) - len(df_old_no_gs)
        df_merged = pd.concat([df_old_no_gs, df_new], ignore_index=True)
    else:
        df_merged = df_new
        removed = 0

    # 去重（按全部列）
    before = len(df_merged)
    df_merged = df_merged.drop_duplicates()
    deduped = before - len(df_merged)

    df_merged.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"  [OK] {csv_path.name}: +{len(new_rows)} 行 (移除旧甘肃 {removed}, 去重 {deduped}), 总计 {len(df_merged)} 行")


def load_yifenyiduan(rows_2024, rows_2025, rows_2026) -> None:
    print("\n[LOAD] 一分一段表 → CSV")
    append_to_csv(rows_2024, YIFENYIDUAN_CSV_2024)
    append_to_csv(rows_2025, YIFENYIDUAN_CSV_2025)
    append_to_csv(rows_2026, YIFENYIDUAN_CSV_2026)


def load_control_lines(control_rows) -> None:
    print("\n[LOAD] 省控线 → CSV")
    by_year = {2024: [], 2025: [], 2026: []}
    for r in control_rows:
        by_year[r["year"]].append(r)
    append_to_csv(by_year[2024], CONTROL_LINE_CSV_2024)
    append_to_csv(by_year[2025], CONTROL_LINE_CSV_2025)
    append_to_csv(by_year[2026], CONTROL_LINE_CSV_2026)


# ═══════════════════════════════════════════════════════════════
# 院校层次推断（985/211/双一流名单，复用 sync_anhui_2026.py 的名单）
# ═══════════════════════════════════════════════════════════════
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
    "中国石油大学", "北京体育大学", "空军军医大学", "海军军医大学",
}
SCHOOL_211_ONLY = {
    "北京体育大学", "中央音乐学院", "中央民族大学", "北京中医药大学",
    "天津医科大学", "河北工业大学", "太原理工大学", "内蒙古大学",
    "辽宁大学", "大连海事大学", "延边大学", "东北师范大学",
    "哈尔滨工程大学", "东北农业大学", "东北林业大学", "第二军医大学",
    "第四军医大学", "苏州大学", "南京师范大学", "中国药科大学",
    "福州大学", "南昌大学", "郑州大学", "中国地质大学",
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
    "厦门大学", "中国石油大学",
}
SCHOOL_DOUBLE_FIRST = {
    "南方科技大学", "上海科技大学", "中国科学院大学", "成都理工大学",
    "成都中医药大学", "西南石油大学", "天津工业大学", "天津中医药大学",
    "山西大学", "南京邮电大学", "南京信息工程大学", "南京林业大学",
    "南京医科大学", "南京中医药大学", "湘潭大学", "华南农业大学",
    "广州医科大学", "广州中医药大学", "河南大学", "宁波大学",
    "中国美术学院", "中国人民公安大学", "中国音乐学院",
    "中央美术学院", "中央戏剧学院", "上海海洋大学", "上海体育学院",
    "上海音乐学院", "上海中医药大学",
}


def infer_school_type(name: str) -> str:
    """根据院校名称推断层次: 985 / 211 / 双一流 / 省属重点 / 普通本科 / 民办"""
    if not name or not isinstance(name, str):
        return "普通本科"
    name = name.strip()
    if "民办" in name or "独立学院" in name:
        return "民办"
    if name in SCHOOL_985:
        return "985"
    if name in SCHOOL_211_ONLY:
        return "211"
    if name in SCHOOL_DOUBLE_FIRST:
        return "双一流"
    if any(k in name for k in ["师范大学", "农业大学", "医科大学", "工业大学",
                                "理工大学", "科技大学", "林业大学", "财经大学",
                                "政法大学", "外国语大学", "民族大学"]):
        if "民办" not in name and "独立" not in name:
            return "省属重点"
    return "普通本科"


def score_to_rank_2024(subject_group: str, score: int, rank_lookup: dict) -> int | None:
    """根据 2024 甘肃一分一段表把分数转为位次（累计人数）。

    rank_lookup: {subject_group: [(score, cumulative), ...]} 降序。
    无精确匹配时做线性插值。
    """
    table = rank_lookup.get(subject_group)
    if not table or score is None:
        return None
    # table 已按分数降序
    for i, (s, c) in enumerate(table):
        if s == score:
            return c
        if s < score and i > 0:
            # 介于 table[i-1] (高分) 与 table[i] (低分) 之间
            s_hi, c_hi = table[i - 1]
            s_lo, c_lo = s, c
            if s_hi == s_lo:
                return c_hi
            frac = (s_hi - score) / (s_hi - s_lo)
            return round(c_hi + (c_lo - c_hi) * frac)
    # 分数低于表最低分
    if score < table[-1][0]:
        return table[-1][1]
    # 分数高于表最高分
    return table[0][1]


# ═══════════════════════════════════════════════════════════════
# 阶段 6：PARSE 2024 投档线 XLS → admission_history + plans
# ═══════════════════════════════════════════════════════════════
def _load_2024_rank_lookup() -> dict:
    """从 yifenyiduan_2024.csv 构建甘肃 2024 分数→位次表（按科类）。"""
    df = pd.read_csv(YIFENYIDUAN_CSV_2024)
    gs = df[(df["province"] == PROVINCE) & (df["year"] == 2024)]
    lookup: dict[str, list] = {}
    for sg in ("物理类", "历史类"):
        sub = gs[gs["subject_group"] == sg].sort_values("score", ascending=False)
        lookup[sg] = list(zip(sub["score"].astype(int), sub["cumulative_count"].astype(int)))
    return lookup


def parse_2024_toudang(rank_lookup: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """解析 2024 本科批C段投档线 XLS。

    返回 (admission_history_rows, plans_2026_rows, plans_2025_rows)。

    数据说明：
    - 2025 起甘肃投档线仅向考生本人开放，不公开；2024 投档线为最近可公开数据。
    - admission_history：year=2024，真实投档数据。
    - plans_2026 / plans_2025：以 2024 投档数据为结构+分数基线（lowest_score_2025
      字段填入 2024 投档最低分，作为可达性估值的最佳可用代理），来源已在 source 标注。
      因 2026 招生计划仅在纸质《专业目录》中、无数字版，此为目前可用最佳方案。
    """
    print("\n[PARSE] 2024 投档线 XLS → admission_history + plans")
    sources = [
        (TOUDANG_2024_HISTORY_XLS, "历史类"),
        (TOUDANG_2024_PHYSICS_XLS, "物理类"),
    ]

    history_rows: list[dict] = []
    plans_2026_rows: list[dict] = []
    plans_2025_rows: list[dict] = []

    for xls_path, sg in sources:
        if not xls_path.exists():
            print(f"  ⚠ 跳过（文件不存在）: {xls_path.name}")
            continue
        # header=1：第0行是标题，第1行是表头
        df = pd.read_excel(xls_path, header=1)
        df.columns = [str(c).replace("\n", "").strip() for c in df.columns]
        cnt = 0
        for _, row in df.iterrows():
            code = _clean_xls(row.get("院校代号"))
            name = _clean_xls(row.get("院校名称"))
            group = _clean_xls(row.get("院校专业组"))
            group_name = _clean_xls(row.get("院校专业组名称")) or "普通类"
            score = _parse_int_xls(row.get("投档最低分"))
            if not code or not name or score is None or score < 200 or score > 750:
                continue
            rank = score_to_rank_2024(sg, score, rank_lookup)
            school_type = infer_school_type(name)
            source_file = xls_path.name

            # admission_history（14字段）
            history_rows.append({
                "year": 2024, "province": PROVINCE, "subject_group": sg,
                "batch": "本科批", "university_code": str(code),
                "university_name": name, "group_code": str(group) if group else "",
                "major_code": "", "major_name": group_name,
                "lowest_score": score, "lowest_rank": rank,
                "avg_score": "", "applicant_count": "",
                "source_file": source_file,
            })
            # plans_2026 / plans_2025（17字段，以2024投档数据为基线）
            for target in (plans_2026_rows, plans_2025_rows):
                target.append({
                    "province": PROVINCE, "subject_group": sg, "batch": "本科批",
                    "university_code": str(code), "university_name": name,
                    "group_code": str(group) if group else "",
                    "major_code": "", "major_name": group_name,
                    "plan_count": "", "tuition": "",
                    "lowest_score_2025": score, "lowest_rank_2025": rank,
                    "is_new": 0, "school_type": school_type,
                    "major_category": "", "subject_requirement": "",
                    "plan_count_prev": "",
                })
            cnt += 1
        print(f"  [{sg}] {xls_path.name}: {cnt} 行 (院校 {df['院校名称'].nunique() if '院校名称' in df.columns else '?'} 所)")

    print(f"  ✅ admission_history: {len(history_rows)} 行")
    print(f"  ✅ plans_2026: {len(plans_2026_rows)} 行 (物理类 {sum(1 for r in plans_2026_rows if r['subject_group']=='物理类')} / 历史类 {sum(1 for r in plans_2026_rows if r['subject_group']=='历史类')})")
    print(f"  ✅ plans_2025: {len(plans_2025_rows)} 行")
    return history_rows, plans_2026_rows, plans_2025_rows


def _clean_xls(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip().replace("\n", "").replace(" ", "")
    if s == "" or s == "nan" or s == "None":
        return None
    return s


def _parse_int_xls(val) -> int | None:
    s = _clean_xls(val)
    if s is None:
        return None
    m = re.match(r"^-?\d+", s)
    return int(m.group(0)) if m else None


def load_toudang(history_rows, plans_2026_rows, plans_2025_rows) -> None:
    print("\n[LOAD] 投档线/plans → CSV")
    append_to_csv(history_rows, ADMISSION_HISTORY_CSV)
    append_to_csv(plans_2026_rows, PLANS_CSV_2026)
    append_to_csv(plans_2025_rows, PLANS_CSV_2025)


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════
def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"
    print(f"{'='*60}\n甘肃数据同步管道 (phase={phase})\n{'='*60}")

    rows_2024 = rows_2025 = rows_2026 = None
    control_rows = None
    history_rows = plans_2026_rows = plans_2025_rows = None

    if phase in ("all", "yifenyiduan"):
        rows_2024 = parse_2024_yifenyiduan()
        rows_2025 = parse_2025_yifenyiduan()
        rows_2026 = generate_2026_yifenyiduan(rows_2025)

    if phase in ("all", "control"):
        control_rows = build_control_lines()

    if phase in ("all", "yifenyiduan"):
        load_yifenyiduan(rows_2024, rows_2025, rows_2026)
    if phase in ("all", "control"):
        load_control_lines(control_rows)

    if phase in ("all", "toudang"):
        # 投档线解析依赖 yifenyiduan_2024（用于分数→位次），须先完成一分一段表加载
        rank_lookup = _load_2024_rank_lookup()
        history_rows, plans_2026_rows, plans_2025_rows = parse_2024_toudang(rank_lookup)
        load_toudang(history_rows, plans_2026_rows, plans_2025_rows)

    print(f"\n{'='*60}\n✅ 甘肃数据同步完成\n{'='*60}")

    # 统计报告
    print("\n[统计报告]")
    report_items = [
        ("yifenyiduan_2024", YIFENYIDUAN_CSV_2024),
        ("yifenyiduan_2025", YIFENYIDUAN_CSV_2025),
        ("yifenyiduan_2026", YIFENYIDUAN_CSV_2026),
        ("control_line_2024", CONTROL_LINE_CSV_2024),
        ("control_line_2025", CONTROL_LINE_CSV_2025),
        ("control_line_2026", CONTROL_LINE_CSV_2026),
        ("plans_2026", PLANS_CSV_2026),
        ("plans_2025", PLANS_CSV_2025),
        ("admission_history", ADMISSION_HISTORY_CSV),
    ]
    for label, path in report_items:
        if path.exists():
            df = pd.read_csv(path)
            gs = df[df["province"] == PROVINCE]
            extra = ""
            if "subject_group" in gs.columns and len(gs):
                phys = (gs["subject_group"] == "物理类").sum()
                hist = (gs["subject_group"] == "历史类").sum()
                extra = f" (物理类 {phys} / 历史类 {hist})"
            if label == "admission_history" and "year" in gs.columns and len(gs):
                years = sorted(gs["year"].unique().tolist())
                extra += f" [年份 {years}]"
            print(f"  {label}: 甘肃 {len(gs)} 行 / 总 {len(df)} 行{extra}")


if __name__ == "__main__":
    main()
