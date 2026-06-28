# 前端开发任务：定制化捡漏雷达 + 两个 Bug 修复

## 一、任务概览

后端已完成三件事，前端需要配合：
1. **修复"object object"红色错误** —— 联网章程检索端点返回结构已变更
2. **修复"输入1显示可以放心"** —— 后端已对无效输入返回 WARNING，前端需要正确渲染
3. **新增"定制化捡漏雷达"完整 UI 流程** —— 结合考生档案 + 志愿草表生成针对性捡漏建议，引导用户付费 ¥9.9 解锁完整报告（核心商业需求）

---

## 二、后端已就绪的接口契约

### 接口1：联网章程检索（已变更返回结构）

`POST /api/check-risk/live`

请求体：
```json
{ "university": "中山大学", "major": "计算机科学与技术" }
```

**新返回结构**（注意：不再返回 `status/reason/matched_clause`，改为 `rules/rules_text/message`）：
```json
{
  "university": "中山大学",
  "major": "计算机科学与技术",
  "source": "local",                         // "local" | "live"
  "rules": { /* 嵌套对象，前端不要直接渲染 */ },
  "rules_text": "【中山大学真实章程条款】\n⚠️ 规则来源年份: 2026年...\n其他: 未发现显性限制",
  "message": "该高校已在本地数据库中，无需联网搜索"
}
```

**关键规则**：
- `rules` 是嵌套 dict，**绝对不能**直接 `{{ liveResult.rules }}` 渲染（会显示 `[object Object]`）
- **必须**用 `rules_text` 字段渲染可读文本
- `source === "local"` 时显示"本地数据库已收录"标签；`source === "live"` 时显示"联网检索"标签
- `message` 字段可作为辅助提示

### 接口2：定制化捡漏雷达（新增）

`POST /api/leakage-radar/customize`

请求体：
```json
{
  "profile": {
    "province": "广东",
    "score": 565,
    "rank": 50000,
    "subjects": "物理,化学,生物",
    "english_score": 120,
    "math_score": 130,
    "chinese_score": 110,
    "vision_status": "正常"
  },
  "subject_group": "物理类",
  "targets": [
    { "university": "深圳大学", "major": "计算机科学与技术" },
    { "university": "广州大学", "major": "软件工程" }
  ],
  "score_tolerance": 30
}
```

返回结构：
```json
{
  "total": 41,
  "preview": [/* LeakageOpportunity[]，前3条免费预览 */],
  "locked": true,
  "locked_count": 38,
  "request_id": "5c193fba-c166-49c6-8...",
  "prompt_text": "基于您的志愿草表（2个目标），捡漏雷达共发现 41 个定制化捡漏机会。已为您预览前 3 条，还有 38 条高价值机会待解锁。\n\n💡 解锁完整报告（仅需 ¥9.9），获取：\n  • 全部 41 个捡漏机会的详细分析\n  • 每个机会的六维评分明细和报考建议\n  • 针对您体检/单科成绩的个性化风险提示\n  • 同档次可替代院校推荐",
  "target_summary": [
    { "university": "深圳大学", "major": "计算机科学与技术", "opportunity_count": 0, "best_score": null, "best_type": null },
    { "university": "广州大学", "major": "软件工程", "opportunity_count": 5, "best_score": 50, "best_type": "分数匹配" }
  ]
}
```

`LeakageOpportunity` 字段参考 `frontend/stores/leakage.ts` 已有的定义。

### 接口3：解锁定制化报告

`POST /api/leakage-radar/customize/unlock`

请求体：
```json
{ "request_id": "5c193fba-c166-49c6-8...", "user_id": "anonymous" }
```

返回结构：
```json
{
  "unlocked": true,
  "total": 41,
  "opportunities": [/* 全部 41 条 LeakageOpportunity */]
}
```

**说明**：比赛期间后端跳过真实支付校验，只要 `request_id` 有效就直接返回完整报告。

---

## 三、任务1：修复联网检索"object object"红色错误

### 文件：`frontend/api/index.ts`

修改 `LiveCheckResult` 接口（第 119-126 行）：

```typescript
export interface LiveCheckResult {
  university: string;
  major: string;
  source: string;            // "local" | "live"
  rules: Record<string, any>; // 嵌套对象，前端不要直接渲染为字符串
  rules_text: string;         // ✅ 可读文本，前端用这个渲染
  message?: string;           // 辅助提示
}
```

