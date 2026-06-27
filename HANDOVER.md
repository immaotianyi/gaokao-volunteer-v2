# 🎯 高考志愿狙击手 — 项目交接文档

> **生成时间**: 2026-06-25  
> **项目路径**: `/Users/sanzhaibanniang/Claude/Projects/gaokao`  
> **GitHub仓库**: https://github.com/immaotianyi/gaokao-volunteer-v2  
> **当前版本**: V0.7.0  
> **交接对象**: 下一任AI开发者

---

## 📋 项目概述

### 产品定位
**高考志愿狙击手** 是一款AI驱动的高考志愿填报Web应用，帮助学生科学、精准地填报志愿，核心功能包括：
- **探雷器**（Risk Scanner）：检测退档风险
- **捡漏雷达**（Leakage Radar）：发现低竞争录取机会
- **AI志愿顾问**（Advisor）：智能咨询对话

### 技术栈
| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + Vite + TypeScript + Vue Router + Pinia |
| 后端 | Python FastAPI + DeepSeek API + SQLAlchemy |
| 数据库 | SQLite（开发）/ PostgreSQL（生产就绪） |
| 缓存 | Redis（代码就绪，本地未运行） |
| 部署 | Docker Compose（配置已完成，未验证） |
| AI推理 | DeepSeek API（V3/V4）+ 本地规则引擎（Mock降级） |

---

## 🚀 快速启动

### 前置条件
1. **后端**: Python 3.9+，安装依赖：`pip install -r backend/requirements.txt`
2. **前端**: Node.js 18+，安装依赖：`cd frontend && npm install`
3. **环境变量**: 复制 `backend/.env.example` 为 `backend/.env`，填入DeepSeek API Key

### 启动命令
```bash
# 终端1：启动后端
cd /Users/sanzhaibanniang/Claude/Projects/gaokao/backend
uvicorn main:app --reload --port 8000

# 终端2：启动前端
cd /Users/sanzhaibanniang/Claude/Projects/gaokao/frontend
npm run dev

# 访问
# 前端: http://localhost:5173
# 后端API文档: http://localhost:8000/docs
# 健康检查: http://localhost:8000/health
```

### 后台启动（不占用终端）
```bash
# 后端
cd /Users/sanzhaibanniang/Claude/Projects/gaokao/backend
nohup uvicorn main:app --port 8000 > ../backend.log 2>&1 &

# 前端
cd /Users/sanzhaibanniang/Claude/Projects/gaokao/frontend
nohup npm run dev > ../frontend.log 2>&1 &
```

---

## 📁 项目结构

