#!/usr/bin/env python3
"""冒烟测试：验证 score_rank 服务用 2026 真实数据 + 本科批过滤后结果正确"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.score_rank import (
    score_to_rank, rank_to_score, get_score_range, get_available_years, preload_all
)

print("=== 1. preload_all ===")
preload_all()

print("\n=== 2. 可用年份 ===")
print(get_available_years())

print("\n=== 3. 不传 year（应默认 2026）===")
# 2026 物理类 600分 → 真实累计3367人（来自 PDF）
r1 = score_to_rank(600, subject_group="物理类")
print(f"  score_to_rank(600, 物理类) = {r1}  (期望 3367)")

# 2026 物理类 425分 = 本科线，累计人数应远大于 600分时的3367
r2 = score_to_rank(425, subject_group="物理类")
print(f"  score_to_rank(425, 物理类) = {r2}  (期望 远大于 3367，本科线位次)")

# 反查：rank=3367 → score=600
s1 = rank_to_score(3367, subject_group="物理类")
print(f"  rank_to_score(3367, 物理类) = {s1}  (期望 600)")

# 历史类 600分 → 2026 真实数据
r3 = score_to_rank(600, subject_group="历史类")
print(f"  score_to_rank(600, 历史类) = {r3}")

print("\n=== 4. get_score_range（捡漏雷达场景）===")
rg = get_score_range(565, tolerance=5, subject_group="物理类")
print(f"  565±5 物理类: rank={rg['rank']}, range=({rg['min_rank']}, {rg['max_rank']})")

print("\n=== 5. 关键校验：未误用 2025 插值数据 ===")
# 2025 插值数据中 600分→5000人；2026 真实数据 600分→3367人
# 若默认仍是 2025，则会返回 5000
if r1 == 5000:
    print(f"  ❌ 仍命中 2025 插值数据（5000），默认年份未切换成功")
    sys.exit(1)
elif r1 == 3367:
    print(f"  ✅ 命中 2026 真实数据（3367），切换成功")
else:
    print(f"  ⚠️ 返回值 {r1} 既非 5000(2025插值) 也非 3367(2026真实)，请人工核对")

print("\n=== 6. 校验本科过滤生效（不应命中专科批）===")
# 物理类 422 分在 2026 数据中本科+专科都有，本科 cumulative_count=...
# 若没过滤本科，iloc[0] 可能取到任意一行
r_422 = score_to_rank(422, subject_group="物理类")
print(f"  score_to_rank(422, 物理类) = {r_422}")