### 文件：`frontend/components/RiskScanner.vue`

修改联网检索结果卡片（第 702-716 行附近），把对 `liveResult.status/reason/matched_clause` 的引用全部替换为 `rules_text`：

```vue
<Transition name="live-result">
  <div v-if="liveResult" class="live-result-card" :class="'live-' + (liveResult.source || 'unknown')">
    <div class="live-result-head">
      <span class="live-result-school">{{ esc(liveResult.university) }}</span>
      <span class="live-result-major">{{ esc(liveResult.major) }}</span>
      <span class="live-source-tag">
        <Icon name="radar" :size="10" />
        {{ liveResult.source === 'local' ? '本地数据库' : '联网检索' }}
      </span>
    </div>
    <!-- ✅ 用 rules_text 渲染，保留换行 -->
    <div class="live-result-text">{{ liveResult.rules_text || liveResult.message || '未获取到章程条款' }}</div>
  </div>
</Transition>
```

样式调整：`.live-result-text` 用 `white-space: pre-line;` 保留换行符。`live-local` 用琥珀色边框，`live-live` 用更亮的金色边框 + 微光动画。

### 同时优化：联网检索支持多所大学批量

当前只能一个一个搜，用户反馈不便。可在输入框旁加一个"从志愿草表导入"按钮：点击后把 `draftText` 里解析出的所有大学批量喂给 `/api/check-risk/live`，并发请求，结果逐条渲染。参考 `parseDraft` 函数已有逻辑。

---

## 四、任务2：修复"输入1显示可以放心"

### 后端行为说明

后端已对无效输入返回 WARNING：
- 输入"1"（大学名过短）→ `status: "WARNING"`, `reason: "大学名称「1」过短，请输入完整校名"`
- 输入"中山大学"+"1"（专业名过短）→ `status: "WARNING"`, `reason: "专业名称「1」过短，请输入完整专业名"`
- 输入"abc"（不含"大学"/"学院"且长度<3）→ `status: "WARNING"`, `reason: "「abc」不像有效的大学名称"`

### 文件：`frontend/components/RiskScanner.vue`

**问题根因**：当前 `parseDraft("1")` 返回 `[{university: "1", major: ""}]`，被当作有效志愿提交。SSE 流确实会返回 WARNING，但：

1. **前端 parseDraft 应增加输入合法性预检**（在提交前给用户即时反馈）：

```typescript
function parseDraft(text: string): { targets: RiskTarget[]; invalid: string[] } {
  if (!text) return { targets: [], invalid: [] }
  const invalid: string[] = []
  const targets = text.split("\n").map(l => l.trim()).filter(Boolean).map(line => {
    const m = line.match(/[-—：:\s]+/)
    const university = m && m.index !== undefined ? line.substring(0, m.index).trim() : line
    const major = m && m.index !== undefined ? line.substring(m.index + m[0].length).trim() : ""
    // 输入合法性预检
    if (university.length < 2 || (!university.includes("大学") && !university.includes("学院") && university.length < 3)) {
      invalid.push(`「${university}」不像有效的大学名称`)
    }
    if (major && major.length < 2) {
      invalid.push(`「${major}」不像有效的专业名称`)
    }
    return { university, major }
  }).filter(x => x.university)
  return { targets, invalid }
}
```

更新 `parsedCount` 为 `parseDraft(draftText.value).targets.length`，并在 textarea 下方显示无效输入提示：

```vue
<div v-if="parseDraftInvalid.length" class="draft-warnings">
  <div v-for="(w, i) in parseDraftInvalid" :key="i" class="draft-warn-item">
    <Icon name="warn" :size="10" /> {{ w }}
  </div>
</div>
```

2. **结果卡片渲染**：WARNING 状态的卡片必须显示"需要留意"琥珀色徽章，**不能**显示"可以放心"。检查 `riskStore.results` 的分类逻辑（`warnResults` / `passResults` computed），确保 WARNING 不会跑到 passResults。

3. **统计栏文案**：当 `riskStore.results.every(r => r.status === 'WARNING')` 时，统计栏不应只显示"0 可以放心"冷冰冰的，可以加一句"请检查志愿草表输入是否完整"。

4. **强制刷新**：测试时务必硬刷新浏览器（Cmd+Shift+R）避免缓存旧版前端。

---

## 五、任务3：定制化捡漏雷达 UI（核心商业需求）

### 用户期望流程

