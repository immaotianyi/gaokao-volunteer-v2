#!/usr/bin/env python3
"""批量生成各省份的爬取提示词文件"""
import os

PROVINCES = [
    # (优先级, 省份, 拼音, 考试院URL, 考试院简称, 高考模式, 首改年份, 备注)
    ("P0", "甘肃", "gansu", "https://www.ganseea.cn", "甘肃省教育考试院", "3+1+2", "2024", "2024年首改3+1+2，历史数据可能仍为文/理科"),
    ("P0", "河南", "henan", "https://www.heao.gov.cn", "河南省招生办公室", "3+1+2", "2025", "2025年首改3+1+2，2024及之前为文/理科"),
    ("P0", "四川", "sichuan", "https://www.sceea.cn", "四川省教育考试院", "3+1+2", "2025", "2025年首改3+1+2，2024及之前为文/理科"),
    ("P0", "陕西", "shaanxi", "https://www.sneac.com", "陕西省教育考试院", "3+1+2", "2025", "2025年首改3+1+2，2024及之前为文/理科"),
    ("P1", "河北", "hebei", "https://www.hebeea.edu.cn", "河北省教育考试院", "3+1+2", "2021", "首批3+1+2省份，数据规范"),
    ("P1", "湖北", "hubei", "https://www.hbea.edu.cn", "湖北省教育考试院", "3+1+2", "2021", "首批3+1+2省份"),
    ("P1", "湖南", "hunan", "https://www.hneao.edu.cn", "湖南省教育考试院", "3+1+2", "2021", "首批3+1+2省份"),
    ("P1", "安徽", "anhui", "https://www.ahzsks.cn", "安徽省教育招生考试院", "3+1+2", "2024", "2024年首改3+1+2"),
    ("P1", "江西", "jiangxi", "https://www.jxeea.cn", "江西省教育考试院", "3+1+2", "2024", "2024年首改3+1+2"),
    ("P1", "福建", "fujian", "https://www.eeafj.cn", "福建省教育考试院", "3+1+2", "2021", "首批3+1+2省份"),
    ("P1", "重庆", "chongqing", "https://www.cqksy.cn", "重庆市教育考试院", "3+1+2", "2021", "首批3+1+2省份"),
    ("P1", "辽宁", "liaoning", "https://www.lnzsks.com", "辽宁招生考试之窗", "3+1+2", "2021", "首批3+1+2省份"),
]

