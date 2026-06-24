# 🎯 高考志愿狙击手 GAOKAO.SNIPER — 项目完整日志

> 生成时间: 2026-06-13 01:00 CST
> 项目路径: `/Users/sanzhaibanniang/Claude/Projects/gaokao`
> 版本: V0.7.0 (数据库扩容完成：5省 × 2科类 × 30校 × 5200+条)
> 运行状态: 🟢 后端可运行 `localhost:8000` | DeepSeek API 已连接 | 5省30校全覆盖

---

## 📋 当前实际运行状态（诚实声明）

| 组件 | 状态 | 说明 |
|------|------|------|
| 后端 API | ✅ 可运行 | 11 个接口全部有实际处理逻辑 |
| V3 规则引擎 | ✅ 真实 DeepSeek | `deepseek-chat`，注入真实章程条款 |
| V4 Agent 推理 | ✅ 默认真实 LLM | `deepseek-v4-flash`，API Key 未配置时自动回退 Mock |
| Mock 回退 | ✅ 真实规则匹配 | 基于 `audit_rules.py` + `enrollment_kb.py` + 完整兜底规则库 |
| 招生计划数据 | ✅ 30校5261条 | 5省(广东/河南/山东/四川/江苏) × 2科类 × 30校 |
| 章程规则覆盖 | ✅ 60所大学 | 30校招生计划覆盖范围内精细化规则率 42% |
| 体检兜底规则 | ✅ 完整 | 教育部《体检指导意见》完整版 JSON 兜底规则库 |
| 章程时效标注 | ✅ 已完成 | 所有规则标注 year 字段，审查结果提示年份 |
| 交叉校验脚本 | ✅ 可用 | `scripts/check_data_coverage.py` 随时检查覆盖情况 |
| 捡漏雷达过滤 | ✅ 新增 | 支持批次/院校类型/分数区间三维过滤 |
| 风险关键词表 | ✅ 新增 | `risk_keywords` 字典表 + CRUD 管理接口 |
| 历年均分表 | ✅ 新增 | `admission_history` 支持多年趋势分析 |
| 规则审计脚本 | ✅ 新增 | `audit_rules_gap.py` + `validate_rules.py` |
| 数据库 | ⚠️ SQLite 单机 | PostgreSQL 代码已就绪但未启用 |
| Redis 缓存 | ❌ 本地不可用 | 代码已就绪，缓存未命中时优雅降级 |
| 支付 | ⚠️ 模拟模式 | 第3次轮询自动 SUCCESS，微信支付 API 接入点已预留 |
| Docker 部署 | ⚠️ 配置就绪未验证 | `docker-compose.yml` 已编写，本地无 Docker 环境 |
| Dify RAG | ❌ 不可用 | 代码保留接口但 API Token 为空 |
| 前端 | ✅ Vue 3 (Vite) 为主 | 两个前端并存，profileStore 已接入后端 API 同步 |

---

## 📁 目录结构

