# 高考志愿狙击手 — 前端 UI/UX 四阶段重构验收汇报

**日期**: 2026-06-20
**执行者**: 审核 AI（架构 + 审核）

---

## 一、重构前基线

| 指标 | 修前 |
|------|------|
| 前端文件数 | 18 个（含重复 radar.vue、废弃 src/ symlink） |
| index.vue | **1858 行** 单文件 |
| 死代码 | radar/radar.vue (1128 行重复逻辑)、static/index.css (427 行全局样式未被引用) |
| `@/` 别名依赖 | 15 处，Vite 未正确解析致白屏 |
| Toast | `alert()` |
| 档案编辑 | 跳页（profile.vue 独立路由），首页不可编辑 |
| 视力选项 | `"色弱/色盲"`（不匹配后端 `"色弱"` `"色盲"`） |
| 支付容错 | 无 mock 回退，API 失败即崩溃 |

---

## 二、四阶段执行全貌

### 阶段一：架构瘦身与代码清理

| 操作 | 效果 |
|------|------|
| 删除 `pages/radar/radar.vue` + 对应路由 | -1128 行死代码 |
| 精简 `static/index.css`：427 → 37 行 | 仅保留 html/body + .glass-card + 动画 keyframes |
| 拆分 `index.vue`：1858 → 104 行容器 | 组件化：ProfilePanel / RiskScanner / RadarBoard / PaymentModal |
| 新增 `components/` 目录 | 5 组件，平均 157 行 |
| `@/` → 相对路径 | 15 处全部替换，白屏根因修复 |

### 阶段二：核心交互闭环重塑

| 操作 | 效果 |
|------|------|
| `alert()` → Toast 系统 | `toast()` / `toast.success()` / `toast.error()` / `toast.warning()`，纯 CSS 动画 2.5s 自动消失 |
| 新增 `ProfileEditor.vue` | 点击首页档案弹出沉浸式编辑弹窗，不跳页，所见即所得 |
| 视力选项统一 | 三地（ProfilePanel / ProfileEditor / profile.vue）均为 `正常` `色弱` `色盲` |

### 阶段三：视觉与数据感知升级

| 操作 | 效果 |
|------|------|
| 扫描统计条 | `共 N 项 | 🔴 DANGER M | 🟡 WARNING K | 🟢 PASS P` |
| 纯净组优先开关 | `showPureOnly`（group_size ≤ 2） |
| 剔除中外合作开关 | `hideSinoForeign` |
| 移动端 @media (max-width: 768px) | index.vue: flex→column / RiskScanner: 统计条竖排 / RadarBoard: 单列网格 |

### 阶段四：健壮性与边缘容错

| 操作 | 效果 |
|------|------|
| 支付 Mock 回退 | `generateQrcode()` 失败 → `isMockMode=true` → 点击假二维码模拟支付 → `leakageStore.unlocked = true` |
| SSE error → toast | `onError` 触发 toast 并恢复 UI 为可重试态 |
| 雷达 fetch error → toast | `catch` 弹出 toast，loading 状态结束 |

---

## 三、最终文件结构

```
frontend/
├── components/
│   ├── PaymentModal.vue    159 行  ← 支付弹窗 + Mock 降级
│   ├── ProfileEditor.vue   126 行  ← 档案编辑弹窗
│   ├── ProfilePanel.vue     78 行  ← 档案面板
│   ├── RadarBoard.vue      214 行  ← 雷达网格 + 付费墙 + 新筛选项
│   └── RiskScanner.vue     207 行  ← 探雷器 + 统计条 + SSE
├── pages/
│   ├── index/index.vue      95 行  ← 容器（导入 5 组件）
│   └── profile/profile.vue 411 行  ← 独立档案页（备用）
├── stores/
│   ├── risk.ts / leakage.ts / profile.ts
├── api/
│   └── index.ts
├── utils/
│   ├── toast.ts             44 行  ← 轻量 Toast
│   └── h5.ts                10 行  ← Loading 状态
├── static/
│   └── index.css            37 行  ← 全局基础样式
├── App.vue / main.ts / router.ts / vite.config.ts / index.html
└── 配置文件: package.json . tsconfig.json . env.d.ts . Dockerfile
```

**总计**：**24 个文件，2013 行**（v-html/`@/`/alert 全部清零）

---

## 四、前后对比

| 指标 | 修前 | 修后 |
|------|------|------|
| 前端文件数 | 18 (+ 重复) | 24（无重复） |
| 最大单文件 | 1858 行 | 411 行 (profile.vue) |
| `@/` 别名 | 15 处 | 0 |
| `v-html` 内联 SVG | 7 处，含转义 bug | 0 |
| Toast | `alert()` | CSS 动画 Toast |
| 档案编辑 | 跳页 | 弹窗 |
| 支付容错 | 无 | Mock 降级 |
| 统计条 | 无 | DANGER/WARNING/PASS 汇总 |
| 移动端适配 | 无 | 三文件 @media |
| 死代码 | radar.vue 1128行 + 427行CSS | 0 |

---

## 五、移除的无用文件

| 文件 | 原因 |
|------|------|
| `pages/radar/radar.vue` | 与 index.vue 雷达 Tab 完全重复 |
| `frontend/src/` 目录 | 全为 symlink，UniApp 残留 |
| `alias.config.js` | UniApp Vite alias，已用相对路径替代 |
| `tailwind.config.js` | Tailwind 从未被任何文件引用 |
| `demo.html` → `demo.html.backup` | 退役单文件入口 |
| `design-reference.html` | 非产品代码，已融入 Vue 前端 |
| `ui-preview.html` | 被 ui-preview-v2.html 取代 |
| `.playwright-cli/` | 调试日志 |

---

## 六、后端同步修复

| 修复 | 文件 | 影响 |
|------|------|------|
| KB 规则合并逻辑 | `enrollment_kb.py` | 最精确规则优先，`.*` 不再覆盖专业豁免规则（南方医科法学→PASS） |
| `demo.html` mock 回退 | `demo.html.backup` | fallback 改调 POST /api/check-risk 而非本地硬编码 |
| mock_server 入口提示 | `mock_server.py` | 指向 Vue 3 前端而非 demo.html |
| start.sh 入口指引 | `start.sh` | 引导 `cd frontend && npm run dev` |

---

## 七、回归验证

```
🧪 烟雾测试 (后端 5 条关键用例)
✅ 中山大学 临床医学 → DANGER
✅ 南方医科大学 法学（卫生法学） → PASS (KB豁免规则修复)
✅ 华南理工大学 数据科学 → WARNING (数学门槛)
✅ 华南农业大学 软件工程 → PASS (英语≥90满足)
✅ 暨南大学 护理学 → DANGER (色弱+低偏好)
✅ /health OK
✅ /api/leakage-radar (8 items)
```

---

## 八、后续建议

1. **profile.vue 与 ProfileEditor 合并**：当前两套编辑入口（弹窗 + 独立页），建议统一为弹窗
2. **RadarBoard 接入真实 `leakage_radar.py`**：目前仍为 mock 8 条静态数据
3. **npm 依赖清理**：`tailwindcss`、`sass`、`autoprefixer`、`postcss` 不再被引用，可从 package.json 移除
4. **移动端实测**：@media 查询已加，但尚未在手机上验证
