# 部署 AI Agent 上线方案

> **下达时间**: 2026-06-27
> **下达方**: 审核员（用户授权）
> **部署目标**: Trae AI 创意大赛演示评委可访问
> **决策**: 阿里云/腾讯云 ECS 或轻量服务器 + Docker Compose 一键部署 + IP 直连演示（无域名无备案）

---

## 一、部署架构

```
┌─────────────────────────────────────────────────────────────┐
│  评委浏览器  ──►  http://<VPS-IP>:80  (无域名，IP 直连演示)   │
└─────────────────────────────────────────────────────────────┘
                            │
            ┌───────────────▼───────────────┐
            │   阿里云/腾讯云 ECS/轻量服务器   │
            │   Ubuntu 22.04 LTS  · 2C4G 50G │
            │   已安装 Docker + docker compose│
            └───────────────┬───────────────┘
                            │ docker compose up -d
        ┌───────────┬───────┴───────┬─────────────┐
        ▼           ▼               ▼             ▼
   ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌──────────┐
   │frontend │  │ backend │  │   db     │  │  redis   │
   │ nginx:80│  │  :8000  │  │ postgres │  │  :6379   │
   │ 静态H5  │  │FastAPI  │  │  :5432   │  │  热度追踪 │
   └─────────┘  └─────────┘  └──────────┘  └──────────┘
        │           │
        └─nginx 反代 /api → backend:8000
```

**关键设计**:
- `docker-compose.yml` 已就绪（PG + Redis + Backend + Cron + Frontend 五服务）
- nginx 已配 `/api/*` 反代到 backend，前端走相对路径
- CSV 数据通过 volume 挂载 `./backend/data:/app/data`，容器重启不丢数据
- PostgreSQL 数据通过 named volume `pgdata` 持久化
- 防火墙仅开放 80 端口（演示用，无 HTTPS 无域名）

---

## 二、分工（用户唯一手动事项）

| 角色 | 事项 | 是否需要用户动手 |
|---|---|---|
| **用户** | 在阿里云/腾讯云控制台买 1 台轻量服务器（推荐 Ubuntu 22.04 LTS，2C4G 50G，按量计费 ¥0.3/小时可随时释放） | ✅ 必须（AI agent 无法代付钱） |
| **用户** | 把服务器公网 IP + root 密码粘贴给部署 AI agent | ✅ 必须（一次性粘贴） |
| **部署 AI agent** | 验证 SSH 连通性 + 远程安装 Docker | ❌ 全自动 |
| **部署 AI agent** | 把当前所有未提交改动 commit + push 到 GitHub | ❌ 全自动 |
| **部署 AI agent** | 远程 git clone + 配 `.env.prod` + docker compose up -d | ❌ 全自动 |
| **部署 AI agent** | 健康检查 + 公网可访问性验证 + 输出访问链接 | ❌ 全自动 |
| **部署 AI agent** | 写完成说明归档 + 更新时间线 | ❌ 全自动 |

**用户全程只需做两件事**：买服务器 + 粘贴 IP/密码。其余全部由部署 AI agent 自动完成。

---

## 三、任务清单（部署 AI agent 执行顺序）

### Phase 0 · 前置校验（用户粘贴凭据后立即执行）

- [ ] 用 RunCommand 测试 `ssh root@<IP>` 是否能连通
- [ ] 校验服务器规格：`uname -a && free -h && df -h`，确认 Ubuntu 22.04 + ≥4G 内存 + ≥40G 磁盘
- [ ] 若不满足规格，立即停下报错，让用户换服务器

### Phase 1 · 本地代码提交并推送

- [ ] 进入项目根目录 `/Users/sanzhaibanniang/Claude/Projects/gaokao`
- [ ] `git status` 审查改动，确认无敏感文件被提交（**重点检查 .env / .env.prod / 任何含密钥的文件**）
- [ ] 检查 `.gitignore` 是否已正确排除：`backend/.env`、`backend/data/raw/`、`backend/data/_snapshot_*`、`logs/`、`node_modules/`、`dist/`
- [ ] 检查 `backend/data/*.csv` 是否纳入版本控制（项目数据需随仓库走，否则 VPS 拉不到数据）
  - **当前 git status 显示 CSV 是 modified 状态 → 说明 CSV 已被跟踪**，确认提交
  - 估算提交后仓库大小，若超过 100MB 警告用户（GitHub 单文件 100MB 限制）
