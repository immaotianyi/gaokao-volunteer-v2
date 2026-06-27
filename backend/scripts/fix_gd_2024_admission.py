"""
修复广东2024 admission_history 的 lowest_score / lowest_rank 缺失问题。

数据源 raw/2024_physics_toudang.csv 有完整的投档最低分和投档最低排位（3121行），
但导入 admission_history.csv 时丢失了。本脚本用 university_code + 提取的专业组代码
作为匹配键，从源文件回填。
"""
import pandas as pd
import re
from pathlib import Path

DATA = Path("/Users/sanzhaibanniang/Claude/Projects/gaokao/backend/data/")


def clean_watermark(val):
    """去除水印噪声字（院/试/考/育/教/省/东/广）和换行符"""
    if pd.isna(val):
        return None
    s = re.sub(r"[院试考育教省东广\n\r]", "", str(val)).strip()
    return s if s else None


def clean_int(val):
    """清洗并转整数"""
    if pd.isna(val):
        return None
    s = re.sub(r"[院试考育教省东广\n\r\s,]", "", str(val))
    if not s or s == "-":
        return None
    try:
        return int(float(s))
    except ValueError:
        m = re.match(r"(\d+)", s)
        return int(m.group(1)) if m else None


def extract_group_code(major_name):
    """从 '专业组203' 或 '专业组院\\n202' 提取 '203' / '202'"""
    if pd.isna(major_name):
        return None
    s = str(major_name)
    # 先清洗水印
    s = re.sub(r"[院试考育教省东广\n\r]", "", s)
    # 提取数字
    m = re.search(r"(\d+)", s)
    return m.group(1) if m else None


def main():
    # 1. 读取源文件
    src = pd.read_csv(DATA / "raw" / "2024_physics_toudang.csv")
    print(f"源文件: {len(src)}行")

    # 清洗源文件
    src["code"] = src["院校代码"].astype(str).str.strip()
    src["group"] = src["专业组代码"].apply(clean_watermark)
    src["score"] = src["投档最低分"].apply(clean_int)
    src["rank"] = src["投档最低排位"].apply(clean_int)

    print(f"  清洗后: score非空{src['score'].notna().sum()}, rank非空{src['rank'].notna().sum()}")

    # 2. 构建查找表 (code, group) → (score, rank)
    src_lookup = {}
    for _, row in src.iterrows():
        key = (row["code"], row["group"])
        src_lookup[key] = (row["score"], row["rank"])
    print(f"  查找表: {len(src_lookup)}条")

    # 3. 读取 admission_history
    ah_path = DATA / "admission_history.csv"
    ah = pd.read_csv(ah_path)

    # 备份
    bak = ah_path.with_suffix(".csv.bak_2024_score")
    ah.to_csv(bak, index=False)
    print(f"  已备份: {bak.name}")

    # 4. 筛选广东2024物理类（缺失score的行）
    mask = (
        (ah["province"] == "广东")
        & (ah["year"] == 2024)
        & (ah["subject_group"] == "物理类")
    )
    gd = ah[mask].copy()
    print(f"\nadmission_history 广东2024物理类: {len(gd)}行")
    print(f"  缺score: {gd['lowest_score'].isna().sum()}行")
    print(f"  缺rank: {gd['lowest_rank'].isna().sum()}行")

    # 5. 提取匹配键
    gd_code = gd["university_code"].astype(str).str.strip()
    gd_group = gd["major_name"].apply(extract_group_code)

    # 6. 回填
    backfill_score = 0
    backfill_rank = 0
    no_match = 0
    for idx, (code, group) in zip(gd.index, zip(gd_code, gd_group)):
        if not code or not group:
            no_match += 1
            continue
        key = (code, group)
        if key not in src_lookup:
            no_match += 1
            continue
        score, rank = src_lookup[key]
        if pd.isna(ah.at[idx, "lowest_score"]) and score is not None:
            ah.at[idx, "lowest_score"] = score
            backfill_score += 1
        if pd.isna(ah.at[idx, "lowest_rank"]) and rank is not None:
            ah.at[idx, "lowest_rank"] = rank
            backfill_rank += 1

    print(f"\n回填结果:")
    print(f"  lowest_score: +{backfill_score}行")
    print(f"  lowest_rank: +{backfill_rank}行")
    print(f"  未匹配: {no_match}行")

    # 7. 保存
    ah.to_csv(ah_path, index=False)
    print(f"\n✅ 已保存 admission_history.csv")

    # 8. 验证
    gd_after = ah[(ah["province"] == "广东") & (ah["year"] == 2024) & (ah["subject_group"] == "物理类")]
    print(f"\n回填后验证:")
    print(f"  广东2024物理类: {len(gd_after)}行")
    s = gd_after["lowest_score"].notna().sum()
    r = gd_after["lowest_rank"].notna().sum()
    print(f"  有lowest_score: {s}行 ({s/len(gd_after)*100:.1f}%)")
    print(f"  有lowest_rank: {r}行 ({r/len(gd_after)*100:.1f}%)")

    # 全局验证
    print(f"\n全局 admission_history:")
    s = ah["lowest_score"].notna().sum()
    r = ah["lowest_rank"].notna().sum()
    print(f"  有lowest_score: {s}/{len(ah)} ({s/len(ah)*100:.1f}%)")
    print(f"  有lowest_rank: {r}/{len(ah)} ({r/len(ah)*100:.1f}%)")


if __name__ == "__main__":
    main()
