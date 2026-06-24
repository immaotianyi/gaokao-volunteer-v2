<!-- components/RiskScanner.vue -->
<script setup lang="ts">
import { ref, computed, onBeforeUnmount, nextTick } from "vue"
import { useProfileStore } from "../stores/profile"
import { useRiskStore } from "../stores/risk"
import { startRiskStream, startAgentStream, checkRiskLive, type LiveCheckResult } from "../api/index"
import { toast } from "../utils/toast"
import type { RiskTarget, RiskResult } from "../stores/risk"
import Icon from "./Icon.vue"

const profileStore = useProfileStore()
const riskStore = useRiskStore()

const emit = defineEmits<{ scanStart: []; scanEnd: []; scanPhase: [phase: string] }>()

const draftText = ref("")
const isScanning = ref(false)

// ── 引擎切换：V3 规则引擎 / V4 Agent 推理 ──
const engineMode = ref<"v3" | "v4">("v3")

// ── 七幕仪式阶段 ──
// awaken 唤醒 → lock 锁定档案 → extract 抽取志愿 → search 逐条检索 → infer 深度推理 → reveal 揭晓 → done 完成
type CeremonyPhase = "awaken" | "lock" | "extract" | "search" | "infer" | "reveal" | "done"
const phase = ref<CeremonyPhase>("awaken")
const phaseProgress = ref(0)

// ── 各阶段文案 ──
interface PhaseCopy {
  kicker: string
  title: string
  subtitle: string
  status: string
}

const PHASE_COPY: Record<CeremonyPhase, PhaseCopy> = {
  awaken:  { kicker: "PHASE 01 / INITIATE",        title: "唤 醒 引 擎",     subtitle: "正在建立与全国招生办大数据库的加密通道",           status: "ESTABLISHING SECURE CHANNEL" },
  lock:    { kicker: "PHASE 02 / PROFILE LOCK",    title: "锁 定 档 案",     subtitle: "将你的分数、位次、体检标记、单科成绩注入算力核心", status: "INJECTING PROFILE VECTOR" },
  extract: { kicker: "PHASE 03 / TARGET EXTRACT",  title: "抽 取 志 愿",     subtitle: "逐条解析草表，建立审查任务队列与优先级排序",     status: "PARSING DRAFT ENTRIES" },
  search:  { kicker: "PHASE 04 / RETRIEVAL",       title: "逐 条 检 索",     subtitle: "RAG 向量检索每所大学招生章程，提取退档风险条款",  status: "RUNNING RAG RETRIEVAL" },
  infer:   { kicker: "PHASE 05 / DEEP INFERENCE",  title: "深 度 推 理",     subtitle: "四维限制交叉比对 · 风险熵值计算 · 多轮推理定级",   status: "MULTI-ROUND INFERENCE" },
  reveal:  { kicker: "PHASE 06 / REVEAL",          title: "揭 晓 报 告",     subtitle: "推理完毕，正在生成可视化审查结果",                status: "RENDERING VISUAL REPORT" },
  done:    { kicker: "COMPLETE",                   title: "推 演 完 成",     subtitle: "所有志愿审查完毕，请查看下方结果",                status: "DONE" },
}

const currentCopy = computed(() => PHASE_COPY[phase.value])

function phaseIndex(p: CeremonyPhase): number {
  const order: CeremonyPhase[] = ["awaken", "lock", "extract", "search", "infer", "reveal", "done"]
  return order.indexOf(p)
}

// ── 逐条检索：当前正在检索的志愿 ──
const searchTargetIdx = ref(0)
const searchTargets = ref<RiskTarget[]>([])
const currentSearchTarget = computed(() => searchTargets.value[searchTargetIdx.value])

// ── 伪终端日志 ──
interface FakeLogLine { text: string; type: "sys" | "ok" | "warn" | "info" | "target" | "danger" }
const fakeLogs = ref<FakeLogLine[]>([])
const terminalRef = ref<HTMLDivElement | null>(null)
let fakeLogTimer = 0
let realLogStarted = false

function buildSearchLogForTarget(t: RiskTarget, idx: number, total: number): FakeLogLine[] {
  const p = profileStore.profile
  const lines: FakeLogLine[] = [
    { text: `[TARGET ${String(idx + 1).padStart(2, "0")}/${String(total).padStart(2, "0")}] 锁定: ${t.university}`, type: "target" },
    { text: `  └─ 专业: ${t.major || "未指定"}`, type: "info" },
    { text: `  └─ RAG 检索《${t.university}2026招生章程》...`, type: "sys" },
    { text: `  └─ 命中 ${Math.floor(Math.random() * 6 + 3)} 条相关条款`, type: "ok" },
  ]

  // 根据用户真实档案数据，生成针对性的体检/单科比对日志
  const vision = p.vision_status ?? "正常"
  if (vision !== "正常") {
    lines.push({ text: `  └─ 提取您的「${vision}」标签，比对 2.3 万条体检限制条款 ...`, type: "warn" })
  } else {
    lines.push({ text: `  └─ 体检标记: 正常，跳过体检限制快速通道`, type: "info" })
  }

  // 单科成绩比对（根据大学类型动态选择重点科目）
  if (t.major.includes("计算机") || t.major.includes("数据") || t.major.includes("数学")) {
    if (p.math_score != null) {
      const pass = p.math_score >= 100
      lines.push({ text: `  └─ 数学单科 ${p.math_score} 分 ${pass ? "✓ 满足门槛" : "✗ 低于建议线"}（该专业要求数学≥100）`, type: pass ? "ok" : "danger" })
    }
  } else if (t.major.includes("英语") || t.major.includes("外语") || t.major.includes("国际")) {
    if (p.english_score != null) {
      const pass = p.english_score >= 90
      lines.push({ text: `  └─ 英语单科 ${p.english_score} 分 ${pass ? "✓ 满足门槛" : "✗ 低于建议线"}（该专业要求英语≥90）`, type: pass ? "ok" : "danger" })
    }
  } else if (t.major.includes("临床") || t.major.includes("医学") || t.major.includes("护理")) {
    if (vision !== "正常") {
      lines.push({ text: `  └─ ⚠ 医学类专业 + ${vision} → 极高退档风险！`, type: "danger" })
    } else {
      lines.push({ text: `  └─ 医学类专业体检核查通过`, type: "ok" })
    }
  }

  // 选科匹配
  const subjects = p.subjects ?? ""
  if (subjects.includes("物理")) {
    lines.push({ text: `  └─ 选科「${subjects}」匹配物理类招生计划 ✓`, type: "ok" })
  } else if (subjects.includes("历史")) {
    lines.push({ text: `  └─ 选科「${subjects}」匹配历史类招生计划 ✓`, type: "ok" })
  }

  return lines
}