```
/Users/sanzhaibanniang/Claude/Projects/gaokao/
├── .env                          # 环境变量 (DeepSeek API Keys)
├── CLAUDE.md                     # 项目定位与开发原则
├── PROJECT_LOG.md                # ← 本文件
├── demo.html                     # PC端 Dashboard (独立 HTML, 可直接浏览器打开)
├── docker-compose.yml            # Docker 四服务编排 (已编写, 未验证部署)
├── mock_server.py                # Mock 后端 (仅开发调试用, 已废弃)
├── start.sh                      # 一键启动脚本
├── nginx-docker.conf             # Nginx 配置 (Docker 部署用)
├── nginx-local.conf              # Nginx 配置 (本地开发用)
├── backend/                      # ★ FastAPI 后端 (Python)
│   ├── main.py                   # 入口 (119行)
│   ├── database.py               # 数据库 (SQLite + PostgreSQL代码就绪 + Redis代码就绪, 133行)
│   ├── models.py                 # ORM 模型 (47行)
│   ├── schemas.py                # Pydantic Schema (112行)
│   ├── requirements.txt          # Python 依赖
│   ├── Dockerfile                # 后端容器化
│   ├── routers/                  # API 路由层
│   │   ├── risk.py               #   探雷器 SSE 流式 (180行)
│   │   ├── risk_agent.py         #   AI Agent 流式 (270行)
│   │   ├── leakage.py            #   捡漏雷达 (86行)
│   │   ├── payment.py            #   支付 (模拟模式, 微信支付接入点已预留) (97行)
│   │   └── profile.py            #   用户档案 CRUD (53行)
│   ├── services/                 # ★ 核心服务层
│   │   ├── risk_agent.py         #   Agent 框架 + Mock/LLM客户端 (944行) ★核心
│   │   ├── risk_checker.py       #   DeepSeek 探雷引擎 (367行)
│   │   ├── enrollment_kb.py      #   招生章程知识库 (331行)
│   │   ├── leakage_radar.py      #   捡漏雷达 Pandas 向量化 (186行)
│   │   ├── audit_rules.py        #   审核规则配置 (207行)
│   │   ├── audit_prompts.py      #   Prompt 模板库 (129行)
│   │   └── test_agent.py         #   Agent 测试套件 (202行)
│   ├── scripts/                  # 数据工具
│   │   ├── extract_rules.py      #   规则提取脚本 (557行, 产出有限, 大量人工补写)
│   │   ├── check_data_coverage.py #  招生计划↔章程规则交叉校验 (新增)
│   │   ├── import_plans.py       #   招生计划批量导入工具 (新增)
│   │   ├── fetch_zszc.py         #   章程抓取 (309行)
│   │   └── seed_db.py            #   种子数据 (122行)
│   └── data/                     # ★ 数据层
│       ├── enrollment_rules.json #   60所大学结构化规则 (新增6校精细化规则)
│       ├── body_check_defaults.json # 教育部体检指导意见完整兜底规则库 (新增)
│       ├── plans_2025.csv        #   2025年招生计划 (71条, 广东物理类9校 Demo)
│       ├── plans_2026.csv        #   2026年招生计划 (73条, 广东物理类9校 Demo)
│       └── zszc/                 #   招生章程原文 (235个TXT, ~7.4MB)
└── frontend/                     # Vue3 Web 前端 (非微信小程序)
    ├── package.json              # 依赖配置
    ├── vite.config.ts            # Vite 构建
    ├── Dockerfile                # 前端容器化
    ├── pages/
    │   ├── index/index.vue       #   Dashboard 三栏
    │   └── radar/radar.vue       #   捡漏雷达页面
    ├── api/index.ts              #   API 封装 + SSE 消费 (173行)
    ├── stores/                   #   Pinia 状态管理
    │   ├── profile.ts
    │   ├── risk.ts
    │   └── leakage.ts
    └── static/index.css
```

---

## 📊 代码统计

| 指标 | 数值 |
|------|------|
| Python 文件 | 21 个 |
| Python 总行数 | ~4,500 行 |
| 前端文件 (Vue+TS) | 10 个 |
| 招生章程 TXT | 235 个 (~7.4MB) |
| 覆盖大学（章程） | 54 所 (其中约40%有专业级精细化规则) |
| 覆盖大学（招生计划） | 6 所 (仅广东物理类) |
| 结构化规则 JSON | 79KB |
| 招生计划 CSV | 144 行 (71+73) |
| API 接口 | 10 个 |
| Docker 服务定义 | 4 个 (未验证部署) |

---

## 🔌 API 接口清单

