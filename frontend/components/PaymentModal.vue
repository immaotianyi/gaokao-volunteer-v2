<!-- components/PaymentModal.vue -->
<script setup lang="ts">
import { ref, reactive, watch } from "vue"
import { useProfileStore } from "../stores/profile"
import { useLeakageStore } from "../stores/leakage"
import { generateQrcode, pollPaymentStatus, unlockCustomLeakage } from "../api/index"
import { toast } from "../utils/toast"
import Icon from "./Icon.vue"

const props = defineProps<{ show: boolean; agreed: boolean }>()
const emit = defineEmits<{ close: []; unlocked: [] }>()

const profileStore = useProfileStore()
const leakageStore = useLeakageStore()

const qrcodeUrl = ref("")
const currentOrderId = ref("")
const payStatus = ref<"" | "PENDING" | "SUCCESS">("")
const payPollCount = ref(0)
const isMockMode = ref(false)
const payMode = ref<"real" | "mock">("mock")   // 后端返回的订单模式
const displayAmount = ref("9.90")               // 展示金额（元）
let pollTimer: number = 0

// ── 视差：保留极轻微的跟随，避免过度晃动 ──
const tiltX = ref(0)
const tiltY = ref(0)
const isTilting = ref(false)

function onPanelMouseMove(e: MouseEvent) {
  const el = e.currentTarget as HTMLElement
  const rect = el.getBoundingClientRect()
  const x = (e.clientX - rect.left) / rect.width  - 0.5
  const y = (e.clientY - rect.top)  / rect.height - 0.5
  tiltX.value = -y * 3   // 减弱：原 12 → 3
  tiltY.value =  x * 3
  isTilting.value = true
}

function onPanelMouseLeave() {
  tiltX.value = 0
  tiltY.value = 0
  isTilting.value = false
}

async function startPayment() {
  payStatus.value = ""
  payPollCount.value = 0
  isMockMode.value = false
  try {
    const res = await generateQrcode(profileStore.profile.user_id || "anonymous")
    currentOrderId.value = res.order_id
    qrcodeUrl.value = res.qrcode_url
    payMode.value = res.mode as "real" | "mock"
    // 金额：分 → 元
    if (res.amount) {
      displayAmount.value = (res.amount / 100).toFixed(2)
    }
    startPolling()
  } catch {
    isMockMode.value = true
    payMode.value = "mock"
    qrcodeUrl.value = ""
    toast("支付服务暂不可用，已切换为演示模式")
  }
}

function startPolling() {
  pollTimer = window.setInterval(async () => {
    if (!currentOrderId.value) return
    try {
      const status = await pollPaymentStatus(currentOrderId.value)
      payPollCount.value = status.poll_count
      if (status.status === "SUCCESS") { onSuccess() }
      else { payStatus.value = "PENDING" }
    } catch { /* silent */ }
  }, 2000)
}

function mockPay() { onSuccess() }

async function onSuccess() {
  payStatus.value = "SUCCESS"
  clearInterval(pollTimer); pollTimer = 0
  // 定制化场景：调 unlock API 获取完整报告；普通场景：直接标记解锁
  const isCustomScene = !!leakageStore.customResult && !leakageStore.customUnlocked
  if (isCustomScene && leakageStore.customRequestId) {
    try {
      const res = await unlockCustomLeakage(
        leakageStore.customRequestId,
        profileStore.profile.user_id || "anonymous",
      )
      leakageStore.setCustomUnlocked(res)
      toast.success("完整定制化报告已解锁")
    } catch (e: any) {
      const msg = typeof e?.message === "string" ? e.message : "解锁失败"
      toast.error(msg)
      payStatus.value = ""
      return
    }
  } else {
    leakageStore.unlocked = true
  }
  setTimeout(() => {
    cleanup()
    emit("unlocked")
  }, 1500)
}

function cleanup() {
  payStatus.value = ""
  currentOrderId.value = ""
  qrcodeUrl.value = ""
  isMockMode.value = false
}

function handleClose() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = 0 }
  cleanup()
  emit("close")
}