````
考生档案已完善（省份+分数+选科+英语/数学/视力）
        ↓
志愿草表已填写（在 RiskScanner 里贴了草表）
        ↓
RadarBoard 顶部出现引导卡片：
  "已检测到你填写了 N 个志愿，要不要做一次定制化捡漏分析？"
  [开始定制化扫描] 按钮
        ↓
点击按钮 → 调 POST /api/leakage-radar/customize
        ↓
展示结果：
  - 顶部：prompt_text 文案（突出"针对你的志愿草表"+"已过滤体检/单科不符"）
  - 中部：3 条预览卡片（用 RadarCard 组件，但加"定制"徽章）
  - 底部：锁定区域（38 条模糊化卡片轮廓 + 付费按钮）
        ↓
点击 [¥9.9 解锁完整报告]
        ↓
弹出 PaymentModal → 用户扫码支付
        ↓
支付成功 → 调 POST /api/leakage-radar/customize/unlock
        ↓
完整 41 条报告渲染，锁定区域消失
````

### 实现要点

#### 5.1 新增 API 封装（`frontend/api/index.ts`）

```typescript
// ── 定制化捡漏雷达 ──

export interface CustomLeakageTarget {
  university: string;
  major: string;
}

export interface CustomLeakagePayload {
  profile: Omit<UserProfile, "user_id">;
  subject_group: string;
  targets: CustomLeakageTarget[];
  score_tolerance?: number;
}

export interface TargetLeakageSummary {
  university: string;
  major: string;
  opportunity_count: number;
  best_score: number | null;
  best_type: string | null;
}

export interface CustomLeakageResult {
  total: number;
  preview: LeakageOpportunity[];
  locked: boolean;
  locked_count: number;
  request_id: string | null;
  prompt_text: string;
  target_summary: TargetLeakageSummary[];
}

export interface CustomUnlockResult {
  unlocked: boolean;
  total: number;
  opportunities: LeakageOpportunity[];
}

export function customizeLeakageRadar(payload: CustomLeakagePayload): Promise<CustomLeakageResult> {
  return request("/api/leakage-radar/customize", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function unlockCustomLeakage(requestId: string, userId: string): Promise<CustomUnlockResult> {
  return request("/api/leakage-radar/customize/unlock", {
    method: "POST",
    body: JSON.stringify({ request_id: requestId, user_id: userId }),
  });
}
```

#### 5.2 扩展 leakage store（`frontend/stores/leakage.ts`）

新增定制化相关状态：

```typescript
// 定制化捡漏状态
const customResult = ref<CustomLeakageResult | null>(null);
const customUnlocked = ref(false);
const customRequestId = ref<string | null>(null);
const customOpportunities = ref<LeakageOpportunity[]>([]); // 解锁后的完整列表
const customLoading = ref(false);

function setCustomResult(data: CustomLeakageResult) {
  customResult.value = data;
  customRequestId.value = data.request_id;
  customUnlocked.value = false;
  customOpportunities.value = data.preview;
}

function setCustomUnlocked(data: CustomUnlockResult) {
  customUnlocked.value = true;
  customOpportunities.value = data.opportunities;
}

function clearCustom() {
  customResult.value = null;
  customUnlocked.value = false;
  customRequestId.value = null;
  customOpportunities.value = [];
}
```

#### 5.3 修改 RadarBoard.vue（`frontend/components/RadarBoard.vue`）

在工具栏下方、雷达网格上方，插入"定制化引导卡片"：

```vue
<!-- 定制化引导：检测到志愿草表已填写时显示 -->
<Transition name="custom-intro">
  <div v-if="showCustomIntro" class="custom-intro-card glass-card">
    <div class="custom-intro-icon"><Icon name="candle" :size="20" /></div>
    <div class="custom-intro-text">
      <div class="custom-intro-title font-brush">为你定制</div>
      <div class="custom-intro-desc">
        检测到你已填写 <span class="highlight">{{ customTargetCount }}</span> 个志愿，
        我们可以结合你的分数、英语、数学、体检信息，
        从全省 25 万条数据中筛选出针对你的捡漏机会。
      </div>
    </div>
    <div class="custom-intro-btn" :class="{ disabled: customLoading }" @click="runCustomLeakage">
      <Icon name="candle" :size="14" />
      <span>{{ customLoading ? '扫描中...' : '开始定制化扫描' }}</span>
    </div>
  </div>
</Transition>
```