TEMPLATE = '''# 爬取任务：{province} 高考数据（{priority}优先级）

> **本提示词是自包含的完整任务指令，AI agent 拿到后可直接执行。**

---

## 你的身份与任务

你是一个专门负责爬取**{province}**高考数据的数据工程 AI agent。

**你的唯一任务**：从{agency}官网爬取{province}的高考相关数据，清洗后追加写入项目的CSV文件。

---

## ⚠️ 第一步：阅读公共技术规范（必读）

在写任何代码之前，**必须先用 Read 工具完整阅读以下文件**：

```
/Users/sanzhaibanniang/Claude/Projects/gaokao/backend/prompts/_common_spec.md
```

该文件定义了：
- 5类数据文件的**精确字段顺序和格式**（不可改动）
- 科类映射规则
- 爬取步骤
- 校验规则
- 代码结构要求
- 数据样本

**如果你没有阅读该文件就开始写代码，字段顺序极可能出错，导致整个项目数据污染。**

---

## 省份信息

| 项目 | 值 |
|------|-----|
| 省份名（中文） | {province} |
| 省份拼音 | {pinyin} |
| 高考模式 | {mode} |
| 科类取值 | **物理类** / **历史类** |
| 首改年份 | {first_year}（{remark}） |
| 考试院官网 | {url} |
| 考试院全称 | {agency} |

### 科类重要说明
- {province} 是 **{mode}** 省份，CSV 中的 `subject_group` 字段**只能**填 `物理类` 或 `历史类`
- **绝对不能**使用"理科"/"文科"（那是老高考的叫法）
- 如果考试院PDF中写的是"首选物理"/"首选历史"，需转换为"物理类"/"历史类"
{history_note}

---

## 数据源（{agency}）

### 官网入口
{url}

### 数据发布位置（在考试院官网查找）
以下是需要爬取的5类数据及其在考试院官网的典型发布位置。**如果具体URL失效，请在考试院首页搜索对应关键词**：

| 数据类型 | 在考试院网站的位置 | 关键词 |
|---------|-------------------|--------|
| ① 招生计划（plans） | 普通高考 → 招生计划 / 专业目录 | "招生计划"、"专业目录"、"招生专业" |
| ② 一分一段表（yifenyiduan） | 普通高考 → 成绩查询 / 分数统计 | "一分一段"、"成绩分段"、"分数段统计" |
| ③ 省控线（control_line） | 普通高考 → 录取控制分数线 | "控制分数线"、"省控线"、"录取分数线" |
| ④ 历史投档线（admission_history） | 普通高考 → 历年数据 / 投档线 | "投档线"、"投档分数线"、"历年录取" |

### 数据年份要求
| 数据文件 | 需要的年份 | 说明 |
|---------|-----------|------|
| plans_2026.csv | 2026 | 当年招生计划 |
| plans_2025.csv | 2025 | 上年招生计划（含最低分/位次） |
| admission_history.csv | 2023, 2024, 2025 | 近3年历史录取 |
| yifenyiduan_2024.csv | 2024 | 2024年一分一段表 |
| yifenyiduan_2025.csv | 2025 | 2025年一分一段表 |
| yifenyiduan_2026.csv | 2026 | 2026年一分一段表（如已发布） |
| control_line_2024.csv | 2024 | 2024年省控线 |
| control_line_2025.csv | 2025 | 2025年省控线 |
| control_line_2026.csv | 2026 | 2026年省控线（如已发布） |

> **注意**：2026年的一分一段表和省控线通常在6月23-26日高考出分后才发布。如果当前没有2026年数据，**先爬2024和2025年的**，2026年数据待发布后补充。

---

## 你的工作流程

### Phase 1: 准备工作
1. 用 Read 工具阅读 `/Users/sanzhaibanniang/Claude/Projects/gaokao/backend/prompts/_common_spec.md`
2. 用 Read 工具阅读参考脚本 `/Users/sanzhaibanniang/Claude/Projects/gaokao/backend/scripts/sync_guangdong_2026.py`（了解现有代码模式）
3. 用 Read 工具阅读参考脚本 `/Users/sanzhaibanniang/Claude/Projects/gaokao/backend/scripts/parse_guangdong_pdf.py`（了解PDF解析模式）
4. 检查目标CSV文件现有数据的省份覆盖情况：
   ```python
   import pandas as pd
   for f in ['plans_2026.csv','plans_2025.csv','admission_history.csv','yifenyiduan_2026.csv','control_line_2026.csv']:
       df = pd.read_csv(f'data/{{f}}')
       print(f, df['province'].unique())
   ```

### Phase 2: 下载原始数据
1. 访问 {url} ，找到招生计划、一分一段表、省控线、投档线的PDF/Excel下载链接
2. 创建目录 `data/raw/{pinyin}_2026/`
3. 下载文件到该目录，命名规则：
   - `{pinyin}_plans_2026.pdf` — 招生计划
   - `{pinyin}_yifenyiduan_2025.pdf` — 一分一段表
   - `{pinyin}_control_line_2025.pdf` — 省控线
   - `{pinyin}_toudang_2024.pdf` — 投档线

### Phase 3: 解析PDF并写入CSV
1. 创建脚本 `scripts/sync_{pinyin}_2026.py`
2. 用 `pdfplumber` 解析每个PDF
3. 将数据映射到目标字段格式（**字段顺序必须与 _common_spec.md 一致**）
4. **追加写入**对应CSV文件（**不要覆盖已有数据**）
5. 每完成一个文件打印进度：`[{province}] ✓ 已解析 {{文件名}} ({{行数}}行)`

### Phase 4: 校验
1. 创建校验脚本 `scripts/validate_{pinyin}.py`
2. 运行校验，检查：
   - province 字段全部为"{province}"
   - subject_group 只含"物理类"/"历史类"
   - plan_count > 0
   - lowest_score 在 200-750 之间
   - 无空行、无重复行
3. 打印校验报告

### Phase 5: 汇报
完成后输出统计报告：
```
========== {province} 数据爬取报告 ==========
plans_2026.csv:     追加 {n1} 行 (物理类 {n2} + 历史类 {n3})
plans_2025.csv:     追加 {n4} 行
admission_history.csv: 追加 {n5} 行 (2023: {n6}, 2024: {n7}, 2025: {n8})
yifenyiduan_*.csv:  追加 {n9} 行
control_line_*.csv: 追加 {n10} 行
校验结果: ✅ 全部通过 / ❌ {error_count} 个错误
原始文件: data/raw/{pinyin}_2026/ ({file_count}个文件)
```

---

## 代码结构

### scripts/sync_{pinyin}_2026.py（主脚本）
```python
#!/usr/bin/env python3
"""
{province} 高考数据爬取脚本
数据源: {url}
"""
import os
import sys
import pandas as pd
import pdfplumber
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw", "{pinyin}_2026")

PROVINCE = "{province}"
SUBJECT_GROUPS = ["物理类", "历史类"]

def download_files():
    """从{agency}下载原始PDF"""
    os.makedirs(RAW_DIR, exist_ok=True)
    # TODO: 实现下载逻辑
    pass

def parse_plans(pdf_path, subject_group):
    """解析招生计划PDF"""
    # TODO: 实现PDF解析，返回 DataFrame
    # 字段顺序: province,subject_group,batch,university_code,university_name,
    #          group_code,major_code,major_name,plan_count,tuition,
    #          lowest_score_2025,lowest_rank_2025,is_new,school_type,
    #          major_category,subject_requirement,plan_count_prev
    pass

def parse_yifenyiduan(pdf_path, subject_group, year):
    """解析一分一段表PDF"""
    # 字段顺序: province,year,subject_group,batch,score,segment_count,cumulative_count
    pass

def parse_control_line(pdf_path, year):
    """解析省控线PDF"""
    # 字段顺序: province,year,batch_section,batch,subject_group,line_type,lowest_score,source_url
    pass

def parse_toudang_history(pdf_path, year, subject_group):
    """解析历史投档线PDF"""
    # 字段顺序: year,province,subject_group,batch,university_code,university_name,
    #          group_code,major_code,major_name,lowest_score,lowest_rank,
    #          avg_score,applicant_count,source_file
    pass

def append_to_csv(new_df, csv_filename):
    """安全追加数据到CSV（去重）"""
    csv_path = os.path.join(DATA_DIR, csv_filename)
    if os.path.exists(csv_path):
        existing = pd.read_csv(csv_path)
        merged = pd.concat([existing, new_df], ignore_index=True)
        merged = merged.drop_duplicates()
    else:
        merged = new_df
    merged.to_csv(csv_path, index=False, encoding="utf-8")
    return len(new_df)

def main():
    print(f"[{PROVINCE}] 开始爬取数据...")
    download_files()
    # 解析并写入各类数据
    # ...
    print(f"[{PROVINCE}] ✓ 爬取完成")

if __name__ == "__main__":
    main()
```

### scripts/validate_{pinyin}.py（校验脚本）
```python
#!/usr/bin/env python3
"""{province} 数据校验"""
import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
PROVINCE = "{province}"
VALID_SUBJECTS = {"物理类", "历史类"}
VALID_SCHOOL_TYPES = {"985", "211", "双一流", "省属重点", "普通本科", "民办"}

errors = []

def check_csv(filename, checks):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return
    df = pd.read_csv(path)
    prov_data = df[df["province"] == PROVINCE]
    if len(prov_data) == 0:
        print(f"⚠ {filename}: 无{PROVINCE}数据")
        return
    for check_name, check_fn in checks.items():
        try:
            check_fn(prov_data)
            print(f"✓ {filename} - {{check_name}}")
        except Exception as e:
            errors.append(f"{filename} - {{check_name}}: {{e}}")
            print(f"✗ {filename} - {{check_name}}: {{e}}")

# 运行校验
print(f"========== {PROVINCE} 数据校验 ==========")
# TODO: 添加具体校验逻辑
print(f"\\n错误数: {{len(errors)}}")
```

---

## ⚠️ 关键注意事项

1. **字段顺序**：CSV的列顺序必须与 `_common_spec.md` 中定义的**完全一致**，不能多列、少列或调换顺序
2. **科类**：{province}是{mode}省份，`subject_group` 只能是 `物理类` 或 `历史类`
   {history_note_detail}
3. **追加不覆盖**：`data/*.csv` 是全国共享文件，已有其他省份数据，**只能追加，不能覆盖**
4. **空值**：缺失字段留空（CSV中为空字符串），**不要写 null / NA / None / nan**
5. **PDF解析**：考试院PDF可能有合并单元格、跨页表格，需要正确处理
6. **专业组代码**：{province}的专业组代码格式按该省实际编码填写
7. **去重**：追加前用 `drop_duplicates()` 去重，避免重复写入
8. **编码**：所有CSV使用 UTF-8 编码
9. **完成后**：通知用户重启后端服务（`uvicorn main:app`）以加载新数据

---

## 完成标准

✅ 以下条件全部满足才算完成：
1. 5类数据全部爬取并追加到对应CSV
2. `province` 字段全部为"{province}"
3. `subject_group` 只含"物理类"/"历史类"
4. `plan_count` 全部 > 0
5. 无重复行
6. 无 null/NA/None 字符串
7. 校验脚本通过
8. 输出爬取统计报告
'''

