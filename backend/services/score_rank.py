"""
分数-位次映射服务

功能：
1. 根据分数自动推算位次（基于一分一段表）
2. 根据位次反推分数
3. 默认使用 2026 年真实数据（2025 年为插值兜底）

数据文件：data/yifenyiduan_{year}.csv
格式：province, year, subject_group, batch, score, segment_count, cumulative_count
"""

import pandas as pd
from pathlib import Path
from typing import Optional, Tuple


# ── 全局缓存 ──
_score_tables: dict = {}  # {(year, subject_group, province): DataFrame}


def _load_table(year: int, subject_group: str, province: str = "广东") -> pd.DataFrame:
    """加载指定年份、科类、省份的一分一段表"""
    cache_key = (year, subject_group, province)
    if cache_key in _score_tables:
        return _score_tables[cache_key]

    data_dir = Path(__file__).parent.parent / "data"
    filepath = data_dir / f"yifenyiduan_{year}.csv"

    if not filepath.exists():
        raise FileNotFoundError(f"一分一段表不存在: {filepath}")

    df = pd.read_csv(filepath)
    # 过滤科类 + 省份（防止多省数据串省）
    if "province" not in df.columns:
        raise ValueError(f"一分一段表 {filepath.name} 缺少 province 列")
    df = df[(df["subject_group"] == subject_group) & (df["province"] == province)].copy()
    if df.empty:
        raise ValueError(f"一分一段表中没有 {province} {subject_group} 的数据")

    # 若存在 batch 列（2026+ 真实数据），默认取本科批
    # 志愿填报/捡漏雷达等业务均基于本科批位次
    if "batch" in df.columns:
        df_bk = df[df["batch"] == "本科"]
        if not df_bk.empty:
            df = df_bk

    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    _score_tables[cache_key] = df
    return df


def score_to_rank(score: int, year: int = 2026, subject_group: str = "物理类", province: str = "广东") -> int:
    """
    根据分数推算全省排位（累计人数）

    参数：
        score: 高考分数（0-750）
        year: 年份（默认2026，使用真实一分一段表）
        subject_group: 科类（物理类/历史类）
        province: 省份（默认广东，多省数据隔离）

    返回：
        该分数对应的全省累计人数（位次）
    """
    df = _load_table(year, subject_group, province)

    # 找到分数对应的行
    match = df[df["score"] == score]
    if not match.empty:
        return int(match.iloc[0]["cumulative_count"])

    # 如果精确分数不在表中，找最接近的（≤该分数的最大分数）
    lower = df[df["score"] <= score]
    if not lower.empty:
        return int(lower.iloc[0]["cumulative_count"])

    # 如果分数低于最低分，返回总人数
    return int(df["cumulative_count"].max())


def rank_to_score(rank: int, year: int = 2026, subject_group: str = "物理类", province: str = "广东") -> int:
    """
    根据位次反推分数

    参数：
        rank: 全省排位
        year: 年份
        subject_group: 科类
        province: 省份（默认广东，多省数据隔离）

    返回：
        该位次对应的分数
    """
    df = _load_table(year, subject_group, province)

    # df 已按分数降序排列；cumulative_count 随分数降低而递增
    # rank 位次对应的分数 = 累计人数 ≥ rank 的最高分（即 match 的第一行）
    match = df[df["cumulative_count"] >= rank]
    if match.empty:
        return int(df["score"].min())
    return int(match.iloc[0]["score"])


def get_score_range(
    score: int,
    tolerance: int = 5,
    year: int = 2026,
    subject_group: str = "物理类",
    province: str = "广东",
) -> dict:
    """
    获取分数对应的位次区间（用于捡漏雷达等功能的分数范围）

    返回：
        {
            "score": 560,
            "rank": 68000,
            "min_score": 555,
            "max_score": 565,
            "min_rank": 73000,
            "max_rank": 62000,
        }
    """
    rank = score_to_rank(score, year, subject_group, province)
    min_score = max(100, score - tolerance)
    max_score = min(750, score + tolerance)
    min_rank = score_to_rank(min_score, year, subject_group, province)
    max_rank = score_to_rank(max_score, year, subject_group, province)

    return {
        "score": score,
        "rank": rank,
        "min_score": min_score,
        "max_score": max_score,
        "min_rank": min_rank,
        "max_rank": max_rank,
        "tolerance": tolerance,
    }


def get_available_years() -> list[int]:
    """获取可用的一分一段表年份列表"""
    data_dir = Path(__file__).parent.parent / "data"
    years = []
    for f in data_dir.glob("yifenyiduan_*.csv"):
        try:
            year = int(f.stem.replace("yifenyiduan_", ""))
            years.append(year)
        except ValueError:
            pass
    return sorted(years)


def preload_all():
    """预加载所有可用的一分一段表（在应用启动时调用）。

    多省数据隔离：遍历每个 CSV 的 unique province 逐个预加载，
    避免爬虫追加新省数据后缓存串省。
    """
    for year in get_available_years():
        filepath = Path(__file__).parent.parent / "data" / f"yifenyiduan_{year}.csv"
        try:
            df_all = pd.read_csv(filepath)
        except Exception:
            continue
        if "province" not in df_all.columns:
            print(f"[ScoreRank] ⚠ {filepath.name} 缺少 province 列，跳过预加载")
            continue
        for province in df_all["province"].unique():
            for subject in ["物理类", "历史类"]:
                try:
                    _load_table(year, subject, province)
                    print(f"[ScoreRank] 已加载 {year}年 {province} {subject} 一分一段表")
                except Exception:
                    # 该省无该科类数据，静默跳过
                    pass
