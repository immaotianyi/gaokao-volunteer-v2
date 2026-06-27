<!-- components/RadarBoard.vue -->
<script setup lang="ts">
import { ref, computed } from "vue"
import { useProfileStore } from "../stores/profile"
import { useLeakageStore } from "../stores/leakage"
import { useRiskStore } from "../stores/risk"
import { runLeakageRadar, customizeLeakageRadar } from "../api/index"
import { toast } from "../utils/toast"
import { DATA_COVERAGE } from "../constants/data"
import RadarCard from "./RadarCard.vue"
import Icon from "./Icon.vue"

const profileStore = useProfileStore()
const leakageStore = useLeakageStore()
const riskStore = useRiskStore()

const emit = defineEmits<{ openPayment: [] }>()
const showPureOnly = ref(false)
const hideSinoForeign = ref(false)

// 已覆盖省份列表（用于数据未覆盖提示）
const coveredProvinces = computed(() => DATA_COVERAGE.provinces.join("、"))

// Enhanced visibleItems with extra filters
const displayItems = computed(() => {
  let items = leakageStore.visibleItems
  if (showPureOnly.value) items = items.filter(i => (i.group_size ?? 0) <= 2)
  if (hideSinoForeign.value) items = items.filter(i => !i.is_sino_foreign)
  return items
})
const freeItems = computed(() => displayItems.value.slice(0, leakageStore.FREE_COUNT))
const lockedItems = computed(() => {
  if (leakageStore.unlocked) return []
  const d = displayItems.value
  return d.slice(leakageStore.FREE_COUNT)
})
const lockedCount = computed(() => {
  if (leakageStore.unlocked) return 0
  const d = displayItems.value
  return Math.max(0, d.length - leakageStore.FREE_COUNT)
})

async function fetchRadarData() {
  // 档案校验
  const p = profileStore.profile
  if (!p.province || !p.score || !p.subjects) {
    toast("请先完善考生档案（省份、分数、选科）")
    return
  }
  // 防止重复点击
  if (leakageStore.loading) return
  leakageStore.loading = true
  leakageStore.error = ""
  // 清空旧结果，让用户看到重新扫描的过程
  leakageStore.result = null
  try {
    const res = await runLeakageRadar({
      province: p.province,
      subject_group: p.subjects?.startsWith("物理") ? "物理类" : "历史类",
      user_score: p.score,
    })
    leakageStore.setResult(res)
  } catch (e: any) {
    const msg = typeof e?.message === "string" ? e.message : "雷达连接失败"
    leakageStore.error = msg
    toast(msg)
  } finally {
    leakageStore.loading = false
  }
}

const disclaimerAgreed = ref(false)

// ── 定制化捡漏雷达 ──
const customTargetCount = computed(() => riskStore.lastTargets.length)

/** 是否显示定制化引导卡片 */
const showCustomIntro = computed(() => {
  const p = profileStore.profile
  const profileReady = !!(p.province && p.score && p.subjects)
  return profileReady && customTargetCount.value > 0 && !leakageStore.customResult && !leakageStore.customLoading
})

async function runCustomLeakage() {
  const p = profileStore.profile
  if (!p.province || !p.score || !p.subjects) {
    toast("请先完善考生档案")
    return
  }
  if (customTargetCount.value === 0) {
    toast("请先在探雷器粘贴志愿草表")
    return
  }
  leakageStore.customLoading = true
  leakageStore.customError = ""
  try {
    const res = await customizeLeakageRadar({
      profile: p,
      subject_group: p.subjects?.startsWith("物理") ? "物理类" : "历史类",
      targets: riskStore.lastTargets,
      score_tolerance: 30,
    })
    leakageStore.setCustomResult(res)
    toast.success(`已为你发现 ${res.total} 个定制化捡漏机会`)
  } catch (e: any) {
    const msg = typeof e?.message === "string" ? e.message : "定制化扫描失败"
    leakageStore.customError = msg
    toast.error(msg)
  } finally {
    leakageStore.customLoading = false
  }
}

function openCustomPayment() {
  if (!disclaimerAgreed.value) {
    toast("请先阅读并同意免责声明")
    return
  }
  emit("openPayment")
}
</script>