```
/Users/sanzhaibanniang/Claude/Projects/gaokao/
├── HANDOVER.md                # ← 本文件
├── README.md                  # 项目说明（建议创建）
├── .gitignore                # Git忽略规则（已排除敏感文件）
├── .env.example              # 环境变量模板
│
├── backend/                  # ★ FastAPI 后端
│   ├── main.py              # 入口（125行，6路由注册）
│   ├── database.py          # 数据库连接（SQLite/PostgreSQL/Redis）
│   ├── models.py            # ORM模型（4表）
│   ├── schemas.py           # Pydantic Schema
│   ├── requirements.txt     # Python依赖
│   ├── routers/             # API路由层
│   │   ├── risk.py         #   探雷器SSE流式
│   │   ├── risk_agent.py   #   Agent推理SSE流式
│   │   ├── leakage.py      #   捡漏雷达
│   │   ├── payment.py      #   支付（模拟模式）
│   │   ├── profile.py      #   用户档案CRUD
│   │   └── admin.py        #   管理后台
│   ├── services/            # ★ 核心服务层
│   │   ├── risk_agent.py   #   Agent框架（944行）★★★
│   │   ├── risk_checker.py #   DeepSeek探雷引擎（367行）★★★
│   │   ├── enrollment_kb.py #  招生章程知识库（331行）★★★
│   │   ├── leakage_radar.py # 捡漏雷达算法（195行）
│   │   ├── audit_rules.py  #   规则配置
│   │   └── audit_prompts.py #  Prompt模板
│   ├── scripts/             # 数据工具
│   │   ├── seed_db.py      #   灌库脚本
│   │   ├── generate_expanded_data.py # 数据扩容
│   │   ├── clean_plans.py  #   数据清洗
│   │   └── audit_rules_gap.py # 规则缺口审计
│   └── data/                # ★ 数据层
│       ├── enrollment_rules.json # 60校结构化规则
│       ├── body_check_defaults.json # 体检兜底规则
│       ├── plans_2026.csv   # 招生计划（5261条）
│       └── guangdong_pdfs/  # 原始PDF数据
│
├── frontend/                 # Vue 3 前端
│   ├── index.html           # Vite入口
│   ├── package.json         # 依赖配置
│   ├── vite.config.ts      # Vite配置
│   ├── main.ts              # Vue入口
│   ├── App.vue              # 根组件（含router-view）
│   ├── router.ts            # Vue Router配置
│   ├── api/index.ts         # API封装 + SSE消费
│   ├── stores/              # Pinia状态管理
│   │   ├── profile.ts       #   用户档案
│   │   ├── risk.ts          #   探雷器
│   │   ├── leakage.ts       #   捡漏雷达
│   │   └── advisor.ts       #   AI顾问
│   ├── components/          # 组件
│   │   ├── RiskScanner.vue  #   探雷器主界面
│   │   ├── RadarBoard.vue   #   捡漏雷达网格
│   │   ├── AdvisorChat.vue  #   AI顾问对话
│   │   └── PaymentModal.vue #   支付弹窗
│   ├── pages/               # 页面
│   │   ├── index/index.vue  #   探雷器页面
│   │   ├── radar/radar.vue #   捡漏雷达页面
│   │   └── profile/profile.vue # 我的档案页面
│   └── static/index.css     # 全局样式（Glassmorphism）
│
└── docker-compose.yml        # Docker编排（4服务，未验证）
```

---

## 🔌 API接口清单

| 方法 | 路径 | 功能 | 状态 |
|------|------|------|------|
| GET | `/health` | 健康检查 | ✅ |
| POST | `/api/profile` | 创建/覆盖用户档案 | ✅ |
| GET | `/api/profile/{user_id}` | 查询用户档案 | ✅ |
| DELETE | `/api/profile/{user_id}` | 删除用户档案 | ✅ |
| POST | `/api/check-risk` | 探雷器JSON模式 | ✅ |
| GET | `/api/check-risk/stream` | 探雷器SSE流式 | ✅ |
| POST | `/api/check-risk/agent` | Agent同步审核 | ✅ |
| GET | `/api/check-risk/agent/stream` | Agent SSE流式 | ✅ |
| POST | `/api/leakage-radar` | 捡漏雷达 | ✅ |
| POST | `/api/pay/qrcode` | 生成支付二维码 | ⚠️ 模拟模式 |
| GET | `/api/pay/status/{order_id}` | 查询支付状态 | ⚠️ 模拟模式 |

**详细API文档**: 启动后端后访问 http://localhost:8000/docs

---

## 🧠 核心架构说明

### 探雷器三级调用链
```
check_admission_risk()
  ├─ DeepSeek API (DEEPSEEK_API_KEY已配置时) ← 当前实际使用
  │   └─ 注入真实章程条款到prompt
  ├─ Dify API (DIFY_API_TOKEN已配置时) ← 当前不可用（Token为空）
  └─ 智能Mock (基于enrollment_kb + audit_rules) ← API Key为空时自动回退
```

### 知识库双层检索
```
EnrollmentKnowledgeBase.query(university, major)
  ├─ 方案A: enrollment_rules.json (60校, O(1)正则匹配)
  │   └─ 命中 → 返回body_check/single_subject/language_restriction
  └─ 方案B: zszc/*.txt (235个章程原文，未上传GitHub)
      └─ 拼接全文 → 注入LLM prompt
```

### V4 Agent推理框架
```
RiskAuditAgent.run()
  ├─ 默认使用真实LLM (deepseek-v4-flash)
  ├─ 支持多轮工具调用 (max_tool_rounds=5)
  └─ 工具注册系统:
      ├─ search_enrollment_rules — 检索招生章程规则
      ├─ check_vision_risk — 专项体检检查
      ├─ check_subject_score — 单科成绩检查
      ├─ lookup_historical_data — 历年录取数据（Mock）
      └─ check_subject_election — 选科匹配检查
```

