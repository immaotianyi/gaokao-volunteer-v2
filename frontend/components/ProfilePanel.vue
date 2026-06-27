<!-- components/ProfilePanel.vue -->
<script setup lang="ts">
import { computed } from "vue"
import { useProfileStore } from "../stores/profile"
import { ELECTIVE_FIELD_MAP } from "../constants/data"
import Icon from "./Icon.vue"
const profileStore = useProfileStore()

const props = defineProps<{ scanning?: boolean }>()

const visionOptions = [
  { key: "正常", label: "无异常" },
  { key: "色弱", label: "色弱" },
  { key: "色盲", label: "色盲" },
] as const

function selectVision(v: string) {
  profileStore.updateProfile({ vision_status: v })
}

const emit = defineEmits<{ openEditor: [] }>()

// 档案完成度
const completion = computed(() => profileStore.completionPercent)

// 选科成绩列表（根据选科组合动态生成）
const electiveScores = computed(() => {
  const subjects = profileStore.profile.subjects?.split(",").filter(Boolean) || []
  return subjects.map(s => ELECTIVE_FIELD_MAP[s]).filter(Boolean)
})
</script>

<template>
  <div class="profile-panel glass-card" :class="{ scanning, incomplete: !profileStore.isProfileComplete }">
    <!-- 扫描时的"正在读取"脉冲提示 -->
    <Transition name="extract-hint">
      <div v-if="scanning" class="extract-hint">
        <span class="extract-dot" />
        <span class="extract-text">正在读取你的档案</span>
      </div>
    </Transition>

    <!-- 未完善提示 -->
    <Transition name="extract-hint">
      <div v-if="!profileStore.isProfileComplete" class="incomplete-hint" @click="emit('openEditor')">
        <Icon name="alert" :size="11" />
        <span>档案未完善 · 点击填写</span>
      </div>
    </Transition>

    <div class="panel-label">考生档案</div>
    <div class="score-hero">
      <span class="score-value" :class="{ glitching: scanning }">{{ profileStore.profile.score || '---' }}</span>
      <span class="score-unit">分</span>
    </div>

    <!-- 完成度进度条 -->
    <div class="completion-bar" v-if="!profileStore.isProfileComplete">
      <div class="completion-track">
        <div class="completion-fill" :style="{ width: completion + '%' }" />
      </div>
      <span class="completion-text">{{ completion }}% 已完成</span>
    </div>

    <div class="profile-rows">
      <div class="profile-row">
        <span class="row-label">省份</span>
        <span class="row-value" :class="{ glitching: scanning }">{{ profileStore.profile.province || '未设置' }}</span>
      </div>
      <div class="profile-row">
        <span class="row-label">科类</span>
        <span class="row-value" :class="{ glitching: scanning }">{{ profileStore.profile.subjects ? (profileStore.profile.subjects.startsWith('物理') ? '物理类' : '历史类') : '未设置' }}</span>
      </div>
      <div class="profile-row">
        <span class="row-label">英语</span>
        <span class="row-value" :class="{ glitching: scanning }">{{ profileStore.profile.english_score ?? '--' }}</span>
      </div>
      <div class="profile-row">
        <span class="row-label">数学</span>
        <span class="row-value" :class="{ glitching: scanning }">{{ profileStore.profile.math_score ?? '--' }}</span>
      </div>
      <div class="profile-row">
        <span class="row-label">位次</span>
        <span class="row-value" :class="{ glitching: scanning }">{{ profileStore.profile.rank?.toLocaleString() ?? '--' }}</span>
      </div>
    </div>

    <!-- 选科成绩展示 -->
    <div v-if="electiveScores.length" class="elective-section">
      <span class="elective-label">选科成绩</span>
      <div class="elective-grid">
        <div v-for="subj in electiveScores" :key="subj.key" class="elective-item">
          <span class="elective-name">{{ subj.label }}</span>
          <span class="elective-score">{{ (profileStore.profile as Record<string, number | null | undefined>)[subj.key] ?? '--' }}</span>
        </div>
      </div>
    </div>

    <div class="vision-bar" :class="{ 'vision-warning': scanning && profileStore.profile.vision_status && profileStore.profile.vision_status !== '正常' }">
      <span class="row-label">体检视力</span>
      <div class="vision-options">
        <div v-for="opt in visionOptions" :key="opt.key" class="vision-chip" :class="{
          active: profileStore.profile.vision_status === opt.key,
          'chip-alert': scanning && opt.key !== '正常' && profileStore.profile.vision_status === opt.key
        }" @click="selectVision(opt.key)">
          {{ opt.label }}
        </div>
      </div>
      <Transition name="vision-warn">
        <div v-if="scanning && profileStore.profile.vision_status && profileStore.profile.vision_status !== '正常'" class="vision-warn-text">
          <Icon name="alert" :size="11" /> {{ profileStore.profile.vision_status }} → 将重点核查
        </div>
      </Transition>
    </div>

    <div class="profile-edit-hint" @click="emit('openEditor')">
      <span>点击编辑档案</span>
    </div>
  </div>
