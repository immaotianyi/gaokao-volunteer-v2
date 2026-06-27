#!/usr/bin/env python3
"""湖北省教育考试院 2024-2026 数据同步管道（统一入口）。

数据源：https://www.hbea.edu.cn （已下载到 data/raw/hubei_2026/）
覆盖：
  - 投档线 PDF: 2023 物理 / 2024 物理+历史 (3 个 PDF)
  - 一分一段表 图片: 2024 (10 张) / 2025 (12 张) / 2026 (10 张) 共 32 张
  - 省控线 图片: 2025 (1 张) / 2026 (1 张) 共 2 张

设计原则：
1. 解析逻辑全部在 parse_hubei_pdf.py（已测试通过），本脚本只做编排
2. 追加模式：保留其他省份已有数据，只新增/替换湖北数据
3. 严格遵循 _common_spec.md 字段顺序
4. yifenyiduan 跨图合并后再次应用累计人数单调过滤
5. admission_history.csv 中湖北旧数据使用 XF+6位 格式（与 PDF 原生 A00105 不一致），
   先删除再追加，保证省内数据格式一致

用法：
    python3 backend/scripts/sync_hubei_2026.py            # 全流程
    python3 backend/scripts/sync_hubei_2026.py toudang    # 仅投档线
    python3 backend/scripts/sync_hubei_2026.py yifenyiduan # 仅一分一段
    python3 backend/scripts/sync_hubei_2026.py control     # 仅省控线
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pandas as pd

# 让脚本能在不安装为包的情况下导入同目录模块
sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_hubei_pdf import (  # noqa: E402
    parse_toudang_pdf,
    parse_yifenyiduan_image,
    parse_control_line_image,
)

# ─────────────────────────────────────────────────────────────────
# 路径配置
# ─────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw" / "hubei_2026"

TOUDANG_DIR = RAW_DIR / "toudang"
YIFYD_2024_DIR = RAW_DIR / "yifenyiduan_2024"
YIFYD_2025_DIR = RAW_DIR / "yifenyiduan_2025"
YIFYD_2026_DIR = RAW_DIR / "yifenyiduan_2026"
CTRL_2025_DIR = RAW_DIR / "control_line_2025"
CTRL_2026_DIR = RAW_DIR / "control_line_2026"

ADMISSION_CSV = DATA_DIR / "admission_history.csv"
YIFYD_CSV_TEMPLATE = "yifenyiduan_{year}.csv"
CTRL_CSV_TEMPLATE = "control_line_{year}.csv"

PROVINCE = "湖北"

# 投档线 PDF 配置（subject_group 与 PDF 标题"首选物理/历史"对应）
TOUDANG_PDFS = [
    {"path": TOUDANG_DIR / "hubei_toudang_2023_physics.pdf", "year": 2023, "sg": "物理类"},
    {"path": TOUDANG_DIR / "hubei_toudang_2024_physics.pdf", "year": 2024, "sg": "物理类"},
    {"path": TOUDANG_DIR / "hubei_toudang_2024_history.pdf", "year": 2024, "sg": "历史类"},
]

# 一分一段表图片目录配置
YIFYD_DIRS = [
    (2024, YIFYD_2024_DIR),
    (2025, YIFYD_2025_DIR),
    (2026, YIFYD_2026_DIR),
]

# 省控线图片配置（source_url 用考试院公告页 URL 占位，便于追溯）
CTRL_IMAGES = [
    {
        "path": CTRL_2025_DIR / "control_line_2025_01.jpg",
        "year": 2025,
        "source_url": "https://www.hbea.edu.cn/",
    },
    {
        "path": CTRL_2026_DIR / "control_line_2026_1.webp.png",
        "year": 2026,
        "source_url": "https://www.hbea.edu.cn/",
    },
]

# 编码：所有现有 CSV 都是 UTF-8 无 BOM，保持一致
CSV_ENCODING = "utf-8"

# ─────────────────────────────────────────────────────────────────
# 通用工具
# ─────────────────────────────────────────────────────────────────


def _read_csv_safe(path: Path) -> pd.DataFrame:
    """读取 CSV，文件不存在返回空 DataFrame。"""
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding=CSV_ENCODING, dtype=str)


def _write_csv_safe(df: pd.DataFrame, path: Path) -> None:
    """写 CSV（UTF-8 无 BOM，index 不保留）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding=CSV_ENCODING)