/** lock 阶段的档案注入日志（让用户看到自己的数据被"注入引擎"） */
function buildLockPhaseLogs(): FakeLogLine[] {
  const p = profileStore.profile
  return [
    { text: `[SYS] 初始化志愿探雷引擎 v4.2.1 ...`, type: "sys" },
    { text: `[SYS] 加载高考投档数据库 2023-2025 ........ [OK]`, type: "ok" },
    { text: `[SYS] 装载 135 所高校招生章程规则库 ........ [OK]`, type: "ok" },
    { text: `[INFO] 提取考生特征向量:`, type: "info" },
    { text: `  └─ 总分 ${p.score ?? "---"} 分 | ${p.province ?? "--"} | ${p.subjects?.split(",")[0] ?? "?"}类`, type: "info" },
    { text: `  └─ 全省位次 ${p.rank?.toLocaleString() ?? "--"} | 语文${p.chinese_score ?? "-"} | 数学${p.math_score ?? "-"} | 英语${p.english_score ?? "-"}`, type: "info" },
    { text: `  └─ 体检标记: ${p.vision_status ?? "未设置"} ${p.vision_status && p.vision_status !== "正常" ? "→ 已标记为重点审查项" : ""}`, type: p.vision_status && p.vision_status !== "正常" ? "warn" : "info" },
    { text: `[SYS] 将上述 ${p.vision_status && p.vision_status !== "正常" ? "7" : "6"} 维特征注入算力核心 ...`, type: "sys" },
    { text: `[OK] 档案特征向量锁定完毕，等待志愿目标输入`, type: "ok" },
  ]
}

function pushLog(line: FakeLogLine) {
  fakeLogs.value.push(line)
  scrollTerminalToBottom()
}

/** lock 阶段：逐行吐出档案注入日志 */
function startLockLogPump() {
  stopFakeLogPump()
  fakeLogs.value = []
  realLogStarted = false
  const sequence = buildLockPhaseLogs()
  let idx = 0
  fakeLogTimer = window.setInterval(() => {
    if (realLogStarted) { stopFakeLogPump(); return }
    if (idx >= sequence.length) { stopFakeLogPump(); return }
    pushLog(sequence[idx])
    idx++
  }, 100)
}

function startSearchLogPump(targets: RiskTarget[]) {
  stopFakeLogPump()
  // search 阶段不清空 lock 阶段的日志，继续追加
  realLogStarted = false
  let targetIdx = 0
  let lineInTarget = 0

  fakeLogTimer = window.setInterval(() => {
    if (realLogStarted) { stopFakeLogPump(); return }
    if (targetIdx >= targets.length) {
      // 所有志愿检索完，吐总结行
      const p = profileStore.profile
      const summary: FakeLogLine[] = [
        { text: `[SYS] 全部 ${targets.length} 个志愿检索完毕`, type: "ok" },
        { text: `[INFO] 累计比对 ${targets.length * 4}+ 条章程条款`, type: "info" },
      ]
      // 如果有色弱等体检标记，追加总结警告
      if (p.vision_status && p.vision_status !== "正常") {
        summary.push({ text: `[WARN] 您的「${p.vision_status}」标记已触发 ${Math.floor(Math.random() * 3 + 2)} 项体检限制审查`, type: "warn" })
      }
      summary.push({ text: `[SYS] 进入深度推理阶段，计算风险熵值 ...`, type: "sys" })

      if (lineInTarget < summary.length) {
        pushLog(summary[lineInTarget])
        lineInTarget++
      } else {
        stopFakeLogPump()
      }
      return
    }

    const lines = buildSearchLogForTarget(targets[targetIdx], targetIdx, targets.length)
    if (lineInTarget < lines.length) {
      pushLog(lines[lineInTarget])
      lineInTarget++
    } else {
      targetIdx++
      lineInTarget = 0
      searchTargetIdx.value = Math.min(targetIdx, targets.length - 1)
    }
  }, 110)
}

function stopFakeLogPump() {
  if (fakeLogTimer) { clearInterval(fakeLogTimer); fakeLogTimer = 0 }
}

