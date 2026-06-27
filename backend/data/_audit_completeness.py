import pandas as pd, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
files = ['plans_2026.csv','plans_2025.csv','admission_history.csv',
         'yifenyiduan_2024.csv','yifenyiduan_2025.csv','yifenyiduan_2026.csv',
         'control_line_2024.csv','control_line_2025.csv','control_line_2026.csv']
print('=' * 72)
for f in files:
    if not os.path.exists(f):
        print(f'{f}: 不存在'); continue
    try:
        df = pd.read_csv(f, dtype=str)
    except Exception as e:
        print(f'{f}: 读取异常 {e}'); continue
    print(f'### {f}  总行数={len(df)}')
    if 'province' not in df.columns:
        print('  (无province列)'); print(); continue
    vc = df['province'].fillna('<<空>>').value_counts()
    for prov, cnt in vc.items():
        flag = ''
        if 'yifenyiduan' in f and cnt < 2000:
            flag = ' ⚠️<2000(每省每年每科类>2000,应含2科类x3年)'
        elif f == 'plans_2026.csv' and cnt < 1000:
            flag = ' ⚠️<1000(每省2科类x500)'
        elif f == 'admission_history.csv' and cnt < 6000:
            flag = ' ⚠️<6000(每省3年x2科类x1000)'
        elif f.startswith('control_line') and cnt < 6:
            flag = ' ⚠️<6(每年本科/专科x2科类)'
        print(f'  {prov:8s} {cnt:>7d}{flag}')
    print()