- [ ] `git add -A` 暂存所有改动
- [ ] `git commit -m "<type>: <subject>"` 按规范化提交（type: feat/fix/chore/docs/refactor）
  - 建议拆 3 个 commit：
    1. `feat: 完成 11 项后端 AI 修复（#1-#12）+ 12 省数据完整化（甘肃起顺序爬取）`
    2. `feat: 数据修复 #13-#20（竞态根治 + raw 隔离 + merge_all.py 原子写 + plans 恢复）`
    3. `chore: 部署就绪校验（Docker Compose 五服务 + nginx 反代 + gunicorn 生产启动）`
- [ ] `git push origin main` 推送，验证推送成功

### Phase 2 · 远程服务器初始化

- [ ] SSH 登录：`ssh root@<VPS-IP>`
- [ ] 系统更新：`apt update && apt upgrade -y`
- [ ] 安装 Docker：`curl -fsSL https://get.docker.com | sh`（中国大陆服务器若慢，改用阿里云镜像 `curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun`）
- [ ] 安装 docker compose plugin：`apt install -y docker-compose-plugin`（验证 `docker compose version`）
- [ ] 安装 git：`apt install -y git`
- [ ] 创建项目目录：`mkdir -p /opt/gaokao && cd /opt/gaokao`

### Phase 3 · 远程拉代码 + 配置环境

- [ ] `git clone https://github.com/immaotianyi/gaokao-volunteer-v2.git .`（若仓库私有需配 token）
- [ ] 创建 `.env.prod` 文件，填入生产密钥：
  ```
  DEEPSEEK_API_KEY=<从用户 .env 复制>
  LLM_API_KEY=<同上>
  DIFY_API_TOKEN=<可选>
  DIFY_API_URL=https://api.dify.ai/v1/workflows/run
  ```
- [ ] 校验 `backend/data/*.csv` 已随仓库拉取（`ls -lh backend/data/*.csv` 应有 9 个文件）
- [ ] **不要执行任何 sync_*.py 或 merge_all.py**，仓库内的 CSV 即最终数据，远程不再爬数据

### Phase 4 · 一键部署 + 健康检查

- [ ] `cd /opt/gaokao && docker compose pull`（拉镜像，验证 Dockerfile）
- [ ] `docker compose up -d --build`（构建 5 个服务，预计 3-5 分钟）
- [ ] `docker compose ps` 确认 5 个容器全部 `Up (healthy)`
- [ ] `docker compose logs --tail=50 backend` 检查后端启动日志：
  - 应看到「135 招生章程 + 271768 录取数据 + 12 省一分一段表」加载完成
  - 不应看到错误堆栈
- [ ] 本机健康检查：`curl http://localhost:8000/health` 应返回 `{"status":"ok"}`
- [ ] 本机前端访问：`curl -I http://localhost/` 应返回 200 + Content-Type: text/html
- [ ] **公网可访问性验证**：从本地 Mac `curl http://<VPS-IP>/health` 应返回 ok
  - 若失败，检查阿里云安全组：开放 80 端口入方向（22 端口已默认开放）
  - 检查 ufw：`ufw status`，若启用需 `ufw allow 80`

### Phase 5 · 验收 + 文档归档

- [ ] 在浏览器打开 `http://<VPS-IP>/`，截图：
  - 首页加载正常（秉烛研卷主题）
  - 志愿探雷器功能可用
  - 捡漏雷达返回 60+ 条数据
  - 12 省 score_rank 多省隔离正常
