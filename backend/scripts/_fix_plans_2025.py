"""#19 plans_2025 多省恢复（Phase 4.3 扩展）

现 plans_2025 仅剩广东(4970)+甘肃(4571)+福建+安徽。为有 plans_2026 但无 plans_2025 的省份反向生成。

策略：以 plans_2026 为模板，生成 plans_2025：
- plans_2025 字段是 plans_2026 的子集（13 列 vs 17 列）
- plan_count = plans_2026 的 plan_count_prev（上一年计划数，即 2025 计划数）
- lowest_score_2025 / lowest_rank_2025 保留 plans_2026 的值
- school_type 保留

适用省份：福建/安徽/山东/河南（有 plans_2026 的省份）
其余 6 省（陕川渝冀鄂湘赣辽）plans_2026 标 TODO 无源，plans_2025 也无法补
"""
import os
import pandas as pd
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

# plans_2025 表头（13 列，无 is_new/major_category/subject_requirement/plan_count_prev）
PLANS_2025_COLS = [
    "province", "subject_group", "batch", "university_code", "university_name",
    "group_code", "major_code", "major_name", "plan_count", "tuition",
    "lowest_score_2025", "lowest_rank_2025", "school_type",
]

print("=" * 60)
print("[#19] plans_2025 多省恢复（Phase 4.3 扩展）")
print("=" * 60)

# 有 plans_2026 但无 plans_2025 的省份（扩展到山东/河南）
for prov in ["福建", "安徽", "山东", "河南"]:
    p26_file = RAW / f"{prov}_plans_2026.csv"
    p25_file = RAW / f"{prov}_plans_2025.csv"

    if not p26_file.exists():
        print(f"\n{prov}: 无 plans_2026 raw，跳过")
        continue

    if p25_file.exists():
        existing = pd.read_csv(p25_file, dtype=str)
        if len(existing) > 100:
            print(f"\n{prov}: plans_2025 已有 {len(existing)} 行，跳过")
            continue

    p26 = pd.read_csv(p26_file, dtype=str)
    print(f"\n{prov}: plans_2026 = {len(p26)} 行 → 反向生成 plans_2025")

    # plan_count = plan_count_prev（2025 计划数）
    p25 = p26.copy()
    p25["plan_count"] = p26["plan_count_prev"].fillna(p26["plan_count"]) if "plan_count_prev" in p26.columns else p26["plan_count"]

    # 只保留 plans_2025 的 13 列
    for col in PLANS_2025_COLS:
        if col not in p25.columns:
            p25[col] = ""
    p25 = p25[PLANS_2025_COLS]

    # 空值处理
    p25 = p25.fillna("")

    print(f"  生成 plans_2025: {len(p25)} 行, {p25['university_name'].nunique()} 院校")

    # 原子写
    tmp = p25_file.with_suffix(".csv.tmp")
    p25.to_csv(tmp, index=False, encoding="utf-8-sig")
    os.replace(tmp, p25_file)
    print(f"  ✅ 已写入 {p25_file.name}: {len(p25)} 行")

print("\n完成。")
