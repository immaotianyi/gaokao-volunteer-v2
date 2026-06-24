<!--
  pages/index/index.vue — 主工作台容器
  子组件: DataUniverse / ProfilePanel / RiskScanner / RadarBoard / PaymentModal
-->
<script setup lang="ts">
import { ref } from "vue"
import { useRouter } from "vue-router"
import { useProfileStore } from "../../stores/profile"
import DataUniverse from "../../components/DataUniverse.vue"
import ProfilePanel from "../../components/ProfilePanel.vue"
import RiskScanner from "../../components/RiskScanner.vue"
import RadarBoard from "../../components/RadarBoard.vue"
import AdvisorChat from "../../components/AdvisorChat.vue"
import PaymentModal from "../../components/PaymentModal.vue"
import ProfileEditor from "../../components/ProfileEditor.vue"
import Icon from "../../components/Icon.vue"

const router = useRouter()
const profileStore = useProfileStore()
const activeTab = ref<"risk" | "radar" | "advisor">("risk")
const showPayModal = ref(false)
const payAgreed = ref(false)
const showProfileEditor = ref(false)
const dataUniverseRef = ref<InstanceType<typeof DataUniverse> | null>(null)
const isScanning = ref(false)

// ── 档案完善校验 ──
// 用户必须先填写基础档案（省份+分数+选科）才能使用核心功能
const showProfileGuide = ref(false)

function handleScanStart() {
  // RiskScanner 在档案未完善时也会 emit scanStart 来触发引导
  if (!profileStore.isProfileComplete) {
    showProfileGuide.value = true
    return
  }
  isScanning.value = true
  dataUniverseRef.value?.setComputeSpeed("awake")
}

/** 探雷阶段变更 → 联动粒子速度 */
function handleScanPhase(phase: string) {
  const phaseMap: Record<string, "awake" | "charge" | "high" | "surge" | "focus" | "release" | "low"> = {
    awaken: "awake",
    lock: "charge",
    extract: "high",
    search: "focus",
    infer: "surge",
    reveal: "release",
    done: "low",
    error: "low",
  }
  const level = phaseMap[phase] ?? "low"
  dataUniverseRef.value?.setComputeSpeed(level)
}

/** 探雷结束 → 粒子恢复低速漂浮 + 停止闪烁 */
function handleScanEnd() {
  isScanning.value = false
  dataUniverseRef.value?.setComputeSpeed("low")
}
</script>

<template>
  <div class="app-shell">
    <!-- Three.js 粒子宇宙背景（z-index:0 最底层） -->
    <DataUniverse ref="dataUniverseRef" />

    <div class="bg-ambient">
      <div class="orb orb-1" />
      <div class="orb orb-2" />
      <div class="orb orb-3" />
    </div>

    <!-- HEADER -->
    <div class="app-header">
      <div class="header-left">
        <div class="logo-mark"><Icon name="shield" :size="14" /></div>
        <span class="logo-text">GAOKAO<span class="logo-accent">·</span>SNIPER</span>
      </div>
      <div class="segment-nav">
        <div class="segment-btn" :class="{ active: activeTab === 'risk' }" @click="activeTab = 'risk'"><Icon name="shield" :size="13" /><span>探雷器</span></div>
        <div class="segment-btn" :class="{ active: activeTab === 'radar' }" @click="activeTab = 'radar'"><Icon name="radar" :size="13" /><span>捡漏雷达</span></div>
        <div class="segment-btn" :class="{ active: activeTab === 'advisor' }" @click="activeTab = 'advisor'"><Icon name="bolt" :size="13" /><span>AI 顾问</span></div>
      </div>
      <div class="header-right">
        <div class="profile-nav-btn" @click="router.push('/pages/profile/profile')"><Icon name="user" :size="13" /><span>我的</span></div>
        <div class="header-status"><div class="status-dot" /><span class="status-text">API 直连</span></div>
      </div>
    </div>

    <!-- MAIN -->
    <div class="app-main">
      <ProfilePanel :scanning="isScanning" @open-editor="showProfileEditor = true" />
      <div class="content-area">
        <RiskScanner v-if="activeTab === 'risk'" @scan-start="handleScanStart" @scan-end="handleScanEnd" @scan-phase="handleScanPhase" />
        <RadarBoard v-if="activeTab === 'radar'" @open-payment="showPayModal = true" />
        <AdvisorChat v-if="activeTab === 'advisor'" />
      </div>
    </div>

    <!-- PROFILE EDITOR DRAWER -->
    <ProfileEditor v-if="showProfileEditor" @close="showProfileEditor = false" />

    <!-- 档案未完善引导弹窗 -->
    <Transition name="guide-fade">
      <div v-if="showProfileGuide" class="guide-overlay" @click.self="showProfileGuide = false">
        <div class="guide-panel">
          <div class="guide-icon"><Icon name="user" :size="32" /></div>
          <h3 class="guide-title">完善考生档案</h3>
          <p class="guide-desc">使用志愿探雷器前，请先填写你的省份、高考分数和选科组合。<br/>这是 AI 精准审查的基础，数据仅存储在你的浏览器本地。</p>
          <div class="guide-stats">
            <div class="guide-stat">
              <span class="guide-stat-value">{{ profileStore.completionPercent }}%</span>
              <span class="guide-stat-label">已完成</span>
            </div>
          </div>
          <div class="guide-actions">
            <div class="guide-btn-secondary" @click="showProfileGuide = false">稍后再说</div>
            <div class="guide-btn-primary" @click="showProfileGuide = false; showProfileEditor = true">
              <Icon name="arrowRight" :size="14" />
              <span>立即填写</span>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- PAYMENT MODAL -->
    <PaymentModal :show="showPayModal" :agreed="payAgreed" @close="showPayModal = false" @unlocked="showPayModal = false" />
  </div>