def gen_history_note(first_year, remark, province):
    """生成历史数据的科类说明"""
    if first_year == "2021":
        return ""
    # 2024或2025首改的省份，历史数据有科类转换问题
    return f"""
### ⚠️ 历史数据科类转换（重要）
{remark}。爬取历史数据时注意：
- **{first_year}年及之后**的数据：使用 `物理类` / `历史类`
- **{first_year}年之前**的数据（如果考试院仍以文/理科发布）：需转换为 `物理类` / `历史类`
  - 理科 → 物理类
  - 文科 → 历史类
- admission_history.csv 中所有{province}数据统一使用 `物理类` / `历史类`"""

def gen_history_note_detail(first_year, remark):
    if first_year == "2021":
        return ""
    return f'如果考试院旧数据用"理科/文科"，需转换为"物理类/历史类"（{remark}）'

def main():
    prompts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")
    os.makedirs(prompts_dir, exist_ok=True)
    
    for priority, province, pinyin, url, agency, mode, first_year, remark in PROVINCES:
        history_note = gen_history_note(first_year, remark, province)
        history_note_detail = gen_history_note_detail(first_year, remark)

        content = TEMPLATE
        content = content.replace("{priority}", priority)
        content = content.replace("{province}", province)
        content = content.replace("{pinyin}", pinyin)
        content = content.replace("{mode}", mode)
        content = content.replace("{first_year}", first_year)
        content = content.replace("{remark}", remark)
        content = content.replace("{url}", url)
        content = content.replace("{agency}", agency)
        content = content.replace("{history_note}", history_note)
        content = content.replace("{history_note_detail}", history_note_detail)
        
        filename = f"{priority.lower()}_{pinyin}.md"
        filepath = os.path.join(prompts_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✓ {filename} ({len(content)} 字符)")
    
    print(f"\n共生成 {len(PROVINCES)} 个提示词文件 → {prompts_dir}/")

if __name__ == "__main__":
    main()
