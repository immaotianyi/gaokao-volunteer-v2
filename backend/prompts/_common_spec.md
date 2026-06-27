# 公共技术规范 — 全国高考数据爬取（所有省份共享）

> 本文件定义所有省份爬取任务共享的技术规范。每个省份的提示词会引用本文件。
> AI agent 在开始工作前，**必须先完整阅读本文件**。

---

## 一、项目工作目录

```
/Users/sanzhaibanniang/Claude/Projects/gaokao/backend
```

- 数据文件目录：`data/`
- 原始PDF缓存目录：`data/raw/{省份拼音}_{年份}/`
- 脚本目录：`scripts/`
- 现有参考脚本：`scripts/sync_guangdong_2026.py`、`scripts/parse_guangdong_pdf.py`

---

## 二、5类数据文件的精确字段格式

### 1. plans_2026.csv（当年招生计划，追加模式）

**表头（精确顺序，不可改动）：**
```
province,subject_group,batch,university_code,university_name,group_code,major_code,major_name,plan_count,tuition,lowest_score_2025,lowest_rank_2025,is_new,school_type,major_category,subject_requirement,plan_count_prev
```

**样本（广东物理类）：**
```
广东,物理类,本科批,10001,北京大学,10001001,70301,化学,91,6000,669.0,28.0,0,985,理学,物理+化学+生物,24
广东,物理类,本科批,10001,北京大学,10001001,50261,翻译,21,6000,669.0,28.0,0,985,文学,物理+化学+生物,24
```

**字段说明：**
| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| province | string | 省份名（中文） | 广东 |
| subject_group | string | 科类：3+1+2省=物理类/历史类；3+3省=综合；老高考=文科/理科 | 物理类 |
| batch | string | 批次：本科批/提前批/专科批 | 本科批 |
| university_code | string | 院校代码（4-6位） | 10001 |
| university_name | string | 院校名称 | 北京大学 |
| group_code | string | 专业组代码（3+1+2省份必填；3+3/老高考可填院校代码_组号） | 10001001 |
| major_code | string | 专业代码 | 70301 |
| major_name | string | 专业名称 | 化学 |
| plan_count | int | 招生计划人数（必须>0） | 91 |
| tuition | int | 学费（元/年，无则留空） | 6000 |
| lowest_score_2025 | float | 2025年该专业组最低录取分（无则留空） | 669.0 |
| lowest_rank_2025 | float | 2025年该专业组最低录取位次（无则留空） | 28.0 |
| is_new | int | 是否新增专业：0=否，1=是 | 0 |
| school_type | string | 院校层次：985/211/双一流/省属重点/普通本科/民办 | 985 |
| major_category | string | 专业大类：理学/工学/文学/医学/法学/经济学/管理学/教育学/艺术学/农学/历史学/哲学/军事学 | 理学 |
| subject_requirement | string | 选科要求（如"物理+化学"） | 物理+化学+生物 |
| plan_count_prev | int | 上一年同专业计划数（无则留空） | 24 |

---

### 2. plans_2025.csv（上年招生计划，追加模式）

**表头（精确顺序）：**
```
province,subject_group,batch,university_code,university_name,group_code,major_code,major_name,plan_count,tuition,lowest_score_2025,lowest_rank_2025,school_type
```

**样本（广东物理类）：**
```
广东,物理类,本科批,10001,北京大学,206,206_001,北京大学组206,34,6000,689.0,99.0,985
广东,物理类,本科批,10002,中国人民大学,206,206_001,中国人民大学组206,3,6000,679.0,388.0,985
```

**注意：** 此文件字段比 plans_2026 少 `is_new`、`major_category`、`subject_requirement`、`plan_count_prev`。

---

### 3. admission_history.csv（历史录取数据，追加模式）

**表头（精确顺序）：**
```
year,province,subject_group,batch,university_code,university_name,group_code,major_code,major_name,lowest_score,lowest_rank,avg_score,applicant_count,source_file
```

**样本（上海综合）：**
```
2024,上海,综合,本科批,XF0,三亚学院,XF,XF0,第03组,419.0,,,,2024年上海市普通高校招生本科普通批次平行志愿院校专业组投档分数线.pdf
2024,上海,综合,本科批,XF1,三峡大学,XF,XF1,第01组,475.0,,,,2024年上海市普通高校招生本科普通批次平行志愿院校专业组投档分数线.pdf
```

