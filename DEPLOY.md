# 高考志愿狙击手 — 部署执行手册

> 生成时间: 2026-06-20
> 适用场景: 从零部署到云服务器（Cloud Studio / Lighthouse / 任意有 Docker 的 Linux 主机）

---

## 一、部署架构

```
用户浏览器
    ↓ HTTP/HTTPS
┌─────────────────────────────────────────┐
│  frontend 容器 (Nginx :80)              │
│  - 静态文件 (Vue3 dist)                 │
│  - /api/* 反代到 backend:8000           │
│  - SSE 长连接优化                       │
└─────────────────────────────────────────┘
    ↓ 内部网络
┌─────────────────────────────────────────┐
│  backend 容器 (gunicorn :8000)          │
│  - FastAPI 4 workers                    │
│  - PostgreSQL + Redis 连接              │
└─────────────────────────────────────────┘
    ↓                    ↓
┌──────────────┐   ┌──────────────┐
│ db (PG 15)   │   │ redis (7)    │
│ :5432        │   │ :6379        │
└──────────────┘   └──────────────┘

可选: cron 容器 (每日定时更新数据)
```

---

## 二、前置条件检查

部署目标机器必须满足：
- [x] Linux/macOS（Cloud Studio / Lighthouse 均可）
- [x] Docker 20.10+ 和 Docker Compose v2
- [x] 至少 2GB 内存 / 10GB 磁盘
- [x] 80 端口可访问（或通过反向代理映射）

**本机状态**：无 Docker，所以必须用云平台。

---

## 三、部署方式 A：Cloud Studio（推荐，最快）

Cloud Studio 是腾讯云的云端开发机，预装 Docker，无需本地装任何东西。

### 步骤

1. **在 CodeBuddy 集成面板连接 Cloud Studio**
   - 点击 IDE 右侧集成菜单 → Cloud Studio → 授权登录
   - 连接成功后我可以在云端机器执行命令

2. **上传项目到 Cloud Studio**
   ```bash
   # 在 Cloud Studio 终端
   git clone <你的仓库地址> gaokao
   # 或用 rsync/scp 从本地上传
   cd gaokao
   ```

3. **配置环境变量**
   ```bash
   # 编辑 .env，填入 DeepSeek API Key（必填）
   # 微信支付相关留空即可（自动模拟模式）
   nano .env
   ```

4. **一键启动**
   ```bash
   docker compose up -d --build
   ```
   首次构建约 5-10 分钟（装 Python/Node 依赖）。

5. **验证**
   ```bash
   docker compose ps          # 查看服务状态
   curl http://localhost/health  # 健康检查
   ```
   浏览器访问 Cloud Studio 分配的预览域名。

---

## 四、部署方式 B：腾讯云 Lighthouse（独立服务器）

适合需要独立 IP + 域名 + HTTPS 的正式上线。

### 步骤

1. **购买 Lighthouse 轻量服务器**
   - 配置：2核2G，Ubuntu 22.04，60元/月起
   - 在控制台开放 80、443 端口

2. **安装 Docker**
   ```bash
   ssh ubuntu@<服务器IP>
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER
   # 重新登录使 docker 组生效
   exit
   ssh ubuntu@<服务器IP>
   ```

3. **上传代码**
   ```bash
   # 本地执行，把项目传到服务器
   rsync -avz --exclude node_modules --exclude __pycache__ \
     /Users/sanzhaibanniang/Claude/Projects/gaokao/ \
     ubuntu@<服务器IP>:~/gaokao/
   ```

4. **启动**
   ```bash
   ssh ubuntu@<服务器IP>
   cd gaokao
   docker compose up -d --build
   ```

5. **配置域名 + HTTPS（可选）**
   ```bash
   # 安装 nginx 做 443 → 80 反代 + Let's Encrypt 证书
   sudo apt install nginx certbot python3-certbot-nginx
   sudo certbot --nginx -d your-domain.com
   ```

---

## 五、部署后验证清单

```bash
# 1. 所有容器运行中
docker compose ps
# 预期: db/redis/backend/frontend 都是 Up 状态

# 2. 健康检查
curl http://localhost/health
# 预期: {"status":"ok","redis":"connected",...}

# 3. 支付模式（应返回 mock）
curl http://localhost/api/pay/mode
# 预期: {"mode":"mock"}

# 4. 支付链路
ORDER=$(curl -s -X POST http://localhost/api/pay/qrcode \
  -H "Content-Type: application/json" -d '{"user_id":"test"}')
echo $ORDER
# 预期: {"order_id":"ORDER_...","mode":"mock",...}

# 5. 前端可访问
curl -s http://localhost/ | head -5
# 预期: <!DOCTYPE html>... Vue 前端
```

---

## 六、微信支付上线（以后申请到商户号后）

**无需改任何代码**，只需编辑 `.env`：

```env
WECHAT_APPID=wx你的appid
WECHAT_MCH_ID=你的商户号
WECHAT_API_V3_KEY=你设置的32位APIv3密钥
WECHAT_CERT_SERIAL_NO=证书序列号
WECHAT_PRIVATE_KEY_PATH=cert/apiclient_key.pem
WECHAT_NOTIFY_URL=https://你的域名/api/pay/notify
```

然后把 `apiclient_key.pem` 放到 `backend/cert/` 目录，重启后端：

```bash
docker compose restart backend
curl http://localhost/api/pay/mode
# 预期: {"mode":"real"}  ← 自动切真实模式
```

---

## 七、常见问题

| 问题 | 解决 |
|------|------|
| `docker compose` 命令不存在 | 用 `docker-compose`（v1）或安装 compose v2 插件 |
| 前端构建失败 `npm install` 卡住 | Dockerfile 已加 `--legacy-peer-deps`，若仍失败检查网络 |
| backend 连不上 db | `docker compose logs backend` 看报错，确认 db 容器 healthy |
| 前端 API 404 | 确认 nginx.conf 的 `/api/` 反代配置正确，`docker compose logs frontend` |
| SSE 连接断开 | nginx 已配 `proxy_buffering off`，确认 cloud 平台没额外超时限制 |
| 支付一直 PENDING | 模拟模式第3次轮询才 SUCCESS，等 6 秒；真实模式检查微信回调是否可达 |

---

## 八、服务管理命令

```bash
docker compose up -d --build    # 构建并启动
docker compose down             # 停止并删除容器
docker compose restart backend  # 重启单个服务
docker compose logs -f backend  # 实时查看日志
docker compose ps               # 查看状态
docker compose pull             # 更新镜像
```
