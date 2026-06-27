#!/usr/bin/env python3
"""merge_all.py — 唯一可写主 CSV 的进程（#14 root fix）

扫描 data/raw/ 下所有 {省}_{类型}.csv，按类型分组合并，跑校验闸门（#20），
原子写（.tmp → os.replace）重建主 CSV。

用法：
    python backend/scripts/merge_all.py              # 全量合并
    python backend/scripts/merge_all.py --dry-run     # 只校验不写
    python backend/scripts/merge_all.py --type yifenyiduan_2026  # 只合并指定类型

红线：
- 主 CSV 只能由本脚本写，任何 sync 脚本直接写主 CSV 视为事故复发
- 校验闸门不达标则报错退出，不写主 CSV
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"

# 类型 → 主 CSV 文件名映射
TYPE_MAP = {
    "plans_2026": "plans_2026.csv",
    "plans_2025": "plans_2025.csv",
    "plans_2024": "plans_2024.csv",
    "yifenyiduan_2024": "yifenyiduan_2024.csv",
    "yifenyiduan_2025": "yifenyiduan_2025.csv",
    "yifenyiduan_2026": "yifenyiduan_2026.csv",
    "admission_history": "admission_history.csv",
    "control_line_2024": "control_line_2024.csv",
    "control_line_2025": "control_line_2025.csv",
    "control_line_2026": "control_line_2026.csv",
}

# 去重 subset（按类型）
DEDUP_SUBSET = {
    "plans_2026": ["province", "subject_group", "batch", "university_code", "group_code", "major_code"],
    "plans_2025": ["province", "subject_group", "batch", "university_code", "group_code", "major_code"],
    "plans_2024": ["province", "subject_group", "batch", "university_code", "group_code", "major_code"],
    "yifenyiduan_2024": ["province", "year", "subject_group", "batch", "score"],
    "yifenyiduan_2025": ["province", "year", "subject_group", "batch", "score"],
    "yifenyiduan_2026": ["province", "year", "subject_group", "batch", "score"],
    "admission_history": ["province", "year", "subject_group", "batch", "university_code", "major_group"],
    "control_line_2024": ["province", "year", "subject_group", "batch"],
    "control_line_2025": ["province", "year", "subject_group", "batch"],
    "control_line_2026": ["province", "year", "subject_group", "batch"],
}

# 校验闸门阈值（#20）
# 注：阈值反映真实数据完整性。一分一段表每分一行，每科类 400-700 行是合理的
# （分数范围 100-700 共 600 分）。原 2000 行/科类阈值过高，调整为 400。
GATE_THRESHOLDS = {
    # type: (per_province_per_dim_threshold, dim_description)
    "yifenyiduan_2024": (400, "每省每科类"),
    "yifenyiduan_2025": (400, "每省每科类"),
    "yifenyiduan_2026": (400, "每省每科类"),
    "plans_2026": (300, "每省每科类"),
    "plans_2025": (300, "每省每科类"),
    "admission_history": (200, "每省每年每科类"),
    "control_line_2024": (4, "每省每年"),
    "control_line_2025": (4, "每省每年"),
    "control_line_2026": (4, "每省每年"),
}


def scan_raw_files() -> dict[str, list[Path]]:
    """扫描 data/raw/ 下所有 {省}_{类型}.csv，按类型分组。

    文件命名规则：{省}_{类型}.csv，如 广东_yifenyiduan_2026.csv
    类型必须是 TYPE_MAP 的 key。
    """
    if not RAW_DIR.exists():
        return {t: [] for t in TYPE_MAP}

    grouped: dict[str, list[Path]] = {t: [] for t in TYPE_MAP}
    for f in sorted(RAW_DIR.glob("*.csv")):
        # 解析文件名：{省}_{类型}.csv
        stem = f.stem  # 如 广东_yifenyiduan_2026
        matched = False
        for t in TYPE_MAP:
            suffix = f"_{t}"
            if stem.endswith(suffix):
                province = stem[: -len(suffix)]
                if province:
                    grouped[t].append(f)
                    matched = True
                    break
        if not matched:
            print(f"[merge_all] ⚠ 跳过无法解析的 raw 文件: {f.name}")
    return grouped


def merge_one_type(data_type: str, raw_files: list[Path]) -> pd.DataFrame:
    """合并某一类型的所有分省 raw 文件。"""
    dfs = []
    for f in raw_files:
        try:
            df = pd.read_csv(f, dtype=str)
            if df.empty:
                print(f"[merge_all] ⚠ {f.name} 为空，跳过")
                continue
            if "province" not in df.columns:
                print(f"[merge_all] ⚠ {f.name} 缺少 province 列，跳过")
                continue
            # 过滤空 province
            df = df[df["province"].fillna("").str.strip() != ""]
            if df.empty:
                print(f"[merge_all] ⚠ {f.name} 过滤空 province 后为空，跳过")
                continue
            dfs.append(df)
            print(f"[merge_all]   + {f.name}: {len(df)} 行")
        except Exception as e:
            print(f"[merge_all] ⚠ 读取 {f.name} 失败: {e}")

    if not dfs:
        return pd.DataFrame()

    merged = pd.concat(dfs, ignore_index=True)

    # 去重
    subset = DEDUP_SUBSET.get(data_type)
    if subset:
        available = [c for c in subset if c in merged.columns]
        if available:
            before = len(merged)
            merged = merged.drop_duplicates(subset=available, keep="last")
            if len(merged) < before:
                print(f"[merge_all]   去重: {before} → {len(merged)} 行 (subset={available})")

    return merged


def run_gate_check(data_type: str, df: pd.DataFrame) -> tuple[bool, list[str]]:
    """跑校验闸门（#20）。返回 (是否通过, 报告行列表)。"""
    reports = []
    threshold, dim_desc = GATE_THRESHOLDS.get(data_type, (0, ""))
    master_name = TYPE_MAP[data_type]

    if df.empty:
        reports.append(f"  [{master_name}] ⚠ 无数据（raw 文件缺失或全部为空）")
        # 空数据不阻塞（可能该类型尚无 raw），但标记警告
        return True, reports

    if "province" not in df.columns:
        reports.append(f"  [{master_name}] ❌ 缺少 province 列")
        return False, reports

    # province 空值检查
    null_prov = df["province"].isna().sum()
    if null_prov > 0:
        reports.append(f"  [{master_name}] ❌ province 空值 {null_prov} 行")
        return False, reports

    # unique_key 重复检查（leakage_radar 用的 university_name|major_group|subject_group）
    if data_type.startswith("plans"):
        key_cols = [c for c in ["province", "university_name", "group_code", "subject_group"] if c in df.columns]
        if key_cols:
            dup_keys = df.duplicated(subset=key_cols).sum()
            if dup_keys > 0:
                reports.append(f"  [{master_name}] ⚠ unique_key 重复 {dup_keys} 行（已去重， informational）")

    # 每省每科类行数阈值检查（#20 硬化）
    # - yifenyiduan: 仅检查 subject_group ∈ {物理类, 历史类}（艺术/体育/校考类天然行数少，跳过）
    # - plans: 按 (province, subject_group) 分组，每科类 ≥ threshold
    # - admission_history: 按 (province, subject_group) 分组，每科类 3 年 ≥ threshold*3
    # - control_line: 按 province 分组（单文件 year 固定，subject_group 含普通类/艺术类/体育类多批次拆分无意义），每省每年 ≥ threshold
    check_df = df
    if data_type.startswith("yifenyiduan") and "subject_group" in df.columns:
        # 仅检查物理类/历史类两大科类（艺术/体育/校考类天然 200-600 行，不纳入闸门）
        check_df = df[df["subject_group"].isin(["物理类", "历史类"])]

    if data_type.startswith("control_line"):
        # control_line 按 province 聚合（单文件 year 固定，subject_group 多批次不拆分）
        group_cols = ["province"]
        expected_min = threshold  # 每省每年 ≥4
    else:
        group_cols = ["province"]
        if "subject_group" in check_df.columns:
            group_cols.append("subject_group")
        if data_type == "admission_history":
            expected_min = threshold * 3  # 每科类 3 年
        else:
            expected_min = threshold  # 每科类/每年

    prov_counts = check_df.groupby(group_cols).size()
    all_pass = True
    for key, cnt in prov_counts.items():
        prov = key[0] if isinstance(key, tuple) else key
        if cnt < expected_min:
            reports.append(f"  [{master_name}] ⚠ {prov}: {cnt} 行 < {expected_min}（{dim_desc}≥{threshold}）")
            # #20 闸门硬化：yifenyiduan/control_line 行数不足视为事故，阻塞合并
            # plans/history 保留 warning（各省数据差异大/图片源普遍无法 OCR）
            if data_type.startswith("yifenyiduan") or data_type.startswith("control_line"):
                all_pass = False
        else:
            reports.append(f"  [{master_name}] ✓ {prov}: {cnt} 行 ≥ {expected_min}")

    # 硬性失败条件：province 空值/缺列/yifenyiduan-control_line 行数不足（#20 硬化）
    return all_pass, reports


