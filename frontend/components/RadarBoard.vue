<!-- components/RadarBoard.vue -->
<script setup lang="ts">
import { ref, computed } from "vue"
import { useProfileStore } from "../stores/profile"
import { useLeakageStore } from "../stores/leakage"
import { runLeakageRadar } from "../api/index"
import { toast } from "../utils/toast"
import RadarCard from "./RadarCard.vue"
import Icon from "./Icon.vue"

const profileStore = useProfileStore()
const leakageStore = useLeakageStore()

const emit = defineEmits<{ openPayment: [] }>()
const showPureOnly = ref(false)
const hideSinoForeign = ref(false)

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
  if (leakageStore.result) return
  try {
    const res = await runLeakageRadar({
      province: p.province,
      subject_group: p.subjects?.startsWith("物理") ? "物理类" : "历史类",
      user_score: p.score,
    })
    leakageStore.setResult(res)
  } catch (e: any) { toast(e?.message || "雷达连接失败") }
}

const disclaimerAgreed = ref(false)
</script>

<template>
  <div class="radar-layout">
    <div class="radar-toolbar glass-card">
      <div class="filter-row">
        <div class="filter-chips">
          <div v-for="opt in [{k:'all',l:'全部优选'},{k:'new',l:'新增专业'},{k:'expanded',l:'暴增扩招'}]" :key="opt.k" class="filter-chip" :class="{ active: leakageStore.filter === opt.k }" @click="leakageStore.filterType = opt.k as any; leakageStore.filter = opt.k as any">{{ opt.l }}</div>
        </div>
        <div class="toggle-row">
          <label class="toggle-label" :class="{ on: showPureOnly }" @click="showPureOnly = !showPureOnly">纯净组优先</label>
          <label class="toggle-label" :class="{ on: hideSinoForeign }" @click="hideSinoForeign = !hideSinoForeign">剔除中外合作</label>
        </div>
      </div>
      <div class="radar-refresh" @click="fetchRadarData"><span>扫描</span></div>
    </div>

    <div class="radar-grid" v-if="leakageStore.result">
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
            <span class="paywall-title">解锁隐秘数据</span>
            <span class="paywall-desc">查看剩余 {{ lockedCount }} 个绝佳捡漏机遇</span>
            <div class="disclaimer-box">
              <div class="disclaimer-check" @click="disclaimerAgreed = !disclaimerAgreed">
                <div class="check-box" :class="{ checked: disclaimerAgreed }"><span v-if="disclaimerAgreed" class="check-mark">✓</span></div>
                <span class="disclaimer-label">我已阅读并同意《免责声明》</span>
              </div>
              <span class="disclaimer-text">本工具数据来源于各省考试院与公开招生章程，受限于数据更新延迟与AI理解能力，本报告仅作为辅助筛查工具，不构成最终填报承诺，考生须最终核对官方《填报指南》与官网章程。</span>
            </div>
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

    <div v-if="!leakageStore.result && !leakageStore.loading" class="empty-state glass-card">
      <div class="empty-icon"><Icon name="radar" :size="32" /></div>
      <span class="empty-title">雷达待命</span>
      <span class="empty-desc">点击扫描按钮开始全网搜索捡漏机会</span>
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
.filter-chip { padding: 7px 14px; border-radius: 10px; font-size: 13px; font-weight: 600; background: rgba(255, 255, 255, 0.04); color: #94a3b8; transition: all 0.2s; cursor: pointer; }
.filter-chip.active { background: rgba(56, 189, 248, 0.15); color: #38bdf8; }
.toggle-row { display: flex; gap: 8px; }
.toggle-label { padding: 5px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; background: rgba(255, 255, 255, 0.04); color: #64748b; cursor: pointer; transition: all 0.2s; }
.toggle-label.on { background: rgba(129, 140, 248, 0.15); color: #a5b4fc; border: 1px solid rgba(129, 140, 248, 0.3); }
.radar-refresh { padding: 7px 14px; border-radius: 10px; font-size: 13px; font-weight: 600; background: linear-gradient(135deg, #38bdf8, #818cf8); color: #fff; cursor: pointer; transition: all 0.2s; }
.radar-refresh:hover { box-shadow: 0 4px 16px rgba(56, 189, 248, 0.35); transform: translateY(-1px); }
.radar-refresh:active { transform: scale(0.96); }

.radar-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }

.paywall-section { grid-column: 1 / -1; position: relative; border-radius: 12px; overflow: hidden; margin-top: 8px; }
.skeleton-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; padding: 12px; filter: blur(8px); opacity: 0.25; pointer-events: none; }
.skeleton-card { position: relative; background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.04); border-radius: 10px; padding: 16px; overflow: hidden; }
.skeleton-card::after { content: ''; position: absolute; top: 0; left: -100%; width: 200%; height: 100%; background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.08) 45%, rgba(255,255,255,0.15) 50%, rgba(255,255,255,0.08) 55%, transparent 100%); animation: shimmer 2s ease-in-out infinite; }
.sk-line { height: 10px; border-radius: 5px; background: rgba(255, 255, 255, 0.06); margin-bottom: 8px; }
.sk-line-1 { width: 60%; } .sk-line-2 { width: 80%; } .sk-line-3 { width: 40%; }
.paywall-overlay { position: absolute; inset: 0; z-index: 10; display: flex; align-items: center; justify-content: center; background: linear-gradient(to top, rgba(2, 6, 23, 1) 0%, rgba(2, 6, 23, 0.7) 60%, rgba(2, 6, 23, 0.2) 100%); }
.paywall-card { background: rgba(255, 255, 255, 0.06); backdrop-filter: blur(40px); -webkit-backdrop-filter: blur(40px); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 16px; padding: 28px 24px; text-align: center; max-width: 240px; }
.paywall-title { font-size: 18px; font-weight: 700; color: #f1f5f9; display: block; margin-bottom: 6px; }
.paywall-desc { font-size: 13px; color: #94a3b8; display: block; margin-bottom: 20px; }
.paywall-btn { background: #f1f5f9; color: #020617; padding: 12px 0; border-radius: 25px; font-size: 14px; font-weight: 700; cursor: pointer; position: relative; transition: all 0.2s; }
.paywall-btn:hover { background: #e2e8f0; transform: translateY(-1px); }
.paywall-btn::after { content: ''; position: absolute; inset: -4px; border-radius: 29px; border: 2px solid rgba(241,245,249,0.3); animation: paywall-pulse 2s ease-out infinite; pointer-events: none; }
.paywall-btn:active { background: #cbd5e1; }
.disclaimer-box { margin-bottom: 12px; text-align: left; padding: 8px; background: rgba(0, 0, 0, 0.2); border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.04); }
.disclaimer-check { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; cursor: pointer; }
.check-box { width: 18px; height: 18px; border-radius: 4px; border: 1px solid rgba(255, 255, 255, 0.15); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.check-box.checked { background: #38bdf8; border-color: #38bdf8; }
.check-mark { color: #020617; font-size: 11px; font-weight: 700; }
.disclaimer-label { font-size: 12px; color: #94a3b8; }
.disclaimer-text { font-size: 10px; color: #475569; line-height: 1.6; display: block; }

.scan-ring { width: 60px; height: 60px; position: relative; margin-bottom: 16px; }
.ring-arc { position: absolute; inset: 0; border-radius: 50%; border: 3px solid transparent; border-top-color: #38bdf8; animation: spin 1.2s linear infinite; }

.empty-state { padding: 40px 20px; text-align: center; }
.empty-icon { width: 32px; height: 32px; margin: 0 auto 10px; color: #94a3b8; font-size: 28px; line-height: 1; }
.empty-title { font-size: 16px; font-weight: 700; color: #94a3b8; display: block; margin-bottom: 6px; }
.empty-desc { font-size: 13px; color: #64748b; }
.loading-state { padding: 40px 20px; text-align: center; }
.loading-text { font-size: 14px; color: #94a3b8; margin-top: 16px; display: block; }

@keyframes shimmer {
  0%   { left: -100%; }
  100% { left: 100%; }
}
@keyframes paywall-pulse {
  0%   { box-shadow: 0 0 0 0 rgba(241,245,249,0.4); opacity: 1; }
  100% { box-shadow: 0 0 0 16px rgba(241,245,249,0); opacity: 0; }
}

@media (max-width: 768px) {
  .radar-grid { grid-template-columns: 1fr; }
  .radar-toolbar { flex-direction: column; align-items: flex-start; }
  .filter-row { width: 100%; }
  .toggle-row { flex-wrap: wrap; }
  .skeleton-grid { grid-template-columns: 1fr; }
}
</style>