- [ ] 写完成说明归档到 `协作中心/反馈/20260627_部署AI_完成说明.md`，含：
  - 公网访问地址（http://<VPS-IP>/）
  - 健康检查截图
  - 各容器状态
  - 已知遗留问题（如非广东 yifenyiduan 数据残缺，已在后端任务清单标 TODO）
  - 停服指南（如何 docker compose down / 释放按量计费服务器）
- [ ] 在 `协作中心/时间线.md` 追加：
  ```
  [YYYY-MM-DD HH:MM:SS][部署AI] ✅ 完成上线部署。公网访问：http://<VPS-IP>/。
  - 5 容器全部 Up healthy（frontend:80, backend:8000, db:5432, redis:6379, cron）
  - 后端加载 135 章程 + 271768 录取数据 + 12 省一分一段表
  - /health ok ✅ / 前端首页 200 ✅ / 公网 curl ok ✅
  - 完成说明：[反馈/20260627_部署AI_完成说明.md](反馈/20260627_部署AI_完成说明.md)
  ```

---

## 四、用户给部署 AI agent 的入职提示词（直接复制粘贴）

> 复制以下内容到新的 Trae AI agent 会话即可启动部署流程。
> 用户在收到部署 AI agent 提示「请提供 VPS IP 与 root 密码」时，把买好的服务器凭据粘贴给它。

```
你是「高考志愿狙击手」项目的部署 AI agent，角色定位：自动化运维工程师。
项目路径：/Users/sanzhaibanniang/Claude/Projects/gaokao
GitHub 仓库：https://github.com/immaotianyi/gaokao-volunteer-v2.git
协作中心：/Users/sanzhaibanniang/Claude/Projects/gaokao/协作中心/

## 你的角色与边界

- 你是部署专员，只负责把现有代码部署到阿里云/腾讯云 VPS 让评委可访问
- 你不写业务代码，不改业务逻辑，不爬数据，不修 bug
- 你严格遵守审核员下发的方案文档：协作中心/提示词/部署AI_上线方案.md
- 任何超出该方案文档的操作（如改业务代码、加监控、加域名），先停下问用户

## 立即执行

1. **读方案文档**：Read /Users/sanzhaibanniang/Claude/Projects/gaokao/协作中心/提示词/部署AI_上线方案.md
2. **读时间线**：Read /Users/sanzhaibanniang/Claude/Projects/gaokao/协作中心/时间线.md（了解项目当前状态）
3. **审查当前 git 状态**：执行 git status / git log，确认未提交改动范围
4. **向用户索取 VPS 凭据**：
   - 用 AskUserQuestion 工具问用户："请提供阿里云/腾讯云服务器的公网 IP 与 root 密码（或 SSH 私钥）。如尚未购买，建议阿里云轻量服务器 Ubuntu 22.04 LTS 2C4G 50G 按量计费。"
5. 收到凭据后按方案文档 Phase 1 → Phase 5 顺序执行

## 红线（违反即停下问用户）

- ❌ 禁止提交 .env / .env.prod / 任何含密钥的文件到 git
- ❌ 禁止在远程 VPS 上执行 sync_*.py / merge_all.py（数据已随仓库走，远程不爬数据）
- ❌ 禁止改 docker-compose.yml 业务配置（仅可改环境变量）
- ❌ 禁止把生产 .env.prod 留在仓库里（用 .gitignore 排除）
- ❌ 禁止在未确认 git push 成功前就 docker compose up
- ❌ 禁止使用 --force push
- ❌ 遇到任何不在方案文档内的需求（如「加监控」「加 HTTPS」「加域名」），先停下问用户

## 验收标准（完成时全部满足）

1. ✅ git push origin main 成功，远程仓库与本地一致
2. ✅ VPS 上 5 个容器全部 Up (healthy)：frontend / backend / db / redis / cron
3. ✅ 后端日志显示「135 章程 + 271768 录取数据 + 12 省一分一段表」加载完成
4. ✅ 本机 `curl http://localhost:8000/health` 返回 ok
5. ✅ 本机 `curl -I http://localhost/` 返回 200
6. ✅ 本地 Mac `curl http://<VPS-IP>/health` 公网可访问
7. ✅ 浏览器打开 http://<VPS-IP>/ 首页正常加载
8. ✅ 完成说明归档到 协作中心/反馈/20260627_部署AI_完成说明.md
9. ✅ 时间线追加 ✅ 记录

