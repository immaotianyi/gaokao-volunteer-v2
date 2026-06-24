#!/usr/bin/env python3
"""
复用前后对比验证脚本

对比维度：
1. 估值模型激活率（estimated_score 非空比例）
2. leakage_score 分布（均值/中位数/最高分/最低分）
3. 维度6（分数匹配度）激活情况
4. 用户分数适配层过滤效果
5. 结果可信度（有数据支撑的推荐 vs 纯规则推断）
"""
import pandas as pd
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.leakage_radar import find_leakage_opportunities

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def load_data(with_history: bool):
    df_2026 = pd.read_csv(DATA_DIR / "plans_2026.csv")
    df_2025 = pd.read_csv(DATA_DIR / "plans_2025.csv")
    df_history = None
    if with_history:
        hist_file = DATA_DIR / "admission_history.csv"
        if hist_file.exists():
            df_history = pd.read_csv(hist_file)
    return df_2026, df_2025, df_history


def run_scenario(province, subject, score, with_history):
    df_2026, df_2025, df_history = load_data(with_history)
    try:
        results = find_leakage_opportunities(
            df_current_year=df_2026.copy(),
            df_last_year=df_2025.copy(),
            df_history=df_history.copy() if df_history is not None else None,
            user_province=province,
            user_subject=subject,
            user_score=score,
        )
        return results
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        return []


def analyze_results(results, label):
    if not results:
        print(f"  {label}: 0 条结果")
        return None

    scores = [r.get("leakage_score", 0) for r in results]
    est_scores = [r.get("estimated_score") for r in results if r.get("estimated_score") is not None]
    has_estimation = len(est_scores)
    has_source = sum(1 for r in results if r.get("estimation_source"))

    # 维度6激活：看 score_breakdown 里有没有"历史分"或"估分"
    dim6_active = 0
    for r in results:
        breakdown = r.get("score_breakdown") or []
        for reason in breakdown:
            if "历史分" in reason or "估分" in reason:
                dim6_active += 1
                break

    stats = {
        "label": label,
        "total": len(results),
        "leakage_score_mean": round(sum(scores) / len(scores), 1) if scores else 0,
        "leakage_score_max": max(scores) if scores else 0,
        "leakage_score_min": min(scores) if scores else 0,
        "estimation_active": has_estimation,
        "estimation_rate": f"{has_estimation}/{len(results)} ({has_estimation*100//len(results)}%)",
        "dim6_active": dim6_active,
        "dim6_rate": f"{dim6_active}/{len(results)} ({dim6_active*100//len(results)}%)",
    }

    print(f"  {label}:")
    print(f"    结果数:        {stats['total']}")
    print(f"    leakage_score: 均值={stats['leakage_score_mean']} 最高={stats['leakage_score_max']} 最低={stats['leakage_score_min']}")
    print(f"    估值模型激活:  {stats['estimation_rate']}")
    print(f"    维度6激活:     {stats['dim6_rate']}")
    return stats


def main():
    print("=" * 70)
    print("捡漏雷达复用前后对比验证")
    print("=" * 70)

    scenarios = [
        ("山东", "物理类", 550),
        ("山东", "物理类", 600),
        ("山东", "历史类", 520),
        ("江苏", "物理类", 550),
        ("江苏", "历史类", 520),
        ("河南", "物理类", 580),
        ("四川", "物理类", 560),
        ("四川", "历史类", 520),
        ("广东", "物理类", 550),
    ]

    all_stats = []

    for province, subject, score in scenarios:
        print(f"\n{'─' * 60}")
        print(f"场景: {province} {subject} {score}分")
        print(f"{'─' * 60}")

        # 复用前（无 df_history）
        results_before = run_scenario(province, subject, score, with_history=False)
        stats_before = analyze_results(results_before, "复用前(无历史数据)")

        # 复用后（有 df_history）
        results_after = run_scenario(province, subject, score, with_history=True)
        stats_after = analyze_results(results_after, "复用后(有历史数据)")

        if stats_before and stats_after:
            delta_est = stats_after["estimation_active"] - stats_before["estimation_active"]
            delta_dim6 = stats_after["dim6_active"] - stats_before["dim6_active"]
            print(f"\n  📊 增量:")
            print(f"    估值激活数: +{delta_est}")
            print(f"    维度6激活数: +{delta_dim6}")
            if stats_before["leakage_score_max"] > 0:
                score_delta = stats_after["leakage_score_max"] - stats_before["leakage_score_max"]
                print(f"    最高分变化: {'+' if score_delta>=0 else ''}{score_delta}")

        all_stats.append({
            "scenario": f"{province} {subject} {score}分",
            "before": stats_before,
            "after": stats_after,
        })

    # 汇总
    print(f"\n{'=' * 70}")
    print("汇总对比")
    print(f"{'=' * 70}")
    print(f"{'场景':20s} | {'复用前估值率':15s} | {'复用后估值率':15s} | {'复用前维度6':15s} | {'复用后维度6':15s}")
    print(f"{'─'*85}")
    for s in all_stats:
        b = s["before"] or {}
        a = s["after"] or {}
        print(f"{s['scenario']:20s} | {b.get('estimation_rate','N/A'):15s} | {a.get('estimation_rate','N/A'):15s} | {b.get('dim6_rate','N/A'):15s} | {a.get('dim6_rate','N/A'):15s}")


if __name__ == "__main__":
    main()