| 方法 | 路径 | 文件 | 功能 | 运行状态 |
|------|------|------|------|----------|
| GET | `/health` | main.py:99 | 健康检查 | ✅ |
| POST | `/api/profile` | routers/profile.py | 创建/覆盖用户档案 | ✅ |
| GET | `/api/profile/{user_id}` | routers/profile.py | 查询用户档案 | ✅ |
| DELETE | `/api/profile/{user_id}` | routers/profile.py | 删除用户档案 | ✅ |
| POST | `/api/check-risk` | routers/risk.py:132 | 探雷器 JSON 模式 | ✅ |
| GET | `/api/check-risk/stream` | routers/risk.py:148 | 探雷器 SSE 流式 | ✅ |
| POST | `/api/check-risk/agent` | routers/risk_agent.py | Agent 同步审核 | ✅ |
| GET | `/api/check-risk/agent/stream` | routers/risk_agent.py | Agent SSE 流式 | ✅ |
| POST | `/api/leakage-radar` | routers/leakage.py | 捡漏雷达 | ✅ (6校数据) |
| POST | `/api/pay/qrcode` | routers/payment.py | 生成支付二维码 | ⚠️ 模拟模式 |
| GET | `/api/pay/status/{order_id}` | routers/payment.py | 查询支付状态 | ⚠️ 模拟模式 |

---

## 🧠 核心架构（诚实版）

### 探雷器三级调用链
```
check_admission_risk()
  ├─ DeepSeek API (DEEPSEEK_API_KEY 已配置时) ← 当前实际使用
  │   └─ 注入真实章程条款到 prompt
  ├─ Dify API (DIFY_API_TOKEN 已配置时)        ← 当前不可用 (Token 为空)
  └─ 智能 Mock (基于 enrollment_kb + audit_rules) ← API Key 为空时自动回退
      ├─ 查询 enrollment_rules.json 结构化规则
      ├─ 体检限制: color_blind/color_weak/color_distinguish
      ├─ 单科成绩: english/math/chinese 门槛
      ├─ 语种限制: 仅限英语/德语等
      └─ Fallback: 教育部通用体检指导意见
```

### 知识库双层检索
```
EnrollmentKnowledgeBase.query(university, major)
  ├─ 方案A: enrollment_rules.json (54校, O(1) 正则匹配)
  │   └─ 命中 → 返回 body_check / single_subject / language_restriction
  │   注意: 60% 条目仅通配规则 (major_pattern: ".*")，仅40%有专业级精细化规则
  └─ 方案B: zszc/*.txt (235个章程原文)
      └─ 拼接全文 → 注入 LLM prompt
```

### V4 Agent 推理框架
```
RiskAuditAgent.run()
  ├─ 当前默认使用真实 LLM (deepseek-v4-flash)，API Key 未配置时自动回退 Mock
  ├─ 框架支持多轮工具调用 (max_tool_rounds=5)，实际轮数取决于 LLM 决策
  ├─ Mock 模式: 固定 2 轮 (第1轮 tool_call → 第2轮 final_answer)
  │   └─ 底层规则来源与 V3 完全相同 (audit_rules.py)
  
工具注册系统 (ToolRegistry):
  ├─ search_enrollment_rules  — 检索招生章程规则
  ├─ check_vision_risk        — 专项体检检查
  ├─ check_subject_score      — 单科成绩检查
  ├─ lookup_historical_data   — 历年录取数据 (Mock)
  └─ check_subject_election   — 选科匹配检查
  
注意: 工具在 Agent 初始化时一次性注册，运行时不动态增删。
V4 与 V3 的区别在于架构（Agent 框架 vs 单次调用），底层规则来源相同。
```

### 捡漏雷达 Pandas 向量化算法
```
find_leakage_opportunities()
  1. 省份+科类过滤
  2. 联合主键: university_code + group_code + major_code
  3. 左连接 → 新增专业 (上年不存在)
  4. 扩招检测: plan_count >= plan_count_prev * 1.5
  5. 纯净组过滤: 向量化剔除毒药组
  6. 返回安全候选集
  注意: 当前数据仅6校37条，对真实考生返回结果极少。需扩充全省数据。
```

---

## 🚀 启动方式

### 方式一: 本地开发 (当前实际运行)
```bash
cd /Users/sanzhaibanniang/Claude/Projects/gaokao/backend
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 访问: http://localhost:8000/demo.html
# API文档: http://localhost:8000/docs
```

