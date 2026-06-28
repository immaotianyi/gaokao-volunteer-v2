# 部署 AI Agent 上线方案（双轨模式）

> **下达时间**: 2026-06-28
> **下达方**: 审核员（用户授权）
> **部署目标**: Trae AI 创意大赛演示评委可访问
> **决策**: 双轨模式 = 先 Cloudflare Tunnel 临时预览（验收演示效果）→ 验收满意后切阿里云 VPS 长期跑
> **用户决策依据**: 评委在自己电脑/手机点链接访问（不在现场）+ Mac 是笔记本会合盖移动 → Cloudflare Tunnel 不能长期跑 → 必须切 VPS

---

## 一、部署架构（双轨）

### 轨道 A：Cloudflare Tunnel 临时预览（5 秒出链接，0 成本 0 操作）

```
┌─────────────────────────────────────────────────────────────┐
│  评委浏览器  ──►  https://xxx.trycloudflare.com  (CF 全球节点) │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Cloudflare Tunnel
                            ▼
   ┌──────────────────────────────────────────────────┐
   │  用户 Mac（笔记本，演示期间需保持开机+连网）        │
   │  ┌─────────────────┐    ┌──────────────────┐    │
   │  │ Vite dev server │ ── │ cloudflared       │    │
   │  │ localhost:5173  │    │ → CF Tunnel       │    │
   │  └────────┬────────┘    └──────────────────┘    │
   │           │ vite proxy /api/*                   │
   │           ▼                                    │
   │  ┌─────────────────┐                            │
   │  │ uvicorn         │                            │
   │  │ localhost:8000  │                            │
   │  └─────────────────┘                            │
   └──────────────────────────────────────────────────┘
```