<template>
  <div class="radar-layout">
    <div class="radar-toolbar glass-card">
      <div class="filter-row">
        <div class="filter-chips">
          <div v-for="opt in [{k:'all',l:'全部'},{k:'new',l:'新增专业'},{k:'expanded',l:'扩招专业'}]" :key="opt.k" class="filter-chip" :class="{ active: leakageStore.filter === opt.k }" @click="leakageStore.filterType = opt.k as any; leakageStore.filter = opt.k as any">{{ opt.l }}</div>
        </div>
        <div class="toggle-row">
          <label class="toggle-label" :class="{ on: showPureOnly }" @click="showPureOnly = !showPureOnly">纯净组优先</label>
          <label class="toggle-label" :class="{ on: hideSinoForeign }" @click="hideSinoForeign = !hideSinoForeign">剔除中外合作</label>
        </div>
      </div>
      <div class="radar-refresh" @click="fetchRadarData"><span>开始扫描</span></div>
    </div>

    <!-- 定制化引导卡片：检测到志愿草表已填写时显示 -->
    <Transition name="custom-intro">
      <div v-if="showCustomIntro" class="custom-intro-card glass-card">
        <div class="custom-intro-icon"><Icon name="candle" :size="22" /></div>
        <div class="custom-intro-text">
          <div class="custom-intro-title font-brush">为你定制</div>
          <div class="custom-intro-desc">
            检测到你已填写 <span class="highlight">{{ customTargetCount }}</span> 个志愿，
            我们可以结合你的分数、英语、数学、体检信息，
            从全省数据中筛选出针对你的捡漏机会。
          </div>
        </div>
        <div class="custom-intro-btn" @click="runCustomLeakage">
          <Icon name="candle" :size="14" />
          <span>开始定制化扫描</span>
        </div>
      </div>
    </Transition>

    <!-- 定制化扫描中 -->
    <div v-if="leakageStore.customLoading" class="custom-loading glass-card">
      <div class="scan-ring"><div class="ring-arc" /></div>
      <span class="loading-text">正在结合你的志愿草表，逐所扫描定制化机会...</span>
    </div>

    <!-- 定制化结果区 -->
    <div v-if="leakageStore.customResult" class="custom-result-section">
      <!-- 顶部 prompt 文案 -->
      <div class="custom-prompt-card glass-card">
        <div class="custom-prompt-icon"><Icon name="scroll" :size="16" /></div>
        <div class="custom-prompt-text">{{ leakageStore.customResult.prompt_text }}</div>
      </div>

      <!-- 各志愿目标统计 -->
      <div v-if="leakageStore.customResult.target_summary.length" class="custom-target-summary">
        <div v-for="(s, i) in leakageStore.customResult.target_summary" :key="i" class="target-summary-chip" :class="{ zero: s.opportunity_count === 0 }">
          <span class="ts-school">{{ s.university }}</span>
          <span class="ts-major" v-if="s.major">{{ s.major }}</span>
          <span class="ts-count">
            <span v-if="s.opportunity_count > 0">{{ s.opportunity_count }} 个机会</span>
            <span v-else>无直接匹配</span>
          </span>
          <span v-if="s.best_score" class="ts-best">最高 {{ s.best_score }} 分 · {{ s.best_type }}</span>
        </div>
      </div>

      <!-- 预览卡片（前3条） -->
      <div class="custom-preview-grid">
        <RadarCard
          v-for="(item, idx) in leakageStore.customResult.preview"
          :key="'cp-'+idx"
          :item="item"
          :user-score="profileStore.profile.score"
        />
      </div>

      <!-- 锁定区域 -->
      <div v-if="!leakageStore.customUnlocked && leakageStore.customResult.locked_count > 0" class="custom-locked-section">
        <div class="locked-overlay">
          <div v-for="n in Math.min(leakageStore.customResult.locked_count, 6)" :key="n" class="locked-card-skeleton">
            <div class="skeleton-line w-60" />
            <div class="skeleton-line w-40" />
            <div class="skeleton-line w-80" />
          </div>
          <div class="locked-blur-mask" />
        </div>
        <div class="locked-cta">
          <div class="locked-cta-icon"><Icon name="candle" :size="22" /></div>
          <div class="locked-cta-text">
            <div class="locked-cta-title font-brush">余下 {{ leakageStore.customResult.locked_count }} 条待解锁</div>
            <div class="locked-cta-desc">
              包含同档次可替代院校、扩招机会、新校区首招<br />
              已为你过滤体检/单科不符的选项
            </div>
          </div>
          <div class="locked-cta-action">
            <div class="disclaimer-box">
              <div class="disclaimer-check" @click="disclaimerAgreed = !disclaimerAgreed">
                <div class="check-box" :class="{ checked: disclaimerAgreed }"><span v-if="disclaimerAgreed" class="check-mark">✓</span></div>
                <span class="disclaimer-label">我已阅读并同意《免责声明》</span>
              </div>
            </div>
            <div class="locked-cta-btn" :class="{ disabled: !disclaimerAgreed }" @click="openCustomPayment">
              <span class="cta-price">¥9.9</span>
              <span class="cta-label">解锁完整报告</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 解锁后的完整列表 -->
      <div v-if="leakageStore.customUnlocked" class="custom-full-grid">
        <RadarCard
          v-for="(item, idx) in leakageStore.customOpportunities"
          :key="'cu-'+idx"
          :item="item"
          :user-score="profileStore.profile.score"
        />
      </div>
    </div>

    <!-- 普通捡漏雷达结果 -->
    <div class="radar-grid" v-if="leakageStore.result && leakageStore.result.total > 0">
      <RadarCard
        v-for="(item, idx) in freeItems"
        :key="'f-'+idx"
        :item="item"
        :user-score="profileStore.profile.score"
      />

      <div v-if="lockedCount > 0" class="paywall-section">
        <div class="skeleton-grid">
          <div v-for="n in Math.min(lockedCount, 4)" :key="'sk-'+n" class="skeleton-card"><div class="sk-line sk-line-1" /><div class="sk-line sk-line-2" /><div class="sk-line sk-line-3" /></div>
        </div>
        <div class="paywall-overlay">
          <div class="paywall-card">
            <span class="paywall-title">查看完整清单</span>
            <span class="paywall-desc">还有 {{ lockedCount }} 所院校的捡漏机会，每一所都经过算法筛选</span>
            <div class="paywall-btn" @click="emit('openPayment')"><span>支付 ¥ 9.9 解锁</span></div>
          </div>
        </div>
      </div>

      <RadarCard
        v-for="(item, idx) in lockedItems"
        :key="'l-'+idx"
        :item="item"
        :user-score="profileStore.profile.score"
        unlocked
      />
    </div>

    <div v-if="!leakageStore.result && !leakageStore.loading && !leakageStore.customResult" class="empty-state glass-card">
      <div class="empty-icon"><Icon name="radar" :size="32" /></div>
      <span class="empty-title">等待开始</span>
      <span class="empty-desc">点击「开始扫描」，从你的分数出发，找出值得关注的院校</span>
    </div>

    <!-- 数据未覆盖提示：扫描完成但0结果 -->
    <div v-if="leakageStore.result && leakageStore.result.total === 0 && !leakageStore.loading" class="empty-state glass-card coverage-empty">
      <div class="empty-icon"><Icon name="scroll" :size="32" /></div>
      <span class="empty-title">{{ profileStore.profile.province }} 暂未覆盖招生计划数据</span>
      <span class="empty-desc">我们正在持续扩充数据，目前已覆盖：<br/><strong>{{ coveredProvinces }}</strong></span>
      <span class="empty-hint">你可以使用「志愿探雷器」核对章程规则（覆盖全国 135 所高校），或切换到已覆盖省份体验捡漏雷达。</span>
    </div>

    <div v-if="leakageStore.loading" class="loading-state glass-card">
      <div class="scan-ring"><div class="ring-arc" /></div>
      <span class="loading-text">正在扫描 {{ profileStore.profile.province }} 全省招生计划...</span>
    </div>
  </div>