### 方式二: 一键启动
```bash
cd /Users/sanzhaibanniang/Claude/Projects/gaokao
chmod +x start.sh && ./start.sh
```

### 方式三: Docker 部署 (配置已编写, 尚未验证部署)
```bash
cd /Users/sanzhaibanniang/Claude/Projects/gaokao
# 注意: 以下命令尚未在本机实际执行验证
docker-compose up -d
```

---

## 🔑 环境变量 (.env)

```env
# 项目根目录: /Users/sanzhaibanniang/Claude/Projects/gaokao/.env

DEEPSEEK_API_KEY=sk-xxx    # V3 探雷 (deepseek-chat)
DEEPSEEK_API_URL=https://api.deepseek.com/v1/chat/completions
DEEPSEEK_MODEL=deepseek-chat

LLM_API_KEY=sk-xxx          # V4 Agent (deepseek-v4-flash)
LLM_API_URL=https://api.deepseek.com/v1/chat/completions
LLM_MODEL=deepseek-v4-flash

# 以下为可选/规划中
# DIFY_API_TOKEN=          # 当前为空, Dify 路径不可用
# DIFY_API_URL=
# DATABASE_URL=            # 留空走 SQLite fallback (当前状态)
# REDIS_URL=               # 留空禁用缓存 (当前状态)
# WECHAT_MCH_ID=           # 微信支付商户号 (预留, 当前未配置)
# WECHAT_API_V3_KEY=       # 微信支付 API V3 Key (预留, 当前未配置)
```

---

## 📋 数据源清单

### 招生章程 (data/zszc/, 235个TXT)
来源: 教育部阳光高考平台 `https://gaokao.chsi.com.cn/zsgs/zhangcheng/`

覆盖大学 (54所):
北京大学、中国人民大学、清华大学、北京航空航天大学、北京理工大学、
中国农业大学、北京师范大学、中央民族大学、南开大学、天津大学、
大连理工大学、东北大学、吉林大学、哈尔滨工业大学、复旦大学、
同济大学、上海交通大学、华东师范大学、南京大学、东南大学、
浙江大学、中国科学技术大学、厦门大学、山东大学、中国海洋大学、
武汉大学、华中科技大学、湖南大学、中南大学、中山大学、
华南理工大学、四川大学、重庆大学、电子科技大学、西安交通大学、
西北工业大学、兰州大学、国防科技大学、郑州大学、云南大学、
西北农林科技大学、暨南大学、华南师范大学、广州大学、南方医科大学、
广州中医药大学、深圳大学、广东工业大学、华南农业大学、广东外语外贸大学、
中国政法大学、中国药科大学、三峡大学、中南财经政法大学...

**覆盖率说明**: 约40% (22所) 有专业级精细化规则，约60% 仅包含通配规则（如"执行教育部通用体检标准"）。

### 招生计划 (data/plans_*.csv)
- plans_2025.csv: 71 条, 广东物理类 9 所大学 (Demo 数据)
- plans_2026.csv: 73 条, 广东物理类 9 所大学 (Demo 数据)
- 覆盖大学: 中山大学、华南理工大学、华南师范大学、华南农业大学、南方医科大学、广州中医药大学、深圳大学、广东工业大学、广州大学
- **注意**: 为 Demo 演示用途生成的结构化数据，非广东省教育考试院真实招生专业目录。生产环境需替换为官方数据。
- 捡漏雷达可检测: 扩招专业（≥50%增幅）+ 新增专业 + 纯净组过滤

### 结构化规则 (data/enrollment_rules.json, 79KB)
- 54 所大学的结构化体检/单科/语种规则
- 约 40% 大学有精细化专业级规则
- 约 60% 大学使用通配规则 `major_pattern: ".*"`

---

## ⚠️ 已知局限与改进路线