**字段说明：**
| 字段 | 类型 | 说明 |
|------|------|------|
| year | int | 录取年份 | 
| province | string | 省份 |
| subject_group | string | 科类 |
| batch | string | 批次 |
| university_code | string | 院校代码 |
| university_name | string | 院校名称 |
| group_code | string | 专业组代码 |
| major_code | string | 专业代码（无专业级数据时填组代码） |
| major_name | string | 专业名称（无专业级数据时填"第XX组"） |
| lowest_score | float | 最低录取分 |
| lowest_rank | float | 最低录取位次（无则留空） |
| avg_score | float | 平均分（无则留空） |
| applicant_count | int | 报考人数（无则留空） |
| source_file | string | 数据来源PDF文件名 |

**重要：** 需爬取近3年（2023、2024、2025）的历史录取数据。如果该省只公布院校专业组级投档线（不公布专业级），major_code 填组代码，major_name 填"第XX组"。

---

### 4. yifenyiduan_2026.csv（一分一段表，追加模式）

**表头（精确顺序）：**
```
province,year,subject_group,batch,score,segment_count,cumulative_count
```

**样本（广东）：**
```
广东,2026,书法(校考),专科,567,18,18
广东,2026,书法(校考),专科,566,1,19
广东,2026,物理类,本科批,750,1,1
广东,2026,物理类,本科批,749,2,3
```

**字段说明：**
| 字段 | 类型 | 说明 |
|------|------|------|
| province | string | 省份 |
| year | int | 年份 |
| subject_group | string | 科类（物理类/历史类/综合/文科/理科，以及艺术体育类） |
| batch | string | 批次（本科批/专科批） |
| score | int | 分数 |
| segment_count | int | 该分数段人数 |
| cumulative_count | int | 累计人数（该分数及以上总人数） |

**重要：**
- 每省每年每科类应 > 2000 行（分数从最高分到最低分）
- cumulative_count 必须递增（分数从高到低，累计人数递增）
- 需要同时爬取 2024、2025、2026 三年的数据
- 3+1+2省份：物理类 + 历史类（共2个科类）
- 3+3省份：综合（1个科类）
- 老高考省份：文科 + 理科（共2个科类）

---

### 5. control_line_2026.csv（省控线，追加模式）

**表头（精确顺序）：**
```
province,year,batch_section,batch,subject_group,line_type,lowest_score,source_url
```

**样本（广东）：**
```
广东,2026,本科院校,本科,历史类,总分,440,https://eea.gd.gov.cn/news/content/post_4915291.html
广东,2026,本科院校,本科,物理类,总分,425,https://eea.gd.gov.cn/news/content/post_4915291.html
广东,2026,本科院校,本科,体育类,文化科总分,350,https://eea.gd.gov.cn/news/content/post_4915291.html
```

**字段说明：**
| 字段 | 类型 | 说明 |
|------|------|------|
| province | string | 省份 |
| year | int | 年份 |
| batch_section | string | 批次段（本科院校/专科院校/特殊类型招生） |
| batch | string | 批次简称（本科/专科/提前） |
| subject_group | string | 科类 |
| line_type | string | 线类型（总分/文化科总分/专业省统考） |
| lowest_score | int | 控制分数线 |
| source_url | string | 数据来源URL |

**重要：** 需要同时爬取 2024、2025、2026 三年的省控线。主要关注普通类（物理类/历史类 或 综合 或 文理）的本科批和专科批控制线。

---

## 三、科类映射规则（按高考模式）

| 高考模式 | 适用省份 | subject_group 取值 |
|---------|---------|-------------------|
| 3+1+2 | 河北/辽宁/江苏/福建/湖北/湖南/广东/重庆/黑龙江/吉林/安徽/江西/甘肃/广西/贵州/河南/山西/内蒙古/四川/云南/陕西/青海/宁夏 | 物理类 / 历史类 |
| 3+3 | 北京/天津/上海/浙江/山东/海南 | 综合 |
| 老高考 | 新疆/西藏 | 文科 / 理科 |

---

## 四、爬取步骤（通用流程）

### Step 1: 创建原始数据缓存目录
```bash
mkdir -p data/raw/{省份拼音}_{年份}/
```

### Step 2: 下载原始PDF/Excel
- 从各省考试院官网下载招生计划、一分一段表、省控线、投档线的PDF/Excel
- 存入 `data/raw/{省份拼音}_{年份}/`
- 文件命名：`{省份拼音}_{数据类型}_{年份}.pdf`
  - 数据类型：plans / yifenyiduan / control_line / toudang（投档线）

### Step 3: 解析PDF并清洗数据
- 使用 `pdfplumber` 库解析PDF表格
- 参考 `scripts/parse_guangdong_pdf.py` 的解析模式
- 将原始数据映射到目标字段格式
- 处理合并单元格、跨页表格等常见PDF问题

### Step 4: 写入 data/raw/ 分省文件（🚫 禁止直接写主 CSV）

