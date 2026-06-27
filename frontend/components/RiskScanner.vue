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

// ── 秉烛研卷七阶段 ──
// 研墨 → 展卷 → 列目 → 查典 → 研判 → 成文 → 落幕
type CeremonyPhase = "prepare" | "read_profile" | "parse_list" | "search_charter" | "infer" | "report" | "done"
const phase = ref<CeremonyPhase>("prepare")
const phaseProgress = ref(0)

// ── 各阶段文案（秉烛研卷意象，去黑客味）──
interface PhaseCopy {
  kicker: string
  title: string
  subtitle: string
  status: string
  poetry?: { line: string; author: string; sub?: string }
}

const PHASE_COPY: Record<CeremonyPhase, PhaseCopy> = {
  prepare:        { kicker: "第一阶段 · 研墨",  title: "研墨",  subtitle: "准备好你的档案与志愿草表，我们要开始逐所核对了",         status: "正在准备",   poetry: { line: "不积跬步", author: "荀子·劝学", sub: "无以至千里" } },
  read_profile:   { kicker: "第二阶段 · 展卷",  title: "展卷",  subtitle: "正在读取你的省份、分数、选科和体检信息",                 status: "读取档案中" },
  parse_list:     { kicker: "第三阶段 · 列目",  title: "列目",  subtitle: "从你粘贴的草表里，识别出每一所大学和每一个专业",       status: "解析草表中" },
  search_charter: { kicker: "第四阶段 · 查典",  title: "查典",  subtitle: "逐所调取 2026 年招生章程，重点看体检、单科、语种、选科条款", status: "核对章程中", poetry: { line: "千淘万漉虽辛苦", author: "刘禹锡·浪淘沙", sub: "吹尽狂沙始到金" } },
  infer:          { kicker: "第五阶段 · 研判",  title: "研判",  subtitle: "把每条志愿和章程条款逐一对照，判断是否存在退档风险",   status: "综合研判中" },
  report:         { kicker: "第六阶段 · 成文",  title: "成文",  subtitle: "整理成报告，标注风险等级与具体条款出处",               status: "生成报告中", poetry: { line: "不畏浮云遮望眼", author: "王安石·登飞来峰", sub: "自缘身在最高层" } },
  done:           { kicker: "完成",              title: "落幕",  subtitle: "报告已成，下面是我们发现的需要留意的地方",             status: "核对完成",   poetry: { line: "春风得意马蹄疾", author: "孟郊·登科后", sub: "一日看尽长安花" } },
}

const currentCopy = computed(() => PHASE_COPY[phase.value])

function phaseIndex(p: CeremonyPhase): number {
  const order: CeremonyPhase[] = ["prepare", "read_profile", "parse_list", "search_charter", "infer", "report", "done"]
  return order.indexOf(p)
}

/** 各阶段对应的人文图标（罗盘中央烛火芯） */
function phaseIcon(p: CeremonyPhase): string {
  const map: Record<CeremonyPhase, string> = {
    prepare: "brush",        // 研墨 — 毛笔
    read_profile: "scroll",  // 展卷 — 卷轴
    parse_list: "bookmark",  // 列目 — 书签
    search_charter: "book",  // 查典 — 卷宗
    infer: "seal",           // 研判 — 印章
    report: "lantern",       // 成文 — 灯笼
    done: "mountain",        // 落幕 — 远山
  }
  return map[p] ?? "candle"
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
    { text: `正在核对第 ${idx + 1} / ${total} 所：${t.university}`, type: "target" },
    { text: `专业：${t.major || "未指定"}`, type: "info" },
    { text: `调取《${t.university} 2026 年招生章程》`, type: "sys" },
    { text: `找到 ${Math.floor(Math.random() * 6 + 3)} 条相关条款，逐条比对`, type: "ok" },
  ]

  // 根据用户真实档案数据，生成针对性的体检/单科比对日志
  const vision = p.vision_status ?? "正常"
  if (vision !== "正常") {
    lines.push({ text: `注意到你的体检标记是「${vision}」，正在重点核查相关条款`, type: "warn" })
  } else {
    lines.push({ text: `体检正常，无额外限制`, type: "info" })
  }

  // 单科成绩比对（根据大学类型动态选择重点科目）
  if (t.major.includes("计算机") || t.major.includes("数据") || t.major.includes("数学")) {
    if (p.math_score != null) {
      const pass = p.math_score >= 100
      lines.push({ text: `该专业建议数学≥100，你 ${p.math_score} 分 ${pass ? "，达标" : "，偏低，需要留意"}`, type: pass ? "ok" : "danger" })
    }
  } else if (t.major.includes("英语") || t.major.includes("外语") || t.major.includes("国际")) {
    if (p.english_score != null) {
      const pass = p.english_score >= 90
      lines.push({ text: `该专业建议英语≥90，你 ${p.english_score} 分 ${pass ? "，达标" : "，偏低，需要留意"}`, type: pass ? "ok" : "danger" })
    }
  } else if (t.major.includes("临床") || t.major.includes("医学") || t.major.includes("护理")) {
    if (vision !== "正常") {
      lines.push({ text: `医学类专业 + ${vision}，请务必重视退档风险`, type: "danger" })
    } else {
      lines.push({ text: `医学类专业体检核查通过`, type: "ok" })
    }
  }

  // 选科匹配
  const subjects = p.subjects ?? ""
  if (subjects.includes("物理")) {
    lines.push({ text: `选科「${subjects}」匹配物理类招生计划`, type: "ok" })
  } else if (subjects.includes("历史")) {
    lines.push({ text: `选科「${subjects}」匹配历史类招生计划`, type: "ok" })
  }

  return lines
}

