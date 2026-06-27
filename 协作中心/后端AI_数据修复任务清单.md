# 后端 AI 数据修复任务清单（#13 P0 事故）

> 下达时间：2026-06-27 11:32:00 | 下达人：审核员（用户授权直接下达）
> 背景：#13 并发追加竞态已实锤造成数据丢失（详见时间线 11:30:28 记录）
> 已保护：损坏状态已快照至 `backend/data/_snapshot_20260627_1130_corrupt/`，修复前禁止任何新省数据进库
> 决策：追加模式改为**分省临时文件 + 串行合并器**（不再并发写同一 CSV）

## 强制前提：先修 #14，再做数据恢复

### 任务 #14 — 追加模式改造（root fix，CRITICAL）

**问题**：当前 12 个 `sync_{省}_2026.py` 各自「read master CSV → concat → to_csv」并发写同一文件，后写覆盖先写。

**方案（分省 raw + 串行合并）**：
1. 新建目录 `backend/data/raw/`（按省隔离，无共享文件）
2. 改造所有 `sync_{省}_*.py`：爬取结果只写 `data/raw/{省份}_{类型}.csv`（如 `data/raw/河南_yifenyiduan_2026.csv`、`data/raw/福建_plans_2026.csv`），**禁止再碰主 CSV**（plans_2026.csv / yifenyiduan_*.csv / admission_history.csv / control_line_*.csv）
3. 新建 `backend/scripts/merge_all.py`（唯一可写主 CSV 的进程，**串行执行**）：
   - 扫 `data/raw/` 所有文件
   - 按类型 groupby：所有 `*_plans_2026.csv` → 合并进 `plans_2026.csv`
   - 合并时 `drop_duplicates(subset=[province, subject_group, batch, university_code, major_group])` 去重（subset 必须能唯一标识专业组）
   - 合并后跑校验闸门（见 #20），不达标则报错退出、不写主 CSV
   - 原子写：先写 `plans_2026.csv.tmp` 再 `os.replace` 覆盖（避免半写状态）
4. 在 `_common_spec.md` Step 4 顶部加红字警告：「爬虫脚本只写 data/raw/{省}_{类型}.csv，禁止直接改主 CSV；主 CSV 由 merge_all.py 统一重建」

**验收**：任一 sync 脚本 grep 不到 `plans_2026.csv`/`yifenyiduan_`/`admission_history.csv`/`control_line_` 直接写入；merge_all.py 跑通且产物通过 #20 闸门。

---

## 数据恢复（#14 完成后执行）

### 任务 #15 — 广东 plans_2026 恢复（378→1856 行）

- 现 plans_2026 广东=378 vs plans_2025 广东=4970，2026 数据缺失
- 跑 `backend/scripts/sync_guangdong_2026.py` 重新爬取，输出到 `data/raw/广东_plans_2026.csv`
- 合并后广东 plans_2026 应 ≥1500 行（专业组级），对照 `import_guangdong_2026.py` 的历史产物校验

### 任务 #16 — 福建 plans_2026 异常处理（26864 行去重）

- 福建 26864 行是广东(378)的 71 倍，疑似 per-major 粒度混杂或重复
- 核查 `sync_fujian` 系列脚本（download_fujian_*.py / parse_fujian_plans.py）实际输出粒度
- 若是 per-major：聚合到专业组级（与广东一致），再写 `data/raw/福建_plans_2026.csv`
- 预期福建专业组级 plans_2026 应在 500-1500 行区间，26864 必有问题

### 任务 #17 — 四川/江苏 409 占位行清理

- 四川=江苏=恰好各 409 行，统计绝无可能，疑似模板/占位
- 核查 `sync_sichuan`/`sync_jiangsu`（若存在）产物，若为占位数据则删除 `data/raw/四川_*.csv`、`data/raw/江苏_*.csv`
- 这两省暂无可靠源则标 TODO，不入主 CSV

### 任务 #18 — 各省 yifenyiduan + admission_history 完整性补全

- yifenyiduan_2026：除广东(8816)外全 484-1612（应 12000+/省=2科类×3年×2000+）
- admission_history：海南6/安徽76/上海264/内蒙古182 明显残缺
- 逐省跑对应 `sync_{省}_2026.py` 补全，输出到 `data/raw/`
- 重点 12 省（粤/赣/甘/陕/皖/湘/豫/渝/辽/川/冀/闽）每省 yifenyiduan_2026 ≥4000 行

### 任务 #19 — plans_2025 多省恢复

- 现 plans_2025 仅剩广东(4970)+甘肃(4571)，其余省份 2025 计划全丢
- 从各 `sync_{省}` 脚本的历史备份或重爬补回，输出 `data/raw/{省}_plans_2025.csv`

### 任务 #20 — 统一校验闸门（merge_all.py 内置，防再发生）

合并器对每个产物跑行数阈值校验，**任一不达标则整体回滚、不写主 CSV**：
- yifenyiduan：每省每年每科类 ≥ 2000 行
- plans_2026：每省每科类 ≥ 500 行（专业组级）
- admission_history：每省每年每科类 ≥ 1000 行
- control_line：每省每年 ≥ 6 行
- 全表 province 字段无空值、无重复 unique_key（leakage_radar 用的 university_name|major_group|subject_group）
- 输出校验报告到 `backend/data/_merge_report_{时间戳}.txt`

---

## 执行顺序与协作闭环

1. 先做 #14（root fix）→ 跑 merge_all.py 验证空跑无错
2. 依次 #15→#16→#17→#18→#19，每项产出 raw 文件后单测
3. 全部 raw 就绪后跑 merge_all.py 一次性重建主 CSV
4. #20 闸门全绿后，重启 uvicorn，跑 `backend/data/_audit_completeness.py` 复核各省行数
5. 时间线写：`[时间][后端AI] ✅ 完成 #14-#20 数据修复，12 省完整性达标`
6. 完成说明归档 `协作中心/反馈/20260627_后端AI_数据修复说明.md`

## 红线
- 修复期间 uvicorn 可继续跑（用旧数据），但**禁止任何 sync 脚本直接写主 CSV**
- 主 CSV 只能由 merge_all.py 在所有 raw 就绪后一次性重建
- 重建后必须过 #20 闸门，否则回滚到 `_snapshot_20260627_1130_corrupt`