def _append_with_replace(
    new_df: pd.DataFrame,
    csv_path: Path,
    province_key: str = "province",
    drop_old_province: bool = False,
) -> tuple[int, int]:
    """安全追加：先合并已有数据，按全行去重，写回。

    Args:
        new_df: 待追加数据
        csv_path: 目标 CSV 路径
        province_key: 省份字段名
        drop_old_province: True 时先删除该省所有旧数据（用于格式变更场景）

    Returns:
        (新增行数, 写入后该省总行数)
    """
    if new_df is None or len(new_df) == 0:
        return (0, 0)

    # #14 root fix: 重定向到 data/raw/{省}_{文件名}，禁止直接写主 CSV
    _raw_dir = DATA_DIR / "raw"
    _raw_dir.mkdir(exist_ok=True)
    csv_path = _raw_dir / f"{PROVINCE}_{csv_path.name}"

    existing = _read_csv_safe(csv_path)
    removed = 0
    if drop_old_province and len(existing) > 0 and province_key in existing.columns:
        before = len(existing)
        existing = existing[existing[province_key] != new_df[province_key].iloc[0]]
        removed = before - len(existing)

    # 字段对齐：以 new_df 列顺序为准，缺失列补空
    if len(existing) > 0:
        for col in new_df.columns:
            if col not in existing.columns:
                existing[col] = ""
        existing = existing[new_df.columns]

    merged = pd.concat([existing, new_df], ignore_index=True)
    # 全字段去重（避免重复追加）
    before_dedup = len(merged)
    merged = merged.drop_duplicates().reset_index(drop=True)
    deduped = before_dedup - len(merged)

    _write_csv_safe(merged, csv_path)

    province_val = new_df[province_key].iloc[0] if len(new_df) > 0 else ""
    province_total = int((merged[province_key] == province_val).sum()) if province_key in merged.columns else 0
    print(f"  [CSV] {csv_path.name}: 追加 {len(new_df)} 行, 删除旧数据 {removed} 行, 去重 {deduped} 行, "
          f"该省总计 {province_total} 行")
    return (len(new_df), province_total)


# ─────────────────────────═══════════════════════════════════════
# 阶段 1：投档线 → admission_history.csv
# ─────────────────────────────────────────────────────────────────
def parse_toudang_history() -> pd.DataFrame:
    """解析所有投档线 PDF，返回合并 DataFrame。"""
    print(f"\n{'='*60}")
    print(f"[湖北] 阶段 1: 投档线 PDF 解析")
    print(f"{'='*60}")

    all_dfs = []
    for cfg in TOUDANG_PDFS:
        path = cfg["path"]
        if not path.exists():
            print(f"  [SKIP] 文件不存在: {path.name}")
            continue
        print(f"  [PARSE] {path.name} (year={cfg['year']}, sg={cfg['sg']})")
        df = parse_toudang_pdf(path, year=cfg["year"], subject_group=cfg["sg"])
        print(f"  [OK] {path.name} -> {len(df)} 行 (有分: {df['lowest_score'].notna().sum()})")
        all_dfs.append(df)

    if not all_dfs:
        return pd.DataFrame()

    merged = pd.concat(all_dfs, ignore_index=True)
    # 按 year+subject_group 统计
    stats = merged.groupby(["year", "subject_group"]).size().reset_index(name="count")
    print(f"\n  [汇总] 投档线总计: {len(merged)} 行")
    for _, r in stats.iterrows():
        print(f"    {r['year']} {r['subject_group']}: {r['count']} 行")
    return merged


