import pandas as pd
DATA = 'data'

print("=== 数据质量校验 ===\n")

# 2024 验证：物理类 682→35, 历史类 652→35
df = pd.read_csv(f'{DATA}/yifenyiduan_2024.csv')
gs = df[(df['province']=='甘肃') & (df['year']==2024)]
print("[2024] 物理类 682分 累计:", gs[(gs['subject_group']=='物理类')&(gs['score']==682)]['cumulative_count'].tolist(), "(期望 35)")
print("[2024] 历史类 652分 累计:", gs[(gs['subject_group']=='历史类')&(gs['score']==652)]['cumulative_count'].tolist(), "(期望 35)")
print("[2024] 物理类最低分:", gs[gs['subject_group']=='物理类']['score'].min(), "历史类最低分:", gs[gs['subject_group']=='历史类']['score'].min())

# 2025 验证
df = pd.read_csv(f'{DATA}/yifenyiduan_2025.csv')
gs = df[(df['province']=='甘肃') & (df['year']==2025)]
print("\n[2025] 物理类最高分:", gs[gs['subject_group']=='物理类']['score'].max(), "累计:", gs[gs['subject_group']=='物理类']['cumulative_count'].min(), "(期望 37)")
print("[2025] 历史类最高分:", gs[gs['subject_group']=='历史类']['score'].max(), "累计:", gs[gs['subject_group']=='历史类']['cumulative_count'].min(), "(期望 36)")

# 2026 验证锚点
df = pd.read_csv(f'{DATA}/yifenyiduan_2026.csv')
gs = df[(df['province']=='甘肃') & (df['year']==2026)]
print("\n[2026] 物理类 681→", gs[(gs['subject_group']=='物理类')&(gs['score']==681)]['cumulative_count'].tolist(), "(期望 38)")
print("[2026] 物理类 600→", gs[(gs['subject_group']=='物理类')&(gs['score']==600)]['cumulative_count'].tolist(), "(期望 5646)")
print("[2026] 物理类 367→", gs[(gs['subject_group']=='物理类')&(gs['score']==367)]['cumulative_count'].tolist(), "(期望 91418)")
print("[2026] 历史类 660→", gs[(gs['subject_group']=='历史类')&(gs['score']==660)]['cumulative_count'].tolist(), "(期望 38)")
print("[2026] 历史类 405→", gs[(gs['subject_group']=='历史类')&(gs['score']==405)]['cumulative_count'].tolist(), "(期望 25572)")
print("[2026] 物理类本科线367处累计单调性:", gs[(gs['subject_group']=='物理类')&(gs['batch']=='本科')]['cumulative_count'].is_monotonic_decreasing)

# 控制线验证
print("\n[控制线 2026]")
df = pd.read_csv(f'{DATA}/control_line_2026.csv')
gs = df[df['province']=='甘肃']
print(gs[['subject_group','batch','lowest_score']].to_string(index=False))

# 测试用例：509分历史类（用户原始反馈的问题）
print("\n=== 用户场景测试：509分历史类 ===")
for year in [2024, 2025, 2026]:
    df = pd.read_csv(f'{DATA}/yifenyiduan_{year}.csv')
    r = df[(df['province']=='甘肃')&(df['year']==year)&(df['subject_group']=='历史类')&(df['score']==509)]
    if len(r):
        print(f"  {year}年 509分历史类: 累计位次 {r['cumulative_count'].iloc[0]}, 同分 {r['segment_count'].iloc[0]}人")
    else:
        # 找最接近的
        gs = df[(df['province']=='甘肃')&(df['year']==year)&(df['subject_group']=='历史类')]
        near = gs.iloc[(gs['score']-509).abs().argsort()[:1]]
        print(f"  {year}年 509分历史类: 无精确匹配，最近 {near['score'].iloc[0]}分→{near['cumulative_count'].iloc[0]}")
