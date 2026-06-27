<!--
  components/RadarCard.vue — 单张捡漏雷达卡片
  特效：数字滚动 + 重点推荐徽章
-->
<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from "vue"
import { useCountUp } from "../utils/useCountUp"
import type { LeakageOpportunity } from "../stores/leakage"
import Icon from "./Icon.vue"

const props = defineProps<{
  item: LeakageOpportunity
  userScore?: number
  unlocked?: boolean
}>()

function esc(s: string) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML }

function scoreTier(s: number) {
  if (s >= 80) return "tier-s"
  if (s >= 60) return "tier-a"
  if (s >= 40) return "tier-b"
  return "tier-c"
}

const isTierS = computed(() => (props.item.leakage_score ?? 0) >= 80)

function getRadarTags(item: any) {
  const tags: { text: string; cls: string }[] = []
  if (item.opportunity_type === "新增专业") tags.push({ text: "新增", cls: "tag-blue" })
  if (item.opportunity_type === "扩招专业") tags.push({ text: "扩招", cls: "tag-amber" })
  if (item.is_new_campus) tags.push({ text: "新校区", cls: "tag-purple" })
  if (item.is_sino_foreign) tags.push({ text: "中外合作", cls: "tag-cyan" })
  if (item.is_high_tuition) tags.push({ text: "高收费", cls: "tag-rose" })
  if (item.group_size === 1) tags.push({ text: "独享组", cls: "tag-emerald" })
  return tags
}

// ── 数字滚动：估分 + 分差 ──
const estScore = useCountUp()
const scoreGap = useCountUp()

const realGap = computed(() => {
  if (!props.item.estimated_score || !props.userScore) return null
  return props.userScore - props.item.estimated_score
})

const gapPositive = computed(() => (realGap.value ?? 0) >= 0)

onMounted(() => {
  const estimated = props.item.estimated_score ?? 0
  const gap = realGap.value ?? 0

  // 估分滚动（800ms）
  if (estimated > 0) {
    setTimeout(() => estScore.start(estimated, 800), 300)
  }
  // 分差滚动（600ms，稍后启动）
  if (gap !== 0) {
    setTimeout(() => scoreGap.start(Math.abs(gap), 600), 500)
  }
})

const tierClass = computed(() => scoreTier(props.item.leakage_score || 0))

// ── 热度徽章（仅 top5 卡片有值，后端 heat_tracker 填充） ──
const heatLevel = computed(() => props.item.heat_level ?? null)
const heatLabel = computed(() => props.item.heat_label ?? "")
const heatTitle = computed(() => {
  // watcher_count 加 Math.max(0, n) 兜底，防 #5 后端修复前的负数
  const v = Math.max(0, props.item.heat_view_count ?? 0)
  const t = Math.max(0, props.item.heat_today_view ?? 0)
  const w = Math.max(0, props.item.heat_watcher_count ?? 0)
  return `累计 ${v} 人查看 · 今日 ${t} 人 · ${w} 人在盯`
})
</script>

