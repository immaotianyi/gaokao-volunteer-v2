<!--
  pages/index/index.vue — 主工作台容器
  子组件: DataUniverse / ProfilePanel / RiskScanner / RadarBoard / PaymentModal
-->
<script setup lang="ts">
import { ref, onMounted } from "vue"
import { useRouter } from "vue-router"
import { useProfileStore } from "../../stores/profile"
import DataUniverse from "../../components/DataUniverse.vue"
import ProfilePanel from "../../components/ProfilePanel.vue"
import RiskScanner from "../../components/RiskScanner.vue"
import RadarBoard from "../../components/RadarBoard.vue"
import AdvisorChat from "../../components/AdvisorChat.vue"
import PaymentModal from "../../components/PaymentModal.vue"
import ProfileEditor from "../../components/ProfileEditor.vue"
import ThemeToggle from "../../components/ThemeToggle.vue"
import Icon from "../../components/Icon.vue"

const router = useRouter()
const profileStore = useProfileStore()
const activeTab = ref<"risk" | "radar" | "advisor">("risk")
const showPayModal = ref(false)
const payAgreed = ref(false)
const showProfileEditor = ref(false)
const dataUniverseRef = ref<InstanceType<typeof DataUniverse> | null>(null)
const isScanning = ref(false)

// ── 免责声明门槛：必须点击「我已阅读并理解」才能使用 ──
// 初始为 true 避免首屏闪烁，onMounted 后根据 localStorage 校正
const disclaimerAccepted = ref(true)
onMounted(() => {
  disclaimerAccepted.value = localStorage.getItem("gaokao_disclaimer_v1") === "1"
})
function acceptDisclaimer() {
  localStorage.setItem("gaokao_disclaimer_v1", "1")
  disclaimerAccepted.value = true
}

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
    prepare: "awake",
    read_profile: "charge",
    parse_list: "high",
    search_charter: "focus",
    infer: "surge",
    report: "release",
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
        <span class="logo-text">志愿守护</span>
      </div>
      <div class="segment-nav" role="tablist" aria-label="功能切换">
        <button type="button" role="tab" class="segment-btn" :class="{ active: activeTab === 'risk' }" :aria-selected="activeTab === 'risk'" @click="activeTab = 'risk'"><Icon name="shield" :size="13" /><span>探雷器</span></button>
        <button type="button" role="tab" class="segment-btn" :class="{ active: activeTab === 'radar' }" :aria-selected="activeTab === 'radar'" @click="activeTab = 'radar'"><Icon name="radar" :size="13" /><span>捡漏雷达</span></button>
        <button type="button" role="tab" class="segment-btn" :class="{ active: activeTab === 'advisor' }" :aria-selected="activeTab === 'advisor'" @click="activeTab = 'advisor'"><Icon name="bolt" :size="13" /><span>AI 顾问</span></button>
      </div>
      <div class="header-right">
        <ThemeToggle />
        <button type="button" class="profile-nav-btn" aria-label="进入我的档案页" @click="router.push('/pages/profile/profile')"><Icon name="user" :size="13" /><span>我的</span></button>
        <div class="header-status"><div class="status-dot" /><span class="status-text">服务在线</span></div>
      </div>
    </div>

    <!-- MAIN -->
    <div class="app-main">
      <ProfilePanel :scanning="isScanning" @open-editor="showProfileEditor = true" />
      <div class="content-area">
        <RiskScanner v-show="activeTab === 'risk'" @scan-start="handleScanStart" @scan-end="handleScanEnd" @scan-phase="handleScanPhase" />
        <RadarBoard v-show="activeTab === 'radar'" @open-payment="showPayModal = true" />
        <AdvisorChat v-show="activeTab === 'advisor'" />
      </div>
    </div>

    <!-- PROFILE EDITOR DRAWER -->
    <ProfileEditor v-if="showProfileEditor" @close="showProfileEditor = false" />

    <!-- 档案未完善引导弹窗 -->
    <Transition name="guide-fade">
      <div v-if="showProfileGuide" class="guide-overlay" @click.self="showProfileGuide = false">
        <div class="guide-panel">
          <div class="guide-icon"><Icon name="scroll" :size="32" /></div>
          <h3 class="guide-title">先填好你的档案</h3>
          <p class="guide-desc">开始核对之前，先把省份、分数和选科填好。<br/>我们逐所核对章程，都靠这些信息。数据只存在你的浏览器里。</p>
          <div class="guide-stats">
            <div class="guide-stat">
              <span class="guide-stat-value">{{ profileStore.completionPercent }}%</span>
              <span class="guide-stat-label">已完成</span>
            </div>
          </div>
          <div class="guide-actions">
            <button type="button" class="guide-btn-secondary" @click="showProfileGuide = false">稍后再说</button>
            <button type="button" class="guide-btn-primary" @click="showProfileGuide = false; showProfileEditor = true">
              <Icon name="arrowRight" :size="14" />
              <span>立即填写</span>
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- PAYMENT MODAL -->
    <PaymentModal :show="showPayModal" :agreed="payAgreed" @close="showPayModal = false" @unlocked="showPayModal = false" />

    <!-- 免责声明门槛：必须点击「我已阅读并理解」才能使用 -->
    <Transition name="guide-fade">
      <div v-if="!disclaimerAccepted" class="disclaimer-overlay">
        <div class="disclaimer-panel">
          <div class="disclaimer-icon"><Icon name="scroll" :size="28" /></div>
          <h3 class="disclaimer-title">先听我说一句</h3>
          <div class="disclaimer-body">
            <p>这个工具会帮你逐所核对招生章程，但它<span class="em">不是万能的</span>。</p>
            <p>它是基于 AI 去理解章程条款，难免会有理解偏差。最终的志愿，请你务必再对照一次官方的《填报指南》和学校官网的最新章程。</p>
            <p>你的档案只存在浏览器里，不会上传给第三方。本工具不构成填报建议，因使用产生的任何后果由你自行承担。</p>
          </div>
          <div class="disclaimer-actions">
            <button type="button" class="disclaimer-btn" @click="acceptDisclaimer">
              <Icon name="check" :size="14" />
              <span>我已阅读并理解</span>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.app-shell { min-height: 100vh; background: var(--ink-900); color: var(--text-primary); font-family: var(--font-sans); position: relative; overflow-x: hidden; }

