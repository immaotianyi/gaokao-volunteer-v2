"""
分数-位次映射服务

功能：
1. 根据分数自动推算位次（基于一分一段表）
2. 根据位次反推分数
3. 支持2025年数据（2026年一分一段表公布后直接替换文件即可）

数据文件：data/yifenyiduan_{year}.csv
格式：province, year, subject_group, score, segment_count, cumulative_count
"""

import pandas as pd
from pathlib import Path
from typing import Optional, Tuple


# ── 全局缓存 ──
_score_tables: dict = {}  # {(year, subject_group): DataFrame}


def _load_table(year: int, subject_group: str) -> pd.DataFrame:
    """加载指定年份和科类的一分一段表"""
    cache_key = (year, subject_group)
    if cache_key in _score_tables:
        return _score_tables[cache_key]

    data_dir = Path(__file__).parent.parent / "data"
    filepath = data_dir / f"yifenyiduan_{year}.csv"

    if not filepath.exists():
        raise FileNotFoundError(f"一分一段表不存在: {filepath}")

    df = pd.read_csv(filepath)
    # 过滤科类
    df = df[df["subject_group"] == subject_group].copy()
    if df.empty:
        raise ValueError(f"一分一段表中没有 {subject_group} 的数据")

    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    _score_tables[cache_key] = df
    return df


def score_to_rank(score: int, year: int = 2025, subject_group: str = "物理类") -> int:
    """
    根据分数推算全省排位（累计人数）

    参数：
        score: 高考分数（0-750）
        year: 年份（默认2025）
        subject_group: 科类（物理类/历史类）

    返回：
        该分数对应的全省累计人数（位次）
    """
    df = _load_table(year, subject_group)

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


def rank_to_score(rank: int, year: int = 2025, subject_group: str = "物理类") -> int:
    """
    根据位次反推分数

    参数：
        rank: 全省排位
        year: 年份
        subject_group: 科类

    返回：
        该位次对应的分数
    """
    df = _load_table(year, subject_group)

    # 找到累计人数 ≥ rank 的第一个分数（从高到低排）
    match = df[df["cumulative_count"] >= rank]
    if match.empty:
        return int(df["score"].min())
    return int(match.iloc[-1]["score"])


def get_score_range(
    score: int,
    tolerance: int = 5,
    year: int = 2025,
    subject_group: str = "物理类",
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
    rank = score_to_rank(score, year, subject_group)
    min_score = max(100, score - tolerance)
    max_score = min(750, score + tolerance)
    min_rank = score_to_rank(min_score, year, subject_group)
    max_rank = score_to_rank(max_score, year, subject_group)

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
    """预加载所有可用的一分一段表（在应用启动时调用）"""
    for year in get_available_years():
        for subject in ["物理类", "历史类"]:
            try:
                _load_table(year, subject)
                print(f"[ScoreRank] 已加载 {year}年 {subject} 一分一段表")
            except Exception as e:
                print(f"[ScoreRank] 加载 {year}年 {subject} 失败: {e}")