</template>

<style scoped>
.radar-layout { display: flex; flex-direction: column; gap: 12px; }
.radar-toolbar { padding: 14px 16px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; }
.filter-row { display: flex; flex-direction: column; gap: 8px; flex: 1; }
.filter-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.filter-chip { padding: 7px 14px; border-radius: 10px; font-size: 13px; font-weight: 600; background: rgba(255, 255, 255, 0.04); color: var(--text-secondary); transition: all 0.2s; cursor: pointer; }
.filter-chip.active { background: rgba(232, 185, 116, 0.15); color: #e8b974; }
.toggle-row { display: flex; gap: 8px; }
.toggle-label { padding: 5px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; background: rgba(255, 255, 255, 0.04); color: var(--text-muted); cursor: pointer; transition: all 0.2s; }
.toggle-label.on { background: rgba(212, 154, 78, 0.15); color: #d49a4e; border: 1px solid rgba(212, 154, 78, 0.3); }
.radar-refresh { padding: 7px 14px; border-radius: 10px; font-size: 13px; font-weight: 600; background: linear-gradient(135deg, #e8b974, #d49a4e); color: #fff; cursor: pointer; transition: all 0.2s; }
.radar-refresh:hover { box-shadow: 0 4px 16px rgba(232, 185, 116, 0.35); transform: translateY(-1px); }
.radar-refresh:active { transform: scale(0.96); }

/* ── 定制化引导卡片 ── */
.custom-intro-card { padding: 18px 20px; display: flex; align-items: center; gap: 14px; border: 1px solid rgba(232, 185, 116, 0.2); background: linear-gradient(135deg, rgba(232, 185, 116, 0.06), rgba(212, 154, 78, 0.03)); }
.custom-intro-icon { width: 44px; height: 44px; border-radius: 12px; background: linear-gradient(135deg, rgba(232, 185, 116, 0.18), rgba(212, 154, 78, 0.12)); border: 1px solid rgba(232, 185, 116, 0.25); display: flex; align-items: center; justify-content: center; color: #e8b974; flex-shrink: 0; }
.custom-intro-text { flex: 1; min-width: 0; }
.custom-intro-title { font-size: 17px; font-weight: 800; color: var(--text-primary); letter-spacing: 2px; margin-bottom: 4px; }
.custom-intro-desc { font-size: 12px; color: var(--text-secondary); line-height: 1.7; }
.custom-intro-desc .highlight { color: #e8b974; font-weight: 700; }
.custom-intro-btn { display: flex; align-items: center; gap: 6px; padding: 10px 18px; border-radius: 12px; font-size: 13px; font-weight: 700; background: linear-gradient(135deg, #e8b974, #d49a4e); color: #fff; cursor: pointer; box-shadow: 0 6px 20px rgba(232, 185, 116, 0.3); transition: all 0.2s; flex-shrink: 0; }
.custom-intro-btn:hover { box-shadow: 0 10px 28px rgba(232, 185, 116, 0.45); transform: translateY(-1px); }
.custom-intro-btn:active { transform: scale(0.96); }
.custom-intro-enter-active, .custom-intro-leave-active { transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1); }
.custom-intro-enter-from, .custom-intro-leave-to { opacity: 0; transform: translateY(-12px); }

/* ── 定制化加载 ── */
.custom-loading { padding: 32px 20px; text-align: center; }

/* ── 定制化结果区 ── */
.custom-result-section { display: flex; flex-direction: column; gap: 12px; }
.custom-prompt-card { padding: 14px 18px; display: flex; gap: 12px; align-items: flex-start; border-left: 3px solid #e8b974; }
.custom-prompt-icon { color: #e8b974; flex-shrink: 0; padding-top: 2px; }
.custom-prompt-text { font-size: 12px; color: var(--text-secondary); line-height: 1.8; white-space: pre-line; }

.custom-target-summary { display: flex; gap: 8px; flex-wrap: wrap; }
.target-summary-chip { display: flex; flex-direction: column; gap: 2px; padding: 8px 12px; background: rgba(232, 185, 116, 0.06); border: 1px solid rgba(232, 185, 116, 0.15); border-radius: 10px; min-width: 0; }
.target-summary-chip.zero { opacity: 0.55; }
.ts-school { font-size: 12px; font-weight: 700; color: var(--text-primary); }
.ts-major { font-size: 10px; color: var(--text-muted); }
.ts-count { font-size: 11px; color: #e8b974; font-weight: 600; }
.target-summary-chip.zero .ts-count { color: var(--text-muted); }
.ts-best { font-size: 10px; color: #f4d8a8; font-family: "SF Mono", monospace; }

.custom-preview-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.custom-full-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }

/* ── 锁定区域 ── */
.custom-locked-section { position: relative; border-radius: 14px; overflow: hidden; border: 1px solid rgba(232, 185, 116, 0.15); }
.locked-overlay { position: relative; padding: 16px; }
.locked-card-skeleton { background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.04); border-radius: 10px; padding: 16px; margin-bottom: 10px; }
.skeleton-line { height: 10px; border-radius: 5px; background: rgba(255, 255, 255, 0.06); margin-bottom: 8px; }
.skeleton-line.w-60 { width: 60%; } .skeleton-line.w-40 { width: 40%; } .skeleton-line.w-80 { width: 80%; }
.locked-blur-mask { position: absolute; inset: 0; backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); background: rgba(7, 16, 28, 0.4); }
.locked-cta { position: relative; z-index: 2; padding: 24px 20px; display: flex; align-items: center; gap: 14px; background: linear-gradient(135deg, rgba(15, 23, 42, 0.92), rgba(15, 23, 42, 0.85)); border-top: 1px solid rgba(232, 185, 116, 0.2); }
.locked-cta-icon { width: 48px; height: 48px; border-radius: 12px; background: linear-gradient(135deg, rgba(232, 185, 116, 0.2), rgba(212, 154, 78, 0.15)); border: 1px solid rgba(232, 185, 116, 0.3); display: flex; align-items: center; justify-content: center; color: #e8b974; flex-shrink: 0; box-shadow: 0 0 24px rgba(232, 185, 116, 0.2); }
.locked-cta-text { flex: 1; min-width: 0; }
.locked-cta-title { font-size: 16px; font-weight: 800; color: var(--text-primary); letter-spacing: 1.5px; margin-bottom: 4px; }
.locked-cta-desc { font-size: 11px; color: var(--text-secondary); line-height: 1.7; }
.locked-cta-action { display: flex; flex-direction: column; gap: 8px; align-items: flex-end; flex-shrink: 0; }
.locked-cta-btn { display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 12px 22px; border-radius: 12px; background: linear-gradient(135deg, #e8b974, #d49a4e); color: #fff; cursor: pointer; box-shadow: 0 8px 24px rgba(232, 185, 116, 0.35); transition: all 0.2s; }
.locked-cta-btn.disabled { opacity: 0.5; cursor: not-allowed; box-shadow: none; }
.locked-cta-btn:not(.disabled):hover { box-shadow: 0 12px 32px rgba(232, 185, 116, 0.5); transform: translateY(-1px); }
.cta-price { font-size: 18px; font-weight: 900; letter-spacing: -0.5px; }
.cta-label { font-size: 10px; font-weight: 600; opacity: 0.9; }
.disclaimer-box { text-align: right; }
.disclaimer-check { display: flex; align-items: center; gap: 6px; cursor: pointer; }
.check-box { width: 16px; height: 16px; border-radius: 4px; border: 1px solid rgba(255, 255, 255, 0.15); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.check-box.checked { background: #e8b974; border-color: #e8b974; }
.check-mark { color: #020617; font-size: 10px; font-weight: 700; }
.disclaimer-label { font-size: 11px; color: var(--text-secondary); white-space: nowrap; }

.radar-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }

.paywall-section { grid-column: 1 / -1; position: relative; border-radius: 12px; overflow: hidden; margin-top: 8px; }
.skeleton-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; padding: 12px; filter: blur(8px); opacity: 0.25; pointer-events: none; }
.skeleton-card { position: relative; background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.04); border-radius: 10px; padding: 16px; overflow: hidden; }
.skeleton-card::after { content: ''; position: absolute; top: 0; left: -100%; width: 200%; height: 100%; background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.08) 45%, rgba(255,255,255,0.15) 50%, rgba(255,255,255,0.08) 55%, transparent 100%); animation: shimmer 2s ease-in-out infinite; }
.sk-line { height: 10px; border-radius: 5px; background: rgba(255, 255, 255, 0.06); margin-bottom: 8px; }
.sk-line-1 { width: 60%; } .sk-line-2 { width: 80%; } .sk-line-3 { width: 40%; }
.paywall-overlay { position: absolute; inset: 0; z-index: 10; display: flex; align-items: center; justify-content: center; background: linear-gradient(to top, rgba(2, 6, 23, 1) 0%, rgba(2, 6, 23, 0.7) 60%, rgba(2, 6, 23, 0.2) 100%); }
.paywall-card { background: rgba(255, 255, 255, 0.06); backdrop-filter: blur(40px); -webkit-backdrop-filter: blur(40px); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 16px; padding: 28px 24px; text-align: center; max-width: 240px; }
.paywall-title { font-size: 18px; font-weight: 700; color: var(--text-primary); display: block; margin-bottom: 6px; }
.paywall-desc { font-size: 13px; color: var(--text-secondary); display: block; margin-bottom: 20px; }
.paywall-btn { background: var(--text-primary); color: #020617; padding: 12px 0; border-radius: 25px; font-size: 14px; font-weight: 700; cursor: pointer; position: relative; transition: all 0.2s; }
.paywall-btn:hover { background: var(--text-primary); transform: translateY(-1px); }
.paywall-btn::after { content: ''; position: absolute; inset: -4px; border-radius: 29px; border: 2px solid rgba(241,245,249,0.3); animation: paywall-pulse 2s ease-out infinite; pointer-events: none; }
.paywall-btn:active { background: var(--text-secondary); }

.scan-ring { width: 60px; height: 60px; position: relative; margin-bottom: 16px; }
.ring-arc { position: absolute; inset: 0; border-radius: 50%; border: 3px solid transparent; border-top-color: #e8b974; animation: spin 1.2s linear infinite; }

.empty-state { padding: 40px 20px; text-align: center; }
.empty-icon { width: 32px; height: 32px; margin: 0 auto 10px; color: var(--text-secondary); font-size: 28px; line-height: 1; }
.empty-title { font-size: 16px; font-weight: 700; color: var(--text-secondary); display: block; margin-bottom: 6px; }
.empty-desc { font-size: 13px; color: var(--text-muted); line-height: 1.7; }
.empty-desc strong { color: #e8b974; font-weight: 600; }
.empty-hint { font-size: 12px; color: var(--text-muted); margin-top: 10px; display: block; line-height: 1.6; opacity: 0.85; }
.coverage-empty { border: 1px dashed rgba(232, 185, 116, 0.25); }
.loading-state { padding: 40px 20px; text-align: center; }
.loading-text { font-size: 14px; color: var(--text-secondary); margin-top: 16px; display: block; }

@keyframes shimmer {
  0%   { left: -100%; }
  100% { left: 100%; }
}
@keyframes paywall-pulse {
  0%   { box-shadow: 0 0 0 0 rgba(241,245,249,0.4); opacity: 1; }
  100% { box-shadow: 0 0 0 16px rgba(241,245,249,0); opacity: 0; }
}

@media (max-width: 768px) {
  .radar-grid, .custom-preview-grid, .custom-full-grid { grid-template-columns: 1fr; }
  .radar-toolbar { flex-direction: column; align-items: flex-start; }
  .filter-row { width: 100%; }
  .toggle-row { flex-wrap: wrap; }
  .skeleton-grid { grid-template-columns: 1fr; }
  .custom-intro-card { flex-direction: column; align-items: flex-start; }
  .custom-intro-btn { width: 100%; justify-content: center; }
  .locked-cta { flex-direction: column; align-items: flex-start; }
  .locked-cta-action { width: 100%; align-items: stretch; }
  .locked-cta-btn { width: 100%; flex-direction: row; justify-content: center; gap: 8px; }
}
</style>