watch(() => props.show, (v) => { if (v) startPayment() })
</script>

<template>
  <div v-if="show" class="holo-overlay" @click="handleClose">
    <div class="holo-bg" />
    <!-- 外层：float 浮动动画；内层：3D tilt 交互 -->
    <div class="holo-float-wrap animate-float-slow" @click.stop>
      <div
        class="holo-panel"
        :class="{ 'tilt-active': isTilting }"
        :style="{ transform: `perspective(1000px) rotateX(${tiltX}deg) rotateY(${tiltY}deg)` }"
        @mousemove="onPanelMouseMove"
        @mouseleave="onPanelMouseLeave"
      >
      <div class="drag-bar" />
      <div class="holo-close" @click="handleClose">✕</div>
      <div class="holo-lock-ring"><Icon name="lock" :size="22" /></div>
      <span class="holo-title">查看完整清单</span>
      <span class="holo-desc">还有更多院校的捡漏机会，每一所都经过算法筛选</span>

      <div v-if="payStatus === 'SUCCESS'" class="holo-success">
        <div class="holo-success-icon">✓</div>
        <span class="holo-success-text">已解锁，祝你好运</span>
      </div>

      <div v-if="payStatus !== 'SUCCESS'" class="holo-qr-wrap">
        <div class="holo-qr-base">
          <div class="holo-qr-glow" />
          <div class="holo-qr-white">
            <img v-if="qrcodeUrl && !isMockMode" :src="qrcodeUrl" class="holo-qr-img" alt="QR" />
            <div
              v-else
              class="holo-qr-placeholder"
              :class="{ mock: isMockMode }"
              @click="isMockMode ? mockPay() : undefined"
            >
              <span v-if="!isMockMode">生成中...</span>
              <span v-else class="mock-text"><Icon name="coin" :size="20" /> 演示模式<br/>点击模拟支付</span>
            </div>
            <div class="holo-scan-line" />
          </div>
        </div>
        <span class="holo-price">¥ {{ displayAmount }}</span>
        <span class="holo-price-hint">{{ isMockMode ? '演示模式 · 点击二维码模拟支付' : (payMode === 'real' ? '微信扫码支付' : '微信扫码支付（演示）') }}</span>
        <div v-if="payStatus === 'PENDING'" class="holo-polling">
          <div class="holo-spinner" /><span>等待支付确认</span>
        </div>
      </div>
      <div class="holo-footer"><span>支付后自动解锁完整清单</span></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.holo-overlay { position: fixed; inset: 0; z-index: 200; display: flex; align-items: flex-end; justify-content: center; pointer-events: auto; }