> **🔴 CRITICAL 红线（#14 root fix）：**
> 爬虫脚本（sync_*、parse_*、download_*、write_*）**只准写 `data/raw/{省}_{类型}.csv`**，禁止直接改主 CSV（plans_2026.csv / yifenyiduan_*.csv / admission_history.csv / control_line_*.csv）。
> 主 CSV 由 `scripts/merge_all.py` 在所有 raw 就绪后一次性重建（原子写 + 校验闸门）。
> 违反此规则会导致多省并发写入时后写覆盖先写（#13 事故根因）。

```python
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_DIR.mkdir(exist_ok=True)
PROVINCE = "广东"  # 替换为目标省份

# 读取新数据
new_df = pd.DataFrame(...)

# ✅ 正确：写入 data/raw/{省}_{类型}.csv（分省隔离，无并发竞态）
raw_path = RAW_DIR / f"{PROVINCE}_plans_2026.csv"
if raw_path.exists():
    existing = pd.read_csv(raw_path, dtype=str)
    merged = pd.concat([existing, new_df.astype(str)]).drop_duplicates(keep="last")
else:
    merged = new_df
merged.to_csv(raw_path, index=False, encoding="utf-8-sig")
print(f"✅ 已写入 raw: {raw_path.name} ({len(merged)} 行)")

# 🚫 错误：禁止直接写主 CSV（会导致并发竞态）
# merged.to_csv('data/plans_2026.csv', index=False)  # 绝对禁止！

# 全部省份 raw 就绪后，由 merge_all.py 统一合并：
#   python backend/scripts/merge_all.py
```

### Step 5: 运行校验
```python
# 校验脚本 scripts/validate_{省份拼音}.py
```

---

## 五、校验规则（必须全部通过）

### 通用校验
1. **province 字段**：必须等于目标省份中文名，不能有其他省份混入
2. **subject_group 字段**：必须与该省高考模式一致（见第三节）
3. **空值处理**：缺失字段留空（CSV中为空字符串），**不要写 null / NA / None / nan**
4. **去重**：不能有完全相同的行重复出现
5. **追加模式**：不能删除或覆盖已有省份的数据

### plans_2026.csv 校验
- `plan_count` 必须 > 0
- `university_code` 长度 4-6 位
- `is_new` 只能是 0 或 1
- `school_type` 必须是以下之一：985 / 211 / 双一流 / 省属重点 / 普通本科 / 民办
- 每省每科类计划数应 > 500 行

### plans_2025.csv 校验
- 同 plans_2026，但字段更少
- `lowest_score_2025` 在 200-750 之间（有值时）
- `lowest_rank_2025` > 0（有值时）

### admission_history.csv 校验
- `year` 必须是 2023 / 2024 / 2025 之一
- `lowest_score` 在 200-750 之间（有值时）
- 每省每年每科类应 > 1000 行

### yifenyiduan_{year}.csv 校验
- `score` 在 0-750 之间
- `segment_count` >= 0
- `cumulative_count` >= 0 且随分数递减而递增
- 每省每年每科类应 > 2000 行（分数段覆盖完整）

### control_line_{year}.csv 校验
- `lowest_score` 在 100-750 之间
- 每省每年至少有物理类/历史类（或综合/文理）的本科批控制线

---

## 六、代码结构要求

### 新建脚本文件
1. `scripts/sync_{省份拼音}_{年份}.py` — 主爬取脚本（下载+解析+写入）
2. `scripts/parse_{省份拼音}_pdf.py` — PDF解析工具函数
3. `scripts/validate_{省份拼音}.py` — 数据校验脚本

### 脚本规范
- 使用 `pdfplumber` 解析PDF
- 使用 `pandas` 处理数据
- 使用 `requests` 下载文件
- 进度打印：每完成一个文件打印 `[省份] ✓ 已解析 {文件名} ({行数}行)`
- 错误处理：解析失败的行记录到 `data/raw/{省份拼音}_errors.csv`
- 最终输出爬取统计报告

---

## 七、注意事项

1. **不要覆盖已有数据**：所有CSV都是多省共享的，只能追加，不能覆盖
2. **科类必须正确**：3+1+2省份用"物理类/历史类"，不能用"理科/文科"
3. **PDF解析容错**：考试院PDF格式可能不统一，需处理合并单元格、跨页、空行
4. **专业组代码**：3+1+2省份的专业组代码格式各省不同，按该省实际编码填写
5. **数据来源URL**：control_line 的 source_url 必须填写实际页面URL
6. **2026年数据**：一分一段表和省控线2026年数据需等高考出分后（6月23-26日）才能爬取；如果当前没有2026年数据，先爬2024和2025年的
7. **编码统一**：所有CSV文件使用 UTF-8 编码
8. **完成后重启后端**：数据写入完成后，通知用户重启后端服务以加载新数据