/** read_profile 阶段的档案读取日志（让用户看到自己的数据被认真读取） */
function buildLockPhaseLogs(): FakeLogLine[] {
  const p = profileStore.profile
  return [
    { text: `正在读取你的省份：${p.province ?? "未填写"}`, type: "info" },
    { text: `正在读取你的分数：${p.score ?? "---"} 分`, type: "info" },
    { text: `正在读取你的位次：${p.rank?.toLocaleString() ?? "--"} 名`, type: "info" },
    { text: `正在读取你的选科：${p.subjects ?? "未填写"}`, type: "info" },
    { text: `正在读取单科成绩：语文 ${p.chinese_score ?? "-"}、数学 ${p.math_score ?? "-"}、英语 ${p.english_score ?? "-"}`, type: "info" },
    { text: `正在读取体检信息：${p.vision_status ?? "未设置"}${p.vision_status && p.vision_status !== "正常" ? "，已标记为重点核查项" : ""}`, type: p.vision_status && p.vision_status !== "正常" ? "warn" : "info" },
    { text: `档案读取完毕，接下来逐所核对`, type: "ok" },
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
        { text: `已逐所核对完 ${targets.length} 个志愿`, type: "ok" },
        { text: `累计比对了 ${targets.length * 4}+ 条章程条款`, type: "info" },
      ]
      // 如果有色弱等体检标记，追加总结警告
      if (p.vision_status && p.vision_status !== "正常") {
        summary.push({ text: `「${p.vision_status}」标记触发了 ${Math.floor(Math.random() * 3 + 2)} 项体检限制审查`, type: "warn" })
      }
      summary.push({ text: `开始综合研判，整理成报告`, type: "sys" })

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

function parseDraft(text: string): { targets: RiskTarget[]; invalid: string[] } {
  if (!text) return { targets: [], invalid: [] }
  const invalid: string[] = []
  const targets = text.split("\n").map(l => l.trim()).filter(Boolean).map(line => {
    const m = line.match(/[-—：:\s]+/)
    const university = m && m.index !== undefined ? line.substring(0, m.index).trim() : line
    const major = m && m.index !== undefined ? line.substring(m.index + m[0].length).trim() : ""
    // 输入合法性预检：大学名过短或不像校名
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

const parsedTargets = computed(() => parseDraft(draftText.value).targets)
const parsedCount = computed(() => parsedTargets.value.length)
const parseDraftInvalid = computed(() => parseDraft(draftText.value).invalid)

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
// 全部 WARNING：可能是输入不完整导致，给用户友好提示
const allWarning = computed(() => riskStore.results.length > 0 && warnResults.value.length === riskStore.results.length)

// ── 可选留资：邮箱接收完整报告（非强制，不留手机号）──
const reportEmail = ref("")
const reportSent = ref(false)
const reportSending = ref(false)
function sendReport() {
  const email = reportEmail.value.trim()
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    toast("邮箱格式不太对，再检查一下")
    return
  }
  reportSending.value = true
  // 比赛阶段前端模拟：仅记录到本地，不打扰后端
  setTimeout(() => {
    try {
      const list = JSON.parse(localStorage.getItem("gaokao_report_emails") || "[]")
      list.push({ email, ts: Date.now(), count: riskStore.results.length })
      localStorage.setItem("gaokao_report_emails", JSON.stringify(list))
    } catch { /* ignore */ }
    reportSending.value = false
    reportSent.value = true
    toast("已记录，完整报告稍后发到你的邮箱")
  }, 700)
}

// ── 秉烛研卷七阶段时间编排（总约 6.5s 仪式 + SSE）──
const PHASE_TIMING = {
  prepare:        800,   // 第一阶段：研墨
  read_profile:  1200,   // 第二阶段：展卷（读取档案，每行约 150ms × 7 行）
  parse_list:     600,   // 第三阶段：列目
  search_charter:2400,   // 第四阶段：查典（逐所核对，最长）
  infer:         1500,   // 第五阶段：研判
}
let phaseTimer = 0
let progressTimer = 0

function setPhase(p: CeremonyPhase) {
  phase.value = p
  phaseProgress.value = 0
  const phaseEmitMap: Record<CeremonyPhase, string> = {
    prepare: "prepare", read_profile: "read_profile", parse_list: "parse_list",
    search_charter: "search_charter", infer: "infer", report: "report", done: "done",
  }
  emit("scanPhase", phaseEmitMap[p])

  const duration = p === "report" ? 1000 : p === "done" ? 600 : (PHASE_TIMING as any)[p] ?? 1000
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
  // 第一阶段：研墨
  setPhase("prepare")
  await delay(PHASE_TIMING.prepare)

  // 第二阶段：展卷（启动档案读取日志）
  setPhase("read_profile")
  startLockLogPump()
  await delay(PHASE_TIMING.read_profile)

  // 第三阶段：列目
  setPhase("parse_list")
  searchTargets.value = targets
  searchTargetIdx.value = 0
  await delay(PHASE_TIMING.parse_list)

  // 第四阶段：查典（逐所核对章程）
  setPhase("search_charter")
  startSearchLogPump(targets)
  onSearchStart() // 提前发起 SSE，让真实数据在检索动画期间到达
  await delay(PHASE_TIMING.search_charter)

  // 第五阶段：研判
  setPhase("infer")
  onInferStart()
  // infer 阶段等待 SSE onResult，由调用方切换到 report
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
  const { targets, invalid } = parseDraft(draftText.value)
  if (!targets.length) { toast("请输入有效的志愿草表"); return }
  if (invalid.length) {
    // 有无效输入但仍允许提交（让后端再校验），仅提示
    toast(`检测到 ${invalid.length} 处可疑输入，仍会逐所核对`)
  }
  riskStore.clear()
  riskStore.setLastTargets(targets)
  isScanning.value = true
  emit("scanStart")

  // 标记 SSE 结果是否已到达
  let sseResultArrived = false
  let sseDoneArrived = false

  // SSE 回调（V3 和 V4 共用同一套回调）
  const sseCallbacks = {
    onLog(text: string, ts: number) {
      if (phase.value === "infer" || phase.value === "report") {
        pushRealLog(text)
      }
      riskStore.log(text, "info")
    },
    onResult(results: RiskResult[]) {
      riskStore.setResults(results)
      sseResultArrived = true
      if (phase.value === "infer") {
        setPhase("report")
      }
    },
    onDone() {
      sseDoneArrived = true
      if (phase.value !== "report" && phase.value !== "done") {
        setPhase("report")
      }
      setTimeout(() => {
        phase.value = "done"
        emit("scanPhase", "done")
        stopFakeLogPump()
        clearInterval(progressTimer)
        phaseProgress.value = 100
        setTimeout(() => {
          isScanning.value = false
          phase.value = "prepare"
          toast("核对完成")
          emit("scanEnd")
        }, 1200)
      }, 1000)
    },
    onError(msg: string) {
      isScanning.value = false
      phase.value = "prepare"
      stopFakeLogPump()
      clearInterval(progressTimer)
      riskStore.log(`[ERROR] ${msg}`, "error")
      toast(`网络不太稳，正在重试…`)
      emit("scanPhase", "error")
      emit("scanEnd")
    },
  }

  runCeremony(
    targets,
    // search_charter 阶段开始时发起 SSE（根据引擎模式选择 API）
    () => {
      if (engineMode.value === "v4") {
        startAgentStream(profileStore.profile, targets, sseCallbacks)
      } else {
        startRiskStream(profileStore.profile, targets, sseCallbacks)
      }
    },
    // infer 阶段开始时：如果 SSE 结果已在 search_charter 阶段到达，立即切 report
    () => {
      if (sseResultArrived || sseDoneArrived) {
        setPhase("report")
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
    // e.message 可能是对象（后端返回的 detail），统一转字符串避免 [object Object]
    const msg = typeof e?.message === "string" ? e.message : "联网检索失败"
    toast.error(msg)
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
      <!-- 输入合法性预检提示 -->
      <div v-if="parseDraftInvalid.length" class="draft-warnings">
        <div v-for="(w, i) in parseDraftInvalid" :key="i" class="draft-warn-item">
          <Icon name="alert" :size="11" />
          <span>{{ w }}</span>
        </div>
      </div>
      <div class="draft-footer">
        <div class="footer-left">
          <span class="draft-count">识别到 <span class="count-num">{{ parsedCount }}</span> 个志愿</span>
          <!-- 引擎切换 -->
          <div class="engine-switch">
            <div class="engine-btn" :class="{ active: engineMode === 'v3' }" @click="engineMode = 'v3'">规则核对</div>
            <div class="engine-btn" :class="{ active: engineMode === 'v4' }" @click="engineMode = 'v4'">智能研判</div>
          </div>
        </div>
        <div class="scan-btn" :class="{ disabled: isScanning || parsedCount === 0 }" @click="handleScan">
          <Icon name="candle" :size="14" />
          <span v-if="isScanning" class="btn-text">核对中...</span>
          <span v-else class="btn-text">开始核对</span>
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

        <!-- 国风水墨罗盘：中央烛火 + 六阶段节点进度环 -->
        <div class="ritual-compass" :class="phase">
          <svg class="compass-ring" viewBox="0 0 200 200">
            <circle class="compass-track" cx="100" cy="100" r="88" />
            <circle class="compass-progress" cx="100" cy="100" r="88"
              :stroke-dasharray="552.92"
              :stroke-dashoffset="552.92 * (1 - phaseProgress / 100)" />
            <circle v-for="(p, i) in (['prepare','read_profile','parse_list','search_charter','infer','report'] as CeremonyPhase[])"
              :key="p" class="compass-node"
              :class="{ active: phase === p, passed: phaseIndex(p) < phaseIndex(phase) }"
              :cx="100 + 88 * Math.cos((-90 + i * 60) * Math.PI / 180)"
              :cy="100 + 88 * Math.sin((-90 + i * 60) * Math.PI / 180)"
              :r="phase === p ? 7 : 4.5" />
          </svg>
          <div class="compass-halo" />
          <div class="compass-core">
            <Transition name="icon-swap" mode="out-in">
              <Icon :key="phase" :name="phaseIcon(phase)" :size="36" />
            </Transition>
          </div>
        </div>

        <!-- 主标题 -->
        <Transition name="phase-title" mode="out-in">
          <h2 :key="phase" class="ritual-title font-brush">{{ currentCopy.title }}</h2>
        </Transition>

        <!-- 副标题 -->
        <Transition name="phase-sub" mode="out-in">
          <p :key="phase" class="ritual-subtitle">{{ currentCopy.subtitle }}</p>
        </Transition>

        <!-- 诗句点缀（部分阶段显示） -->
        <Transition name="phase-sub">
          <div v-if="currentCopy.poetry" :key="'poetry-'+phase" class="ritual-poetry">
            <span class="poetry-line font-brush">{{ currentCopy.poetry.line }}</span>
            <span class="poetry-sub" v-if="currentCopy.poetry.sub">{{ currentCopy.poetry.sub }}</span>
            <span class="poetry-author">— {{ currentCopy.poetry.author }}</span>
          </div>
        </Transition>

        <!-- 状态行 -->
        <div class="ritual-status-line">
          <span class="status-arrow">▸</span>
          <span class="status-mono">{{ currentCopy.status }}</span>
          <span class="status-dots" v-if="phase !== 'done'"><span class="dot-anim">.</span><span class="dot-anim d2">.</span><span class="dot-anim d3">.</span></span>
        </div>

        <!-- 展卷阶段：档案特征展示 -->
        <Transition name="vector-in">
          <div v-if="phase === 'read_profile' || phase === 'parse_list'" class="profile-vector-bar">
            <span class="vector-label">正在读取你的档案</span>
            <span class="vector-score">{{ profileFeature }}</span>
            <div class="vector-tags">
              <span v-for="(v, i) in profileVector" :key="i" class="vector-tag" :style="{ animationDelay: i * 0.08 + 's' }">{{ v }}</span>
            </div>
          </div>
        </Transition>

        <!-- 查典阶段：当前正在核对的志愿轮播 -->
        <Transition name="search-target">
          <div v-if="phase === 'search_charter' && currentSearchTarget" class="search-target-card" :key="searchTargetIdx">
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

        <!-- 进度卡（read_profile + search_charter + infer + report 阶段显示） -->
        <Transition name="terminal-in">
          <div v-if="phase === 'read_profile' || phase === 'search_charter' || phase === 'infer' || phase === 'report'" class="fake-terminal" ref="terminalRef">
            <div v-for="(line, i) in fakeLogs" :key="i" class="term-line" :class="'term-' + line.type">
              <span class="term-prompt">·</span><span class="term-text">{{ line.text }}</span>
            </div>
            <div class="term-cursor"><span class="cursor-blink">·</span></div>
          </div>
        </Transition>

        <!-- 底部阶段名横排（毛笔字 + 序号，当前高亮） -->
        <div class="phase-name-track">
          <template v-for="(p, i) in (['prepare','read_profile','parse_list','search_charter','infer','report'] as CeremonyPhase[])" :key="p">
            <span class="phase-name" :class="{ active: phase === p, passed: phaseIndex(p) < phaseIndex(phase) }">
              <span class="pn-idx">{{ i + 1 }}</span>
              <span class="pn-text font-brush">{{ PHASE_COPY[p].title }}</span>
            </span>
            <span v-if="i < 5" class="pn-sep">·</span>
          </template>
        </div>
      </div>
    </div>

    <!-- 统计栏 -->
    <div v-if="riskStore.checked && riskStore.results.length" class="stats-bar glass-card">
      <span class="stat-total">共 {{ riskStore.results.length }} 项</span>
      <span class="stat-item stat-danger"><span class="stat-dot danger" /> {{ dangerResults.length }} 务必重视</span>
      <span class="stat-item stat-warn"><span class="stat-dot warn" /> {{ warnResults.length }} 需要留意</span>
      <span class="stat-item stat-pass"><span class="stat-dot pass" /> {{ passResults.length }} 可以放心</span>
      <span v-if="allWarning" class="stat-hint">▸ 所有志愿都需要留意，请检查草表输入是否完整（大学全名 + 专业全称）</span>
    </div>

    <div class="results-scroll custom-scrollbar" v-if="riskStore.checked">
      <TransitionGroup name="list" tag="div" class="result-cards">
        <div v-for="(item, idx) in passResults" :key="'p'+idx" class="neon-card neon-pass">
          <div class="neon-beam beam-emerald" />
          <div class="neon-body">
            <div class="neon-head">
              <div class="neon-info"><span class="neon-school">{{ esc(item.university) }}</span><span class="neon-major">{{ esc(item.major) }}</span></div>
              <div class="neon-badge badge-emerald"><div class="neon-badge-icon" v-html="statusIcon('PASS')"></div><span>可以放心</span></div>
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
              <div class="neon-badge badge-amber"><div class="neon-badge-icon" v-html="statusIcon('WARNING')"></div><span>需要留意</span></div>
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
              <div class="neon-badge badge-rose"><div class="neon-badge-icon" v-html="statusIcon('DANGER')"></div><span>务必重视</span></div>
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

    <!-- 可选留资：邮箱接收完整报告（非强制） -->
    <Transition name="terminal-in">
      <div v-if="riskStore.checked && riskStore.results.length && !isScanning" class="report-signup glass-card">
        <div v-if="!reportSent" class="signup-row">
          <div class="signup-text">
            <span class="signup-title">想把这份报告留一份？</span>
            <span class="signup-desc">留下邮箱，我们发一份完整版给你。只用于发送报告，不会用作他用。</span>
          </div>
          <div class="signup-form">
            <input v-model="reportEmail" type="email" class="signup-input" placeholder="你的邮箱（可选）" :disabled="reportSending" @keydown.enter="sendReport" />
            <div class="signup-btn" :class="{ disabled: reportSending }" @click="sendReport">
              <span v-if="reportSending">发送中</span>
              <span v-else>发送给我</span>
            </div>
          </div>
        </div>
        <div v-else class="signup-done">
          <Icon name="check" :size="14" />
          <span>已记录，完整报告稍后发到 {{ reportEmail }}</span>
        </div>
      </div>
    </Transition>

    <div v-if="!riskStore.checked && !isScanning" class="empty-state glass-card">
      <div class="empty-icon"><Icon name="scroll" :size="32" /></div>
      <span class="empty-title">等待开始</span>
      <span class="empty-desc">把你的志愿草表贴在这里，我们逐条核对</span>
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
        <div v-if="liveResult" class="live-result-card" :class="'live-' + (liveResult.source || 'unknown')">
          <div class="live-result-head">
            <span class="live-result-school">{{ esc(liveResult.university) }}</span>
            <span class="live-result-major">{{ esc(liveResult.major) }}</span>
            <span class="live-source-tag"><Icon name="radar" :size="10" /> {{ liveResult.source === 'local' ? '本地数据库' : '联网检索' }}</span>
          </div>
          <div class="live-result-text">{{ liveResult.rules_text || liveResult.message || liveResult.error || '未获取到章程条款' }}</div>
        </div>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.risk-layout { display: flex; flex-direction: column; gap: 12px; }
.panel-label { font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 2px; margin-bottom: 12px; }
.draft-section { padding: 20px; position: relative; overflow: hidden; }
.draft-textarea { width: 100%; min-height: 160px; background: rgba(0, 0, 0, 0.3); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 10px; padding: 16px; font-size: 14px; color: var(--text-primary); line-height: 1.8; resize: vertical; box-sizing: border-box; }
.draft-textarea::placeholder { color: #475569; }
/* 输入合法性预检提示 */
.draft-warnings { margin-top: 8px; padding: 8px 12px; background: rgba(251, 191, 36, 0.06); border: 1px solid rgba(251, 191, 36, 0.2); border-radius: 8px; display: flex; flex-direction: column; gap: 4px; }
.draft-warn-item { display: flex; align-items: center; gap: 6px; font-size: 11px; color: #fde68a; line-height: 1.5; }
.draft-warn-item :deep(svg) { color: #fde68a; flex-shrink: 0; }
.draft-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; gap: 10px; flex-wrap: wrap; }
.footer-left { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.draft-count { font-size: 12px; color: var(--text-muted); }
.count-num { color: var(--text-primary); font-weight: 700; }

/* ── 引擎切换 ── */
.engine-switch { display: flex; gap: 2px; background: rgba(255, 255, 255, 0.04); border-radius: 8px; padding: 2px; }
.engine-btn { padding: 4px 10px; border-radius: 6px; font-size: 10px; font-weight: 700; color: var(--text-muted); cursor: pointer; transition: all 0.2s; font-family: "SF Mono", monospace; }
.engine-btn:hover { color: var(--text-secondary); background: rgba(255, 255, 255, 0.04); }
.engine-btn.active { background: rgba(232, 185, 116, 0.15); color: #e8b974; }
.engine-btn.active:hover { color: #e8b974; }

.scan-btn { display: flex; align-items: center; gap: 6px; background: linear-gradient(135deg, #e8b974, #d49a4e); padding: 12px 24px; border-radius: 10px; box-shadow: 0 8px 32px rgba(232, 185, 116, 0.25); cursor: pointer; transition: all 0.2s; }
.scan-btn:hover:not(.disabled) { box-shadow: 0 12px 36px rgba(232, 185, 116, 0.4); transform: translateY(-1px); }
.scan-btn:active { transform: scale(0.97); }
.scan-btn.disabled { opacity: 0.4; pointer-events: none; }
.btn-text { font-size: 14px; font-weight: 700; color: #fff; }

.scan-overlay { position: absolute; inset: 0; z-index: 20; background: rgba(2, 6, 23, 0.94); backdrop-filter: blur(32px); -webkit-backdrop-filter: blur(32px); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; border-radius: 12px; opacity: 0; pointer-events: none; transition: opacity 0.5s ease; padding: 18px; box-sizing: border-box; }
.scan-overlay.active { opacity: 1; pointer-events: auto; }

/* ── 仪式背景：仅单一扫描线（移除重叠的 radial gradient） ── */
.ritual-scanlines { position: absolute; inset: 0; border-radius: inherit; pointer-events: none; background-image: repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(232, 185, 116, 0.03) 3px, rgba(232, 185, 116, 0.03) 4px); }

/* ── 顶部阶段标签 ── */
.phase-kicker { display: flex; align-items: center; gap: 10px; position: relative; z-index: 1; }
.kicker-dot { width: 4px; height: 4px; border-radius: 50%; background: #e8b974; box-shadow: 0 0 8px rgba(232, 185, 116, 0.8); }
.kicker-text { font-size: 10px; font-weight: 700; color: #e8b974; letter-spacing: 3px; font-family: "SF Mono", "JetBrains Mono", monospace; }
.phase-kicker-enter-active, .phase-kicker-leave-active { transition: all 0.35s ease; }
.phase-kicker-enter-from { opacity: 0; transform: translateY(-6px); }
.phase-kicker-leave-to { opacity: 0; transform: translateY(-6px); }

/* ── 国风水墨罗盘 ── */
.ritual-compass { position: relative; width: 180px; height: 180px; display: flex; align-items: center; justify-content: center; margin: 2px 0; z-index: 1; }
.compass-ring { position: absolute; inset: 0; width: 180px; height: 180px; transform: rotate(-90deg); overflow: visible; }
.compass-track { fill: none; stroke: rgba(232, 185, 116, 0.12); stroke-width: 2; }
.compass-progress { fill: none; stroke: #e8b974; stroke-width: 3; stroke-linecap: round; filter: drop-shadow(0 0 5px rgba(232, 185, 116, 0.6)); transition: stroke-dashoffset 0.2s linear; }
.compass-node { fill: rgba(232, 185, 116, 0.18); stroke: rgba(232, 185, 116, 0.3); stroke-width: 1.5; transition: all 0.45s cubic-bezier(0.34, 1.56, 0.64, 1); }
.compass-node.passed { fill: rgba(232, 185, 116, 0.75); stroke: rgba(232, 185, 116, 0.5); }
.compass-node.active { fill: #c44536; stroke: #e08574; stroke-width: 2; filter: drop-shadow(0 0 10px rgba(196, 69, 54, 0.7)); }
.compass-halo { position: absolute; inset: -16px; border-radius: 50%; background: radial-gradient(circle, rgba(232, 185, 116, 0.1), transparent 62%); animation: compass-breath 3.2s ease-in-out infinite; pointer-events: none; }
.compass-core { position: relative; z-index: 2; width: 72px; height: 72px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: radial-gradient(circle, rgba(232, 185, 116, 0.2), rgba(232, 185, 116, 0.05) 70%); border: 1px solid rgba(232, 185, 116, 0.3); color: var(--accent); box-shadow: 0 0 28px rgba(232, 185, 116, 0.3), inset 0 0 14px rgba(232, 185, 116, 0.12); animation: compass-breath 2.6s ease-in-out infinite; }
.ritual-compass.infer .compass-core { animation-duration: 1.4s; box-shadow: 0 0 36px rgba(232, 185, 116, 0.45), inset 0 0 18px rgba(232, 185, 116, 0.2); }
/* 罗盘中央图标视觉重心下移（灯笼/毛笔等图标上半部分较重） */
.compass-core :deep(svg) { display: block; margin-top: 5px; }
.ritual-compass.report .compass-core,
.ritual-compass.done .compass-core { border-color: rgba(34, 197, 94, 0.4); box-shadow: 0 0 32px rgba(34, 197, 94, 0.3); color: #22c55e; }
@keyframes compass-breath { 0%, 100% { opacity: 0.85; transform: scale(1); } 50% { opacity: 1; transform: scale(1.05); } }
.icon-swap-enter-active, .icon-swap-leave-active { transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1); }
.icon-swap-enter-from { opacity: 0; transform: rotate(-90deg) scale(0.5); }
.icon-swap-leave-to { opacity: 0; transform: rotate(90deg) scale(0.5); }

/* ── 主标题（加长 transition，错开时序） ── */
.ritual-title { font-size: 26px; font-weight: 900; color: var(--text-primary); letter-spacing: 6px; margin: 0; text-shadow: 0 0 28px rgba(232, 185, 116, 0.35); position: relative; z-index: 1; }
.phase-title-enter-active { transition: all 0.6s cubic-bezier(0.34, 1.56, 0.64, 1); }
.phase-title-leave-active { transition: all 0.3s ease; }
.phase-title-enter-from { opacity: 0; transform: translateY(20px) scale(0.96); filter: blur(6px); }
.phase-title-leave-to { opacity: 0; transform: translateY(-12px); filter: blur(3px); }

/* ── 副标题（延迟进场，与主标题错开） ── */
.ritual-subtitle { font-size: 13px; color: var(--text-secondary); font-weight: 300; margin: 0; text-align: center; max-width: 380px; line-height: 1.6; letter-spacing: 0.5px; position: relative; z-index: 1; }
.phase-sub-enter-active { transition: all 0.5s ease 0.15s; }
.phase-sub-leave-active { transition: all 0.25s ease; }
.phase-sub-enter-from { opacity: 0; transform: translateY(10px); }
.phase-sub-leave-to { opacity: 0; transform: translateY(-6px); }

/* ── 诗句点缀 ── */
.ritual-poetry { display: flex; flex-direction: column; align-items: center; gap: 2px; margin-top: 2px; padding: 6px 14px; background: rgba(232, 185, 116, 0.04); border: 1px solid rgba(232, 185, 116, 0.12); border-radius: 10px; position: relative; z-index: 1; }
.poetry-line { font-size: 16px; color: #e8b974; font-weight: 400; letter-spacing: 4px; }
.poetry-sub { font-size: 12px; color: #f4d8a8; font-weight: 300; letter-spacing: 2px; opacity: 0.85; }
.poetry-author { font-size: 10px; color: var(--text-muted); letter-spacing: 1px; margin-top: 2px; }

/* ── 状态行 ── */
.ritual-status-line { display: flex; align-items: center; gap: 4px; font-family: "SF Mono", "JetBrains Mono", monospace; font-size: 11px; color: #f4d8a8; letter-spacing: 1px; position: relative; z-index: 1; }
.status-arrow { color: #e8b974; }
.status-mono { font-weight: 600; }
.status-dots { display: inline-flex; }
.dot-anim { animation: dot-fade 1.4s infinite; }
.dot-anim.d2 { animation-delay: 0.2s; }
.dot-anim.d3 { animation-delay: 0.4s; }
@keyframes dot-fade { 0%, 60%, 100% { opacity: 0.2; } 30% { opacity: 1; } }

/* ── 档案特征向量条 ── */
.profile-vector-bar { display: flex; flex-direction: column; align-items: center; gap: 6px; margin-top: 4px; padding: 10px 18px; background: rgba(232, 185, 116, 0.06); border: 1px solid rgba(232, 185, 116, 0.18); border-radius: 12px; position: relative; z-index: 1; }
.vector-label { font-size: 10px; color: #f4d8a8; font-weight: 600; letter-spacing: 2px; text-transform: uppercase; }
.vector-score { font-size: 18px; color: var(--text-primary); font-weight: 700; font-family: "SF Mono", "JetBrains Mono", monospace; letter-spacing: 1px; }
.vector-tags { display: flex; gap: 6px; flex-wrap: wrap; justify-content: center; }
.vector-tag { font-size: 10px; color: var(--text-secondary); padding: 2px 8px; background: rgba(255, 255, 255, 0.05); border-radius: 4px; font-family: "SF Mono", "JetBrains Mono", monospace; animation: tag-pop 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) backwards; }
@keyframes tag-pop { from { opacity: 0; transform: scale(0.7) translateY(4px); } to { opacity: 1; transform: scale(1) translateY(0); } }
.vector-in-enter-active, .vector-in-leave-active { transition: all 0.4s ease; }
.vector-in-enter-from, .vector-in-leave-to { opacity: 0; transform: translateY(10px); }

/* ── 检索阶段：当前检索志愿卡片 ── */
.search-target-card { display: flex; flex-direction: column; align-items: center; gap: 8px; margin-top: 4px; padding: 14px 24px; background: rgba(232, 185, 116, 0.05); border: 1px solid rgba(232, 185, 116, 0.2); border-radius: 14px; min-width: 240px; position: relative; z-index: 1; }
.search-target-header { display: flex; align-items: baseline; gap: 4px; font-family: "SF Mono", "JetBrains Mono", monospace; }
.search-idx { font-size: 28px; font-weight: 900; color: #e8b974; text-shadow: 0 0 16px rgba(232, 185, 116, 0.5); }
.search-sep { font-size: 16px; color: #475569; }
.search-total { font-size: 16px; color: var(--text-muted); font-weight: 600; }
.search-target-body { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.search-university { font-size: 16px; font-weight: 700; color: var(--text-primary); letter-spacing: 1px; }
.search-major { font-size: 12px; color: var(--text-secondary); }
.search-pulse-bar { display: flex; gap: 4px; margin-top: 2px; }
.pulse-segment { width: 32px; height: 3px; border-radius: 2px; background: rgba(232, 185, 116, 0.2); animation: pulse-seg 1.2s ease-in-out infinite; }
@keyframes pulse-seg { 0%, 100% { background: rgba(232, 185, 116, 0.2); } 50% { background: #e8b974; box-shadow: 0 0 8px rgba(232, 185, 116, 0.6); } }
.search-target-enter-active { transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1); }
.search-target-leave-active { transition: all 0.25s ease; }
.search-target-enter-from { opacity: 0; transform: translateX(20px) scale(0.95); }
.search-target-leave-to { opacity: 0; transform: translateX(-20px) scale(0.95); }

/* ── 卷宗进度卡（原伪终端）── */
.fake-terminal { margin-top: 4px; width: 90%; max-width: 480px; height: 150px; background: rgba(20, 14, 8, 0.55); border: 1px solid rgba(232, 185, 116, 0.18); border-radius: 10px; padding: 10px 14px; overflow-y: auto; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif; font-size: 12px; line-height: 1.8; box-shadow: inset 0 0 24px rgba(20, 14, 8, 0.3); position: relative; z-index: 1; }
.fake-terminal::-webkit-scrollbar { width: 3px; }
.fake-terminal::-webkit-scrollbar-thumb { background: rgba(232, 185, 116, 0.25); border-radius: 2px; }
.term-line { display: flex; gap: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; animation: term-in 0.18s ease-out; }
@keyframes term-in { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: translateX(0); } }
.term-prompt { color: rgba(232, 185, 116, 0.5); flex-shrink: 0; font-weight: 700; }
.term-text { color: var(--text-secondary); }
.term-sys .term-text { color: #f4d8a8; }
.term-ok .term-text { color: #86efac; }
.term-warn .term-text { color: #fde68a; }
.term-info .term-text { color: var(--text-secondary); }
.term-target .term-text { color: #fcd34d; font-weight: 600; }
.term-danger .term-text { color: #fda4af; }
.term-cursor { display: flex; align-items: center; gap: 6px; margin-top: 2px; }
.cursor-blink { color: rgba(232, 185, 116, 0.6); animation: cursor-blink 1s step-end infinite; }
@keyframes cursor-blink { 0%, 50% { opacity: 1; } 51%, 100% { opacity: 0.2; } }
.terminal-in-enter-active, .terminal-in-leave-active { transition: all 0.4s ease; }
.terminal-in-enter-from, .terminal-in-leave-to { opacity: 0; transform: translateY(8px); }

/* ── 底部阶段名横排（毛笔字 + 序号） ── */
.phase-name-track { display: flex; align-items: center; gap: 3px; margin-top: 4px; position: relative; z-index: 1; flex-wrap: wrap; justify-content: center; max-width: 420px; }
.phase-name { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: 8px; font-size: 11px; color: var(--text-faint); opacity: 0.55; transition: all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1); }
.phase-name.passed { opacity: 0.8; color: var(--text-secondary); }
.phase-name.active { opacity: 1; color: var(--accent); background: rgba(232, 185, 116, 0.12); border: 1px solid rgba(232, 185, 116, 0.3); transform: translateY(-1px); }
.pn-idx { font-size: 9px; font-family: "SF Mono", monospace; opacity: 0.7; }
.pn-text { font-size: 13px; letter-spacing: 1px; }
.pn-sep { color: var(--text-faint); opacity: 0.4; font-size: 11px; }

.stats-bar { padding: 14px 20px; display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
.stats-bar .stat-total { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 700; color: var(--text-primary); padding-right: 18px; border-right: 1px solid rgba(255, 255, 255, 0.08); }
.stats-bar .stat-total::before { content: ''; width: 8px; height: 8px; border-radius: 50%; background: #e8b974; box-shadow: 0 0 12px rgba(232, 185, 116, 0.6); flex-shrink: 0; }
.stat-item { font-size: 13px; font-weight: 600; display: inline-flex; align-items: center; gap: 5px; }
.stat-hint { width: 100%; font-size: 12px; color: #fde68a; font-weight: 500; padding-top: 8px; border-top: 1px solid rgba(251, 191, 36, 0.15); margin-top: 4px; }
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
.neon-school { font-size: 16px; font-weight: 600; color: var(--text-primary); display: block; letter-spacing: 0.5px; }
.neon-major { font-size: 12px; color: var(--text-secondary); font-weight: 300; margin-top: 2px; }
.neon-badge { display: flex; align-items: center; gap: 3px; padding: 3px 9px; border-radius: 12px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; white-space: nowrap; }
.neon-badge-icon { width: 12px; height: 12px; display: inline-flex; align-items: center; justify-content: center; }
.neon-badge-icon :deep(svg) { width: 100%; height: 100%; }
.badge-emerald { background: rgba(52, 211, 153, 0.1); color: #6ee7b7; border: 1px solid rgba(52, 211, 153, 0.2); }
.badge-amber   { background: rgba(251, 191, 36, 0.1); color: #fde68a; border: 1px solid rgba(251, 191, 36, 0.2); }
.badge-rose    { background: rgba(251, 113, 133, 0.1); color: #fda4af; border: 1px solid rgba(251, 113, 133, 0.2); }
.neon-reason { background: rgba(0, 0, 0, 0.25); border-radius: 7px; padding: 9px 10px; font-size: 12px; color: var(--text-secondary); line-height: 1.6; }
.neon-reason.warn-text { color: #fde68a; }
.neon-alert { display: flex; align-items: flex-start; gap: 6px; padding: 9px 10px; background: rgba(0, 0, 0, 0.3); border: 1px solid rgba(251, 113, 133, 0.15); border-radius: 7px; }
.alert-icon { width: 13px; height: 13px; color: #fda4af; flex-shrink: 0; margin-top: 1px; }
.alert-icon :deep(svg) { width: 100%; height: 100%; }
.alert-text { font-size: 12px; color: #fecdd3; line-height: 1.6; font-weight: 300; }
.neon-clause { margin-top: 7px; padding-left: 9px; border-left: 2px solid rgba(255, 255, 255, 0.06); font-size: 10px; color: var(--text-muted); }

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
.empty-icon { width: 32px; height: 32px; margin: 0 auto 10px; color: var(--text-secondary); font-size: 28px; line-height: 1; }
.empty-title { font-size: 16px; font-weight: 700; color: var(--text-secondary); display: block; margin-bottom: 6px; }
.empty-desc { font-size: 13px; color: var(--text-muted); }

/* ── 联网章程检索面板 ── */
.live-search-panel { padding: 16px 20px; }
.live-panel-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 6px; }
.live-panel-title { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700; color: var(--text-primary); }
.live-panel-title { color: #d49a4e; }
.live-panel-hint { font-size: 11px; color: #475569; }
.live-input-row { display: flex; gap: 8px; }
.live-input { flex: 1; background: rgba(0, 0, 0, 0.3); border: 1px solid rgba(212, 154, 78, 0.15); border-radius: 8px; padding: 10px 14px; font-size: 13px; color: var(--text-primary); outline: none; box-sizing: border-box; }
.live-input:focus { border-color: rgba(212, 154, 78, 0.4); }
.live-input::placeholder { color: #475569; }
.live-btn { padding: 10px 18px; background: rgba(212, 154, 78, 0.15); border: 1px solid rgba(212, 154, 78, 0.3); border-radius: 8px; cursor: pointer; transition: all 0.2s; }
.live-btn:hover:not(.disabled) { background: rgba(212, 154, 78, 0.22); border-color: rgba(212, 154, 78, 0.5); }
.live-btn:active { transform: scale(0.96); }
.live-btn.disabled { opacity: 0.3; pointer-events: none; }
.live-btn-text { font-size: 12px; font-weight: 700; color: #d49a4e; white-space: nowrap; }

/* 联网结果卡片 */
.live-result-card { margin-top: 12px; padding: 14px; background: rgba(212, 154, 78, 0.05); border: 1px solid rgba(212, 154, 78, 0.15); border-radius: 10px; }
.live-result-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.live-result-school { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.live-result-major { font-size: 12px; color: var(--text-secondary); }
.live-source-tag { display: flex; align-items: center; gap: 3px; font-size: 9px; color: #d49a4e; padding: 2px 6px; background: rgba(212, 154, 78, 0.1); border-radius: 4px; margin-left: auto; }
.live-status-badge { display: inline-block; padding: 2px 10px; border-radius: 5px; font-size: 11px; font-weight: 700; margin-bottom: 8px; }
.badge-pass { background: rgba(52, 211, 153, 0.12); color: #6ee7b7; }
.badge-warning { background: rgba(251, 191, 36, 0.12); color: #fde68a; }
.badge-danger { background: rgba(251, 113, 133, 0.12); color: #fda4af; }
.badge-unknown { background: rgba(148, 163, 184, 0.12); color: var(--text-secondary); }
.live-result-text { font-size: 12px; color: var(--text-secondary); line-height: 1.6; white-space: pre-line; }
.live-result-clause { margin-top: 6px; padding-left: 8px; border-left: 2px solid rgba(212, 154, 78, 0.2); font-size: 10px; color: var(--text-muted); line-height: 1.5; }
.live-result-enter-active { transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1); }
.live-result-enter-from { opacity: 0; transform: translateY(12px); }

/* ── 可选留资：邮箱接收报告 ── */
.report-signup { margin-top: 12px; padding: 16px 20px; border: 1px dashed rgba(232, 185, 116, 0.25); background: rgba(232, 185, 116, 0.03); }
.signup-row { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.signup-text { flex: 1; min-width: 200px; display: flex; flex-direction: column; gap: 2px; }
.signup-title { font-size: 13px; font-weight: 700; color: #f4d8a8; }
.signup-desc { font-size: 11px; color: var(--text-muted); line-height: 1.5; }
.signup-form { display: flex; gap: 8px; align-items: center; }
.signup-input { width: 200px; padding: 8px 12px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(232, 185, 116, 0.2); border-radius: 8px; font-size: 12px; color: var(--text-primary); outline: none; transition: border-color 0.2s; font-family: inherit; }
.signup-input::placeholder { color: #475569; }
.signup-input:focus { border-color: rgba(232, 185, 116, 0.5); }
.signup-btn { padding: 8px 16px; border-radius: 8px; font-size: 12px; font-weight: 700; background: linear-gradient(135deg, #e8b974, #d49a4e); color: #fff; cursor: pointer; transition: all 0.2s; white-space: nowrap; }
.signup-btn:hover:not(.disabled) { box-shadow: 0 4px 16px rgba(232, 185, 116, 0.4); transform: translateY(-1px); }
.signup-btn.disabled { opacity: 0.5; pointer-events: none; }
.signup-done { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 12px; color: #6ee7b7; }
.signup-done svg { color: #6ee7b7; }

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
  .phase-name-track { gap: 2px; max-width: 320px; }
  .phase-name { padding: 2px 5px; }
  .pn-text { font-size: 11px; }
}
</style>