---

## ⚙️ 环境变量配置

### backend/.env
```env
# 必需配置
DEEPSEEK_API_KEY=sk-xxx    # V3探雷 (deepseek-chat)
LLM_API_KEY=sk-xxx          # V4 Agent (deepseek-v4-flash)

# 可选配置（当前未使用）
# DIFY_API_TOKEN=
# DATABASE_URL=              # 留空走SQLite fallback
# REDIS_URL=                # 留空禁用缓存
# WECHAT_MCH_ID=            # 微信支付商户号（预留）
# WECHAT_API_V3_KEY=        # 微信支付API V3 Key（预留）
```

**注意**: `.env` 文件已加入 `.gitignore`，不会上传到GitHub。

---

## 📊 当前运行状态（诚实声明）

| 组件 | 状态 | 说明 |
|------|------|------|
| 后端API | ✅ 可运行 | 11个接口全部有实际处理逻辑 |
| 前端Vue 3 | ✅ 可运行 | 三页面路由正常 |
| V3规则引擎 | ✅ 真实DeepSeek | `deepseek-chat`，注入真实章程条款 |
| V4 Agent推理 | ✅ 默认真实LLM | `deepseek-v4-flash` |
| 招生计划数据 | ✅ 30校5261条 | 5省×2科类×30校 |
| 章程规则覆盖 | ✅ 60所大学 | 约40%有专业级精细化规则 |
| 数据库 | ⚠️ SQLite单机 | PostgreSQL代码已就绪但未启用 |
| Redis缓存 | ❌ 本地不可用 | 代码已就绪，缓存未命中时优雅降级 |
| 支付 | ⚠️ 模拟模式 | 第3次轮询自动SUCCESS |
| Docker部署 | ⚠️ 配置就绪未验证 | `docker-compose.yml`已编写 |

---

## ⚠️ 已知局限与改进路线

| 问题 | 严重程度 | 说明 | 改进方向 |
|------|----------|------|----------|
| 招生计划数据仍需扩充 | 🔴 重要 | 仅5省30校，需扩充至全国 | 接入各省教育考试院API |
| 章程规则深度不均 | 🔴 重要 | 60%大学仅通配规则 | 补足目标高校的专业级规则 |
| 支付为模拟 | 🟡 中等 | 无法上线收费 | 接入微信支付Native API V3 |
| PostgreSQL未使用 | 🟡 中等 | 代码支持但运行在SQLite | 生产环境切换 |
| Redis未运行 | 🟡 中等 | 本地不可用，优雅降级 | 生产环境启用 |
| Docker未验证 | 🟢 低 | 配置已编写但未实际部署 | 跑通一次docker-compose up |

---

## 🎯 下一步优先级

### P0（立即处理）
1. **扩充招生计划数据**：接入更多省份和高校
2. **完善章程规则**：为60%仅通配规则的大学补充专业级精细化规则
3. **前端优化**：确保移动端H5体验流畅

### P1（近期处理）
4. **接入真实支付**：替换模拟模式，接入微信支付API
5. **Docker部署验证**：完成一次完整的Docker Compose部署测试
6. **PostgreSQL迁移**：从SQLite迁移到PostgreSQL

### P2（长期规划）
7. **Redis缓存启用**：提升API响应速度
8. **用户系统**：添加注册/登录功能
9. **数据分析面板**：为运营提供数据洞察

---

## 🔍 快速验证命令