<template>
  <div class="radar-card" :class="[
    tierClass,
    { unlocked, 'tier-s-card': isTierS }
  ]">
    <!-- 重点推荐光晕背景 -->
    <div v-if="isTierS" class="s-glow-bg" />

    <!-- 重点推荐徽章 -->
    <div v-if="isTierS" class="s-alert-badge">
      <span class="badge-icon-wrap"><Icon name="diamond" :size="11" /></span>
      <span class="badge-text">重点推荐</span>
    </div>

    <div class="card-head">
      <div class="card-info">
        <span class="card-school">{{ esc(item.university_name) }}</span>
        <span class="card-school-type" v-if="item.school_type">{{ item.school_type }}</span>
        <!-- 热度徽章：仅当后端返回 heat_level 时渲染 -->
        <span v-if="heatLevel" class="heat-badge" :class="'heat-' + heatLevel" :title="heatTitle">
          <span class="heat-dot" />
          {{ heatLabel }}
        </span>
      </div>
      <div class="card-score" :class="tierClass"><Icon name="flame" :size="12" /> {{ item.leakage_score || '--' }}</div>
    </div>

    <span class="card-major">{{ esc(item.major_name) }} · 计划 {{ item.plan_count }} 人</span>

    <!-- 数字老虎机：估分 + 分差 -->
    <div v-if="item.estimated_score" class="card-estimate">
      <span class="est-label">估分</span>
      <span class="est-value" :class="{ rolling: estScore.rolling.value, 'positive-final': !estScore.rolling.value && gapPositive, 'negative-final': !estScore.rolling.value && !gapPositive }">
        {{ estScore.display.value }}
      </span>
      <span v-if="realGap !== null" class="gap-sep">|</span>
      <span v-if="realGap !== null" class="gap-value" :class="{ rolling: scoreGap.rolling.value, 'positive-final': !scoreGap.rolling.value && gapPositive, 'negative-final': !scoreGap.rolling.value && !gapPositive }">
        {{ gapPositive ? '+' : '-' }}{{ scoreGap.display.value }}
      </span>
    </div>

    <div class="card-tags">
      <div v-for="tag in getRadarTags(item)" :key="tag.text" class="card-tag" :class="tag.cls">{{ tag.text }}</div>
      <!-- 数据可信度标签 -->
      <span v-if="item.data_trust_level" class="card-tag trust-tag" :class="'trust-' + item.data_trust_level.toLowerCase()">
        {{ item.data_trust_level }} 数据
      </span>
    </div>

    <!-- 联网动态信息 -->
    <div v-if="item.live_latest_score || item.live_employment || item.live_news" class="live-info-section">
      <div v-if="item.live_latest_score" class="live-row">
        <span class="live-label">最新分数线</span>
        <span class="live-text">{{ esc(item.live_latest_score) }}</span>
      </div>
      <div v-if="item.live_employment" class="live-row">
        <span class="live-label">就业前景</span>
        <span class="live-text">{{ esc(item.live_employment) }}</span>
      </div>
      <div v-if="item.live_news" class="live-row">
        <span class="live-label">相关动态</span>
        <span class="live-text">{{ esc(item.live_news) }}</span>
      </div>
      <div v-if="item.live_sources && item.live_sources.length" class="live-sources">
        <span class="source-label">来源:</span>
        <a v-for="(src, i) in item.live_sources.slice(0, 2)" :key="i" :href="src" target="_blank" rel="noopener" class="source-link">{{ src.length > 40 ? src.substring(0, 40) + '...' : src }}</a>
      </div>
    </div>

    <!-- 数据可信度说明 -->
    <div v-if="item.data_trust_desc" class="trust-desc">{{ esc(item.data_trust_desc) }}</div>

    <div class="card-footer">
      <span class="card-reason">{{ esc(item.reason) }}</span>
    </div>
  </div>
</template>

<style scoped>
.radar-card { position: relative; background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 10px; padding: 14px; overflow: hidden; transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); z-index: 0; animation: card-enter 0.5s cubic-bezier(0.34, 1.56, 0.64, 1); }
@keyframes card-enter { from { opacity: 0; transform: translateY(16px) scale(0.96); } to { opacity: 1; transform: translateY(0) scale(1); } }

.radar-card:hover { transform: translateY(-5px); border-color: rgba(232, 185, 116, 0.2); box-shadow: 0 12px 24px -10px rgba(0,0,0,0.5); }
.radar-card:active { background: rgba(255, 255, 255, 0.06); }
.radar-card.unlocked { border-color: rgba(232, 185, 116, 0.2); background: rgba(232, 185, 116, 0.03); }