@media (min-width: 640px) { .holo-overlay { align-items: center; padding: 16px; } }
.holo-bg { position: absolute; inset: 0; background: rgba(2, 6, 23, 0.45); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); }
/* 外层包装：只负责 float 动画，不参与 tilt */
.holo-float-wrap { width: 100%; max-width: 270px; }
.holo-float-wrap.animate-float-slow { animation: float 6s ease-in-out infinite; }
/* 内层面板：负责 3D tilt 交互 + 渐变过渡回弹 */
.holo-panel { position: relative; width: 100%; background: rgba(15, 23, 42, 0.82); backdrop-filter: blur(48px); -webkit-backdrop-filter: blur(48px); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 24px 24px 0 0; padding: 28px 24px 24px; display: flex; flex-direction: column; align-items: center; box-shadow: 0 0 100px rgba(232, 185, 116, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.1); transition: transform 0.6s cubic-bezier(0.34, 1.56, 0.64, 1); will-change: transform; }
.holo-panel.tilt-active { transition: transform 0.1s linear; }
@media (min-width: 640px) { .holo-panel { border-radius: 24px; } }
.holo-float-wrap .animate-float-slow { animation: float 6s ease-in-out infinite; }
.drag-bar { width: 32px; height: 3px; background: rgba(255, 255, 255, 0.12); border-radius: 2px; margin-bottom: 20px; }
@media (min-width: 640px) { .drag-bar { display: none; } }
.holo-close { position: absolute; top: 16px; right: 16px; width: 28px; height: 28px; border-radius: 50%; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--text-secondary); font-size: 14px; }
.holo-close:active { background: rgba(255, 255, 255, 0.12); }
.holo-lock-ring { width: 50px; height: 50px; border-radius: 50%; background: linear-gradient(135deg, rgba(232, 185, 116, 0.2), rgba(212, 154, 78, 0.15)); border: 1px solid rgba(232, 185, 116, 0.25); display: flex; align-items: center; justify-content: center; box-shadow: 0 0 48px rgba(232, 185, 116, 0.2); margin-bottom: 14px; font-size: 24px; }
.holo-title { font-size: 18px; font-weight: 700; color: var(--text-primary); letter-spacing: 2px; margin-bottom: 4px; }
.holo-desc { font-size: 13px; color: var(--text-secondary); font-weight: 300; margin-bottom: 20px; }
.holo-success { padding: 20px 0; text-align: center; }
.holo-success-icon { width: 32px; height: 32px; line-height: 32px; color: #86efac; margin: 0 auto; font-size: 22px; font-weight: 700; }
.holo-success-text { font-size: 14px; color: #86efac; display: block; margin-top: 8px; }
.holo-qr-wrap { display: flex; flex-direction: column; align-items: center; margin-bottom: 12px; }
.holo-qr-base { position: relative; padding: 3px; border-radius: 20px; background: linear-gradient(to bottom, rgba(255, 255, 255, 0.08), transparent); border: 1px solid rgba(255, 255, 255, 0.08); margin-bottom: 14px; }
.holo-qr-glow { position: absolute; inset: 0; border-radius: 20px; background: radial-gradient(circle at center, rgba(232, 185, 116, 0.15), transparent 70%); animation: pulse-glow 4s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
.holo-qr-white { position: relative; background: #ffffff; border-radius: 18px; padding: 8px; overflow: hidden; }
.holo-qr-img { width: 140px; height: 140px; display: block; border-radius: 12px; }
.holo-qr-placeholder { width: 140px; height: 140px; display: flex; align-items: center; justify-content: center; color: var(--text-secondary); font-size: 13px; }
.holo-qr-placeholder.mock { cursor: pointer; background: var(--text-primary); border-radius: 12px; }
.mock-text { font-size: 12px; color: #020617; text-align: center; line-height: 1.5; }
.holo-scan-line { position: absolute; top: 0; left: 6px; right: 6px; height: 2px; background: linear-gradient(to right, transparent, #e8b974, transparent); box-shadow: 0 0 20px rgba(232, 185, 116, 0.8); animation: qr-scan 2.5s cubic-bezier(0.4, 0, 0.2, 1) infinite; }
.holo-price { font-size: 26px; font-weight: 900; color: var(--text-primary); letter-spacing: -1px; }
.holo-price-hint { font-size: 12px; color: var(--text-muted); margin-top: 3px; }
.holo-polling { display: flex; align-items: center; gap: 8px; padding: 10px 16px; background: rgba(232, 185, 116, 0.08); border: 1px solid rgba(232, 185, 116, 0.18); border-radius: 24px; font-size: 13px; color: #7dd3fc; margin-top: 14px; }
.holo-spinner { width: 16px; height: 16px; border-radius: 50%; border: 3px solid rgba(232, 185, 116, 0.2); border-top-color: #e8b974; animation: spin 0.8s linear infinite; }
.holo-footer { margin-top: 16px; padding-top: 12px; border-top: 1px solid rgba(255, 255, 255, 0.04); width: 100%; }
.holo-footer span { font-size: 10px; color: #475569; }

/* Fallback keyframes (also in global CSS) */
@keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-3px); } }
@keyframes pulse-glow { 0%, 100% { opacity: 0.5; } 50% { opacity: 0.95; } }
@keyframes qr-scan { 0% { transform: translateY(-4px); opacity: 0; } 10% { opacity: 1; } 90% { opacity: 1; } 100% { transform: translateY(150px); opacity: 0; } }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