.bg-ambient { position: fixed; inset: 0; z-index: 1; pointer-events: none; overflow: hidden; }
.orb { position: absolute; border-radius: 50%; filter: blur(120px); opacity: 0.12; }
.orb-1 { width: 600px; height: 600px; background: radial-gradient(circle, #e8b974, transparent); top: -200px; left: -100px; }
.orb-2 { width: 400px; height: 400px; background: radial-gradient(circle, #d49a4e, transparent); bottom: -100px; right: -50px; }
.orb-3 { width: 300px; height: 300px; background: radial-gradient(circle, #facc15, transparent); top: 40%; left: 50%; }

.app-header { position: sticky; top: 0; z-index: 100; display: flex; align-items: center; justify-content: space-between; padding: 12px 20px; background: rgba(2, 6, 23, 0.85); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border-bottom: 1px solid rgba(255, 255, 255, 0.06); }
.header-left { display: flex; align-items: center; gap: 8px; }
.logo-mark { width: 28px; height: 28px; background: linear-gradient(135deg, #e8b974, #d49a4e); border-radius: 8px; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 24px rgba(232, 185, 116, 0.3); color: #fff; }
.logo-text { font-size: 18px; font-weight: 900; color: var(--text-primary); letter-spacing: -0.5px; }
.logo-accent { color: #e8b974; }
.segment-nav { display: flex; gap: 2px; background: rgba(255, 255, 255, 0.06); border-radius: 50px; padding: 2px; border: 1px solid rgba(255, 255, 255, 0.04); box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.2); }
button.segment-btn { display: flex; align-items: center; gap: 5px; padding: 8px 18px; border-radius: 50px; font-size: 14px; font-weight: 500; color: var(--text-secondary); cursor: pointer; transition: all 0.3s cubic-bezier(0.32, 0.72, 0, 1); appearance: none; border: none; font-family: inherit; }
button.segment-btn.active { background: rgba(255, 255, 255, 0.12); color: var(--text-primary); box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.1); }
.header-right { display: flex; align-items: center; gap: 10px; }
button.profile-nav-btn { display: flex; align-items: center; gap: 4px; padding: 5px 14px; border-radius: 10px; font-size: 12px; font-weight: 600; background: rgba(255, 255, 255, 0.06); color: var(--text-secondary); border: 1px solid rgba(255, 255, 255, 0.06); cursor: pointer; transition: all 0.2s; appearance: none; font-family: inherit; }
.profile-nav-btn:active { background: rgba(255, 255, 255, 0.12); color: var(--text-primary); }
.header-status { display: flex; align-items: center; gap: 6px; }
.status-dot { width: 6px; height: 6px; background: #22c55e; border-radius: 50%; box-shadow: 0 0 8px rgba(34, 197, 94, 0.5); }
.status-text { font-size: 11px; color: var(--text-muted); font-weight: 500; }

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
.guide-icon { width: 64px; height: 64px; margin: 0 auto 20px; border-radius: 18px; background: linear-gradient(135deg, rgba(232, 185, 116, 0.15), rgba(212, 154, 78, 0.15)); border: 1px solid rgba(232, 185, 116, 0.2); display: flex; align-items: center; justify-content: center; color: #e8b974; }
.guide-title { font-size: 22px; font-weight: 800; color: var(--text-primary); margin: 0 0 12px; letter-spacing: -0.5px; }
.guide-desc { font-size: 13px; color: var(--text-secondary); line-height: 1.8; margin: 0 0 20px; font-weight: 300; }
.guide-stats { margin-bottom: 24px; }
.guide-stat { display: inline-flex; flex-direction: column; align-items: center; gap: 4px; padding: 12px 28px; background: rgba(255, 255, 255, 0.04); border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.06); }
.guide-stat-value { font-size: 28px; font-weight: 900; color: #e8b974; font-family: "SF Mono", monospace; }
.guide-stat-label { font-size: 11px; color: var(--text-muted); }
.guide-actions { display: flex; gap: 10px; }
button.guide-btn-secondary { flex: 1; padding: 12px 0; border-radius: 10px; font-size: 14px; font-weight: 600; background: rgba(255, 255, 255, 0.06); color: var(--text-secondary); cursor: pointer; transition: all 0.2s; appearance: none; border: none; font-family: inherit; }
button.guide-btn-secondary:hover { background: rgba(255, 255, 255, 0.1); color: var(--text-primary); }
button.guide-btn-primary { flex: 1.5; display: flex; align-items: center; justify-content: center; gap: 6px; padding: 12px 0; border-radius: 10px; font-size: 14px; font-weight: 700; background: linear-gradient(135deg, #e8b974, #d49a4e); color: #fff; cursor: pointer; box-shadow: 0 8px 24px rgba(232, 185, 116, 0.3); transition: all 0.2s; appearance: none; border: none; font-family: inherit; }
button.guide-btn-primary:hover { box-shadow: 0 12px 32px rgba(232, 185, 116, 0.45); transform: translateY(-1px); }
.guide-fade-enter-active, .guide-fade-leave-active { transition: all 0.3s ease; }
.guide-fade-enter-from, .guide-fade-leave-to { opacity: 0; }
.guide-fade-enter-active .guide-panel, .guide-fade-leave-active .guide-panel { transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); }
.guide-fade-enter-from .guide-panel, .guide-fade-leave-to .guide-panel { transform: scale(0.92) translateY(20px); }

/* ── 免责声明门槛 ── */
.disclaimer-overlay { position: fixed; inset: 0; z-index: 300; display: flex; align-items: center; justify-content: center; background: rgba(2, 6, 23, 0.82); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); padding: 24px; }
.disclaimer-panel { width: 100%; max-width: 460px; background: rgba(15, 23, 42, 0.92); border: 1px solid rgba(232, 185, 116, 0.2); border-radius: 20px; padding: 32px 28px; text-align: center; box-shadow: 0 24px 56px rgba(0, 0, 0, 0.5); }
.disclaimer-icon { width: 56px; height: 56px; margin: 0 auto 16px; border-radius: 16px; background: linear-gradient(135deg, rgba(232, 185, 116, 0.15), rgba(212, 154, 78, 0.12)); border: 1px solid rgba(232, 185, 116, 0.25); display: flex; align-items: center; justify-content: center; color: #e8b974; }
.disclaimer-title { font-size: 20px; font-weight: 800; color: var(--text-primary); margin: 0 0 16px; letter-spacing: -0.3px; }
.disclaimer-body { text-align: left; margin-bottom: 24px; }
.disclaimer-body p { font-size: 13px; color: var(--text-secondary); line-height: 1.9; margin: 0 0 12px; font-weight: 300; }
.disclaimer-body p:last-child { margin-bottom: 0; }
.disclaimer-body .em { color: #f4d8a8; font-weight: 600; }
.disclaimer-actions { display: flex; justify-content: center; }
button.disclaimer-btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 12px 32px; border-radius: 12px; font-size: 14px; font-weight: 700; background: linear-gradient(135deg, #e8b974, #d49a4e); color: #fff; cursor: pointer; box-shadow: 0 8px 24px rgba(232, 185, 116, 0.35); transition: all 0.2s; appearance: none; border: none; font-family: inherit; }
.disclaimer-btn:hover { box-shadow: 0 12px 32px rgba(232, 185, 116, 0.5); transform: translateY(-1px); }
.disclaimer-btn:active { transform: translateY(0); }
</style>