</template>

<style scoped>
.profile-panel { width: 160px; flex-shrink: 0; padding: 20px 16px; position: sticky; top: 70px; align-self: flex-start; }
.profile-panel.incomplete { border-color: rgba(251, 191, 36, 0.2); }
.panel-label { font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 2px; margin-bottom: 12px; }
.score-hero { margin-bottom: 16px; }
.score-value { font-size: 48px; font-weight: 200; color: var(--text-primary); line-height: 1; letter-spacing: -3px; }
.score-unit { font-size: 16px; color: var(--text-muted); margin-left: 4px; }
.profile-rows { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.profile-row { display: flex; justify-content: space-between; align-items: center; padding-bottom: 6px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); }
.row-label { font-size: 13px; color: var(--text-muted); }
.row-value { font-size: 13px; color: var(--text-primary); font-weight: 600; }

/* ── 完成度进度条 ── */
.completion-bar { margin-bottom: 14px; }
.completion-track { height: 4px; background: rgba(255, 255, 255, 0.06); border-radius: 2px; overflow: hidden; }
.completion-fill { height: 100%; background: linear-gradient(90deg, #fbbf24, #e8b974); border-radius: 2px; transition: width 0.5s ease; }
.completion-text { font-size: 9px; color: var(--text-muted); margin-top: 4px; display: block; }

/* ── 选科成绩 ── */
.elective-section { margin-bottom: 12px; padding-top: 10px; border-top: 1px solid rgba(255, 255, 255, 0.04); }
.elective-label { font-size: 10px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; display: block; margin-bottom: 8px; }
.elective-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.elective-item { display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 6px 4px; background: rgba(255, 255, 255, 0.03); border-radius: 6px; }
.elective-name { font-size: 10px; color: var(--text-muted); }
.elective-score { font-size: 14px; font-weight: 700; color: var(--text-primary); }

.vision-bar { margin-bottom: 12px; }
.vision-options { display: flex; gap: 4px; margin-top: 6px; }
.vision-chip { flex: 1; padding: 7px 0; text-align: center; border-radius: 8px; font-size: 12px; font-weight: 600; background: rgba(255, 255, 255, 0.04); color: var(--text-secondary); transition: all 0.2s; cursor: pointer; }
.vision-chip:hover { background: rgba(232, 185, 116, 0.08); color: #f4d8a8; }
.vision-chip.active { background: rgba(232, 185, 116, 0.15); color: #e8b974; border: 1px solid rgba(232, 185, 116, 0.3); }
.profile-edit-hint { font-size: 10px; color: #475569; text-align: center; cursor: pointer; }
.profile-edit-hint:hover { color: #e8b974; }

/* ── 未完善提示 ── */
.incomplete-hint { display: flex; align-items: center; gap: 4px; padding: 5px 10px; margin-bottom: 10px; background: rgba(251, 191, 36, 0.1); border-radius: 8px; border: 1px solid rgba(251, 191, 36, 0.2); font-size: 10px; color: #fde68a; font-weight: 600; cursor: pointer; transition: all 0.2s; }
.incomplete-hint:hover { background: rgba(251, 191, 36, 0.15); }

/* 扫描时分数/位次数字柔和烛光呼吸 */
.glitching { animation: candle-glow 1.6s ease-in-out 2; }
@keyframes candle-glow {
  0%, 100% { color: var(--text-primary); text-shadow: none; }
  50% { color: #e8b974; text-shadow: 0 0 12px rgba(232, 185, 116, 0.45); }
}

/* ── 扫描时的"正在提取档案特征"脉冲提示 ── */
.profile-panel.scanning { border-color: rgba(232, 185, 116, 0.3); box-shadow: 0 0 24px rgba(232, 185, 116, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.1); }
.extract-hint { display: flex; align-items: center; gap: 6px; padding: 5px 10px; margin-bottom: 10px; background: rgba(232, 185, 116, 0.1); border-radius: 8px; border: 1px solid rgba(232, 185, 116, 0.2); }
.extract-dot { width: 6px; height: 6px; border-radius: 50%; background: #e8b974; box-shadow: 0 0 8px rgba(232, 185, 116, 0.8); animation: extract-pulse 0.8s ease-in-out infinite; }
@keyframes extract-pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(1.4); } }
.extract-text { font-size: 10px; color: #f4d8a8; font-weight: 600; letter-spacing: 1px; }
.extract-hint-enter-active, .extract-hint-leave-active { transition: all 0.3s ease; }
.extract-hint-enter-from, .extract-hint-leave-to { opacity: 0; transform: translateY(-6px); }

/* ── 视力警告高亮 ── */
.vision-bar.vision-warning { padding: 8px; margin: 4px -8px 12px; background: rgba(251, 113, 133, 0.06); border-radius: 8px; border: 1px solid rgba(251, 113, 133, 0.15); }
.vision-chip.chip-alert { background: rgba(251, 113, 133, 0.2) !important; color: #fda4af !important; border: 1px solid rgba(251, 113, 133, 0.4) !important; animation: chip-alert-blink 0.6s ease-in-out infinite; }
@keyframes chip-alert-blink { 0%, 100% { box-shadow: 0 0 0 rgba(251, 113, 133, 0); } 50% { box-shadow: 0 0 12px rgba(251, 113, 133, 0.4); } }
.vision-warn-text { font-size: 10px; color: #fda4af; margin-top: 6px; font-weight: 600; letter-spacing: 0.5px; }
.vision-warn-enter-active, .vision-warn-leave-active { transition: all 0.3s ease; }
.vision-warn-enter-from, .vision-warn-leave-to { opacity: 0; transform: translateY(4px); }

/* ── 移动端：档案面板横向布局 ── */
@media (max-width: 768px) {
  .profile-panel { width: 100%; position: relative; top: 0; padding: 14px 16px; }
  .panel-label { margin-bottom: 8px; }
  .score-hero { margin-bottom: 10px; display: flex; align-items: baseline; gap: 4px; }
  .score-value { font-size: 36px; }
  .profile-rows { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 8px; }
  .profile-row { flex-direction: column; gap: 2px; padding-bottom: 4px; border-bottom: none; }
  .row-label { font-size: 10px; }
  .row-value { font-size: 12px; }
  .elective-grid { grid-template-columns: repeat(3, 1fr); gap: 4px; }
  .vision-options { gap: 3px; }
  .vision-chip { font-size: 11px; padding: 5px 0; }
  .profile-edit-hint { margin-top: 4px; }
  .extract-hint, .incomplete-hint { margin-bottom: 6px; }
}
</style>
