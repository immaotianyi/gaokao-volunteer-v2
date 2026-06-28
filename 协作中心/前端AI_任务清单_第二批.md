# 前端 AI 任务清单（第二批）

> 派发时间：2026-06-28 | 派发人：审核员
> 任务数：35 项（3 CRITICAL / 16 MAJOR / 16 MINOR）
> 项目根：`/Users/sanzhaibanniang/Claude/Projects/gaokao`

## 协作约定

1. 修复完成后在 `协作中心/反馈/` 新建 `20260628_前端AI_完成说明_第二批.md`
2. 在 `协作中心/时间线.md` 追加 `[时间][前端AI] ✅ 完成 #C1` 等记录
3. 验证：`cd frontend && npm run build` 必须 0 错误 0 警告
4. 不影响既有「秉烛研卷」视觉主题（墨色底+烛光琥珀+毛笔标题+诗句点缀）
5. 按 ROI 推荐顺序执行（见末尾），不强制但建议
6. CRITICAL 全部完成后写一条 ✅ 汇总，触发审核员验收

---

## 🔴 CRITICAL（影响核心功能/数据正确性，必先做）

### #C1 · AdvisorChat 多轮上下文丢失 — `history.slice(0, -2)` 截断错误

**文件**：[frontend/components/AdvisorChat.vue#L51](../../frontend/components/AdvisorChat.vue#L51)

**问题**：`advisorStore.history.slice(0, -2)` 在 `addMessage(user)` 与 `addMessage(assistant, streaming:true)` 之后求值。`history` 计算属性（[stores/advisor.ts L29-33](../../frontend/stores/advisor.ts#L29-L33)）已过滤 `streaming` 消息，所以最后只剩新加入的 user 消息为最后一个元素。`slice(0, -2)` 会再多删一个元素，即上一轮 AI 回复被从发给后端的 history 中剥离。结果：服务器在多轮对话中看不到自己上一轮的回答，多轮记忆被破坏。

**修复**：改为 `advisorStore.history.slice(0, -1)`，仅排除当前 user 消息（已通过 `message` 参数单独发送）。

**工作量**：小

---

### #C2 · `esc()` 双重转义导致 HTML 实体泄漏

**文件**：[frontend/components/AdvisorChat.vue#L22](../../frontend/components/AdvisorChat.vue#L22)（同样函数在 [RiskScanner.vue L261](../../frontend/components/RiskScanner.vue#L261)、[RadarCard.vue L17](../../frontend/components/RadarCard.vue#L17) 重复定义）

**问题**：`function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML }` 会把 `<` 转成 `&lt;` 等。模板里再用 `{{ esc(msg.content) }}`，Vue 的 `{{ }}` 走 `textContent` 绑定，会把字符串 `"&lt;"` 当字面量渲染，用户实际看到 `&lt;` 而不是 `<`。AI 回复中含 `<`、`>`、`&` 的内容（如代码块、`分数<100` 这类比较）会出现实体字符。

**修复**：直接用 `{{ msg.content }}`，Vue 的 `{{ }}` 已经做了一次 textContent 转义；三处 `esc` 函数均应删除。

**工作量**：小

---

### #C3 · 工作台 Tab 切换销毁组件状态

**文件**：[frontend/pages/index/index.vue#L109-L111](../../frontend/pages/index/index.vue#L109-L111)

**问题**：`<RiskScanner v-if="activeTab === 'risk'" />`、`<RadarBoard v-if="activeTab === 'radar'" />`、`<AdvisorChat v-if="activeTab === 'advisor'" />` 使用 `v-if` 切换。每次切换都会卸载并重建组件，导致：AdvisorChat 聊天记录全部丢失（store 仍在，但滚动位置、输入框内容、SSE 连接均断）；RadarBoard 已扫描结果丢失；RiskScanner 阶段动画/草表内容丢失。

**修复**：用 `<KeepAlive>` 包裹三个组件 + `v-show` 切换；或在 `v-if` 之外保留组件实例。

**工作量**：小

---

## 🟡 MAJOR（功能性缺陷/重要工程缺口）

### #M1 · 路由 history 模式与 nginx 配置不一致

**文件**：[frontend/router.ts#L5](../../frontend/router.ts#L5) vs [frontend/nginx.conf L53-55](../../frontend/nginx.conf#L53-L55)

**问题**：`router.ts` 使用 `createWebHashHistory()`（hash 模式，URL 形如 `/#/workbench`），但 `nginx.conf` 已配置 `try_files $uri $uri/ /index.html;` SPA fallback。注释说「避免 nginx 未配置 SPA fallback 时刷新 404」，但 nginx 实际已配置。结果：URL 不可分享、不利 SEO、与 nginx 配置意图矛盾。

**修复**：改用 `createWebHistory()`，确保 nginx fallback 生效。

**工作量**：小

---

### #M2 · 路由无 404 兜底

**文件**：[frontend/router.ts#L6-L23](../../frontend/router.ts#L6-L23)

**问题**：仅定义了 3 条路由，无 `/:pathMatch(.*)*` 兜底。访问任何未定义路径（如 `/foo`）在 hash 模式下显示空白 `<router-view>`，用户无任何反馈。

**修复**：增加 catch-all 路由重定向到 landing 或专门的 404 页。

**工作量**：小

---

### #M3 · profile 页面路径不统一

**文件**：[frontend/router.ts#L19-L22](../../frontend/router.ts#L19-L22)

**问题**：工作台路径为 `/workbench`（短），档案页却用 `/pages/profile/profile`（长）。landing.vue L234 跳转也用此长路径。无 `/profile` 短别名，URL 不友好。

**修复**：新增 `path: "/profile"` 重定向到 `/pages/profile/profile`，或直接重命名。

**工作量**：小

---

### #M4 · `<router-view>` 缺少 Suspense / 错误边界

**文件**：[frontend/App.vue#L15](../../frontend/App.vue#L15)

**问题**：路由已懒加载（`router.ts` 用 `() => import(...)`），但 `<router-view />` 未包裹 `<Suspense>` 或 `<ErrorBoundary>`。若懒加载 chunk 网络失败（用户在线弱、新版本部署后旧 hash 失效），整页空白，无重试 UI。

**修复**：包裹 `<Suspense>` + fallback，或在 `router.ts` 加 onError 钩子重试 + 提示。

**工作量**：中

---

### #M5 · `request<T>` 无超时 / 无 AbortSignal

**文件**：[frontend/api/index.ts#L20-L39](../../frontend/api/index.ts#L20-L39)

**问题**：基础 fetch 封装未设置超时，也不支持传入 `AbortSignal`。后端挂起时前端无限等待，且用户切走后无法取消在飞请求。PaymentModal 的 `pollPaymentStatus` 每 2s 轮询一次（L69-78），无最大次数限制，关闭弹窗靠 `clearInterval`，但若用户网络异常会一直静默 fail。

**修复**：`request` 内置 `AbortController` + 默认超时（如 30s），允许 caller 传入 signal；轮询加最大次数。

**工作量**：中

---

### #M6 · `startAdvisorStream` 无自动重连，与 `startRiskStream` 行为不一致

**文件**：[frontend/api/index.ts#L256-L303](../../frontend/api/index.ts#L256-L303)

**问题**：`startRiskStream` 与 `startAgentStream` 走 `createSSEConnection` → `ReconnectingSSE`（最多 2 次自动重连，L383-449），但 `startAdvisorStream` 直接 `new EventSource(url)`（L267），无重连。AI 顾问连接一旦抖动就直接报错「顾问连接已断开」。

**修复**：让 `startAdvisorStream` 也走 `ReconnectingSSE`，或抽公共重连逻辑。

**工作量**：中

---

### #M7 · DataUniverse 持续 rAF，不响应 `visibilitychange`

**文件**：[frontend/components/DataUniverse.vue#L319-L349](../../frontend/components/DataUniverse.vue#L319-L349)

**问题**：4000（移动端 2000）颗星 + 9 个 Sprite 持续 `requestAnimationFrame`，标签页切到后台或用户切到别的 Tab 时仍持续渲染，移动端电池消耗显著。也未响应 `prefers-reduced-motion`。

**修复**：监听 `document.visibilitychange`，hidden 时 `cancelAnimationFrame`，visible 时恢复；CSS 媒体查询 `prefers-reduced-motion: reduce` 时降低旋转速度。

**工作量**：小

---

### #M8 · three.js 未做 vendor 拆分

**文件**：[frontend/vite.config.ts#L5-L15](../../frontend/vite.config.ts#L5-L15)；使用方：DataUniverse.vue L9、ArmorParticles.vue L7

**问题**：`import * as THREE from "three"` 静态导入，three.js（~600KB minified）被打进主 chunk。`vite.config.ts` 没配置 `build.rollupOptions.output.manualChunks`，所有 vendor 混在一起，首屏体积膨胀。

**修复**：`build.rollupOptions.output.manualChunks: { three: ['three'] }`，或对 DataUniverse 用 `defineAsyncComponent` + 路由级懒加载（注意 DataUniverse 是工作台必渲染组件，不宜延迟）。

**工作量**：小

---

### #M9 · profile.vue 编辑保存无校验

**文件**：[frontend/pages/profile/profile.vue#L50-L58](../../frontend/pages/profile/profile.vue#L50-L58)

**问题**：`toggleEdit` 在 `editMode=true → false` 时直接 `profileStore.updateProfile(form.value)`，无任何校验。分数可保存为负数、超 750；省份/选科可为空字符串。对比 [ProfileEditor.vue L52-57](../../frontend/components/ProfileEditor.vue#L52-L57) 有 `validationError` computed，profile 页面却完全没有。

**修复**：复用 ProfileEditor 的 `validationError` 逻辑，保存前校验。

**工作量**：小

---

### #M10 · RiskScanner 邮件留资是假实现

**文件**：[frontend/components/RiskScanner.vue#L282-L300](../../frontend/components/RiskScanner.vue#L282-L300)

**问题**：`sendReport` 仅 `localStorage.setItem("gaokao_report_emails", ...)` + `setTimeout(700)` 模拟延迟，注释明说「比赛阶段前端模拟：仅记录到本地，不打扰后端」。但 UI 显示「已记录，完整报告稍后发到你的邮箱」——用户会等一封永远不会来的邮件。

**修复**：明确标注「演示模式」，或对接真实后端 API；最起码 toast 提示「演示模式：不会真实发送邮件」。

**工作量**：小

---

### #M11 · 大量 `@click` 在 `div` 上，无键盘可达性

**文件**：[frontend/pages/landing/landing.vue#L176-L188-L230-L234](../../frontend/pages/landing/landing.vue#L176)、[pages/index/index.vue L94-L100](../../frontend/pages/index/index.vue#L94)、[components/RiskScanner.vue L509-L513](../../frontend/components/RiskScanner.vue#L509)、[components/RadarBoard.vue L128-L150-L220](../../frontend/components/RadarBoard.vue#L128)、[components/ProfilePanel.vue L45](../../frontend/components/ProfilePanel.vue#L45)

**问题**：所有可点击 `div` 都缺少 `role="button"`、`tabindex="0"`、`@keyup.enter` 处理。键盘用户无法 Tab 到达、无法 Enter 触发。屏幕阅读器读作「通用区块」而非按钮。

**修复**：用 `<button>` 替换 `<div>`（推荐，配合 CSS reset）；或补 `role="button" tabindex="0" @keyup.enter="..."`。

**工作量**：中（量大但模式统一）

---

### #M12 · Icon.vue 完全无障碍语义

**文件**：[frontend/components/Icon.vue#L70-L82](../../frontend/components/Icon.vue#L70-L82)

**问题**：渲染 `<svg v-html="ICONS[name]" />`，无 `role="img"`、无 `aria-hidden="true"`（装饰性图标）、无 `aria-label`（语义图标）。ThemeToggle（L13）、PaymentModal 关闭按钮（L139 `✕`）等图标按钮均无 `aria-label`。

**修复**：Icon 增加 `ariaLabel?: string` prop，有则输出 `role="img" aria-label`，无则 `aria-hidden="true"`；调用方补 aria-label。

**工作量**：中

---

### #M13 · `index.html` 缺 SEO/分享元信息

**文件**：[frontend/index.html#L1-L12](../../frontend/index.html#L1-L12)

**问题**：仅 `<title>高考志愿狙击手</title>` + viewport，缺：`<meta name="description">`、`<meta property="og:title/description/image">`、`<link rel="icon">`（无 favicon，浏览器默认 404）、`<meta name="theme-color">`、`<html lang>` 倒是有但 og:url 缺失。

**修复**：补全 meta 标签、加 favicon（可用 SVG）、加 theme-color（`#07101c`）。

**工作量**：小

---

### #M14 · profile.vue 选科成绩字段用 `as Record<string, ...>` 类型断言

**文件**：[frontend/pages/profile/profile.vue#L213-L218](../../frontend/pages/profile/profile.vue#L213)

**问题**：模板里 `(form as Record<string, number | null | undefined>)[subj.key]`——`UserProfile`（[stores/profile.ts L19-38](../../frontend/stores/profile.ts#L19-L38)）定义了显式字段却无索引签名，导致动态字段访问要类型断言。同样模式在 [ProfilePanel.vue L94](../../frontend/components/ProfilePanel.vue#L94) 重复。`ProfileEditor.vue` L77 已用 `const scoreFields = computed(() => form.value as Record<...>)` 抽出来，是更好的写法但仍是 `as`。

**修复**：在 `UserProfile` 加 `[key: string]: number | string | null | undefined` 索引签名，或抽 `ElectiveScoreAccessor` 工具函数。

**工作量**：小

---

### #M15 · App.vue 无路由切换过渡 / 无顶部加载进度条

**文件**：[frontend/App.vue#L14-L16](../../frontend/App.vue#L14-L16)

**问题**：`<router-view />` 裸用，无 `<Transition>` 包裹，路由切换硬切；懒加载 chunk 拉取期间无任何视觉反馈（用户感知「卡住」）。

**修复**：用 `<Transition name="page-fade" mode="out-in"><router-view /></Transition>`；可选加 `router.beforeEach` + nprogress 风格顶部进度条。

**工作量**：小

---

### #M16 · 缺少 lint / 类型检查 / 测试脚本

**文件**：[frontend/package.json#L5-L9](../../frontend/package.json#L5-L9)

**问题**：`scripts` 只有 `dev`/`build`/`preview`，无 `lint`、`typecheck`（`vue-tsc --noEmit`）、`test`。无 `.eslintrc`、`.prettierrc`、vitest 配置。CI 无法做类型门禁。

**修复**：加 `"typecheck": "vue-tsc --noEmit"`、引入 ESLint + `eslint-plugin-vue`。

**工作量**：中

---

## 🟢 MINOR（代码质量/死代码/小缺陷）

### #m1 · `saveProfile` 返回 `Promise<any>` 丢失类型
**文件**：[frontend/api/index.ts#L50](../../frontend/api/index.ts#L50)
**问题**：`return request<any>("/api/profile", ...)` 丢失类型。后端响应类型未定义。
**修复**：定义 `ProfileSaveResponse` 接口。
**工作量**：小

### #m2 · 多处 `Record<string, any>` 代替 `Omit<UserProfile, "user_id">`
**文件**：[frontend/api/index.ts#L86-L102-L257](../../frontend/api/index.ts#L86)
**问题**：`startRiskStream`、`startAgentStream`、`startAdvisorStream` 的 `profile` 参数用 `Record<string, any>`，丢失类型安全。
**修复**：改 `Omit<UserProfile, "user_id">`。
**工作量**：小

### #m3 · 假 EventSource `readyState` 永远为 0
**文件**：[frontend/api/index.ts#L451-L458](../../frontend/api/index.ts#L451-L458)
**问题**：`createSSEConnection` 返回 `{ close, readyState: 0 } as unknown as EventSource`。调用方若检查 `es.readyState === EventSource.CLOSED` 永远不成立。
**修复**：让 `ReconnectingSSE` 暴露真实 `readyState`，或返回 `ReconnectingSSE` 实例本身。
**工作量**：中

### #m4 · `request` headers 合并被 `...options` 覆盖
**文件**：[frontend/api/index.ts#L21-L24](../../frontend/api/index.ts#L21-L24)
**问题**：`{ headers: {...}, ...options }` 中 `...options` 在 headers 之后展开，若 `options.headers` 存在，会覆盖前面合并好的 headers 对象（丢失 Content-Type）。
**修复**：`const { headers, ...rest } = options; return fetch(url, { ...rest, headers: { "Content-Type": "application/json", ...(headers || {}) } })`。
**工作量**：小

### #m5 · `(PHASE_TIMING as any)[p]`
**文件**：[frontend/components/RiskScanner.vue#L322](../../frontend/components/RiskScanner.vue#L322)
**问题**：`PHASE_TIMING` 定义时无 `as const` 也未标注 `Record<CeremonyPhase, number>`，索引用 `string` 类型时被迫 `as any`。
**修复**：`const PHASE_TIMING: Record<CeremonyPhase, number> = { ... }`，去掉 `as any`。
**工作量**：小

### #m6 · RadarBoard.vue 双重赋值 + `as any`
**文件**：[frontend/components/RadarBoard.vue#L128](../../frontend/components/RadarBoard.vue#L128)
**问题**：`leakageStore.filterType = opt.k as any; leakageStore.filter = opt.k as any`。`filter` 在 [stores/leakage.ts L132-135](../../frontend/stores/leakage.ts#L132-L135) 是 `filterType` 的 computed setter，两行等价。同时 `as any` 绕过类型检查。
**修复**：仅保留 `leakageStore.filter = opt.k`，opt 列表用 `as const` 标注。
**工作量**：小

### #m7 · RadarBoard.vue 空状态条件漏判 customLoading
**文件**：[frontend/components/RadarBoard.vue#L270](../../frontend/components/RadarBoard.vue#L270)
**问题**：`v-if="!leakageStore.result && !leakageStore.loading && !leakageStore.customResult"` 未排除 `customLoading`，定制化扫描启动瞬间，empty-state 与 custom-loading 块（L158）可能同时短暂渲染。
**修复**：加 `&& !leakageStore.customLoading`。
**工作量**：小

### #m8 · 多处 `catch (e: any)`
**文件**：[RiskScanner.vue L480](../../frontend/components/RiskScanner.vue#L480)、[RadarBoard.vue L63-L105](../../frontend/components/RadarBoard.vue#L63)、[PaymentModal.vue L95](../../frontend/components/PaymentModal.vue#L95)
**问题**：TS strict 模式下推荐 `catch (e: unknown)` 后做类型窄化。
**修复**：改 `catch (e: unknown)` + `e instanceof Error ? e.message : "..."`。
**工作量**：小

### #m9 · ProfileEditor.vue `:style as any`
**文件**：[frontend/components/ProfileEditor.vue#L161](../../frontend/components/ProfileEditor.vue#L161)
**问题**：`:style="{ '--count': electiveFields.length } as any"`——CSS 自定义属性本应能用 `as Record<string, string>` 或定义 `CSSProperties` 扩展。
**修复**：`as Record<string, number>` 即可。
**工作量**：小

### #m10 · profile.vue `disclaimerAccepted` 是组件内本地 state
**文件**：[frontend/pages/profile/profile.vue#L71](../../frontend/pages/profile/profile.vue#L71)
**问题**：工作台用 `localStorage.getItem("gaokao_disclaimer_v1")`（[index.vue L32](../../frontend/pages/index/index.vue#L32)）做门槛，profile 页的 `disclaimerAccepted` 是 `ref(false)`，刷新即重置，且与全局门槛状态不联动。
**修复**：复用同一 localStorage key，或抽到 store。
**工作量**：小

### #m11 · landing.vue 重复注册 scroll 监听
**文件**：[frontend/pages/landing/landing.vue#L29-L83-L88](../../frontend/pages/landing/landing.vue#L29)
**问题**：两处 `onMounted` 都调用 `window.addEventListener("scroll", onScroll)`。现代浏览器对相同 (listener, options) 的重复 add 做幂等处理，不会触发两次回调，但代码冗余。
**修复**：合并两个 `onMounted` 块。
**工作量**：小

### #m12 · 死代码：`runTerminalAnimation` / `h5.ts` / leakage store 部分 state / constants
**文件**：
- [stores/risk.ts L49-73](../../frontend/stores/risk.ts#L49-L73) `runTerminalAnimation` 从未被任何组件调用
- [utils/h5.ts](../../frontend/utils/h5.ts) 全文导出 `isLoading/showLoading/hideLoading` 但全项目无引用，注释自承「Toast 已迁移至 utils/toast.ts」
- [stores/leakage.ts L65-69](../../frontend/stores/leakage.ts#L65-L69) `filterTier/filterBatch/sortBy/scoreMin/scoreMax` 在任何组件中均未读取
- [constants/data.ts L58-64-L79-108-L111-114-L171-211](../../frontend/constants/data.ts#L58) `COMPLIANCE_TERMS`/`POETRY_LINES`/`pickPoetry`/`RITUAL_STAGES` 均无引用

**问题**：死代码与死常量占维护成本、误导排查。
**修复**：删除或在 CI 加 unused export 检查。
**工作量**：小

### #m13 · index.html viewport 缺 `viewport-fit=cover`
**文件**：[frontend/index.html#L5](../../frontend/index.html#L5)
**问题**：iPhone 刘海屏/灵动岛需 `viewport-fit=cover` 配合 `env(safe-area-inset-*)` 才能避免内容被遮挡。当前 PaymentModal 等底部贴边组件未考虑安全区。
**修复**：`content="width=device-width, initial-scale=1.0, viewport-fit=cover"`，弹窗与 sticky 顶栏加 `padding: env(safe-area-inset-top)`。
**工作量**：小

### #m14 · profile.vue 表单不响应外部 store 变更
**文件**：[frontend/pages/profile/profile.vue#L18](../../frontend/pages/profile/profile.vue#L18)
**问题**：`const form = ref<UserProfile>({ ...profileStore.profile })` 是 mount 时刻的浅拷贝。若 `App.vue` 的 `loadFromBackend` 异步返回后 `profile.value` 更新，profile 页 form 不会同步。
**修复**：`watch(() => profileStore.profile, (p) => { if (!editMode.value) form.value = { ...p } })`。
**工作量**：小

### #m15 · Toast 容器无最大堆叠数
**文件**：[frontend/utils/toast.ts#L37](../../frontend/utils/toast.ts#L37)
**问题**：每次 `toastImpl` 直接 `appendChild`，无最大数量限制。RiskScanner 在 `onError` 路径连续触发 toast 时，可能堆叠多条。
**修复**：`if (toastContainer!.children.length > 3) toastContainer!.firstChild?.remove()`。
**工作量**：小

### #m16 · ArmorParticles.vue 未被任何页面引用
**文件**：[frontend/components/ArmorParticles.vue](../../frontend/components/ArmorParticles.vue)（整个文件）
**问题**：项目根 `LS` 显示该组件存在，但 `pages/index/index.vue`、`pages/landing/landing.vue`、`pages/profile/profile.vue` 均未 import 它。仅 `public/models/armor.glb` 模型文件被它独占引用。
**修复**：若废弃则删除组件 + 模型文件；若计划启用则在某个页面接入。
**工作量**：小

---

## 📊 概览统计

| 严重程度 | 数量 | 工作量小 | 工作量中 |
|---|---|---|---|
| CRITICAL | 3 | 3 | 0 |
| MAJOR | 16 | 11 | 5 |
| MINOR | 16 | 14 | 2 |
| **合计** | **35** | **28** | **7** |

---

## 🎯 ROI 推荐执行顺序

按「影响大/工作量小」优先排序，建议按以下顺序分批完成：

### 第 1 批（必做，CRITICAL + 高 ROI MAJOR，约 11 项）

1. **#C1** AdvisorChat slice(0,-2) → slice(0,-1)
2. **#C2** 三处 esc() 函数删除
3. **#C3** 工作台 Tab 改 KeepAlive
4. **#M1** router 改 createWebHistory
5. **#M2** 路由加 404 兜底
6. **#M3** profile 路径加短别名
7. **#M7** DataUniverse visibilitychange
8. **#M8** vite manualChunks 拆 three.js
9. **#M9** profile.vue 编辑保存加校验
10. **#M10** RiskScanner 邮件留资标演示模式
11. **#M13** index.html 补 SEO meta + favicon

### 第 2 批（重要工程化，约 8 项）

12. **#M4** router-view 包 Suspense
13. **#M5** request 加超时 + AbortSignal
14. **#M6** startAdvisorStream 走 ReconnectingSSE
15. **#M11** 全局可点击 div 改 button
16. **#M12** Icon 无障碍语义
17. **#M14** UserProfile 加索引签名
18. **#M15** App.vue 加路由切换过渡
19. **#M16** 引入 typecheck/lint 脚本

### 第 3 批（MINOR 清扫，约 16 项）

20-35. 全部 MINOR 项一次性扫掉

---

## ✅ 完成后自检清单

- [ ] `cd frontend && npm run build` 0 错误 0 警告
- [ ] 浏览器控制台无报错
- [ ] CRITICAL 全部修复（#C1 #C2 #C3）
- [ ] 工作台 Tab 切换不丢失聊天记录/扫描结果
- [ ] AI 顾问多轮对话记忆正常（含 `<`、`>` 内容不出现 `&lt;`）
- [ ] 路由用 history 模式 + 404 兜底 + profile 短路径
- [ ] index.html 有 favicon + SEO meta + theme-color
- [ ] DataUniverse 切后台暂停 rAF
- [ ] 在 `协作中心/反馈/20260628_前端AI_完成说明_第二批.md` 写完成说明
- [ ] 在 `协作中心/时间线.md` 追加 ✅ 记录