# ─────────────────────────═══════════════════════════════════════
# 阶段 2：一分一段表 → yifenyiduan_{year}.csv
# ─────────────────────────────────────────────────────────────────
def _cross_image_monotonic_filter(df: pd.DataFrame) -> pd.DataFrame:
    """跨图合并后再次应用累计人数单调过滤。

    每张图内已做单调过滤，但跨图合并后可能产生重叠 score 或累计跳跃，
    需重新去重 + 排序 + 单调过滤。
    """
    if len(df) == 0:
        return df

    # 按 (year, subject_group, score) 去重，保留累计人数最大的
    df = df.sort_values("cumulative_count", ascending=False).drop_duplicates(
        subset=["year", "subject_group", "score"]
    )

    # 按 subject_group 分组，每组内按 score 降序、累计人数递增过滤
    out = []
    for sg, group in df.groupby("subject_group", sort=False):
        group = group.sort_values("score", ascending=False).reset_index(drop=True)
        kept = []
        prev_cum = 0
        for _, r in group.iterrows():
            cum = int(r["cumulative_count"]) if pd.notna(r["cumulative_count"]) else 0
            seg = int(r["segment_count"]) if pd.notna(r["segment_count"]) else 0
            if cum >= prev_cum and cum >= seg:
                kept.append(r)
                prev_cum = cum
        out.extend(kept)

    if not out:
        return pd.DataFrame(columns=df.columns)
    return pd.DataFrame(out).reset_index(drop=True)


