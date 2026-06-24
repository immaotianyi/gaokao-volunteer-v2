# 高考志愿狙击手 · 前端开发交接文档 (V2)

> 更新日期：2026-06-20
> 上次 AI 会话完成了 P0 修复 + 部分 P1/P2 优化

## 项目概览

| 项目 | 详情 |
|---|---|
| **名称** | 高考志愿狙击手 (GAOKAO·SNIPER) |
| **技术栈** | Vue 3 + TypeScript + Vite + Pinia + Vue Router |
| **路径** | `/Users/sanzhaibanniang/Claude/Projects/gaokao/frontend/` |
| **运行** | `npm run dev` (端口 5173) |
| **构建** | `npm run build` → dist/ |
| **设计语言** | Apple Vision 空间计算质感 · 深色主题 `#020617` |

## 路由结构 (hash 模式)
```
#/                  → pages/landing/landing.vue (产品主页)
#/workbench         → pages/index/index.vue (主工作台)
#/pages/index/index → 重定向到 #/workbench
#/pages/profile/profile → pages/profile/profile.vue (档案管理页)
```

---

## 本轮变更总结

### P0：构建验证 + 关键 Bug 修复
- `npm run build` 已验证通过（需先 `rm -rf node_modules && npm install` 修复 rollup 原生模块）
- Landing 导航栏"立即使用"按钮：`router.push('/workbench')` → `goToWorkbench()`
- AdvisorChat `sendMessage()` 已添加档案校验

### P1：视觉一致性 + SVG 图标化
- ProfileEditor 关闭按钮：文字 `✕` → `<Icon name="close">` SVG 图标
- profile.vue 免责声明勾选：文字 `✓` → `<Icon name="check">` SVG 图标
- Icon.vue 新增 `close` 图标

### P2：结构优化
- **新增 `constants/data.ts`** — 共享常量模块：
  - `DATA_COVERAGE`（数据覆盖说明）
  - `DISCLAIMER`（合规免责声明）
  - `PROVINCE_OPTIONS`（31省列表）
  - `SUBJECT_PRESETS`（7种选科组合）
  - `getSubjectGroup()`（选科→科类映射）
  - `ELECTIVE_FIELD_MAP`（选科→成绩字段映射）
  - `COMPLIANCE_TERMS`（合规文案替换表）
- `tsconfig.json` 移除已弃用的 `baseUrl` / `extends: []`
- ProfileEditor、profile.vue、ProfilePanel 全部引用 `constants/data.ts`，消除代码重复
- `as any` 类型断言替换为 `Record<string, number | null | undefined>` 明确类型

---

## 已完成工作（累计）

| 状态 | 工作项 | 涉及文件 |
|---|---|---|
| ✅ | 路由改为 hash 模式 | `router.ts` |
| ✅ | 考生档案完全重构（空默认值 + 扩展学科 + 必填校验） | `stores/profile.ts` |
| ✅ | 引导弹窗 + 档案完成度进度条 + 数据覆盖说明 | `pages/index/index.vue`, `ProfilePanel.vue`, `ProfileEditor.vue` |
| ✅ | 三个功能入口（探雷器/雷达/顾问）档案校验 | `RiskScanner.vue`, `RadarBoard.vue`, `AdvisorChat.vue` |
| ✅ | Landing 页 countUp 动画 + 导航按钮修复 | `landing.vue` |
| ✅ | 废弃 3D 模型页面及组件 | 删除 `armor.vue`，`ArmorParticles.vue` 无引用 |
| ✅ | 构建验证通过（0 错误） | `npm run build` |
| ✅ | Emoji/SVG 图标替换（Editor关闭按钮、免责声明勾选） | `ProfileEditor.vue`, `profile.vue`, `Icon.vue` |
| ✅ | 共享常量抽取 + 消除代码重复 | `constants/data.ts`, `ProfileEditor.vue`, `profile.vue`, `ProfilePanel.vue` |
| ✅ | `as any` 类型消除 | `ProfileEditor.vue`, `profile.vue`, `ProfilePanel.vue` |
| ✅ | tsconfig 清理（移除 `baseUrl`, `extends`） | `tsconfig.json` |

---

## 当前代码结构
```
frontend/
├── api/index.ts                # 后端 API 封装（SSE、REST）
├── constants/data.ts           # 【新增】共享常量 + 选科/省份/合规数据
├── stores/
│   ├── profile.ts              # 考生档案 Store（核心）
│   ├── risk.ts                 # 探雷结果 Store
│   ├── leakage.ts              # 捡漏雷达 Store
│   └── advisor.ts              # AI 顾问聊天 Store
├── pages/
│   ├── landing/landing.vue     # 产品主页
│   ├── index/index.vue         # 主工作台
│   └── profile/profile.vue     # 档案管理页
├── components/
│   ├── AdvisorChat.vue         # AI 顾问聊天
│   ├── DataUniverse.vue        # Three.js 粒子背景
│   ├── Icon.vue                # SVG 图标库
│   ├── PaymentModal.vue        # 支付弹窗
│   ├── ProfileEditor.vue       # 档案编辑弹窗
│   ├── ProfilePanel.vue        # 侧栏档案面板
│   ├── RadarBoard.vue          # 捡漏雷达
│   ├── RadarCard.vue           # 雷达卡片
│   ├── RiskScanner.vue         # 志愿探雷器
│   └── ArmorParticles.vue      # 已废弃（无引用）
├── App.vue                     # 根组件
├── main.ts                     # 入口
├── router.ts                   # 路由配置
├── static/index.css            # 全局样式
├── vite.config.ts              # Vite 配置
├── tsconfig.json               # TS 配置（已清理弃用项）
└── package.json                # 依赖
```

---

## 待完成任务（后续 AI 可继续）

### 优先级 P2：功能增强
1. **`profile.vue` 模板中的选科成绩非编辑模式展示**：第 210 行内联箭头函数较复杂，可抽取为 computed
2. **支付流程真实对接**：当前为模拟支付，需对接微信支付 Native API

### 优先级 P3：可选优化
3. **Large chunk 优化**：构建后主 chunk 551KB，可考虑按路由 lazy-load 拆分
4. **暗色/亮色主题切换**：当前仅支持暗色主题
5. **国际化 (i18n)**：如计划推广到多省份需不同语言表述
6. **E2E 测试**：添加 Playwright/Cypress 端到端测试
7. **README.md 更新**：补充部署步骤和 CloudBase 资源说明
8. **后端真实存储 API 对接**：`saveProfile`/`getProfile` API 已就位，待后端部署

---

## 启动命令
```bash
cd /Users/sanzhaibanniang/Claude/Projects/gaokao/frontend
npm install          # 如果是全新环境
npm run dev          # 开发模式（端口 5173）
npm run build        # 生产构建
```

## 后续 AI 继续工作的建议提示词
> 请继续完善「高考志愿狙击手」前端项目。项目路径：`/Users/sanzhaibanniang/Claude/Projects/gaokao/frontend/`。请先阅读 `frontend-handoff.md` 了解项目全貌和待办事项。核心架构已稳定：hash 路由 + Vue3 + Pinia + 空档案默认值 + 三入口档案校验 + Glassmorphism 深色主题。构建验证已通过（0 错误）。待办见文档 P2/P3 优先级列表。