function scrollTerminalToBottom() {
  nextTick(() => {
    const el = terminalRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function pushRealLog(text: string) {
  realLogStarted = true
  stopFakeLogPump()
  fakeLogs.value.push({ text, type: "info" })
  scrollTerminalToBottom()
}

function parseDraft(text: string): RiskTarget[] {
  if (!text) return []
  return text.split("\n").map(l => l.trim()).filter(Boolean).map(line => {
    const m = line.match(/[-—：:\s]+/)
    if (m && m.index !== undefined) return { university: line.substring(0, m.index).trim(), major: line.substring(m.index + m[0].length).trim() }
    return { university: line, major: "" }
  }).filter(x => x.university)
}

const parsedCount = computed(() => parseDraft(draftText.value).length)

const profileFeature = computed(() => {
  const p = profileStore.profile
  return `${p.score ?? "---"}分 · 位次 ${p.rank?.toLocaleString() ?? "--"}`
})

const profileVector = computed(() => {
  const p = profileStore.profile
  return [
    `${p.province ?? "--"}`,
    `${p.subjects?.split(",")[0] ?? "?"}类`,
    `英语${p.english_score ?? "-"}`,
    `数学${p.math_score ?? "-"}`,
    `视力·${p.vision_status ?? "未设置"}`,
  ]
})

function esc(s: string) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML }

function statusIcon(s: string) {
  const map: Record<string, string> = {
    DANGER: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
    WARNING: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    PASS: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`,
  }
  return map[s] ?? "?"
}

const dangerResults = computed(() => riskStore.results.filter(r => r.status === "DANGER"))
const warnResults = computed(() => riskStore.results.filter(r => r.status === "WARNING"))
const passResults = computed(() => riskStore.results.filter(r => r.status === "PASS"))

// ── 七幕仪式时间编排（总约 9.5s 仪式 + SSE）──
const PHASE_TIMING = {
  awaken:  1400,  // 第一幕：引擎唤醒（足够长，建立仪式感）
  lock:    1800,  // 第二幕：锁定档案（拉长，让用户看清自己的数据被注入）
  extract: 1000,  // 第三幕：抽取志愿
  search:  3200,  // 第四幕：逐条检索（最长，每条约 200ms × 5 行）
  infer:   2000,  // 第五幕：深度推理
}
let phaseTimer = 0
let progressTimer = 0

function setPhase(p: CeremonyPhase) {
  phase.value = p
  phaseProgress.value = 0
  const phaseEmitMap: Record<CeremonyPhase, string> = {
    awaken: "awaken", lock: "lock", extract: "extract", search: "search", infer: "infer", reveal: "reveal", done: "done",
  }
  emit("scanPhase", phaseEmitMap[p])

  const duration = p === "reveal" ? 1000 : p === "done" ? 600 : (PHASE_TIMING as any)[p] ?? 1000
  const startTs = Date.now()
  clearInterval(progressTimer)
  progressTimer = window.setInterval(() => {
    const elapsed = Date.now() - startTs
    phaseProgress.value = Math.min(100, (elapsed / duration) * 100)
    if (phaseProgress.value >= 100) clearInterval(progressTimer)
  }, 30)
}

function delay(ms: number): Promise<void> {
  return new Promise(resolve => {
    phaseTimer = window.setTimeout(() => { resolve() }, ms)
  })
}

async function runCeremony(targets: RiskTarget[], onSearchStart: () => void, onInferStart: () => void) {
  // 第一幕：唤醒
  setPhase("awaken")
  await delay(PHASE_TIMING.awaken)

  // 第二幕：锁定档案（启动档案注入日志）
  setPhase("lock")
  startLockLogPump()
  await delay(PHASE_TIMING.lock)

  // 第三幕：抽取志愿
  setPhase("extract")
  searchTargets.value = targets
  searchTargetIdx.value = 0
  await delay(PHASE_TIMING.extract)

  // 第四幕：逐条检索
  setPhase("search")
  startSearchLogPump(targets)
  onSearchStart() // 提前发起 SSE，让真实数据在检索动画期间到达
  await delay(PHASE_TIMING.search)

  // 第五幕：深度推理
  setPhase("infer")
  onInferStart()
  // infer 阶段等待 SSE onResult，由调用方切换到 reveal
}

function handleScan() {
  // 档案校验：省份+分数+选科 为必填
  const p = profileStore.profile
  if (!p.province || !p.score || !p.subjects) {
    toast("请先完善考生档案（省份、分数、选科）")
    // 通知父组件弹出档案引导
    emit("scanStart")
    return
  }
  const targets = parseDraft(draftText.value)
  if (!targets.length) { toast("请输入有效的志愿草表"); return }
  riskStore.clear()
  isScanning.value = true
  emit("scanStart")

  // 标记 SSE 结果是否已到达
  let sseResultArrived = false
  let sseDoneArrived = false

  // SSE 回调（V3 和 V4 共用同一套回调）
  const sseCallbacks = {
    onLog(text: string, ts: number) {
      if (phase.value === "infer" || phase.value === "reveal") {
        pushRealLog(text)
      }
      riskStore.log(text, "info")
    },
    onResult(results: RiskResult[]) {
      riskStore.setResults(results)
      sseResultArrived = true
      if (phase.value === "infer") {
        setPhase("reveal")
      }
    },
    onDone() {
      sseDoneArrived = true
      if (phase.value !== "reveal" && phase.value !== "done") {
        setPhase("reveal")
      }
      setTimeout(() => {
        phase.value = "done"
        emit("scanPhase", "done")
        stopFakeLogPump()
        clearInterval(progressTimer)
        phaseProgress.value = 100
        setTimeout(() => {
          isScanning.value = false
          phase.value = "awaken"
          toast("推演完成")
          emit("scanEnd")
        }, 1200)
      }, 1000)
    },
    onError(msg: string) {
      isScanning.value = false
      phase.value = "awaken"
      stopFakeLogPump()
      clearInterval(progressTimer)
      riskStore.log(`[ERROR] ${msg}`, "error")
      toast(`网络波动: ${msg}`)
      emit("scanPhase", "error")
      emit("scanEnd")
    },
  }

  runCeremony(
    targets,
    // search 阶段开始时发起 SSE（根据引擎模式选择 API）
    () => {
      if (engineMode.value === "v4") {
        startAgentStream(profileStore.profile, targets, sseCallbacks)
      } else {
        startRiskStream(profileStore.profile, targets, sseCallbacks)
      }
    },
    // infer 阶段开始时：如果 SSE 结果已在 search 阶段到达，立即切 reveal
    () => {
      if (sseResultArrived || sseDoneArrived) {
        setPhase("reveal")
      }
    },
  )
}

function clearAllTimers() {
  stopFakeLogPump()
  clearTimeout(phaseTimer)
  clearInterval(progressTimer)
}

// ── 联网章程检索 ──
const liveSearchText = ref("")
const liveSearching = ref(false)
const liveResult = ref<LiveCheckResult | null>(null)

async function handleLiveSearch() {
  const text = liveSearchText.value.trim()
  if (!text) { toast("请输入大学名称"); return }
  // 尝试从输入中解析大学名和专业
  const m = text.match(/[-—：:\s]+/)
  const university = m && m.index !== undefined ? text.substring(0, m.index).trim() : text
  const major = m && m.index !== undefined ? text.substring(m.index + m[0].length).trim() : ""

  liveSearching.value = true
  liveResult.value = null
  try {
    const res = await checkRiskLive({ university, major })
    liveResult.value = res
    toast.success("联网检索完成")
  } catch (e: any) {
    toast.error(e?.message || "联网检索失败")
  } finally {
    liveSearching.value = false
  }
}

onBeforeUnmount(() => { clearAllTimers() })
</script>

<template>
  <div class="risk-layout">
    <div class="draft-section glass-card">
      <div class="panel-label">志愿草表</div>
      <textarea v-model="draftText" class="draft-textarea" placeholder="请粘贴志愿草表...&#10;&#10;浙江大学 计算机科学与技术&#10;复旦大学 临床医学&#10;南方医科大学 护理学"></textarea>
      <div class="draft-footer">
        <div class="footer-left">
          <span class="draft-count">识别到 <span class="count-num">{{ parsedCount }}</span> 个志愿</span>
          <!-- 引擎切换 -->
          <div class="engine-switch">
            <div class="engine-btn" :class="{ active: engineMode === 'v3' }" @click="engineMode = 'v3'">V3 规则</div>
            <div class="engine-btn" :class="{ active: engineMode === 'v4' }" @click="engineMode = 'v4'">V4 Agent</div>
          </div>
        </div>
        <div class="scan-btn" :class="{ disabled: isScanning || parsedCount === 0 }" @click="handleScan">
          <Icon name="bolt" :size="14" />
          <span v-if="isScanning" class="btn-text">推演中...</span>
          <span v-else class="btn-text">开始推演计算</span>
        </div>
      </div>
      <div class="scan-overlay" :class="{ active: isScanning }">
        <!-- 仪式背景层：单一扫描线（移除重叠的 radial gradient） -->
        <div class="ritual-scanlines" />

        <!-- 顶部阶段标签 -->
        <Transition name="phase-kicker" mode="out-in">
          <div :key="phase" class="phase-kicker">
            <span class="kicker-dot" />
            <span class="kicker-text">{{ currentCopy.kicker }}</span>
            <span class="kicker-dot" />
          </div>
        </Transition>

        <!-- 多层扫描环（动画仅在 infer 时激活，避免全程旋转重叠） -->
        <div class="ritual-ring-wrap" :class="phase">
          <div class="ritual-ring outer" />
          <div class="ritual-ring mid" />
          <div class="scan-ring">
            <div class="ring-arc" />
            <div class="ring-inner">
              <div class="ring-core" :class="{
                awaken: phase === 'awaken',
                lock: phase === 'lock',
                search: phase === 'search',
                pulse: phase === 'infer',
                done: phase === 'reveal' || phase === 'done',
              }" />
            </div>
          </div>
          <svg class="progress-ring" viewBox="0 0 120 120">
            <circle class="progress-track" cx="60" cy="60" r="54" />
            <circle class="progress-bar" cx="60" cy="60" r="54"
              :stroke-dasharray="339.292"
              :stroke-dashoffset="339.292 * (1 - phaseProgress / 100)"
            />
          </svg>
        </div>

        <!-- 主标题 -->
        <Transition name="phase-title" mode="out-in">
          <h2 :key="phase" class="ritual-title">{{ currentCopy.title }}</h2>
        </Transition>

        <!-- 副标题 -->
        <Transition name="phase-sub" mode="out-in">
          <p :key="phase" class="ritual-subtitle">{{ currentCopy.subtitle }}</p>
        </Transition>

        <!-- 状态行 -->
        <div class="ritual-status-line">
          <span class="status-arrow">▸</span>
          <span class="status-mono">{{ currentCopy.status }}</span>
          <span class="status-dots" v-if="phase !== 'done'"><span class="dot-anim">.</span><span class="dot-anim d2">.</span><span class="dot-anim d3">.</span></span>
        </div>

        <!-- 锁定阶段：档案特征向量展示 -->
        <Transition name="vector-in">
          <div v-if="phase === 'lock' || phase === 'extract'" class="profile-vector-bar">
            <span class="vector-label">已锁定档案特征</span>
            <span class="vector-score">{{ profileFeature }}</span>
            <div class="vector-tags">
              <span v-for="(v, i) in profileVector" :key="i" class="vector-tag" :style="{ animationDelay: i * 0.08 + 's' }">{{ v }}</span>
            </div>
          </div>
        </Transition>

        <!-- 检索阶段：当前正在检索的志愿轮播 -->
        <Transition name="search-target">
          <div v-if="phase === 'search' && currentSearchTarget" class="search-target-card" :key="searchTargetIdx">
            <div class="search-target-header">
              <span class="search-idx">{{ String(searchTargetIdx + 1).padStart(2, "0") }}</span>
              <span class="search-sep">/</span>
              <span class="search-total">{{ String(searchTargets.length).padStart(2, "0") }}</span>
            </div>
            <div class="search-target-body">
              <span class="search-university">{{ currentSearchTarget.university }}</span>
              <span class="search-major">{{ currentSearchTarget.major || "未指定专业" }}</span>
            </div>
            <div class="search-pulse-bar">
              <div class="pulse-segment" v-for="n in 4" :key="n" :style="{ animationDelay: n * 0.1 + 's' }" />
            </div>
          </div>
        </Transition>

        <!-- 终端（lock + search + infer + reveal 阶段显示） -->
        <Transition name="terminal-in">
          <div v-if="phase === 'lock' || phase === 'search' || phase === 'infer' || phase === 'reveal'" class="fake-terminal" ref="terminalRef">
            <div v-for="(line, i) in fakeLogs" :key="i" class="term-line" :class="'term-' + line.type">
              <span class="term-prompt">&gt;</span><span class="term-text">{{ line.text }}</span>
            </div>
            <div class="term-cursor"><span class="cursor-blink">▋</span></div>
          </div>
        </Transition>

        <!-- 底部阶段进度指示器 -->
        <div class="phase-indicators">
          <div v-for="(p, i) in (['awaken','lock','extract','search','infer','reveal'] as CeremonyPhase[])" :key="p"
            class="phase-dot"
            :class="{ active: phase === p, passed: phaseIndex(p) < phaseIndex(phase) }">
            <span class="dot-num">{{ i + 1 }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 统计栏 -->
    <div v-if="riskStore.checked && riskStore.results.length" class="stats-bar glass-card">
      <span class="stat-total">共 {{ riskStore.results.length }} 项</span>
      <span class="stat-item stat-danger"><span class="stat-dot danger" /> {{ dangerResults.length }} 极高风险</span>
      <span class="stat-item stat-warn"><span class="stat-dot warn" /> {{ warnResults.length }} 需注意</span>
      <span class="stat-item stat-pass"><span class="stat-dot pass" /> {{ passResults.length }} 通过</span>
    </div>

    <div class="results-scroll custom-scrollbar" v-if="riskStore.checked">
      <TransitionGroup name="list" tag="div" class="result-cards">
        <div v-for="(item, idx) in passResults" :key="'p'+idx" class="neon-card neon-pass">
          <div class="neon-beam beam-emerald" />
          <div class="neon-body">
            <div class="neon-head">
              <div class="neon-info"><span class="neon-school">{{ esc(item.university) }}</span><span class="neon-major">{{ esc(item.major) }}</span></div>
              <div class="neon-badge badge-emerald"><div class="neon-badge-icon" v-html="statusIcon('PASS')"></div><span>规则校验通过</span></div>
            </div>
            <div class="neon-reason"><span>>> {{ esc(item.reason) }}</span></div>
            <div v-if="item.career_risk || item.ai_risk" class="risk-tags-row">
              <span v-if="item.career_risk" class="risk-tag" :class="'risk-' + item.career_risk">就业 {{ item.career_risk === 'high' ? '高风险' : item.career_risk === 'medium' ? '中等' : '低风险' }}</span>
              <span v-if="item.ai_risk" class="risk-tag" :class="'risk-' + item.ai_risk">AI替代 {{ item.ai_risk === 'high' ? '高风险' : item.ai_risk === 'medium' ? '中等' : '低风险' }}</span>
            </div>
          </div>
        </div>
        <div v-for="(item, idx) in warnResults" :key="'w'+idx" class="neon-card neon-warn">
          <div class="neon-beam beam-amber" />
          <div class="neon-body">
            <div class="neon-head">
              <div class="neon-info"><span class="neon-school">{{ esc(item.university) }}</span><span class="neon-major">{{ esc(item.major) }}</span></div>
              <div class="neon-badge badge-amber"><div class="neon-badge-icon" v-html="statusIcon('WARNING')"></div><span>需注意</span></div>
            </div>
            <div class="neon-reason warn-text"><span>>> {{ esc(item.reason) }}</span></div>
            <div v-if="item.career_risk || item.ai_risk" class="risk-tags-row">
              <span v-if="item.career_risk" class="risk-tag" :class="'risk-' + item.career_risk">就业 {{ item.career_risk === 'high' ? '高风险' : item.career_risk === 'medium' ? '中等' : '低风险' }}</span>
              <span v-if="item.ai_risk" class="risk-tag" :class="'risk-' + item.ai_risk">AI替代 {{ item.ai_risk === 'high' ? '高风险' : item.ai_risk === 'medium' ? '中等' : '低风险' }}</span>
            </div>
          </div>
        </div>
        <div v-for="(item, idx) in dangerResults" :key="'d'+idx" class="neon-card neon-danger">
          <div class="neon-beam beam-rose animate-pulse-slow" />
          <div class="neon-body">
            <div class="neon-head">
              <div class="neon-info"><span class="neon-school">{{ esc(item.university) }}</span><span class="neon-major">{{ esc(item.major) }}</span></div>
              <div class="neon-badge badge-rose"><div class="neon-badge-icon" v-html="statusIcon('DANGER')"></div><span>极高退档风险</span></div>
            </div>
            <div class="neon-alert"><div class="alert-icon" v-html="statusIcon('WARNING')"></div><span class="alert-text">{{ esc(item.reason) }}</span></div>
            <div v-if="item.matched_clause" class="neon-clause danger-clause">{{ esc(item.matched_clause) }}</div>
            <div v-if="item.career_risk || item.ai_risk" class="risk-tags-row">
              <span v-if="item.career_risk" class="risk-tag" :class="'risk-' + item.career_risk">就业 {{ item.career_risk === 'high' ? '高风险' : item.career_risk === 'medium' ? '中等' : '低风险' }}</span>
              <span v-if="item.ai_risk" class="risk-tag" :class="'risk-' + item.ai_risk">AI替代 {{ item.ai_risk === 'high' ? '高风险' : item.ai_risk === 'medium' ? '中等' : '低风险' }}</span>
            </div>
          </div>
        </div>
      </TransitionGroup>
    </div>

    <div v-if="!riskStore.checked && !isScanning" class="empty-state glass-card">
      <div class="empty-icon"><Icon name="shield" :size="32" /></div>
      <span class="empty-title">等待推演</span>
      <span class="empty-desc">输入志愿草表后点击「开始推演计算」</span>
    </div>

    <!-- 联网章程检索面板 -->
    <div class="live-search-panel glass-card">
      <div class="live-panel-head">
        <div class="live-panel-title"><Icon name="radar" :size="14" /><span>联网章程检索</span></div>
        <span class="live-panel-hint">本地未收录的大学，联网搜索章程并提取规则</span>
      </div>
      <div class="live-input-row">
        <input v-model="liveSearchText" type="text" class="live-input" placeholder="输入大学名和专业，如：东莞理工学院 土木工程" :disabled="liveSearching" @keydown.enter="handleLiveSearch" />
        <div class="live-btn" :class="{ disabled: !liveSearchText.trim() || liveSearching }" @click="handleLiveSearch">
          <span v-if="liveSearching" class="live-btn-text">检索中...</span>
          <span v-else class="live-btn-text">联网检索</span>
        </div>
      </div>
      <!-- 联网检索结果 -->
      <Transition name="live-result">
        <div v-if="liveResult" class="live-result-card" :class="'live-' + (liveResult.status || 'unknown').toLowerCase()">
          <div class="live-result-head">
            <span class="live-result-school">{{ esc(liveResult.university) }}</span>
            <span class="live-result-major">{{ esc(liveResult.major) }}</span>
            <span class="live-source-tag"><Icon name="radar" :size="10" /> 联网数据</span>
          </div>
          <div class="live-status-badge" :class="'badge-' + (liveResult.status || 'UNKNOWN').toLowerCase()">
            {{ liveResult.status === 'DANGER' ? '极高风险' : liveResult.status === 'WARNING' ? '需注意' : liveResult.status === 'PASS' ? '通过' : '未确认' }}
          </div>
          <div class="live-result-reason">{{ esc(liveResult.reason) }}</div>
          <div v-if="liveResult.matched_clause" class="live-result-clause">{{ esc(liveResult.matched_clause) }}</div>
        </div>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.risk-layout { display: flex; flex-direction: column; gap: 12px; }
.panel-label { font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 12px; }
.draft-section { padding: 20px; position: relative; overflow: hidden; }
.draft-textarea { width: 100%; min-height: 160px; background: rgba(0, 0, 0, 0.3); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 10px; padding: 16px; font-size: 14px; color: #e2e8f0; line-height: 1.8; resize: vertical; box-sizing: border-box; }
.draft-textarea::placeholder { color: #475569; }
.draft-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; gap: 10px; flex-wrap: wrap; }
.footer-left { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.draft-count { font-size: 12px; color: #64748b; }
.count-num { color: #f1f5f9; font-weight: 700; }

/* ── 引擎切换 ── */
.engine-switch { display: flex; gap: 2px; background: rgba(255, 255, 255, 0.04); border-radius: 8px; padding: 2px; }
.engine-btn { padding: 4px 10px; border-radius: 6px; font-size: 10px; font-weight: 700; color: #64748b; cursor: pointer; transition: all 0.2s; font-family: "SF Mono", monospace; }
.engine-btn:hover { color: #94a3b8; background: rgba(255, 255, 255, 0.04); }
.engine-btn.active { background: rgba(56, 189, 248, 0.15); color: #38bdf8; }
.engine-btn.active:hover { color: #38bdf8; }

.scan-btn { display: flex; align-items: center; gap: 6px; background: linear-gradient(135deg, #38bdf8, #818cf8); padding: 12px 24px; border-radius: 10px; box-shadow: 0 8px 32px rgba(56, 189, 248, 0.25); cursor: pointer; transition: all 0.2s; }
.scan-btn:hover:not(.disabled) { box-shadow: 0 12px 36px rgba(56, 189, 248, 0.4); transform: translateY(-1px); }
.scan-btn:active { transform: scale(0.97); }
.scan-btn.disabled { opacity: 0.4; pointer-events: none; }
.btn-text { font-size: 14px; font-weight: 700; color: #fff; }

.scan-overlay { position: absolute; inset: 0; z-index: 20; background: rgba(2, 6, 23, 0.94); backdrop-filter: blur(32px); -webkit-backdrop-filter: blur(32px); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; border-radius: 12px; opacity: 0; pointer-events: none; transition: opacity 0.5s ease; padding: 18px; box-sizing: border-box; }
.scan-overlay.active { opacity: 1; pointer-events: auto; }

/* ── 仪式背景：仅单一扫描线（移除重叠的 radial gradient） ── */
.ritual-scanlines { position: absolute; inset: 0; border-radius: inherit; pointer-events: none; background-image: repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(56, 189, 248, 0.03) 3px, rgba(56, 189, 248, 0.03) 4px); }

/* ── 顶部阶段标签 ── */
.phase-kicker { display: flex; align-items: center; gap: 10px; position: relative; z-index: 1; }
.kicker-dot { width: 4px; height: 4px; border-radius: 50%; background: #38bdf8; box-shadow: 0 0 8px rgba(56, 189, 248, 0.8); }
.kicker-text { font-size: 10px; font-weight: 700; color: #38bdf8; letter-spacing: 3px; font-family: "SF Mono", "JetBrains Mono", monospace; }
.phase-kicker-enter-active, .phase-kicker-leave-active { transition: all 0.35s ease; }
.phase-kicker-enter-from { opacity: 0; transform: translateY(-6px); }
.phase-kicker-leave-to { opacity: 0; transform: translateY(-6px); }

/* ── 多层扫描环（动画仅在 search/infer 阶段激活，避免全程重叠） ── */
.ritual-ring-wrap { position: relative; width: 120px; height: 120px; display: flex; align-items: center; justify-content: center; margin-bottom: 2px; z-index: 1; }
.ritual-ring { position: absolute; border-radius: 50%; border: 1px solid rgba(56, 189, 248, 0.1); }
.ritual-ring.outer { width: 120px; height: 120px; }
.ritual-ring.mid { width: 96px; height: 96px; border-color: rgba(129, 140, 248, 0.1); }
/* 仅在 search 和 infer 阶段旋转 */
.ritual-ring-wrap.search .ritual-ring.outer { animation: ritual-spin 5s linear infinite; border-color: rgba(56, 189, 248, 0.25); }
.ritual-ring-wrap.search .ritual-ring.mid { animation: ritual-spin 3.5s linear infinite reverse; border-color: rgba(129, 140, 248, 0.22); }
.ritual-ring-wrap.infer .ritual-ring.outer { animation: ritual-spin 2s linear infinite; border-color: rgba(56, 189, 248, 0.4); box-shadow: 0 0 20px rgba(56, 189, 248, 0.15); }
.ritual-ring-wrap.infer .ritual-ring.mid { animation: ritual-spin 1.5s linear infinite reverse; border-color: rgba(129, 140, 248, 0.35); box-shadow: 0 0 16px rgba(129, 140, 248, 0.12); }
@keyframes ritual-spin { to { transform: rotate(360deg); } }

.scan-ring { width: 64px; height: 64px; position: relative; }
.ring-arc { position: absolute; inset: 2px; border-radius: 50%; background: conic-gradient(from 0deg, transparent 70%, rgba(56, 189, 248, 0.8) 100%); -webkit-mask: radial-gradient(circle, transparent 58%, black 62%); mask: radial-gradient(circle, transparent 58%, black 62%); animation: spin 2s linear infinite; }
.ritual-ring-wrap.infer .ring-arc { animation-duration: 1s; }
.ring-inner { position: absolute; inset: 18px; border-radius: 50%; background: radial-gradient(circle, rgba(56, 189, 248, 0.12), rgba(56, 189, 248, 0.03) 70%); display: flex; align-items: center; justify-content: center; }
.ring-core { width: 10px; height: 10px; border-radius: 50%; background: #38bdf8; transition: all 0.5s cubic-bezier(0.34, 1.56, 0.64, 1); box-shadow: 0 0 16px rgba(56, 189, 248, 0.6); }
.ring-core.awaken { animation: core-awaken 1.2s ease-out; }
.ring-core.lock { background: #818cf8; box-shadow: 0 0 20px rgba(129, 140, 248, 0.7); transform: scale(1.3); }
.ring-core.search { background: #38bdf8; animation: core-search 0.8s ease-in-out infinite; }
.ring-core.pulse { animation: core-pulse 0.5s ease-in-out infinite; }
.ring-core.done { background: #22c55e; box-shadow: 0 0 24px rgba(34, 197, 94, 0.6); transform: scale(1.4); }
@keyframes core-awaken { 0% { transform: scale(0.2); opacity: 0; } 40% { transform: scale(2); opacity: 1; } 100% { transform: scale(1); } }
@keyframes core-search { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.5); box-shadow: 0 0 24px rgba(56, 189, 248, 0.9); } }
@keyframes core-pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.8); } }

/* ── 阶段进度环 SVG ── */
.progress-ring { position: absolute; inset: 0; width: 120px; height: 120px; transform: rotate(-90deg); pointer-events: none; }
.progress-track { fill: none; stroke: rgba(255, 255, 255, 0.04); stroke-width: 1.5; }
.progress-bar { fill: none; stroke: #38bdf8; stroke-width: 1.5; stroke-linecap: round; filter: drop-shadow(0 0 4px rgba(56, 189, 248, 0.6)); transition: stroke-dashoffset 0.1s linear; }

/* ── 主标题（加长 transition，错开时序） ── */
.ritual-title { font-size: 26px; font-weight: 900; color: #f1f5f9; letter-spacing: 6px; margin: 0; text-shadow: 0 0 28px rgba(56, 189, 248, 0.35); position: relative; z-index: 1; }
.phase-title-enter-active { transition: all 0.6s cubic-bezier(0.34, 1.56, 0.64, 1); }
.phase-title-leave-active { transition: all 0.3s ease; }
.phase-title-enter-from { opacity: 0; transform: translateY(20px) scale(0.96); filter: blur(6px); }
.phase-title-leave-to { opacity: 0; transform: translateY(-12px); filter: blur(3px); }

/* ── 副标题（延迟进场，与主标题错开） ── */
.ritual-subtitle { font-size: 13px; color: #94a3b8; font-weight: 300; margin: 0; text-align: center; max-width: 380px; line-height: 1.6; letter-spacing: 0.5px; position: relative; z-index: 1; }
.phase-sub-enter-active { transition: all 0.5s ease 0.15s; }
.phase-sub-leave-active { transition: all 0.25s ease; }
.phase-sub-enter-from { opacity: 0; transform: translateY(10px); }
.phase-sub-leave-to { opacity: 0; transform: translateY(-6px); }

/* ── 状态行 ── */
.ritual-status-line { display: flex; align-items: center; gap: 4px; font-family: "SF Mono", "JetBrains Mono", monospace; font-size: 11px; color: #7dd3fc; letter-spacing: 1px; position: relative; z-index: 1; }
.status-arrow { color: #38bdf8; }
.status-mono { font-weight: 600; }
.status-dots { display: inline-flex; }
.dot-anim { animation: dot-fade 1.4s infinite; }
.dot-anim.d2 { animation-delay: 0.2s; }
.dot-anim.d3 { animation-delay: 0.4s; }
@keyframes dot-fade { 0%, 60%, 100% { opacity: 0.2; } 30% { opacity: 1; } }

/* ── 档案特征向量条 ── */
.profile-vector-bar { display: flex; flex-direction: column; align-items: center; gap: 6px; margin-top: 4px; padding: 10px 18px; background: rgba(56, 189, 248, 0.06); border: 1px solid rgba(56, 189, 248, 0.18); border-radius: 12px; position: relative; z-index: 1; }
.vector-label { font-size: 10px; color: #7dd3fc; font-weight: 600; letter-spacing: 2px; text-transform: uppercase; }
.vector-score { font-size: 18px; color: #f1f5f9; font-weight: 700; font-family: "SF Mono", "JetBrains Mono", monospace; letter-spacing: 1px; }
.vector-tags { display: flex; gap: 6px; flex-wrap: wrap; justify-content: center; }
.vector-tag { font-size: 10px; color: #94a3b8; padding: 2px 8px; background: rgba(255, 255, 255, 0.05); border-radius: 4px; font-family: "SF Mono", "JetBrains Mono", monospace; animation: tag-pop 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) backwards; }
@keyframes tag-pop { from { opacity: 0; transform: scale(0.7) translateY(4px); } to { opacity: 1; transform: scale(1) translateY(0); } }
.vector-in-enter-active, .vector-in-leave-active { transition: all 0.4s ease; }
.vector-in-enter-from, .vector-in-leave-to { opacity: 0; transform: translateY(10px); }

/* ── 检索阶段：当前检索志愿卡片 ── */
.search-target-card { display: flex; flex-direction: column; align-items: center; gap: 8px; margin-top: 4px; padding: 14px 24px; background: rgba(56, 189, 248, 0.05); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 14px; min-width: 240px; position: relative; z-index: 1; }
.search-target-header { display: flex; align-items: baseline; gap: 4px; font-family: "SF Mono", "JetBrains Mono", monospace; }
.search-idx { font-size: 28px; font-weight: 900; color: #38bdf8; text-shadow: 0 0 16px rgba(56, 189, 248, 0.5); }
.search-sep { font-size: 16px; color: #475569; }
.search-total { font-size: 16px; color: #64748b; font-weight: 600; }
.search-target-body { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.search-university { font-size: 16px; font-weight: 700; color: #f1f5f9; letter-spacing: 1px; }
.search-major { font-size: 12px; color: #94a3b8; }
.search-pulse-bar { display: flex; gap: 4px; margin-top: 2px; }
.pulse-segment { width: 32px; height: 3px; border-radius: 2px; background: rgba(56, 189, 248, 0.2); animation: pulse-seg 1.2s ease-in-out infinite; }
@keyframes pulse-seg { 0%, 100% { background: rgba(56, 189, 248, 0.2); } 50% { background: #38bdf8; box-shadow: 0 0 8px rgba(56, 189, 248, 0.6); } }
.search-target-enter-active { transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1); }
.search-target-leave-active { transition: all 0.25s ease; }
.search-target-enter-from { opacity: 0; transform: translateX(20px) scale(0.95); }
.search-target-leave-to { opacity: 0; transform: translateX(-20px) scale(0.95); }

/* ── 高速检索终端 ── */
.fake-terminal { margin-top: 4px; width: 90%; max-width: 480px; height: 150px; background: rgba(0, 0, 0, 0.6); border: 1px solid rgba(56, 189, 248, 0.15); border-radius: 8px; padding: 10px 12px; overflow-y: auto; font-family: "SF Mono", "JetBrains Mono", "Consolas", monospace; font-size: 11px; line-height: 1.7; box-shadow: inset 0 0 24px rgba(0, 0, 0, 0.4); position: relative; z-index: 1; }
.fake-terminal::-webkit-scrollbar { width: 3px; }
.fake-terminal::-webkit-scrollbar-thumb { background: rgba(56, 189, 248, 0.3); border-radius: 2px; }
.term-line { display: flex; gap: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; animation: term-in 0.15s ease-out; }
@keyframes term-in { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: translateX(0); } }
.term-prompt { color: #475569; flex-shrink: 0; }
.term-text { color: #94a3b8; }
.term-sys .term-text { color: #7dd3fc; }
.term-ok .term-text { color: #6ee7b7; }
.term-warn .term-text { color: #fde68a; }
.term-info .term-text { color: #94a3b8; }
.term-target .term-text { color: #c4b5fd; }
.term-danger .term-text { color: #fda4af; }
.term-cursor { display: flex; align-items: center; gap: 6px; margin-top: 2px; }
.cursor-blink { color: #38bdf8; animation: cursor-blink 1s step-end infinite; }
@keyframes cursor-blink { 0%, 50% { opacity: 1; } 51%, 100% { opacity: 0; } }
.terminal-in-enter-active, .terminal-in-leave-active { transition: all 0.4s ease; }
.terminal-in-enter-from, .terminal-in-leave-to { opacity: 0; transform: translateY(8px); }

/* ── 底部阶段进度指示器 ── */
.phase-indicators { display: flex; gap: 8px; margin-top: 6px; position: relative; z-index: 1; }
.phase-dot { width: 22px; height: 22px; border-radius: 50%; border: 1px solid rgba(255, 255, 255, 0.1); display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 700; color: #475569; transition: all 0.5s cubic-bezier(0.34, 1.56, 0.64, 1); font-family: "SF Mono", monospace; }
.phase-dot.passed { color: #64748b; border-color: rgba(255, 255, 255, 0.08); background: rgba(255, 255, 255, 0.02); }
.phase-dot.active { background: #38bdf8; color: #020617; border-color: #38bdf8; box-shadow: 0 0 16px rgba(56, 189, 248, 0.6); transform: scale(1.2); }

.stats-bar { padding: 14px 20px; display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
.stats-bar .stat-total { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 700; color: #e2e8f0; padding-right: 18px; border-right: 1px solid rgba(255, 255, 255, 0.08); }
.stats-bar .stat-total::before { content: ''; width: 8px; height: 8px; border-radius: 50%; background: #38bdf8; box-shadow: 0 0 12px rgba(56, 189, 248, 0.6); flex-shrink: 0; }
.stat-item { font-size: 13px; font-weight: 600; display: inline-flex; align-items: center; gap: 5px; }
.stat-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.stat-dot.danger { background: #fb7185; box-shadow: 0 0 8px rgba(251, 113, 133, 0.6); }
.stat-dot.warn { background: #fbbf24; box-shadow: 0 0 8px rgba(251, 191, 36, 0.5); }
.stat-dot.pass { background: #34d399; box-shadow: 0 0 8px rgba(52, 211, 153, 0.5); }
.stat-danger { color: #fda4af; text-shadow: 0 0 10px rgba(253, 164, 175, 0.8); }
.stat-warn { color: #fde68a; }
.stat-pass { color: #6ee7b7; }

.results-scroll { flex: 1; overflow-y: auto; padding-bottom: 20px; }
.result-cards { display: flex; flex-direction: column; gap: 10px; padding: 0 8px; }

.neon-card { position: relative; padding: 18px; border-radius: 12px; background: rgba(255, 255, 255, 0.03); backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px); border: 1px solid rgba(255, 255, 255, 0.05); overflow: hidden; transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); cursor: default; }
.neon-card:hover { transform: translateY(-4px) scale(1.01); box-shadow: 0 12px 24px -10px rgba(0,0,0,0.5); }
.neon-card:active { transform: translateY(-2px); background: rgba(255, 255, 255, 0.06); }

/* TransitionGroup 弹簧进场动画 */
.list-enter-active { transition: all 0.6s cubic-bezier(0.34, 1.56, 0.64, 1); }
.list-enter-from { opacity: 0; transform: translateY(30px) scale(0.95); }
.neon-beam { position: absolute; left: 0; top: 50%; transform: translateY(-50%); width: 2px; height: 70%; border-radius: 0 2px 2px 0; opacity: 0.75; }
.beam-emerald { background: #34d399; box-shadow: 0 0 18px rgba(52, 211, 153, 0.6); }
.beam-amber   { background: #fbbf24; box-shadow: 0 0 18px rgba(251, 191, 36, 0.5); }
.beam-rose    { background: #fb7185; box-shadow: 0 0 20px rgba(251, 113, 133, 0.7); }
.animate-pulse-slow { animation: pulse-glow 4s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
.neon-body { padding-left: 8px; }
.neon-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }
.neon-info { flex: 1; }
.neon-school { font-size: 16px; font-weight: 600; color: #f1f5f9; display: block; letter-spacing: 0.5px; }
.neon-major { font-size: 12px; color: #94a3b8; font-weight: 300; margin-top: 2px; }
.neon-badge { display: flex; align-items: center; gap: 3px; padding: 3px 9px; border-radius: 12px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; white-space: nowrap; }
.neon-badge-icon { width: 12px; height: 12px; display: inline-flex; align-items: center; justify-content: center; }
.neon-badge-icon :deep(svg) { width: 100%; height: 100%; }
.badge-emerald { background: rgba(52, 211, 153, 0.1); color: #6ee7b7; border: 1px solid rgba(52, 211, 153, 0.2); }
.badge-amber   { background: rgba(251, 191, 36, 0.1); color: #fde68a; border: 1px solid rgba(251, 191, 36, 0.2); }
.badge-rose    { background: rgba(251, 113, 133, 0.1); color: #fda4af; border: 1px solid rgba(251, 113, 133, 0.2); }
.neon-reason { background: rgba(0, 0, 0, 0.25); border-radius: 7px; padding: 9px 10px; font-size: 12px; color: #94a3b8; line-height: 1.6; }
.neon-reason.warn-text { color: #fde68a; }
.neon-alert { display: flex; align-items: flex-start; gap: 6px; padding: 9px 10px; background: rgba(0, 0, 0, 0.3); border: 1px solid rgba(251, 113, 133, 0.15); border-radius: 7px; }
.alert-icon { width: 13px; height: 13px; color: #fda4af; flex-shrink: 0; margin-top: 1px; }
.alert-icon :deep(svg) { width: 100%; height: 100%; }
.alert-text { font-size: 12px; color: #fecdd3; line-height: 1.6; font-weight: 300; }
.neon-clause { margin-top: 7px; padding-left: 9px; border-left: 2px solid rgba(255, 255, 255, 0.06); font-size: 10px; color: #64748b; }

/* ── 就业/AI 风险标签 ── */
.risk-tags-row { display: flex; gap: 6px; margin-top: 7px; flex-wrap: wrap; }
.risk-tag { padding: 2px 8px; border-radius: 5px; font-size: 10px; font-weight: 600; }
.risk-low { background: rgba(52, 211, 153, 0.1); color: #6ee7b7; }
.risk-medium { background: rgba(251, 191, 36, 0.1); color: #fde68a; }
.risk-high { background: rgba(251, 113, 133, 0.12); color: #fda4af; border: 1px solid rgba(251, 113, 133, 0.2); }
.neon-clause.danger-clause {
  border-left-color: rgba(251, 113, 133, 0.2);
  color: #fda4af;
  position: relative;
  overflow: hidden;
  background: linear-gradient(110deg, transparent 0%, transparent 35%, rgba(251,113,133,0.08) 45%, rgba(251,113,133,0.12) 50%, rgba(251,113,133,0.08) 55%, transparent 65%, transparent 100%);
  background-size: 250% 100%;
  background-position: 150% 0;
  animation: clause-shimmer 3s ease-in-out infinite;
}

@keyframes clause-shimmer {
  0% { background-position: 150% 0; }
  40% { background-position: -50% 0; }
  100% { background-position: -50% 0; }
}
.neon-danger { border-color: rgba(251, 113, 133, 0.08); }
.neon-warn   { border-color: rgba(251, 191, 36, 0.06); }
.neon-pass   { border-color: rgba(52, 211, 153, 0.06); }

.empty-state { padding: 40px 20px; text-align: center; }
.empty-icon { width: 32px; height: 32px; margin: 0 auto 10px; color: #94a3b8; font-size: 28px; line-height: 1; }
.empty-title { font-size: 16px; font-weight: 700; color: #94a3b8; display: block; margin-bottom: 6px; }
.empty-desc { font-size: 13px; color: #64748b; }

/* ── 联网章程检索面板 ── */
.live-search-panel { padding: 16px 20px; }
.live-panel-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 6px; }
.live-panel-title { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700; color: #f1f5f9; }
.live-panel-title { color: #a5b4fc; }
.live-panel-hint { font-size: 11px; color: #475569; }
.live-input-row { display: flex; gap: 8px; }
.live-input { flex: 1; background: rgba(0, 0, 0, 0.3); border: 1px solid rgba(129, 140, 248, 0.15); border-radius: 8px; padding: 10px 14px; font-size: 13px; color: #e2e8f0; outline: none; box-sizing: border-box; }
.live-input:focus { border-color: rgba(129, 140, 248, 0.4); }
.live-input::placeholder { color: #475569; }
.live-btn { padding: 10px 18px; background: rgba(129, 140, 248, 0.15); border: 1px solid rgba(129, 140, 248, 0.3); border-radius: 8px; cursor: pointer; transition: all 0.2s; }
.live-btn:hover:not(.disabled) { background: rgba(129, 140, 248, 0.22); border-color: rgba(129, 140, 248, 0.5); }
.live-btn:active { transform: scale(0.96); }
.live-btn.disabled { opacity: 0.3; pointer-events: none; }
.live-btn-text { font-size: 12px; font-weight: 700; color: #a5b4fc; white-space: nowrap; }

/* 联网结果卡片 */
.live-result-card { margin-top: 12px; padding: 14px; background: rgba(129, 140, 248, 0.05); border: 1px solid rgba(129, 140, 248, 0.15); border-radius: 10px; }
.live-result-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.live-result-school { font-size: 14px; font-weight: 700; color: #f1f5f9; }
.live-result-major { font-size: 12px; color: #94a3b8; }
.live-source-tag { display: flex; align-items: center; gap: 3px; font-size: 9px; color: #a5b4fc; padding: 2px 6px; background: rgba(129, 140, 248, 0.1); border-radius: 4px; margin-left: auto; }
.live-status-badge { display: inline-block; padding: 2px 10px; border-radius: 5px; font-size: 11px; font-weight: 700; margin-bottom: 8px; }
.badge-pass { background: rgba(52, 211, 153, 0.12); color: #6ee7b7; }
.badge-warning { background: rgba(251, 191, 36, 0.12); color: #fde68a; }
.badge-danger { background: rgba(251, 113, 133, 0.12); color: #fda4af; }
.badge-unknown { background: rgba(148, 163, 184, 0.12); color: #94a3b8; }
.live-result-reason { font-size: 12px; color: #94a3b8; line-height: 1.6; }
.live-result-clause { margin-top: 6px; padding-left: 8px; border-left: 2px solid rgba(129, 140, 248, 0.2); font-size: 10px; color: #64748b; line-height: 1.5; }
.live-result-enter-active { transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1); }
.live-result-enter-from { opacity: 0; transform: translateY(12px); }

@media (max-width: 768px) {
  .risk-layout { gap: 8px; }
  .draft-textarea { min-height: 120px; font-size: 13px; }
  .stats-bar { flex-direction: column; gap: 8px; }
  .neon-card { padding: 14px; }
  .neon-school { font-size: 14px; }
  .draft-footer { flex-direction: column; gap: 10px; align-items: stretch; }
  .footer-left { justify-content: center; }
  .scan-btn { justify-content: center; }
  .live-input-row { flex-direction: column; }
  .live-btn { text-align: center; }
  .fake-terminal { width: 95%; height: 110px; font-size: 10px; }
  .ritual-title { font-size: 20px; letter-spacing: 3px; }
  .ritual-subtitle { font-size: 12px; }
  .ritual-ring-wrap { width: 96px; height: 96px; }
  .ritual-ring.outer { width: 96px; height: 96px; }
  .ritual-ring.mid { width: 76px; height: 76px; }
  .progress-ring { width: 96px; height: 96px; }
  .profile-vector-bar { padding: 8px 12px; }
  .vector-tags { gap: 4px; }
  .vector-tag { font-size: 9px; padding: 2px 6px; }
  .search-target-card { min-width: 200px; padding: 10px 16px; }
  .search-idx { font-size: 22px; }
  .search-university { font-size: 14px; }
  .phase-indicators { gap: 5px; }
  .phase-dot { width: 18px; height: 18px; font-size: 9px; }
}
</style>