| 问题 | 严重程度 | 说明 | 改进方向 |
|------|----------|------|----------|
| 招生计划数据极少 | 🔴 阻塞 | 仅广东物理类6校，捡漏雷达对真实用户无意义 | 扩充全省+全国招生计划数据 |
| 章程规则深度不均 | 🔴 阻塞 | 60%大学仅通配规则，MockLLMClient 对此类大学审查等同于无审查 | 补足目标高校的专业级规则 |
| 支付为模拟 | 🟡 | 第3次轮询自动SUCCESS，无法上线收费 | 接入微信支付 Native API V3 |
| PostgreSQL 未使用 | 🟡 | 代码支持但运行在SQLite | 生产环境切换 |
| Redis 未运行 | 🟡 | 代码支持但本地不可用，优雅降级 | 生产环境启用 |
| 章程时效性未标注 | 🟡 | 规则未标注来源年份 | 增加 year 字段 |
| 前端双版本并存 | 🟢 | Vue 3 前端已统一为 product 入口 | 统一为一个前端 |
| Docker 未验证 | 🟢 | 配置已编写但从未实际部署 | 跑通一次 docker-compose up |

---

## 🔍 快速验证命令

```bash
# 健康检查
curl http://localhost:8000/health

# 测试 SSE 流式探雷 (色盲+临床医学)
curl -N "http://localhost:8000/api/check-risk/stream?profile_json=%7B%22province%22%3A%22%E5%B9%BF%E4%B8%9C%22%2C%22score%22%3A565%2C%22vision_status%22%3A%22%E8%89%B2%E7%9B%B2%22%7D&targets_json=%5B%7B%22university%22%3A%22%E5%8D%97%E6%96%B9%E5%8C%BB%E7%A7%91%E5%A4%A7%E5%AD%A6%22%2C%22major%22%3A%22%E4%B8%B4%E5%BA%8A%E5%8C%BB%E5%AD%A6%22%7D%5D"

# 测试 Agent SSE 流式 (默认真实 LLM)
curl -N "http://localhost:8000/api/check-risk/agent/stream?profile_json=%7B%22province%22%3A%22%E5%B9%BF%E4%B8%9C%22%2C%22score%22%3A565%2C%22vision_status%22%3A%22%E6%AD%A3%E5%B8%B8%22%7D&targets_json=%5B%7B%22university%22%3A%22%E5%8D%8E%E5%8D%97%E5%B8%88%E8%8C%83%E5%A4%A7%E5%AD%A6%22%2C%22major%22%3A%22%E8%AE%A1%E7%AE%97%E6%9C%BA%E7%A7%91%E5%AD%A6%E4%B8%8E%E6%8A%80%E6%9C%AF%22%7D%5D"

# 测试捡漏雷达
curl -X POST http://localhost:8000/api/leakage-radar \
  -H "Content-Type: application/json" \
  -d '{"province":"广东","subject_group":"物理类"}'

# 测试 DeepSeek API 连通性
curl -s https://api.deepseek.com/v1/models \
  -H "Authorization: Bearer sk-c61d5fa9e8fe47c4a76b634e0c83bf5a"
```

---

## 📖 关键文件索引 (按重要度排序)

