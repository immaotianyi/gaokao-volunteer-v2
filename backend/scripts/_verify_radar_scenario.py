import pandas as pd

# 用户场景：509分历史类甘肃
USER_SCORE = 509
SG = "历史类"

df = pd.read_csv('data/plans_2026.csv')
gs = df[(df['province']=='甘肃') & (df['subject_group']==SG)]
print(f"=== 甘肃{SG} plans_2026: {len(gs)} 行 ===")
print(f"batch值: {gs['batch'].unique().tolist()}")
print(f"school_type分布: {gs['school_type'].value_counts().to_dict()}")
print(f"lowest_score_2025 范围: {gs['lowest_score_2025'].min()} - {gs['lowest_score_2025'].max()}")

# 捡漏雷达默认 score_tolerance=30，寻找用户可达的（分数±30内或低于用户分）
tolerance = 30
# 用户分数可达：最低分在 [用户分-tolerance, 用户分+tolerance] 区间（捡漏区间）
reachable = gs[(gs['lowest_score_2025'] >= USER_SCORE - tolerance) & (gs['lowest_score_2025'] <= USER_SCORE + tolerance)]
print(f"\n=== 509分历史类 ±{tolerance} 可达机会: {len(reachable)} 个 ===")
print(reachable[['university_name','group_code','major_name','lowest_score_2025','lowest_rank_2025','school_type']].head(15).to_string())

# 低于用户分的（用户能稳上的）
safe = gs[gs['lowest_score_2025'] < USER_SCORE - tolerance].sort_values('lowest_score_2025', ascending=False)
print(f"\n=== 低于509-{tolerance}={USER_SCORE-tolerance}（稳上）: {len(safe)} 个，前10: ===")
print(safe[['university_name','major_name','lowest_score_2025','school_type']].head(10).to_string())

# admission_history 验证
print("\n=== admission_history 甘肃2024 样本 ===")
ah = pd.read_csv('data/admission_history.csv')
gs_ah = ah[(ah['province']=='甘肃') & (ah['subject_group']==SG)]
print(f"{SG} 2024: {len(gs_ah)} 行")
print(gs_ah[['university_name','major_name','lowest_score','lowest_rank']].head(5).to_string())