```bash
# 健康检查
curl http://localhost:8000/health

# 测试SSE流式探雷（色盲+临床医学）
curl -N "http://localhost:8000/api/check-risk/stream?profile_json=%7B%22province%22%3A%22%E5%B9%BF%E4%B8%9C%22%2C%22score%22%3A565%2C%22vision_status%22%3A%22%E8%89%B2%E7%9B%B2%22%7D&targets_json=%5B%7B%22university%22%3A%22%E5%8D%97%E6%96%B9%E5%8C%BB%E7%A7%91%E5%A4%A7%E5%AD%A6%22%2C%22major%22%3A%22%E4%B8%B4%E5%BA%8A%E5%8C%BB%E5%AD%A6%22%7D%5D"

# 测试捡漏雷达
curl -X POST http://localhost:8000/api/leakage-radar \
  -H "Content-Type: application/json" \
  -d '{"province":"广东","subject_group":"物理类"}'

# 查看后端日志
tail -f /Users/sanzhaibanniang/Claude/Projects/gaokao/backend.log

# 查看前端日志
tail -f /Users/sanzhaibanniang/Claude/Projects/gaokao/frontend.log
```

---

## 📚 关键文件速查（按重要度排序）

| 优先级 | 文件 | 行数 | 说明 |
|--------|------|------|------|
| ★★★ | `backend/services/risk_agent.py` | 944 | Agent框架 + Mock/LLM客户端 |
| ★★★ | `backend/services/risk_checker.py` | 367 | DeepSeek探雷引擎 |
| ★★★ | `backend/services/enrollment_kb.py` | 331 | 知识库双层检索 |
| ★★☆ | `backend/services/leakage_radar.py` | 195 | 捡漏雷达Pandas向量化 |
| ★★☆ | `backend/routers/risk.py` | 180 | V3 SSE流式路由 |
| ★★☆ | `backend/routers/risk_agent.py` | 270 | V4 Agent SSE路由 |
| ★★☆ | `backend/main.py` | 125 | FastAPI入口 |
| ★★☆ | `frontend/api/index.ts` | 173 | 前端API + SSE |
| ★☆☆ | `backend/scripts/seed_db.py` | 220 | 灌库脚本 |
| ★☆☆ | `backend/data/enrollment_rules.json` | - | 60校结构化规则 |

---

## 📖 相关文档

| 文档 | 用途 |
|------|------|
| `CLAUDE.md` | 项目定位与开发原则（已加入.gitignore） |
| `PROJECT_LOG.md` | 完整项目状态日志 |
| `TECHNICAL_OVERVIEW.md` | 工程实现机制说明 |
| `INDUSTRY_BENCHMARK.md` | 行业竞品分析 |
| `frontend-upgrade-report.md` | 前端升级报告（UniApp→Vue3） |

---

## 🚨 重要提醒

###  GitHub仓库
- **仓库地址**: https://github.com/immaotianyi/gaokao-volunteer-v2
- **已排除文件**: `.env`, `.cursor/`, `CLAUDE.md`, `armor.glb`, 视频文件
- **如需克隆**: `git clone https://github.com/immaotianyi/gaokao-volunteer-v2.git`

### API Key安全
- **绝对不要**将包含真实API Key的 `.env` 文件上传到GitHub
- 使用 `backend/.env.example` 作为模板，让其他开发者自己填写

### 数据文件
- `backend/data/zszc/` (235个章程原文) 未上传GitHub（体积大）
- 如需完整数据，从教育部阳光高考平台重新下载

### 前端技术栈
- **已完成**: 从UniApp跨平台方案重构为纯Vue 3 + Vite方案
- **原因**: UniApp多端兼容性问题，纯Web H5方案更简单高效
- **关键变更**: `<view>`→`<div>`, `<text>`→`<span>`, `@tap`→`@click`, `rpx`→`px`

---

## 🤝 交接清单

- [x] 代码已上传GitHub
- [x] .gitignore已配置（排除敏感文件）
- [x] 环境变量模板(.env.example)已创建
- [x] 本交接文档(HANDOVER.md)已创建
- [ ] README.md待创建（项目说明、功能介绍、截图）
- [ ] Docker部署验证
- [ ] 微信支付接入

---

## 📞 联系方式

- **项目所有者**: immaotianyi
- **GitHub**: https://github.com/immaotianyi
- **项目Issues**: https://github.com/immaotianyi/gaokao-volunteer-v2/issues

---

**祝下一任开发者工作顺利！🎉**

---

*本文档生成于2026年6月25日，反映项目当前状态。如有更新，请直接修改本文档。*
