# 捡漏雷达 训练与回测报告

## 一、当前状态

### 数据情况
| 数据集 | 行数 | 省份 | 学校 | 录取分覆盖率 |
|--------|------|------|------|-------------|
| plans_2024.csv | 1815 | 5 | 30 | 100%（模拟数据） |
| plans_2025.csv | 2612 | 5 | 30 | 100%（基于真实2025分构造） |
| plans_2026.csv | 2649 | 5 | 32 | 0%（待出分后填入） |
| admission_history.csv | 1815 | 5 | 30 | 100%（基于2024分） |

> 注意：plans_2024 和 admission_history 当前是基于2025数据模拟生成的，不是真实2024数据。
> 估值模型回测的准确性受限于模拟数据的质量。

### 算法版本
- **V2.1**：六维评分 + 热度系数估值 + 锚定校准 + 纯净组V2

---

## 二、回测结果（2024→2025，广东物理类）

### 估值模型
| 指标 | 值 |
|------|-----|
| 样本数 | 74 |
| 均值误差 | -16.2分（算法偏保守） |
| 中位误差 | -14.5分 |
| 标准差 | 32.0分 |
| +/-15分命中率 | 35.1% |
| +/-20分命中率 | 48.6% |

### 捡漏有效性
| 类型 | 数量 | 占比 |
|------|------|------|
| 真捡漏（低于同校中位>3分） | 48 | 43.2% |
| 反捡漏（高于同校中位>3分） | 48 | 43.2% |
| 持平 | 15 | 13.5% |

### 关键发现
1. 估值偏保守：算法平均低估16分。原因是热度系数对冷门专业打折过猛
2. TOP5质量好：前5名中4个是真捡漏（哈工大、华科）
3. 中外合作检出：华科中外合作专业被正确识别且为真捡漏

---

## 三、2026年出分后的操作步骤

### 第一步：导入2025真实数据
```bash
python3 backend/scripts/import_real_data.py --year 2025 --source ./data/raw/2025_real_plans.csv
```

### 第二步：导入2024真实数据（训练估值模型）
```bash
python3 backend/scripts/import_real_data.py --year 2024 --source ./data/raw/2024_real_plans.csv
```

### 第三步：导入2026招生计划（分数线待出）
```bash
python3 backend/scripts/import_real_data.py --year 2026 --source ./data/raw/2026_plans.csv --plans-only
```

### 第四步：回测验证
```bash
python3 backend/scripts/backtest.py --year 2025 --province 广东 --subject 物理类
```

### 第五步：2026分数线公布后填入真实录取分
### 第六步：启动每日自动更新
```bash
0 7 * * * cd /path/to/gaokao && python3 backend/scripts/daily_update.py
```

---

## 四、CSV数据格式规范

### 必要列
province, subject_group, batch, university_code, university_name,
group_code, major_code, major_name, plan_count, tuition, school_type

### 推荐列
subject_requirement, lowest_score_YYYY, lowest_rank_YYYY, notes

---

## 五、需人工维护的配置

### new_campuses.json
每年高考前手动更新新校区字典。
折扣率参考：一线城市 0.90-0.95，二三线 0.82-0.88，偏远 0.75-0.82

### MAJOR_HOTNESS（专业热度系数）
在 leakage_radar.py 中维护，根据每年报考趋势调整。

---

## 六、当前局限与改进方向

| 问题 | 影响 | 改进方案 |
|------|------|---------|
| 2024数据为模拟 | 估值不准 | 接入真实2024录取数据 |
| 仅5省30校 | 覆盖面小 | 扩展至全国31省 |
| 无真实位次数据 | 无法做位次匹配 | 接入真实位次 |
| 选科稀缺度为估算 | 稀缺度不够精确 | 接入各省选科统计 |
| 新校区字典需手动 | 可能遗漏 | 爬取教育部公告自动发现 |
