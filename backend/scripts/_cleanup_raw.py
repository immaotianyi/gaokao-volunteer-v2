"""Phase 3 前清理不达标 raw（#20 闸门硬化准备）。

红线：只删不达标的残缺 raw（OCR 失败/图片源无法解析），不删有真实数据的偏少 raw。
保留 plans/history 残缺（数据差异大/图片源普遍，闸门保留 warning）。
"""
import pandas as pd
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

print("=" * 60)
print("Phase 3 清理不达标 raw")
print("=" * 60)

# 1. 删除湖北 yfd_2026（172 行 OCR 失败，不达标）
f = RAW / "湖北_yifenyiduan_2026.csv"
if f.exists():
    df = pd.read_csv(f, dtype=str)
    print(f"删除 {f.name}（{len(df)} 行 OCR 失败，<800 阈值）")
    f.unlink()

# 2. 福建yfd_2026 过滤历史类（204<400 不达标），保留物理类 415
f = RAW / "福建_yifenyiduan_2026.csv"
if f.exists():
    df = pd.read_csv(f, dtype=str)
    before = len(df)
    vc = df["subject_group"].value_counts().to_dict() if "subject_group" in df.columns else {}
    print(f"福建_yifenyiduan_2026 清理前: {before} 行, 科类分布: {vc}")
    # 保留物理类（415>=400 达标），删除历史类（204<400 不达标）
    df = df[df["subject_group"] == "物理类"]
    df.to_csv(f, index=False, encoding="utf-8-sig")
    print(f"福建_yifenyiduan_2026 清理后: {len(df)} 行（仅物理类）")

# 3. 删除海南/上海/内蒙古 history（Phase 4.4 残缺清理，<200 不达标）
for prov in ["海南", "上海", "内蒙古"]:
    f = RAW / f"{prov}_admission_history.csv"
    if f.exists():
        df = pd.read_csv(f, dtype=str)
        if len(df) < 200:
            print(f"删除 {f.name}（{len(df)} 行残缺 <200）")
            f.unlink()

print("\n清理完成")
print("注：plans 偏少（山东369/河南291）和安徽 history 76 保留（有真实数据，闸门 warning 不 block）")