/* ── 重点推荐特效 ── */
.radar-card.tier-s-card { border-color: rgba(250, 204, 21, 0.25); }
.s-glow-bg { position: absolute; inset: 0; background: radial-gradient(circle at 50% 50%, rgba(250, 204, 21, 0.15) 0%, transparent 70%); pointer-events: none; animation: s-glow-pulse 4s ease-in-out infinite; }
@keyframes s-glow-pulse { 0%, 100% { opacity: 0.6; } 50% { opacity: 1; } }
.s-alert-badge { position: absolute; top: 8px; right: 8px; display: flex; align-items: center; gap: 3px; padding: 3px 8px; background: linear-gradient(135deg, rgba(250, 204, 21, 0.2), rgba(232, 185, 116, 0.15)); border: 1px solid rgba(250, 204, 21, 0.4); border-radius: 6px; z-index: 2; animation: s-badge-blink 1.5s ease-in-out infinite; }
.badge-icon-wrap { display: flex; align-items: center; color: #facc15; }
.badge-text { font-size: 9px; font-weight: 700; color: #facc15; letter-spacing: 0.5px; }
@keyframes s-badge-blink { 0%, 100% { opacity: 1; box-shadow: 0 0 8px rgba(250, 204, 21, 0.3); } 50% { opacity: 0.6; box-shadow: 0 0 16px rgba(250, 204, 21, 0.6); } }

.card-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px; position: relative; z-index: 1; }
.card-info { display: flex; align-items: center; gap: 6px; }
.card-school { font-size: 15px; font-weight: 700; color: var(--text-primary); max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-school-type { font-size: 10px; color: var(--text-muted); background: rgba(255, 255, 255, 0.04); padding: 1px 6px; border-radius: 4px; }

/* ── 热度徽章（秉烛研卷主题：墨色底+烛光琥珀，按热度分级） ── */
.heat-badge { display: inline-flex; align-items: center; gap: 4px; padding: 2px 7px; border-radius: 5px; font-size: 10px; font-weight: 600; cursor: help; line-height: 1.4; }
.heat-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
.heat-cold { background: rgba(148, 163, 184, 0.1); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.18); }      /* 灰墨色 · 低饱和 */
.heat-normal { background: rgba(232, 185, 116, 0.1); color: #f4d8a8; border: 1px solid rgba(232, 185, 116, 0.2); }    /* 默认琥珀 */
.heat-hot { background: rgba(251, 191, 36, 0.15); color: #fde68a; border: 1px solid rgba(251, 191, 36, 0.3); }        /* 加亮琥珀 */
.heat-viral { background: rgba(250, 204, 21, 0.18); color: #facc15; border: 1px solid rgba(250, 204, 21, 0.4); animation: heat-viral-breath 2.4s ease-in-out infinite; }  /* 强调琥珀 + 呼吸光效 */
@keyframes heat-viral-breath { 0%, 100% { box-shadow: 0 0 6px rgba(250, 204, 21, 0.25); } 50% { box-shadow: 0 0 14px rgba(250, 204, 21, 0.55); } }
.card-score { padding: 4px 10px; border-radius: 7px; font-size: 12px; font-weight: 700; display: flex; align-items: center; gap: 3px; }
.tier-s { background: rgba(34, 197, 94, 0.12); color: #86efac; border: 1px solid rgba(34, 197, 94, 0.25); }
.tier-a { background: rgba(232, 185, 116, 0.12); color: #f4d8a8; border: 1px solid rgba(232, 185, 116, 0.25); }
.tier-b { background: rgba(251, 191, 36, 0.12); color: #fde68a; border: 1px solid rgba(251, 191, 36, 0.25); }
.tier-c { background: rgba(148, 163, 184, 0.12); color: var(--text-secondary); border: 1px solid rgba(148, 163, 184, 0.25); }
.card-major { font-size: 12px; color: var(--text-secondary); display: block; margin: 6px 0; position: relative; z-index: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── 数字滚动 ── */
.card-estimate { display: flex; align-items: baseline; gap: 6px; margin-bottom: 6px; position: relative; z-index: 1; }
.est-label { font-size: 10px; color: var(--text-muted); }
.est-value { font-size: 20px; font-weight: 900; font-family: "SF Mono", "JetBrains Mono", monospace; transition: color 0.2s; }
.gap-sep { font-size: 14px; color: #334155; }
.gap-value { font-size: 20px; font-weight: 900; font-family: "SF Mono", "JetBrains Mono", monospace; transition: color 0.2s, text-shadow 0.2s; }
/* 滚动中：琥珀色 */
.est-value.rolling, .gap-value.rolling { color: #e8b974; text-shadow: 0 0 8px rgba(232, 185, 116, 0.5); }
/* 定格正分差：温和绿色 */
.est-value.positive-final, .gap-value.positive-final { color: #6ee7b7; text-shadow: 0 0 8px rgba(110, 231, 183, 0.4); }
/* 定格负分差：柔和红色 */
.est-value.negative-final, .gap-value.negative-final { color: #fda4af; text-shadow: 0 0 6px rgba(253, 164, 175, 0.35); }

.card-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; position: relative; z-index: 1; }
.card-tag { padding: 2px 7px; border-radius: 5px; font-size: 10px; font-weight: 600; }
.tag-blue    { background: rgba(232, 185, 116, 0.1); color: #f4d8a8; }
.tag-amber   { background: rgba(251, 191, 36, 0.1); color: #fde68a; }
.tag-purple  { background: rgba(167, 139, 250, 0.1); color: #c4b5fd; }
.tag-cyan    { background: rgba(6, 182, 212, 0.1); color: #67e8f9; }
.tag-rose    { background: rgba(244, 63, 94, 0.1); color: #fda4af; }
.tag-emerald { background: rgba(16, 185, 129, 0.1); color: #6ee7b7; }
.card-footer { padding-top: 8px; border-top: 1px solid rgba(255, 255, 255, 0.04); position: relative; z-index: 1; }
.card-reason { font-size: 10px; color: var(--text-muted); display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── 数据可信度标签 ── */
.trust-tag { font-family: "SF Mono", monospace; }
.trust-t1 { background: rgba(52, 211, 153, 0.12); color: #6ee7b7; border: 1px solid rgba(52, 211, 153, 0.2); }
.trust-t2 { background: rgba(232, 185, 116, 0.12); color: #f4d8a8; border: 1px solid rgba(232, 185, 116, 0.2); }
.trust-t3 { background: rgba(251, 191, 36, 0.12); color: #fde68a; border: 1px solid rgba(251, 191, 36, 0.2); }
.trust-t4 { background: rgba(148, 163, 184, 0.12); color: var(--text-secondary); border: 1px solid rgba(148, 163, 184, 0.2); }

/* ── 联网动态信息 ── */
.live-info-section { margin-top: 6px; padding: 8px 10px; background: rgba(232, 185, 116, 0.04); border: 1px solid rgba(232, 185, 116, 0.1); border-radius: 7px; position: relative; z-index: 1; }
.live-row { display: flex; gap: 6px; font-size: 10px; line-height: 1.5; margin-bottom: 3px; }
.live-row:last-child { margin-bottom: 0; }
.live-label { color: #f4d8a8; font-weight: 600; flex-shrink: 0; min-width: 56px; }
.live-text { color: var(--text-secondary); word-break: break-all; }
.live-sources { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; padding-top: 4px; border-top: 1px solid rgba(232, 185, 116, 0.08); }
.source-label { font-size: 9px; color: #475569; }
.source-link { font-size: 9px; color: #e8b974; text-decoration: none; }
.source-link:hover { text-decoration: underline; }

/* ── 数据可信度说明 ── */
.trust-desc { font-size: 9px; color: #475569; margin-top: 4px; padding-left: 8px; border-left: 2px solid rgba(148, 163, 184, 0.15); line-height: 1.4; position: relative; z-index: 1; }

@media (max-width: 768px) {
  .est-value, .gap-value { font-size: 17px; }
}
</style>