</template>

<style scoped>
.app-shell { min-height: 100vh; background: #020617; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, "Inter", "SF Pro Display", sans-serif; position: relative; overflow-x: hidden; }

.bg-ambient { position: fixed; inset: 0; z-index: 1; pointer-events: none; overflow: hidden; }
.orb { position: absolute; border-radius: 50%; filter: blur(120px); opacity: 0.12; }
.orb-1 { width: 600px; height: 600px; background: radial-gradient(circle, #38bdf8, transparent); top: -200px; left: -100px; }
.orb-2 { width: 400px; height: 400px; background: radial-gradient(circle, #818cf8, transparent); bottom: -100px; right: -50px; }
.orb-3 { width: 300px; height: 300px; background: radial-gradient(circle, #facc15, transparent); top: 40%; left: 50%; }

.app-header { position: sticky; top: 0; z-index: 100; display: flex; align-items: center; justify-content: space-between; padding: 12px 20px; background: rgba(2, 6, 23, 0.85); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border-bottom: 1px solid rgba(255, 255, 255, 0.06); }
.header-left { display: flex; align-items: center; gap: 8px; }
.logo-mark { width: 28px; height: 28px; background: linear-gradient(135deg, #38bdf8, #818cf8); border-radius: 8px; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 24px rgba(56, 189, 248, 0.3); color: #fff; }
.logo-text { font-size: 18px; font-weight: 900; color: #f1f5f9; letter-spacing: -0.5px; }
.logo-accent { color: #38bdf8; }
.segment-nav { display: flex; gap: 2px; background: rgba(255, 255, 255, 0.06); border-radius: 50px; padding: 2px; border: 1px solid rgba(255, 255, 255, 0.04); box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.2); }
.segment-btn { display: flex; align-items: center; gap: 5px; padding: 8px 18px; border-radius: 50px; font-size: 14px; font-weight: 500; color: #94a3b8; cursor: pointer; transition: all 0.3s cubic-bezier(0.32, 0.72, 0, 1); }
.segment-btn.active { background: rgba(255, 255, 255, 0.12); color: #f1f5f9; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.1); }
.header-right { display: flex; align-items: center; gap: 10px; }
.profile-nav-btn { display: flex; align-items: center; gap: 4px; padding: 5px 14px; border-radius: 10px; font-size: 12px; font-weight: 600; background: rgba(255, 255, 255, 0.06); color: #94a3b8; border: 1px solid rgba(255, 255, 255, 0.06); cursor: pointer; transition: all 0.2s; }
.profile-nav-btn:active { background: rgba(255, 255, 255, 0.12); color: #e2e8f0; }
.header-status { display: flex; align-items: center; gap: 6px; }
.status-dot { width: 6px; height: 6px; background: #22c55e; border-radius: 50%; box-shadow: 0 0 8px rgba(34, 197, 94, 0.5); }
.status-text { font-size: 11px; color: #64748b; font-weight: 500; }

.app-main { position: relative; z-index: 2; display: flex; gap: 16px; padding: 16px 20px; max-width: 1440px; margin: 0 auto; }
.content-area { flex: 1; min-width: 0; }

@media (max-width: 768px) {
  .app-main { flex-direction: column; padding: 12px; }
  .app-header { padding: 10px 12px; flex-wrap: wrap; gap: 8px; }
  .segment-nav { order: 3; width: 100%; justify-content: center; }
  .segment-btn { padding: 6px 12px; font-size: 12px; gap: 4px; }
  .segment-btn span { font-size: 12px; }
  .header-right { gap: 6px; }
  .header-status .status-text { display: none; }
  .logo-text { font-size: 16px; }
  .content-area { min-height: 60vh; }
}

/* ── 档案引导弹窗 ── */
.guide-overlay { position: fixed; inset: 0; z-index: 200; display: flex; align-items: center; justify-content: center; background: rgba(2, 6, 23, 0.7); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); padding: 24px; }
.guide-panel { width: 100%; max-width: 400px; background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 20px; padding: 36px 28px; text-align: center; box-shadow: 0 24px 48px rgba(0, 0, 0, 0.4); }
.guide-icon { width: 64px; height: 64px; margin: 0 auto 20px; border-radius: 18px; background: linear-gradient(135deg, rgba(56, 189, 248, 0.15), rgba(129, 140, 248, 0.15)); border: 1px solid rgba(56, 189, 248, 0.2); display: flex; align-items: center; justify-content: center; color: #38bdf8; }
.guide-title { font-size: 22px; font-weight: 800; color: #f1f5f9; margin: 0 0 12px; letter-spacing: -0.5px; }
.guide-desc { font-size: 13px; color: #94a3b8; line-height: 1.8; margin: 0 0 20px; font-weight: 300; }
.guide-stats { margin-bottom: 24px; }
.guide-stat { display: inline-flex; flex-direction: column; align-items: center; gap: 4px; padding: 12px 28px; background: rgba(255, 255, 255, 0.04); border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.06); }
.guide-stat-value { font-size: 28px; font-weight: 900; color: #38bdf8; font-family: "SF Mono", monospace; }
.guide-stat-label { font-size: 11px; color: #64748b; }
.guide-actions { display: flex; gap: 10px; }
.guide-btn-secondary { flex: 1; padding: 12px 0; border-radius: 10px; font-size: 14px; font-weight: 600; background: rgba(255, 255, 255, 0.06); color: #94a3b8; cursor: pointer; transition: all 0.2s; }
.guide-btn-secondary:hover { background: rgba(255, 255, 255, 0.1); color: #e2e8f0; }
.guide-btn-primary { flex: 1.5; display: flex; align-items: center; justify-content: center; gap: 6px; padding: 12px 0; border-radius: 10px; font-size: 14px; font-weight: 700; background: linear-gradient(135deg, #38bdf8, #818cf8); color: #fff; cursor: pointer; box-shadow: 0 8px 24px rgba(56, 189, 248, 0.3); transition: all 0.2s; }
.guide-btn-primary:hover { box-shadow: 0 12px 32px rgba(56, 189, 248, 0.45); transform: translateY(-1px); }
.guide-fade-enter-active, .guide-fade-leave-active { transition: all 0.3s ease; }
.guide-fade-enter-from, .guide-fade-leave-to { opacity: 0; }
.guide-fade-enter-active .guide-panel, .guide-fade-leave-active .guide-panel { transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); }
.guide-fade-enter-from .guide-panel, .guide-fade-leave-to .guide-panel { transform: scale(0.92) translateY(20px); }
</style>