`showCustomIntro` 的判断条件：
- `profileStore.profile` 已完善（省份+分数+选科）
- `riskStore.targets`（或从 localStorage 读取的草表）非空
- `customResult.value === null`（还没扫描过）

需要让 RiskScanner 把解析出的 targets 暴露给 RadarBoard。可以在 risk store 里加一个 `lastTargets` 字段，RiskScanner 提交时写入。

#### 5.4 定制化结果展示区

```vue
<!-- 定制化结果区 -->
<div v-if="customResult" class="custom-result-section">
  <!-- 顶部 prompt 文案（突出定制化） -->
  <div class="custom-prompt-card glass-card">
    <div class="custom-prompt-icon"><Icon name="scroll" :size="16" /></div>
    <div class="custom-prompt-text">{{ customResult.prompt_text }}</div>
  </div>

  <!-- 各志愿目标统计 -->
  <div class="custom-target-summary">
    <div v-for="(s, i) in customResult.target_summary" :key="i" class="target-summary-chip">
      <span class="ts-school">{{ s.university }}</span>
      <span class="ts-major">{{ s.major }}</span>
      <span class="ts-count" :class="{ zero: s.opportunity_count === 0 }">
        {{ s.opportunity_count > 0 ? `${s.opportunity_count} 个机会` : '无直接匹配' }}
      </span>
      <span v-if="s.best_score" class="ts-best">最高 {{ s.best_score }} 分 · {{ s.best_type }}</span>
    </div>
  </div>

  <!-- 预览卡片（前3条） -->
  <div class="custom-preview-grid">
    <RadarCard
      v-for="(item, idx) in customResult.preview"
      :key="'cp-'+idx"
      :item="item"
      :user-score="profileStore.profile.score"
      :custom-badge="true"
    />
  </div>

  <!-- 锁定区域 -->
  <div v-if="!customUnlocked" class="custom-locked-section">
    <div class="locked-overlay">
      <div v-for="n in Math.min(customResult.locked_count, 6)" :key="n" class="locked-card-skeleton">
        <div class="skeleton-line w-60" />
        <div class="skeleton-line w-40" />
        <div class="skeleton-line w-80" />
      </div>
      <div class="locked-blur-mask" />
    </div>
    <div class="locked-cta">
      <div class="locked-cta-icon"><Icon name="candle" :size="20" /></div>
      <div class="locked-cta-text">
        <div class="locked-cta-title font-brush">余下 {{ customResult.locked_count }} 条待解锁</div>
        <div class="locked-cta-desc">
          包含同档次可替代院校、扩招机会、新校区首招
          <br />已为你过滤体检/单科不符的选项
        </div>
      </div>
      <div class="locked-cta-btn" @click="openCustomPayment">
        <span class="cta-price">¥9.9</span>
        <span class="cta-label">解锁完整报告</span>
      </div>
    </div>
  </div>

  <!-- 解锁后的完整列表 -->
  <div v-else class="custom-full-grid">
    <RadarCard
      v-for="(item, idx) in customOpportunities"
      :key="'cu-'+idx"
      :item="item"
      :user-score="profileStore.profile.score"
      :custom-badge="true"
    />
  </div>
</div>
```

#### 5.5 付费流程对接

复用已有的 `PaymentModal.vue`，但需要让它支持"定制化解锁"模式：

```typescript
async function openCustomPayment() {
  // 直接打开 PaymentModal
  showPaymentModal.value = true
}

// PaymentModal 的 onUnlock 回调里，判断是定制化还是普通解锁
async function onPaymentUnlocked() {
  if (customResult.value && !customUnlocked.value) {
    // 定制化场景：调 unlock 接口
    try {
      const res = await unlockCustomLeakage(
        customRequestId.value!,
        profileStore.profile.user_id || 'anonymous'
      )
      leakageStore.setCustomUnlocked(res)
      toast.success('完整报告已解锁')
    } catch (e: any) {
      toast.error(e?.message || '解锁失败')
    }
  } else {
    // 普通捡漏雷达场景：原有逻辑
    leakageStore.unlocked = true
  }
  showPaymentModal.value = false
}
```

---

## 六、付费转化设计要点（让用户愿意付 ¥9.9）

### 文案策略

1. **预览3条要有冲击力**：选评分最高的3条，在卡片上突出 `leakage_score`（如"捡漏指数 85"）、`opportunity_type`（如"扩招专业 · 计划+15人"）、`lowest_score_2025`（如"去年最低 558 · 你 565 稳上"）

