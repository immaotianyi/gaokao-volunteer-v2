# 高考志愿狙击手

> 十二年寒窗，值得一份安心的志愿表。

在点提交之前，把需要留意的地方告诉你。

---

## 这是什么

一个独立第三方志愿表审查工具。不替你填志愿，只帮你看清楚志愿表里那些**容易忽略、但可能致命**的细节。

AI 志愿工具能帮你生成方案，但它们不检查招生章程里的色盲限制、单科分数要求、语种限制、选科匹配——这些恰恰是退档的高发区。**本工具就是那道桥上的安检员。**

### 三大核心功能

| 功能 | 做什么 | 怎么做 |
|---|---|---|
| **志愿探雷器** | 逐所核对招生章程，体检/单科/语种/选科四维风险扫描 | 基于真实招生章程知识库（135 所高校）+ DeepSeek 推理 |
| **捡漏雷达** | 六维评分发现分数匹配、扩招、新校区、断档等机会 | 新增专业/扩招/新校区/实时热度捡漏评分 + Tavily 联网搜索 |
| **AI 顾问** | 多轮对话答疑，像和雪峰老师聊天 | DeepSeek V4 多轮记忆 + 秉烛研卷主题 UI |

---

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- DeepSeek API Key（[platform.deepseek.com](https://platform.deepseek.com) 获取）

### 1. 克隆仓库

```bash
git clone https://github.com/immaotianyi/gaokao-volunteer-v2.git
cd gaokao-volunteer-v2
```

### 2. 启动后端

```bash
cd backend
pip install -r requirements.txt

# 配置环境变量
cp .env.example ../.env
# 编辑 ../.env 填入你的 DeepSeek API Key

# 启动服务（默认 8000 端口，使用 SQLite，无需额外安装数据库）
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev          # 默认 http://127.0.0.1:5173
```

打开浏览器访问 http://127.0.0.1:5173 即可使用。

### 4. 环境变量说明

见 [backend/.env.example](backend/.env.example)：

| 变量 | 说明 | 必填 |
|---|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek V3 API Key（规则引擎推理用） | 是 |
| `LLM_API_KEY` | DeepSeek V4 API Key（Agent 多轮对话用） | 是 |
| `DATABASE_URL` | PostgreSQL 连接串（不填则自动降级为 SQLite） | 否 |
| `REDIS_URL` | Redis 连接串（不填则缓存禁用，不影响主流程） | 否 |

> 无 PostgreSQL / Redis 也能运行，自动降级为 SQLite + 无缓存模式。

---

## 数据覆盖

| 数据类型 | 范围 | 行数 |
|---|---|---|
| 历年录取数据 | 12 省 × 3 年 | 270,820 行 |
| 招生章程知识库 | 135 所高校 | 460 条规则 |
| 一分一段表 | 12 省 × 3 年 × 物理类/历史类 | 66 份 |
| 招生计划 | 广东/河南/山东/四川/江苏 | 2024-2026 |

**已覆盖省份**：广东、江西、甘肃、陕西、安徽、湖南、河南、重庆、辽宁、四川、河北、福建

---

## 技术栈

### 前端

- Vue 3 + TypeScript + Vite 5
- Pinia 状态管理
- Vue Router 4（history 模式）
- Three.js（粒子宇宙背景，秉烛研卷主题）
- ESLint + vue-tsc 类型检查

### 后端

- FastAPI + Uvicorn
- SQLAlchemy 2.0（async）
- Pandas（数据处理）
- SQLite（默认）/ PostgreSQL（生产）
- Redis（缓存/热度追踪，可选）
- DeepSeek V3/V4（推理引擎）
- Tavily API（联网章程搜索）

### 部署

- Docker Compose（前端 nginx + 后端 uvicorn + PostgreSQL + Redis + cron）
- 详见 [DEPLOY.md](DEPLOY.md)

---

## 项目结构

```
gaokao-volunteer-v2/
├── frontend/                  # Vue 3 前端
│   ├── components/             # 探雷器/捡漏雷达/AI顾问/支付弹窗等组件
│   ├── pages/                  # 落地页/工作台/档案页
│   ├── stores/                 # Pinia 状态管理
│   ├── api/                    # 统一 API 封装
│   └── router.ts               # 路由配置
├── backend/                    # FastAPI 后端
│   ├── routers/                # API 路由（profile/risk/leakage/advisor/payment）
│   ├── services/               # 业务逻辑（risk_checker/leakage_radar/score_rank 等）
│   ├── data/                   # 录取数据/章程知识库/一分一段表
│   ├── scripts/                # 数据同步脚本（sync_{省}_2026.py）
│   └── main.py                 # FastAPI 入口
├── 协作中心/                   # AI 协作文档（时间线/任务清单/提示词）
├── docker-compose.yml          # 生产部署编排
├── DEPLOY.md                   # 部署文档
└── start.sh                    # 一键启动脚本
```

---

## 免责声明

本工具基于 AI 理解招生章程条款，难免会有理解偏差。最终的志愿，请务必再对照一次官方的《填报指南》和学校官网的最新章程。

- 本工具**不构成填报建议**，不承诺录取
- 用户档案只存在浏览器本地，不会上传给第三方
- 因使用本工具产生的任何后果由使用者自行承担
- 所有退档案例均引用官方/媒体报道数据

---

## 许可证

本项目采用 [MIT License](LICENSE) 开源协议。

---

## 致谢

- 招生章程数据来源：各高校官方招生网
- 一分一段表/省控线数据来源：各省教育考试院
- AI 推理：[DeepSeek](https://www.deepseek.com)
- 联网搜索：[Tavily](https://tavily.com)

---

> 本项目为 Trae AI 创意大赛参赛作品。
