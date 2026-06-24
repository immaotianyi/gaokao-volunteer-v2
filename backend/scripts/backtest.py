#!/usr/bin/env python3
"""
回测与校准脚本 — 用已知数据验证算法有效性

用法：
  python3 backend/scripts/backtest.py --year 2025 --province 广东 --subject 物理类

功能：
  1. 用 year-1 数据作为"去年"，year 数据作为"今年"
  2. 跑捡漏算法得到候选列表
  3. 用 year 的真实录取分验证：
     a) 估值模型准确性（estimated vs real）
     b) 捡漏有效性（候选专业的真实分是否低于同校中位数）
  4. 输出校准建议
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.leakage_radar import find_leakage_opportunities


def run_backtest(
    plans_current: pd.DataFrame,
    plans_previous: pd.DataFrame,
    history: pd.DataFrame,
    province: str,
    subject: str,
    user_score: int = None,
) -> dict:
    """
    执行回测并返回报告。
    """
    results = find_leakage_opportunities(
        df_current_year=plans_current,
        df_last_year=plans_previous,
        df_history=history,
        user_province=province,
        user_subject=subject,
        user_score=user_score,
    )

    # 真实分索引
    score_col = None
    for c in plans_current.columns:
        if c.startswith("lowest_score_"):
            score_col = c
            break

    real_map = {}
    if score_col:
        for _, row in plans_current.iterrows():
            k = str(row["university_name"]) + "|" + str(row["major_name"])
            v = row[score_col]
            if pd.notna(v):
                real_map[k] = float(v)

    # 估值准确性
    estimation_errors = []
    for r in results:
        k = str(r.get("university_name", "")) + "|" + str(r.get("major_name", ""))
        real = real_map.get(k)
        est = r.get("estimated_score")
        if real is not None and est is not None:
            estimation_errors.append(float(est) - float(real))

    # 捡漏有效性
    province_data = plans_current[plans_current["province"] == province]
    true_pick = 0
    false_pick = 0
    neutral = 0

    for r in results:
        k = str(r.get("university_name", "")) + "|" + str(r.get("major_name", ""))
        real = real_map.get(k)
        if real is None:
            continue
        same_uni = province_data[province_data["university_name"] == r["university_name"]]
        if same_uni.empty:
            continue
        median = same_uni[score_col].median() if score_col else 0
        if real < median - 3:
            true_pick += 1
        elif real > median + 3:
            false_pick += 1
        else:
            neutral += 1

    # 构建报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "province": province,
        "subject": subject,
        "total_candidates": len(results),
        "estimation": {
            "sample_size": len(estimation_errors),
            "mean_error": float(np.mean(estimation_errors)) if estimation_errors else None,
            "median_error": float(np.median(estimation_errors)) if estimation_errors else None,
            "std_error": float(np.std(estimation_errors)) if estimation_errors else None,
            "within_15": sum(1 for e in estimation_errors if abs(e) <= 15),
            "within_20": sum(1 for e in estimation_errors if abs(e) <= 20),
        } if estimation_errors else None,
        "pick_effectiveness": {
            "true_pick": true_pick,
            "false_pick": false_pick,
            "neutral": neutral,
            "true_rate": true_pick / len(results) * 100 if results else 0,
        },
        "top5": [],
    }

    # TOP5
    for r in sorted(results, key=lambda x: x.get("leakage_score", 0), reverse=True)[:5]:
        k = str(r.get("university_name", "")) + "|" + str(r.get("major_name", ""))
        real = real_map.get(k)
        same_uni = province_data[province_data["university_name"] == r["university_name"]]
        median = same_uni[score_col].median() if score_col and not same_uni.empty else 0
        report["top5"].append({
            "university": r["university_name"],
            "major": r["major_name"],
            "leakage_score": r["leakage_score"],
            "estimated_score": r.get("estimated_score"),
            "real_score": int(real) if real else None,
            "uni_median": int(median) if median else None,
            "is_true_pick": real is not None and real < median - 3,
        })

    return report


def print_report(report: dict):
    """格式化打印回测报告。"""
    print("=" * 60)
    print("  捡漏雷达 回测报告")
    print("=" * 60)
    print(f"  省份: {report['province']}  科类: {report['subject']}")
    print(f"  候选总数: {report['total_candidates']}")
    print()

    est = report.get("estimation")
    if est and est["sample_size"] > 0:
        print("  [估值模型准确性]")
        print(f"    样本: {est['sample_size']}")
        print(f"    均值误差: {est['mean_error']:+.1f}分")
        print(f"    中位误差: {est['median_error']:+.1f}分")
        print(f"    标准差: {est['std_error']:.1f}分")
        print(f"    ±15分命中: {est['within_15']}/{est['sample_size']} = {est['within_15']/est['sample_size']*100:.1f}%")
        print(f"    ±20分命中: {est['within_20']}/{est['sample_size']} = {est['within_20']/est['sample_size']*100:.1f}%")
        print()

    eff = report["pick_effectiveness"]
    print("  [捡漏有效性]")
    print(f"    真捡漏(低于中位>3): {eff['true_pick']} = {eff['true_rate']:.1f}%")
    print(f"    反捡漏(高于中位>3): {eff['false_pick']}")
    print(f"    持平: {eff['neutral']}")
    print()

    print("  [TOP5 详情]")
    for i, t in enumerate(report["top5"]):
        tag = "✅真捡漏" if t["is_true_pick"] else "❌"
        print(f"    #{i+1} [{t['leakage_score']}分] {t['university']} {t['major']}")
        est_str = f"估{int(t['estimated_score'])}" if t['estimated_score'] else "无估分"
        real_str = f"实{int(t['real_score'])}" if t['real_score'] else "无真实分"
        med_str = f"中位{int(t['uni_median'])}" if t['uni_median'] else ""
        print(f"        {est_str} {real_str} {med_str} {tag}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="捡漏雷达回测")
    parser.add_argument("--year", type=int, default=2025, help="回测年份（作为'今年'）")
    parser.add_argument("--province", type=str, default="广东")
    parser.add_argument("--subject", type=str, default="物理类")
    parser.add_argument("--user-score", type=int, default=None)
    args = parser.parse_args()

    data_dir = Path(__file__).resolve().parent.parent / "data"
    prev_year = args.year - 1

    plans_current = data_dir / f"plans_{args.year}.csv"
    plans_previous = data_dir / f"plans_{prev_year}.csv"
    history_file = data_dir / "admission_history.csv"

    for fp, label in [(plans_current, f"{args.year}计划"), (plans_previous, f"{prev_year}计划")]:
        if not fp.exists():
            print(f"❌ 缺少数据: {label} ({fp})")
            print(f"   请先运行 import_real_data.py 导入数据")
            sys.exit(1)

    df_current = pd.read_csv(plans_current)
    df_previous = pd.read_csv(plans_previous)
    df_history = pd.read_csv(history_file) if history_file.exists() else None

    print(f"[{datetime.now().isoformat()}] 回测 {prev_year}→{args.year} | {args.province} {args.subject}")
    print(f"  今年数据: {len(df_current)} 行")
    print(f"  去年数据: {len(df_previous)} 行")
    print(f"  历史数据: {len(df_history) if df_history is not None else 0} 行")
    print()

    report = run_backtest(
        plans_current=df_current,
        plans_previous=df_previous,
        history=df_history,
        province=args.province,
        subject=args.subject,
        user_score=args.user_score,
    )

    print_report(report)


if __name__ == "__main__":
    main()
