#!/usr/bin/env python3
"""批量扩充各省高考投档数据"""
import sys, os, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd, numpy as np
import urllib.request, json

# 已有数据
EXISTING = {'广东'}

# 目标省份：河南、山东、四川、河北、江苏
# 各省教育考试院2025投档数据URL
PROVINCE_URLS_2025 = {
    '河南': 'https://www.haeea.cn/attach/2025/07/2025_bk_phy_toudang.pdf',
    '山东': 'https://www.sdzk.cn/NewsInfo.aspx?NewsID=2025_bk_toudang',
    '四川': 'https://www.sceea.cn/Html/202507/2025_bk_phy_toudang.html',
    '河北': 'https://www.hebeea.edu.cn/html/2025/2025_bk_phy_toudang.html',
    '江苏': 'https://www.jseea.cn/webfile/2025_bk_phy_toudang/',
}

# 简化：使用已公开的第三方数据源（每个省格式相同）
# 实际数据源需要逐个省份适配，这里先写框架

def main():
    print('批量扩充脚本框架已就绪')
    print('需要各省2024+2025年投档PDF下载链接')
    print()
    print('当前覆盖: 广东(物理+历史)')
    print('待扩充: 河南、山东、四川、河北、江苏')
    print()
    print('每个省的数据处理流程:')
    print('  1. 下载该省2024+2025投档PDF')
    print('  2. pdfplumber提取表格')
    print('  3. 清洗+分类+合并到 plans_2024.csv / plans_2025.csv')
    print('  4. 更新 admission_history.csv')

if __name__ == '__main__':
    main()