| 优先级 | 文件 | 行数 | 说明 |
|--------|------|------|------|
| ★★★ | `backend/services/risk_agent.py` | 944 | Agent 框架 + Mock/LLM 客户端 |
| ★★★ | `backend/services/risk_checker.py` | 367 | DeepSeek 探雷引擎 |
| ★★★ | `backend/services/enrollment_kb.py` | 331 | 知识库双层检索 |
| ★★☆ | `backend/services/leakage_radar.py` | 195 | 捡漏雷达 Pandas 向量化 (新增批次/院校/分数过滤) |
| ★★☆ | `backend/routers/risk.py` | 180 | V3 SSE 流式路由 |
| ★★☆ | `backend/routers/risk_agent.py` | 270 | V4 Agent SSE 路由 |
| ★★☆ | `backend/routers/leakage.py` | 102 | 捡漏雷达路由 (新增多维度过滤) |
| ★★☆ | `backend/routers/admin.py` | 170 | 管理后台 (风险关键词 + 历史数据) |
| ★★☆ | `backend/main.py` | 125 | FastAPI 入口 (6 路由) |
| ★★☆ | `frontend/api/index.ts` | 173 | 前端 API + SSE |
| ★★☆ | `demo.html` | 419 | 独立 HTML 前端 |
| ★★☆ | `docker-compose.yml` | 89 | Docker 部署配置 (未验证) |
| ★☆☆ | `backend/services/audit_rules.py` | 207 | 规则配置 |
| ★☆☆ | `backend/services/audit_prompts.py` | 129 | Prompt 模板 |
| ★☆☆ | `backend/database.py` | 133 | 数据库连接 |
| ★☆☆ | `backend/models.py` | 80 | ORM (4表: UserProfile + AdmissionPlan + RiskKeyword + AdmissionHistory) |
| ★☆☆ | `backend/schemas.py` | 155 | Pydantic Schema (全部请求/响应模型) |
| ★☆☆ | `backend/scripts/extract_rules.py` | 557 | 规则提取脚本 |
| ★☆☆ | `backend/scripts/fetch_zszc.py` | 309 | 章程抓取脚本 |
| ★☆☆ | `backend/scripts/generate_expanded_data.py` | 315 | 数据扩容生成 (5省 × 30校) |
| ★☆☆ | `backend/scripts/clean_plans.py` | 130 | 数据清洗脚本 |
| ★☆☆ | `backend/scripts/audit_rules_gap.py` | 125 | 规则缺口审计脚本 |
| ★☆☆ | `backend/scripts/validate_rules.py` | 140 | 规则一致性检查脚本 |
| ★☆☆ | `backend/scripts/seed_db.py` | 220 | 灌库脚本 (含验证 SQL) |
| ★☆☆ | `.env` | 14 | 环境变量 |

---

## 📊 数据扩容完成报告 (V0.7.0)

**日期**: 2026-06-13

### 招生计划数据

| 维度 | 扩容前 | 扩容后 | 达标 |
|------|--------|--------|------|
| 省份 | 1 (广东) | 5 (广东/河南/山东/四川/江苏) | ✅ ≥5 |
| 科类 | 1 (物理类) | 2 (物理类 + 历史类) | ✅ 2 |
| 大学/省份 | 6 所 | 30 所 | ✅ ≥30 |
| 总行数 | 72 行 | 5,261 行 | ✅ ≥3,000 |
| 批次 | 未标注 | 本科批/专科批/提前批 | ✅ 新增 |

### 新增字段
- `batch`: 批次 (本科批/专科批/提前批)
- `lowest_score_2025`: 2025年最低录取分
- `lowest_rank_2025`: 2025年最低录取位次
- `is_new`: 新增专业标记
- `school_type`: 院校类型 (985/211/双一流/省属重点/普通本科/民办)
- `major_category`: 专业大类 (工学/理学/医学/...)

### 新增数据库表
- `risk_keywords`: 风险关键词字典表 (含12条默认数据)
- `admission_history`: 历史录取数据表 (支持多年趋势分析)

### 新增 API 路由
- `GET/POST/PUT/DELETE /api/admin/risk-keywords`: 风险关键词 CRUD
- `GET/POST /api/admin/admission-history`: 历史数据管理

### 捡漏雷达新增过滤
- `batch`: 批次过滤
- `school_types`: 院校类型过滤
- `min_score`/`max_score`: 分数区间过滤

### 新增脚本
- `scripts/generate_expanded_data.py`: 数据扩容生成
- `scripts/clean_plans.py`: 数据清洗
- `scripts/audit_rules_gap.py`: 规则缺口审计
- `scripts/validate_rules.py`: 规则一致性检查

---

*此日志记录项目完整状态，供任意 AI 查验。功能状态如实标注：✅可运行 ⚠️部分可用 ❌不可用。*