def atomic_write_csv(df: pd.DataFrame, master_path: Path) -> None:
    """原子写：先写 .tmp 再 os.replace。"""
    tmp_path = master_path.with_suffix(".csv.tmp")
    df.to_csv(tmp_path, index=False, encoding="utf-8-sig")
    os.replace(tmp_path, master_path)


def main():
    parser = argparse.ArgumentParser(description="合并 data/raw/ 分省文件到主 CSV")
    parser.add_argument("--dry-run", action="store_true", help="只校验不写主 CSV")
    parser.add_argument("--type", default=None, help="只合并指定类型（如 yifenyiduan_2026）")
    args = parser.parse_args()

    print("=" * 72)
    print("[merge_all] 开始合并 data/raw/ → 主 CSV")
    print(f"[merge_all] RAW_DIR = {RAW_DIR}")
    print("=" * 72)

    grouped = scan_raw_files()

    # 过滤类型
    types_to_merge = [args.type] if args.type else list(TYPE_MAP.keys())

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report_path = DATA_DIR / f"_merge_report_{timestamp}.txt"
    report_lines = [
        f"merge_all.py 合并报告 — {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"RAW_DIR = {RAW_DIR}",
        f"模式 = {'dry-run' if args.dry_run else 'write'}",
        "=" * 72,
    ]

    total_written = 0
    has_hard_fail = False

    for data_type in types_to_merge:
        if data_type not in TYPE_MAP:
            print(f"[merge_all] ⚠ 未知类型: {data_type}")
            continue

        master_name = TYPE_MAP[data_type]
        raw_files = grouped.get(data_type, [])

        print(f"\n--- {master_name} (raw 文件 {len(raw_files)} 个) ---")
        report_lines.append(f"\n--- {master_name} (raw 文件 {len(raw_files)} 个) ---")

        if not raw_files:
            print(f"[merge_all]   无 raw 文件，跳过（保留现有主 CSV）")
            report_lines.append("  无 raw 文件，跳过")
            continue

        merged = merge_one_type(data_type, raw_files)
        if merged.empty:
            print(f"[merge_all]   合并后为空，跳过")
            report_lines.append("  合并后为空，跳过")
            continue

        # 校验闸门
        gate_pass, gate_reports = run_gate_check(data_type, merged)
        for line in gate_reports:
            print(line)
            report_lines.append(line)

        if not gate_pass:
            has_hard_fail = True
            print(f"[merge_all] ❌ 闸门硬性失败，跳过写入 {master_name}")
            report_lines.append(f"  ❌ 闸门硬性失败，跳过写入")
            continue

        if args.dry_run:
            print(f"[merge_all] [dry-run] 将写入 {master_name}: {len(merged)} 行（不实际写入）")
            report_lines.append(f"  [dry-run] 将写入 {len(merged)} 行")
        else:
            master_path = DATA_DIR / master_name
            atomic_write_csv(merged, master_path)
            print(f"[merge_all] ✅ 写入 {master_name}: {len(merged)} 行（原子写）")
            report_lines.append(f"  ✅ 写入 {len(merged)} 行")
            total_written += len(merged)

    report_lines.append("\n" + "=" * 72)
    report_lines.append(f"总计写入: {total_written} 行")
    report_lines.append(f"硬性失败: {'是' if has_hard_fail else '否'}")

    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\n[merge_all] 校验报告: {report_path}")
    print(f"[merge_all] 完成。总计写入 {total_written} 行。")

    if has_hard_fail:
        print("[merge_all] ⚠ 存在硬性失败，请检查报告")
        sys.exit(1)


if __name__ == "__main__":
    main()