## 沟通规范

- 所有动作通过 RunCommand 执行，不要让用户手动跑命令
- 遇到非阻塞决策（如 commit message 怎么写），自主决策不问用户
- 遇到阻塞性决策（如服务器规格不达标、git push 失败重试 3 次、安全组未开放），停下问用户
- 完成每个 Phase 后简短汇报一次进度，不啰嗦

## 完成后

- 输出公网访问地址给用户
- 提示用户「演示完毕后，如需释放服务器省钱，执行 ssh root@<IP> "docker compose down && poweroff"，然后在阿里云控制台释放实例」
- 不要主动提议加监控/域名/HTTPS 等增强项，让用户先验收演示效果

立即开始：Read 方案文档 → 审查 git → 向用户索取 VPS 凭据。
```

---

## 五、风险与兜底

| 风险 | 兜底措施 |
|---|---|
| VPS 在中国大陆，docker 镜像拉取慢 | 用阿里云镜像加速器 `--mirror Aliyun` |
| git push 因大文件失败（CSV 271768 行） | 提前 `du -sh backend/data/*.csv` 评估，必要时用 Git LFS 或单独打包传 VPS |
| 后端容器启动失败（如缺环境变量） | `docker compose logs backend` 看错误，缺啥补啥 |
| 阿里云安全组未开放 80 | 检查并提示用户去控制台开放 80 入方向 |
| 评委访问期间容器崩 | docker compose 已配 `restart: unless-stopped`，自动拉起 |
| 服务器被薅羊毛（公网暴露） | 演示完毕立即 `poweroff` 释放，不要长期开 |
| 后端启动慢（首次加载数据） | gunicorn timeout 已设 120s，应足够 |
| GitHub 私有仓库 clone 失败 | 让用户配 Personal Access Token，或临时改公开 |

---

## 六、给用户的购买指引（最低门槛）

**阿里云轻量服务器（推荐演示用）**：
- 控制台：https://swas.console.aliyun.com/
- 配置：2 核 4G 60G SSD  ·  3M 带宽  ·  Ubuntu 22.04 LTS
- 价格：按量计费约 ¥0.05/小时（演示 4 小时 ¥0.2）
- 区域：选「华北 2（北京）」或「华东 1（杭州）」延迟低
- 购买后在「防火墙」自动开放 22/80/443，无需额外配置

**腾讯云轻量服务器（备选）**：
- 控制台：https://console.cloud.tencent.com/lighthouse
- 同规格价格略低

买完后把以下信息粘贴给部署 AI agent：
```
公网 IP: <例如 47.xx.xx.xx>
root 密码: <例如 Abcd1234>
SSH 端口: 22（默认）
服务器区域: <例如 阿里云北京>
```

---

## 七、Trae 自动化能力评估备忘（供审核员留档）

| Trae 能力 | 适用本项目？ | 原因 |
|---|---|---|
| 内置 Vercel 一键部署 | ❌ | 仅适合纯前端/Serverless，本项目有 FastAPI 长驻+PG+Redis+CSV 持久化 |
| IGA Pages（火山引擎） | ❌ | 国产加速好，但偏静态/Serverless，跑不动长驻后端 |
| trae-gstack MCP 工具包 | ⚠️ | 21 命令含「部署项目/ship it」，但主要是 Vercel 体系，不适合本栈 |
| SOLO 模式 | ❌ | PRD→开发→Vercel 部署，同上限制 |
| RunCommand + SSH | ✅ | AI agent 可全程通过 RunCommand 执行 git/ssh/docker，是本项目唯一可行路径 |

**最终结论**：本项目无法用 Trae 内置 Vercel 集成一键部署。但通过「派部署 AI agent + RunCommand + SSH」的组合，用户全程不动手可行，且效果可保证。用户唯一手动事项：买 VPS + 粘贴凭据。
