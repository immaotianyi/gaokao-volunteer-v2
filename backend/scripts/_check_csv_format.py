import pandas as pd
files = [
    'data/yifenyiduan_2024.csv',
    'data/yifenyiduan_2025.csv',
    'data/yifenyiduan_2026.csv',
    'data/control_line_2024.csv',
    'data/control_line_2025.csv',
    'data/control_line_2026.csv',
]
for f in files:
    df = pd.read_csv(f)
    print(f'=== {f} ===')
    print('  cols:', list(df.columns))
    print('  rows:', len(df))
    print('  provinces:', df['province'].unique().tolist() if 'province' in df.columns else 'N/A')
    if 'batch' in df.columns:
        print('  batch vals:', df['batch'].unique().tolist()[:10])
    if 'batch_section' in df.columns:
        print('  batch_section vals:', df['batch_section'].unique().tolist()[:10])
    if 'subject_group' in df.columns:
        print('  subject_group vals:', df['subject_group'].unique().tolist()[:10])
    print('  sample row:', df.iloc[0].to_dict())
    print()