2. **锁定区域文案要制造"信息差焦虑"**：
   - "余下 38 条包含：12 个同档次可替代院校、8 个新校区首招、5 个中外合作低分机会"
   - "已为你过滤 3 所体检不符的院校、2 所英语单科不符的专业"
   - "这些机会窗口期仅 3 天，建议尽早确认"

3. **价格锚定**：
   - 在 ¥9.9 旁边划掉 ¥99，标注"比赛期间限时"
   - 强调"一顿早餐钱，换 38 个可能改变 trajectory 的机会"

4. **稀缺性**：
   - "前 100 名解锁用户额外赠送『同档次院校对比表』"
   - 实时显示"已有 N 人查看此报告"（前端 mock 一个递增数字）

5. **信任建设**：
   - 在付费按钮下方加小字"比赛演示期间，扫码后直接解锁，不真实扣款"
   - 强调"已为 X 位考生生成定制化报告"

### 视觉策略

- 锁定区域用**毛玻璃模糊**（`backdrop-filter: blur(8px)`）遮住卡片内容，但保留卡片轮廓（看得见数量）
- 付费按钮用**暖金色渐变 + 呼吸光晕动画**，与"秉烛研卷"主题一致
- 解锁瞬间用**粒子消散动画**（模糊层从中心向外消散）

---

## 七、设计风格约束（必须遵守）

参考 `project_memory`：
- **视觉**：墨色底 + 烛光琥珀（#e8b974 / #d49a4e）+ 毛笔字标题（`font-brush` class）+ 诗句点缀 + 克制留白
- **交互**：温暖、人文、安慰感，**避免 AI 感**
- **诗句点缀**：可在定制化引导卡片加"山重水复疑无路，柳暗花明又一村"（陆游·游山西村），暗示"看似没机会，其实还有捡漏机会"
- **阶段命名**：保持"秉烛研卷"七阶段意象（研墨→展卷→列目→查典→研判→成文→落幕），定制化扫描可命名为"为你秉烛"
- **Light/Dark 双主题**：所有新组件必须用 `var(--text-primary)` / `var(--text-secondary)` / `var(--text-muted)` 等 CSS 变量，不能硬编码颜色

---

## 八、验收标准

1. **联网章程检索**：输入"中山大学 计算机科学与技术" → 显示完整章程文本（不再是 `[object Object]`）
2. **输入校验**：志愿草表输入"1" → 显示琥珀色警告"大学名称「1」过短"，不会出现"可以放心"
3. **定制化扫描**：填写考生档案 + 志愿草表 → 点击"开始定制化扫描" → 显示3条预览 + 38条锁定 + ¥9.9 解锁按钮
4. **付费解锁**：点击解锁 → PaymentModal 弹出 → 扫码（演示模式）→ 完整 41 条报告显示
5. **设计风格**：新组件与现有"秉烛研卷"风格一致，墨色+琥珀色+毛笔字+诗句点缀
6. **构建通过**：`npm run build` 无报错
7. **无浏览器控制台错误**

---

## 九、后端服务信息

- 后端运行在 `http://localhost:8000`（开发模式）
- 所有 API 已就绪并经过验证，可直接联调
- 后端进程 PID 24873，端口 8000

完成后请用 `npm run build` 验证构建，并在浏览器硬刷新测试三个场景。
````

---

## 验证小结

后端三个核心问题已全部修复并验证通过：

| 问题 | 后端状态 | 验证结果 |
|---|---|---|
| 输入"1"显示"可以放心" | ✅ 返回 WARNING + 明确原因 | `{"status":"WARNING","reason":"大学名称「1」过短"}` |
| 联网检索"object object"红色 | ✅ 新增 `rules_text` 可读字段 | 返回完整章程文本 |
| 定制化捡漏雷达 | ✅ `/customize` + `/customize/unlock` 双端点 | 41机会/3预览/38锁定/解锁返回全部 |

"object object"和"输入1可以放心"在前端仍然出现，**根因是前端**：
1. `LiveCheckResult` 类型定义与后端实际返回不匹配（前端期待 `status/reason/matched_clause`，后端返回 `rules/rules_text/message`）
2. 前端 `parseDraft` 没有输入合法性预检，WARNING 卡片可能没正确分类

上面的提示词已经把修复方案、API 契约、UI 流程、付费转化设计、风格约束都写清楚了，可以直接转给前端 AI 执行。