def parse_yifenyiduan_year(year: int, img_dir: Path) -> pd.DataFrame:
    """解析某一年所有一分一段表图片，返回跨图合并+单调过滤后的 DataFrame。"""
    print(f"\n  [PARSE] year={year} 图片目录: {img_dir.name}")
    if not img_dir.exists():
        print(f"  [SKIP] 目录不存在")
        return pd.DataFrame()

    images = sorted(list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png")) + list(img_dir.glob("*.jpeg")))
    if not images:
        print(f"  [SKIP] 无图片文件")
        return pd.DataFrame()

    print(f"  发现 {len(images)} 张图片")
    all_dfs = []
    for img in images:
        try:
            df = parse_yifenyiduan_image(img, year=year)
        except Exception as e:
            print(f"    [FAIL] {img.name}: {e}")
            continue
        if len(df) == 0:
            print(f"    [EMPTY] {img.name}: 未识别科类或无数据")
        else:
            sg = df["subject_group"].iloc[0] if "subject_group" in df.columns else "?"
            print(f"    [OK] {img.name}: {len(df)} 行 ({sg}, 分数 {df['score'].min()}-{df['score'].max()})")
            all_dfs.append(df)

    if not all_dfs:
        return pd.DataFrame()

    merged = pd.concat(all_dfs, ignore_index=True)
    print(f"  [合并前] {len(merged)} 行")
    filtered = _cross_image_monotonic_filter(merged)
    print(f"  [合并后] {len(filtered)} 行 (跨图去重+单调过滤)")

    if len(filtered) > 0:
        for sg, group in filtered.groupby("subject_group"):
            print(f"    {sg}: {len(group)} 行 (分数 {group['score'].min()}-{group['score'].max()})")
    return filtered


def parse_yifenyiduan() -> dict[int, pd.DataFrame]:
    """解析所有年份的一分一段表，返回 {year: DataFrame}。"""
    print(f"\n{'='*60}")
    print(f"[湖北] 阶段 2: 一分一段表 图片 OCR 解析")
    print(f"{'='*60}")

    result = {}
    for year, img_dir in YIFYD_DIRS:
        df = parse_yifenyiduan_year(year, img_dir)
        result[year] = df
    return result


# ─────────────────────────═══════════════════════════════════════
# 阶段 3：省控线 → control_line_{year}.csv
# ─────────────────────────────────────────────────────────────────
def parse_control_line() -> dict[int, pd.DataFrame]:
    """解析所有省控线图片，返回 {year: DataFrame}。"""
    print(f"\n{'='*60}")
    print(f"[湖北] 阶段 3: 省控线 图片 OCR 解析")
    print(f"{'='*60}")

    result = {}
    for cfg in CTRL_IMAGES:
        path = cfg["path"]
        if not path.exists():
            print(f"  [SKIP] 文件不存在: {path}")
            continue
        print(f"\n  [PARSE] {path.name} (year={cfg['year']})")
        try:
            df = parse_control_line_image(path, year=cfg["year"], source_url=cfg["source_url"])
        except Exception as e:
            print(f"  [FAIL] {path.name}: {e}")
            continue
        print(f"  [OK] {path.name} -> {len(df)} 行")
        if len(df) > 0:
            # 按 batch_section, subject_group 排序打印
            for (bs, sg), group in df.groupby(["batch_section", "subject_group"], sort=False):
                if len(group) > 0:
                    print(f"    {bs} / {sg}: {group['lowest_score'].iloc[0]} 分")
        result[cfg["year"]] = df
    return result


# ─────────────────═══════════════════════════════════════════════
# 主入口
# ─────────────────────────────────────────────────────────────────
def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"

    print(f"\n{'#'*60}")
    print(f"# 湖北 高考数据同步")
    print(f"# 数据源: https://www.hbea.edu.cn")
    print(f"# 阶段: {phase}")
    print(f"{'#'*60}")

    stats = {
        "admission_history": {"rows": 0, "by_year_sg": {}},
        "yifenyiduan": {"rows": 0, "by_year_sg": {}},
        "control_line": {"rows": 0, "by_year_sg": {}},
    }

    # ── 阶段 1: 投档线 ──
    if phase in ("all", "toudang"):
        df_toudang = parse_toudang_history()
        if len(df_toudang) > 0:
            # admission_history.csv 中湖北旧数据格式不一致（XF+6位 vs A00105），
            # 先删除旧湖北数据再追加新格式数据
            added, total = _append_with_replace(
                df_toudang, ADMISSION_CSV, province_key="province", drop_old_province=True
            )
            stats["admission_history"]["rows"] = added
            grp = df_toudang.groupby(["year", "subject_group"]).size()
            for (y, sg), n in grp.items():
                stats["admission_history"]["by_year_sg"][f"{y} {sg}"] = int(n)

    # ── 阶段 2: 一分一段表 ──
    if phase in ("all", "yifenyiduan"):
        yifyd_result = parse_yifenyiduan()
        for year, df in yifyd_result.items():
            if len(df) == 0:
                continue
            csv_path = DATA_DIR / YIFYD_CSV_TEMPLATE.format(year=year)
            # 一分一段表当前无湖北数据，无需 drop_old_province
            added, total = _append_with_replace(
                df, csv_path, province_key="province", drop_old_province=True
            )
            stats["yifenyiduan"]["rows"] += added
            grp = df.groupby(["subject_group"]).size()
            for sg, n in grp.items():
                stats["yifenyiduan"]["by_year_sg"][f"{year} {sg}"] = int(n)

    # ── 阶段 3: 省控线 ──
    if phase in ("all", "control"):
        ctrl_result = parse_control_line()
        for year, df in ctrl_result.items():
            if len(df) == 0:
                continue
            csv_path = DATA_DIR / CTRL_CSV_TEMPLATE.format(year=year)
            added, total = _append_with_replace(
                df, csv_path, province_key="province", drop_old_province=True
            )
            stats["control_line"]["rows"] += added
            grp = df.groupby(["subject_group"]).size()
            for sg, n in grp.items():
                stats["control_line"]["by_year_sg"][f"{year} {sg}"] = int(n)

    # ── 输出统计报告 ──
    print(f"\n\n{'='*60}")
    print(f"========== 湖北 数据爬取报告 ==========")
    print(f"{'='*60}")
    print(f"admission_history.csv:  追加 {stats['admission_history']['rows']} 行")
    for k, v in stats["admission_history"]["by_year_sg"].items():
        print(f"  └─ {k}: {v}")
    print(f"yifenyiduan_*.csv:      追加 {stats['yifenyiduan']['rows']} 行")
    for k, v in stats["yifenyiduan"]["by_year_sg"].items():
        print(f"  └─ {k}: {v}")
    print(f"control_line_*.csv:     追加 {stats['control_line']['rows']} 行")
    for k, v in stats["control_line"]["by_year_sg"].items():
        print(f"  └─ {k}: {v}")
    print(f"\n原始文件目录: {RAW_DIR}")
    raw_count = sum(1 for _ in RAW_DIR.rglob("*") if _.is_file())
    print(f"原始文件数: {raw_count}")
    print(f"\n[完成] 请重启后端服务以加载新数据: uvicorn main:app --reload")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
