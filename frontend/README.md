# 高考志愿狙击手 - 前端 (Vue 3 正式版)

> **产品入口** — Vite + Vue 3 + Pinia + TypeScript

## 快速启动

```bash
cd frontend
npm install
npm run dev          # 开发模式 (默认 http://localhost:5173)
```

确保后端 `mock_server.py` 在项目根目录运行（端口 8000）。

## 技术栈
- Vue 3 + TypeScript
- Pinia (状态管理)
- Vite (构建)

## 项目结构

```
frontend/
├── pages/
│   ├── index/index.vue      # 志愿探雷器 (SSE 流式)
│   ├── radar/radar.vue      # 捡漏雷达
│   └── profile/profile.vue  # 用户档案
├── stores/
│   ├── profile.ts            # 用户档案 Store
│   ├── risk.ts               # 探雷结果 Store
│   └── leakage.ts            # 捡漏结果 Store
├── api/
│   └── index.ts              # 统一 API 请求封装 (fetch + SSE)
├── App.vue                   # 根组件
├── main.ts                   # 入口
├── router.ts                 # 三页面路由
└── vite.config.ts            # Vite 配置
```

## 后端 API 对接

默认后端地址: `http://localhost:8000`（在 `api/index.ts` 中配置）