**关键点**：
- 复用 Mac 已跑的 vite dev server (5173) + uvicorn (8000)
- vite.config.ts 加 proxy 配置 `/api → http://localhost:8000`（仅 dev 模式生效，生产构建走相对路径 + nginx 不受影响）
- cloudflared 暴露 5173 单端口
- 评委访问 HTTPS 链接 → CF 转发到 Mac:5173 → vite dev server 响应 → fetch /api/* → vite proxy → localhost:8000 → uvicorn 响应

### 轨道 B：阿里云 VPS 长期部署（用户验收预览满意后切）

```
┌─────────────────────────────────────────────────────────────┐
│  评委浏览器  ──►  http://<VPS-IP>:80  (IP 直连，无域名无备案)  │
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
   └─────────┘  └─────────┘  └──────────┘  └──────────┘
```

---

## 二、分工（用户操作极限压缩）

| 阶段 | 角色 | 事项 | 用户动手？ |
|---|---|---|---|
| **轨道 A 预览** | 部署 AI | 装 cloudflared + 加 vite proxy + 启动 Tunnel + 输出链接 | ❌ 0 操作 |
| **轨道 A 验收** | 用户 | 在浏览器点开链接验收演示效果 | ✅ 1 分钟 |
| **轨道 B 购买** | 用户 | 阿里云控制台买轻量服务器（按量计费 ¥0.05/小时） | ✅ 5 分钟 |
| **轨道 B 授权** | 用户 | 把 `公网 IP + root 密码` 粘贴给部署 AI | ✅ 30 秒 |
| **轨道 B 部署** | 部署 AI | SSH 装机 + git clone + docker compose up + 健康检查 | ❌ 全自动 |
| **轨道 B 归档** | 部署 AI | 关闭 Mac 上 Tunnel + 写完成说明 + 更新时间线 | ❌ 全自动 |
| **演示完释放** | 用户 | 阿里云控制台「释放实例」（避免持续扣费） | ✅ 1 分钟 |

**用户全程只需 3 件事**：① 点链接验收 1 分钟 ② 买服务器 5 分钟 ③ 粘贴凭据 30 秒 ④ 演示完释放 1 分钟。其余全由部署 AI agent 自动完成。

---

## 三、任务清单（部署 AI 执行顺序）

### 🚂 轨道 A · Cloudflare Tunnel 预览

#### Phase A1 · 探测 Mac 当前运行状态

- [ ] 用 RunCommand 检查端口监听：
  ```bash
  lsof -iTCP -sTCP:LISTEN -P -n 2>/dev/null | grep -E ':(5173|8000) ' || echo "NO_SERVICE"
  ```
- [ ] **情况 1：5173 + 8000 都在跑**（推荐，当前已知状态）→ 跳到 Phase A3
- [ ] **情况 2：仅 8000 在跑**（后端 OK，前端没跑）→ Phase A2 启动前端
- [ ] **情况 3：仅 5173 在跑**（前端 OK，后端没跑）→ Phase A2 启动后端
- [ ] **情况 4：都没跑** → Phase A2 启动前后端

#### Phase A2 · 启动缺失服务（仅当 A1 探测到缺服务时）

- [ ] 启动后端（若 8000 未监听）：
  ```bash
  cd /Users/sanzhaibanniang/Claude/Projects/gaokao/backend
  nohup uvicorn main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
  sleep 5
  curl -s http://localhost:8000/health | head -1
  ```
  应返回 `{"status":"ok"}`
- [ ] 启动前端（若 5173 未监听）：
  ```bash
  cd /Users/sanzhaibanniang/Claude/Projects/gaokao/frontend
  nohup npm run dev > /tmp/vite.log 2>&1 &
  sleep 8
  curl -sI http://localhost:5173 | head -1
  ```
  应返回 `HTTP/1.1 200 OK`

#### Phase A3 · 加 vite proxy 配置（让前端 dev 模式 /api 反代到 8000）

- [ ] Read `frontend/vite.config.ts`，检查是否已配 `server.proxy`
- [ ] 若无 proxy，用 Edit 在 `server:` 块内追加：
  ```typescript
    server: {
      host: "0.0.0.0",
      port: 5173,
      proxy: {
        "/api": {
          target: "http://localhost:8000",
          changeOrigin: true,
        },
        "/sse": {
          target: "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
  ```
  **注意**：proxy 仅 dev 模式生效，生产构建走相对路径 + nginx 反代，**不影响 VPS 部署**
- [ ] 若 vite dev server 已在跑，需要重启让它加载新配置：
  ```bash
  # 找到 vite 进程并 kill
  pkill -f "vite" 2>/dev/null
  sleep 2
  cd /Users/sanzhaibanniang/Claude/Projects/gaokao/frontend
  nohup npm run dev > /tmp/vite.log 2>&1 &
  sleep 8
  curl -sI http://localhost:5173 | head -1
  ```
- [ ] 提交这个改动到 git（让 VPS 部署也能复用）：
  ```bash
  cd /Users/sanzhaibanniang/Claude/Projects/gaokao
  git add frontend/vite.config.ts
  git commit -m "chore(frontend): 加 vite proxy /api,/sse → :8000（dev 模式 Tunnel 预览用，生产 nginx 不受影响）"
  git push origin main
  ```

#### Phase A4 · 安装并启动 Cloudflare Tunnel

- [ ] 检查 cloudflared 是否已装：
  ```bash
  which cloudflared || echo "NOT_INSTALLED"
  ```
- [ ] 若未装，用 Homebrew 安装（约 30 秒）：
  ```bash
  brew install cloudflared
  ```
- [ ] 启动 Tunnel（前台运行，输出在 stdout）：
  ```bash
  cloudflared tunnel --url http://localhost:5173 > /tmp/cloudflared.log 2>&1 &
  sleep 8
  grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/cloudflared.log | head -1
  ```
- [ ] 从输出提取 `https://xxx.trycloudflare.com` 链接

#### Phase A5 · 自检 + 输出预览链接给用户

- [ ] 本机自检：
  ```bash
  curl -sI https://xxx.trycloudflare.com | head -1  # 应 200
  curl -s https://xxx.trycloudflare.com/api/health  # 应返回 ok
  ```
- [ ] 输出给用户：
  ```
  ✅ Tunnel 预览链接已生成：https://xxx.trycloudflare.com
  
  评委现在可以访问这个链接查看你的作品。
  Mac 合盖/断网链接即失效。
  
  请你点开链接验收演示效果：
  - 首页加载正常（秉烛研卷主题）
  - 志愿探雷器功能可用
  - 捡漏雷达返回 60+ 条数据
  - 12 省 score_rank 多省隔离正常
  
  验收满意后告诉我「切 VPS」，我引导你买阿里云服务器切到长期部署。
  验收不满意告诉我具体问题，我修。
  ```

#### Phase A6 · 等待用户验收反馈

- [ ] 暂停执行，等用户回复
- [ ] 用户回复「切 VPS」或「满意」→ 进入轨道 B
- [ ] 用户回复「有问题」或具体 bug → 修完重测 Tunnel

---

### 🚂 轨道 B · 阿里云 VPS 长期部署

#### Phase B0 · 用户购买服务器（用户操作 5 分钟）

部署 AI 用 AskUserQuestion 提示用户：
```
请买阿里云轻量服务器：
1. 打开 https://swas.console.aliyun.com/
2. 创建实例：
   - 地域：华北 2（北京）或华东 1（杭州）
   - 镜像：Ubuntu 22.04 LTS（系统镜像，不要应用镜像）
   - 套餐：2 核 4G 60G SSD 3M 带宽
   - 计费：按量计费 ¥0.05/小时
   - 密码：自定义（如 Trae2026Demo）
3. 等待实例「运行中」（约 30 秒）
4. 复制公网 IP（47.xx.xx.xx）

买完把以下信息粘贴给我：
公网 IP: <例如 47.xx.xx.xx>
root 密码: <例如 Trae2026Demo>
```

#### Phase B1 · SSH 连通性 + 系统校验

- [ ] 用 RunCommand 测试 SSH（首次连接自动接受 host key）：
  ```bash
  ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 root@<IP> 'uname -a && free -h && df -h'
  ```
- [ ] 校验：Ubuntu 22.04 + ≥4G 内存 + ≥40G 磁盘
- [ ] 不达标立即停下问用户

#### Phase B2 · 远程安装 Docker

- [ ] 用阿里云镜像加速装 Docker：
  ```bash
  ssh root@<IP> 'curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun'
  ssh root@<IP> 'apt install -y docker-compose-plugin git && docker compose version'
  ```

#### Phase B3 · 拉代码 + 配环境

- [ ] 远程 git clone：
  ```bash
  ssh root@<IP> 'mkdir -p /opt/gaokao && cd /opt/gaokao && git clone https://github.com/immaotianyi/gaokao-volunteer-v2.git .'
  ```
- [ ] 用 AskUserQuestion 向用户索取 `.env.prod` 内容：
  ```
  请把本地 backend/.env 文件内容粘贴给我（含 DEEPSEEK_API_KEY 等），我配到 VPS 上。
  或者你授权我直接从本地读取 backend/.env 配置到 VPS。
  ```
- [ ] 推荐方案：部署 AI 直接读本地 `backend/.env`，SCP 到 VPS：
  ```bash
  scp /Users/sanzhaibanniang/Claude/Projects/gaokao/backend/.env root@<IP>:/opt/gaokao/backend/.env.prod
  ```
- [ ] 校验 CSV 已随仓库拉取：
  ```bash
  ssh root@<IP> 'ls -lh /opt/gaokao/backend/data/*.csv | head -10'
  ```

#### Phase B4 · 一键部署 + 健康检查

- [ ] 拉镜像 + 构建 + 启动：
  ```bash
  ssh root@<IP> 'cd /opt/gaokao && docker compose pull && docker compose up -d --build' 2>&1 | tail -20
  ```
- [ ] 等待 3-5 分钟，检查容器状态：
  ```bash
  ssh root@<IP> 'cd /opt/gaokao && docker compose ps'
  ```
  5 个容器全部 `Up (healthy)`
- [ ] 检查后端启动日志：
  ```bash
  ssh root@<IP> 'cd /opt/gaokao && docker compose logs --tail=30 backend'
  ```
  应看到「135 章程 + 270820 录取数据 + 12 省一分一段表」加载完成
- [ ] 本机健康检查：
  ```bash
  ssh root@<IP> 'curl -s http://localhost:8000/health'
  ssh root@<IP> 'curl -sI http://localhost/ | head -1'
  ```
  应返回 `{"status":"ok"}` 和 `HTTP/1.1 200 OK`
- [ ] **公网可访问性验证**（从 Mac 本地）：
  ```bash
  curl -s http://<IP>/health
  curl -sI http://<IP>/ | head -1
  ```
  若失败，提示用户去阿里云控制台防火墙开放 80 端口（轻量服务器默认已开 22/80/443）

#### Phase B5 · 关闭轨道 A Tunnel + 验收归档

- [ ] 关闭 Mac 上的 cloudflared（避免重复暴露）：
  ```bash
  pkill -f cloudflared
  ```
- [ ] 浏览器打开 `http://<IP>/`，截图：
  - 首页加载正常（秉烛研卷主题）
  - 志愿探雷器功能可用
  - 捡漏雷达返回 60+ 条数据
  - 12 省 score_rank 多省隔离正常
- [ ] 写完成说明归档到 `协作中心/反馈/20260628_部署AI_完成说明.md`，含：
  - 公网访问地址（http://<IP>/）
  - 健康检查结果
  - 各容器状态
  - 已知遗留问题（非广东部分 yfd 残缺，已在后端任务清单标 TODO）
  - 停服指南（`ssh root@<IP> "cd /opt/gaokao && docker compose down && poweroff"` + 阿里云控制台释放实例）
- [ ] 在 `协作中心/时间线.md` 追加：
  ```
  [YYYY-MM-DD HH:MM:SS][部署AI] ✅ 完成双轨部署。
  轨道 A Tunnel 预览已关闭。
  轨道 B VPS 长期部署：http://<IP>/
  - 5 容器 Up healthy
  - 后端加载 135 章程 + 270820 录取数据 + 12 省一分一段表
  - /health ok ✅
  - 完成说明：[反馈/20260628_部署AI_完成说明.md](反馈/20260628_部署AI_完成说明.md)
  ```

---

## 四、用户给部署 AI agent 的入职提示词（直接复制粘贴）

> 复制以下内容到新的 Trae AI agent 会话即可启动双轨部署流程。

```
你是「高考志愿狙击手」项目的部署 AI agent，角色定位：自动化运维工程师。
项目路径：/Users/sanzhaibanniang/Claude/Projects/gaokao
GitHub 仓库：https://github.com/immaotianyi/gaokao-volunteer-v2.git
协作中心：/Users/sanzhaibanniang/Claude/Projects/gaokao/协作中心/

## 你的角色与边界

- 你是部署专员，只负责把现有代码部署上线让评委可访问
- 你不写业务代码，不改业务逻辑，不爬数据，不修 bug
- 你严格遵守审核员下发的方案文档：协作中心/提示词/部署AI_上线方案.md
- 任何超出该方案文档的操作（如改业务代码、加监控、加域名），先停下问用户

## 双轨模式

用户已选择「先 Tunnel 预览 → 验收后切 VPS」双轨部署：

### 轨道 A：Cloudflare Tunnel 临时预览（立即执行）
- 在 Mac 上加 vite proxy + 启 cloudflared + 输出 https://xxx.trycloudflare.com 链接
- Mac 合盖/断网链接即失效，仅用于预览验收
- 用户点开链接验收满意后告诉「切 VPS」才进入轨道 B

### 轨道 B：阿里云 VPS 长期部署（用户验收满意后执行）
- 用户买阿里云轻量服务器 + 粘贴凭据
- 你 SSH 装机 + git clone + docker compose up + 健康检查 + 输出 http://<IP>/ 链接
- 关闭轨道 A 的 Tunnel 避免重复暴露

## 立即执行

1. Read 方案文档：/Users/sanzhaibanniang/Claude/Projects/gaokao/协作中心/提示词/部署AI_上线方案.md
2. Read 时间线：/Users/sanzhaibanniang/Claude/Projects/gaokao/协作中心/时间线.md
3. 直接进入轨道 A：
   - Phase A1：探测 Mac 当前 5173/8000 端口状态
   - Phase A2：若缺服务则启动（已知 Mac 当前 5173+8000 都在跑，大概率跳过）
   - Phase A3：Read frontend/vite.config.ts → 加 server.proxy /api,/sse → localhost:8000（dev 模式生效，生产构建不受影响）→ commit + push
   - Phase A4：brew install cloudflared → 启动 cloudflared tunnel --url http://localhost:5173 → 提取 https://xxx.trycloudflare.com
   - Phase A5：自检后输出链接给用户，暂停等用户验收
4. 用户回复「切 VPS」后进入轨道 B：
   - Phase B0：用 AskUserQuestion 引导用户买阿里云轻量服务器 + 索取公网 IP 与密码
   - Phase B1-B5：SSH 装机 → git clone → docker compose up → 健康检查 → 关 Tunnel → 归档

## 红线（违反即停下问用户）

- ❌ 禁止提交 .env / .env.prod / 任何含密钥的文件到 git
- ❌ 禁止在远程 VPS 上执行 sync_*.py / merge_all.py（数据已随仓库走，远程不爬数据）
- ❌ 禁止改 docker-compose.yml 业务配置（仅可改环境变量）
- ❌ 禁止改业务代码（leakage_radar.py / score_rank.py / main.py 等）
- ❌ 禁止在未确认 git push 成功前就 docker compose up
- ❌ 禁止使用 --force push
- ❌ vite.config.ts 只准加 server.proxy 配置，不准动其他配置
- ❌ 遇到任何不在方案文档内的需求（如「加监控」「加 HTTPS」「加域名」），先停下问用户

## 验收标准（双轨全部完成时满足）

轨道 A 验收：
1. ✅ cloudflared 已启动，输出 https://xxx.trycloudflare.com
2. ✅ curl https://xxx.trycloudflare.com 返回 200
3. ✅ curl https://xxx.trycloudflare.com/api/health 返回 ok
4. ✅ 用户点开链接验收满意，回复「切 VPS」

轨道 B 验收：
5. ✅ git push origin main 成功（含 vite proxy 改动）
6. ✅ VPS 上 5 个容器全部 Up (healthy)
7. ✅ 后端日志显示「135 章程 + 270820 录取数据 + 12 省一分一段表」加载完成
8. ✅ 本机 + 公网 curl http://<IP>/health 都返回 ok
9. ✅ Mac 上 cloudflared 已关闭
10. ✅ 完成说明归档到 协作中心/反馈/20260628_部署AI_完成说明.md
11. ✅ 时间线追加 ✅ 记录

## 沟通规范

- 所有动作通过 RunCommand 执行，不要让用户手动跑命令
- 轨道 A 完成后必须暂停，等用户验收反馈再进入轨道 B
- 遇到非阻塞决策（如 commit message 怎么写），自主决策不问用户
- 遇到阻塞性决策（如服务器规格不达标、git push 失败重试 3 次、安全组未开放、用户 .env 文件不存在），停下问用户
- 完成每个 Phase 后简短汇报一次进度，不啰嗦

## 完成后

- 输出 VPS 公网访问地址给用户
- 提示用户「演示完毕后，如需释放服务器省钱：ssh root@<IP> "cd /opt/gaokao && docker compose down && poweroff"，然后在阿里云控制台释放实例」
- 不要主动提议加监控/域名/HTTPS 等增强项，让用户先验收演示效果

立即开始：Read 方案文档 → 进入轨道 A Phase A1。
```

---

## 五、风险与兜底

| 风险 | 兜底措施 |
|---|---|
| Mac 合盖/睡眠导致 Tunnel 断 | 轨道 A 仅用于预览验收，验收完立即切轨道 B |
| cloudflared 首次启动慢 | 等待 8 秒读 /tmp/cloudflared.log 提取链接，重试 3 次 |
| vite proxy 配置错误 | 改完立即 curl 自检，失败回滚 |
| VPS 在中国大陆，docker 镜像拉取慢 | 用阿里云镜像加速器 `--mirror Aliyun` |
| git push 因大文件失败 | 已验证 CSV 总大小 ~52M 未超 GitHub 100MB 限制 |
| 后端容器启动失败 | `docker compose logs backend` 看错误，缺啥补啥 |
| 阿里云安全组未开放 80 | 轻量服务器默认开放 22/80/443；若未开提示用户去控制台 |
| 评委访问期间容器崩 | docker compose 已配 `restart: unless-stopped`，自动拉起 |
| 服务器被薅羊毛（公网暴露） | 演示完毕立即 `poweroff` 释放，不要长期开 |
| 用户 .env 文件不存在 | AskUserQuestion 索取 DEEPSEEK_API_KEY 等环境变量手动配 |
| GitHub 私有仓库 clone 失败 | 让用户配 Personal Access Token，或临时改公开 |

---

## 六、给用户的购买指引（轨道 B 用）

**阿里云轻量服务器（推荐演示用）**：
- 控制台：https://swas.console.aliyun.com/
- 配置：2 核 4G 60G SSD  ·  3M 带宽  ·  Ubuntu 22.04 LTS
- 价格：按量计费约 ¥0.05/小时（演示 4 小时 ¥0.2）
- 区域：选「华北 2（北京）」或「华东 1（杭州）」延迟低
- 镜像：**系统镜像 Ubuntu 22.04 LTS**（不要选应用镜像，部署 AI 会自己装 Docker）
- 购买后在「防火墙」自动开放 22/80/443，无需额外配置

买完后把以下信息粘贴给部署 AI agent：
```
公网 IP: <例如 47.xx.xx.xx>
root 密码: <例如 Trae2026Demo>
SSH 端口: 22（默认）
服务器区域: <例如 阿里云北京>
```

**演示完毕释放**：
1. 部署 AI 执行 `ssh root@<IP> "cd /opt/gaokao && docker compose down && poweroff"`
2. 阿里云控制台「实例列表」→「释放实例」→ 0 后续扣费

---

## 七、Trae 自动化能力评估备忘（供审核员留档）

| Trae 能力 | 适用本项目？ | 原因 |
|---|---|---|
| 内置 Vercel 一键部署 | ❌ | 仅适合纯前端/Serverless，本项目有 FastAPI 长驻+PG+Redis+CSV 持久化 |
| IGA Pages（火山引擎） | ❌ | 国产加速好，但偏静态/Serverless，跑不动长驻后端 |
| trae-gstack MCP 工具包 | ⚠️ | 21 命令含「部署项目/ship it」，但主要是 Vercel 体系，不适合本栈 |
| SOLO 模式 | ❌ | PRD→开发→Vercel 部署，同上限制 |
| RunCommand + SSH | ✅ | AI agent 可全程通过 RunCommand 执行 git/ssh/docker，是本项目唯一可行路径 |
| Cloudflare Tunnel | ✅ | 0 成本 5 秒出公网 HTTPS 链接，AI 全自动，适合预览验收 |
| 双轨模式（Tunnel+VPS） | ✅ | 最终采纳方案：先 Tunnel 预览 0 操作 → 验收后切 VPS 长期跑 |

**最终结论**：用户「0 操作」诉求在物理上无法实现（买服务器+粘贴凭据必须用户做），但通过双轨模式把用户操作推迟到验收满意后，心理门槛最低。Cloudflare Tunnel 让用户先看到效果再付钱。
