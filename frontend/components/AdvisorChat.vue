<!--
  components/AdvisorChat.vue — AI 顾问聊天界面
  SSE 流式接收：knowledge → live → token → done
-->
<script setup lang="ts">
import { ref, computed, onBeforeUnmount, nextTick } from "vue"
import { useProfileStore } from "../stores/profile"
import { useAdvisorStore, type AdvisorMessage } from "../stores/advisor"
import { startAdvisorStream } from "../api/index"
import { toast } from "../utils/toast"
import Icon from "./Icon.vue"

const profileStore = useProfileStore()
const advisorStore = useAdvisorStore()

const inputText = ref("")
const scrollRef = ref<HTMLDivElement | null>(null)
let currentES: EventSource | null = null

const suggestions = computed(() => advisorStore.lastSuggestions)

function scrollToBottom() {
  nextTick(() => {
    const el = scrollRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function sendMessage(message?: string) {
  const text = (message ?? inputText.value).trim()
  if (!text || advisorStore.loading) return

  // 档案校验：未完善时提示引导
  if (!profileStore.isProfileComplete) {
    toast("请先完善考生档案（省份、分数、选科）")
    return
  }

  advisorStore.addMessage({ id: advisorStore.genId(), role: "user", content: text })
  inputText.value = ""
  advisorStore.loading = true

  const assistantId = advisorStore.genId()
  advisorStore.addMessage({ id: assistantId, role: "assistant", content: "", streaming: true })
  scrollToBottom()

  currentES = startAdvisorStream(
    text,
    advisorStore.history.slice(0, -1),
    profileStore.profile,
    {
      onKnowledge(k) { advisorStore.updateLastAssistant({ knowledge: k }); scrollToBottom() },
      onLive(live) { advisorStore.updateLastAssistant({ live }); scrollToBottom() },
      onToken(token) { advisorStore.appendToLastAssistant(token); scrollToBottom() },
      onDone(data) {
        advisorStore.updateLastAssistant({ streaming: false, sources: data.sources, data_trust_level: data.data_trust_level, suggestions: data.suggestions })
        advisorStore.loading = false
        scrollToBottom()
      },
      onError(msg) {
        advisorStore.updateLastAssistant({ streaming: false })
        advisorStore.loading = false
        toast.error(msg)
      },
    },
  )
}

const quickQuestions = [
  "我的分数能上什么学校？",
  "计算机专业就业前景如何？",
  "色弱能报临床医学吗？",
  "物理类550分怎么冲稳保？",
]

onBeforeUnmount(() => { currentES?.close() })
</script>

<template>
  <div class="advisor-layout">
    <!-- 消息列表 -->
    <div class="messages-scroll custom-scrollbar" ref="scrollRef">
      <!-- 空状态 -->
      <div v-if="advisorStore.messages.length === 0" class="empty-state">
        <div class="empty-icon"><Icon name="candle" :size="32" /></div>
        <span class="empty-title">AI 志愿顾问</span>
        <span class="empty-desc">基于 135 所大学章程 + 雪峰知识库 + 联网搜索，<br/>把你的困惑问出来，我陪你一起想清楚</span>
        <div class="empty-poetry">
          <span class="poetry-line font-brush">山重水复疑无路</span>
          <span class="poetry-sub">— 陆游·游山西村 · 柳暗花明又一村</span>
        </div>
        <div class="quick-questions">
          <div v-for="q in quickQuestions" :key="q" class="quick-q" @click="sendMessage(q)">{{ q }}</div>
        </div>
      </div>

      <!-- 消息气泡 -->
      <div v-for="msg in advisorStore.messages" :key="msg.id" class="msg-row" :class="msg.role">
        <!-- 用户消息 -->
        <div v-if="msg.role === 'user'" class="msg-bubble user-bubble">
          {{ msg.content }}
        </div>

        <!-- AI 消息 -->
        <div v-else class="msg-bubble ai-bubble">
          <!-- 知识检索前置 -->
          <div v-if="msg.knowledge" class="ai-prelude">
            <span class="prelude-label"><Icon name="database" :size="11" /> 知识检索</span>
            <span class="prelude-text">{{ msg.knowledge.substring(0, 200) }}{{ msg.knowledge.length > 200 ? '...' : '' }}</span>
          </div>
          <!-- 联网搜索前置 -->
          <div v-if="msg.live" class="ai-prelude live-prelude">
            <span class="prelude-label"><Icon name="radar" :size="11" /> 联网搜索</span>
            <span class="prelude-text">{{ msg.live.substring(0, 200) }}{{ msg.live.length > 200 ? '...' : '' }}</span>
          </div>

          <!-- 回复正文 -->
          <div class="ai-content" v-if="msg.content">{{ msg.content }}<span v-if="msg.streaming" class="typing-cursor">▋</span></div>
          <div v-else-if="msg.streaming" class="ai-thinking">
            <span class="thinking-dot" /><span class="thinking-dot d2" /><span class="thinking-dot d3" />
          </div>

          <!-- 来源 -->
          <div v-if="msg.sources && msg.sources.length" class="ai-sources">
            <span class="source-label">来源:</span>
            <a v-for="(src, i) in msg.sources.slice(0, 3)" :key="i" :href="src" target="_blank" rel="noopener" class="source-link">{{ src.length > 35 ? src.substring(0, 35) + '...' : src }}</a>
          </div>

          <!-- 数据可信度 -->
          <div v-if="msg.data_trust_level" class="ai-trust">
            <span class="trust-badge" :class="'trust-' + msg.data_trust_level.toLowerCase()">{{ msg.data_trust_level }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 建议追问 -->
    <Transition name="suggestions">
      <div v-if="suggestions.length && !advisorStore.loading" class="suggestions-bar">
        <div v-for="s in suggestions" :key="s" class="suggestion-chip" @click="sendMessage(s)">{{ s }}</div>
      </div>
    </Transition>

    <!-- 输入栏 -->
    <div class="input-bar">
      <input
        v-model="inputText"
        type="text"
        class="input-field"
        placeholder="把你的问题写在这里..."
        :disabled="advisorStore.loading"
        @keydown.enter="sendMessage()"
      />
      <div class="send-btn" :class="{ disabled: !inputText.trim() || advisorStore.loading }" @click="sendMessage()">
        <Icon name="arrowRight" :size="16" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.advisor-layout { display: flex; flex-direction: column; height: 100%; min-height: 400px; position: relative; }

/* ── 消息列表 ── */
.messages-scroll { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }

/* ── 空状态 ── */
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; text-align: center; gap: 8px; }
.empty-icon { color: #e8b974; margin-bottom: 4px; }
.empty-title { font-size: 18px; font-weight: 700; color: var(--text-primary); }
.empty-desc { font-size: 12px; color: var(--text-muted); max-width: 320px; line-height: 1.6; }
.empty-poetry { display: flex; flex-direction: column; align-items: center; gap: 2px; margin-top: 6px; padding: 8px 18px; background: rgba(232, 185, 116, 0.04); border: 1px solid rgba(232, 185, 116, 0.12); border-radius: 10px; }
.poetry-line { font-size: 16px; color: #e8b974; font-weight: 400; letter-spacing: 3px; }
.poetry-sub { font-size: 10px; color: var(--text-muted); letter-spacing: 1px; }
.quick-questions { display: flex; flex-direction: column; gap: 8px; margin-top: 16px; width: 100%; max-width: 320px; }
.quick-q { padding: 10px 14px; background: rgba(232, 185, 116, 0.06); border: 1px solid rgba(232, 185, 116, 0.15); border-radius: 10px; font-size: 13px; color: #f4d8a8; cursor: pointer; transition: all 0.2s; text-align: left; }
.quick-q:hover { background: rgba(232, 185, 116, 0.12); border-color: rgba(232, 185, 116, 0.3); }

/* ── 消息气泡 ── */
.msg-row { display: flex; }
.msg-row.user { justify-content: flex-end; }
.msg-row.assistant { justify-content: flex-start; }
.msg-bubble { max-width: 80%; padding: 12px 16px; border-radius: 14px; font-size: 13px; line-height: 1.6; }
.user-bubble { background: linear-gradient(135deg, #e8b974, #d49a4e); color: #fff; border-bottom-right-radius: 4px; }
.ai-bubble { background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); color: var(--text-primary); border-bottom-left-radius: 4px; }

/* ── AI 前置信息 ── */
.ai-prelude { margin-bottom: 8px; padding: 6px 10px; background: rgba(232, 185, 116, 0.05); border-radius: 7px; border: 1px solid rgba(232, 185, 116, 0.1); }
.live-prelude { background: rgba(212, 154, 78, 0.05); border-color: rgba(212, 154, 78, 0.1); }
.prelude-label { display: flex; align-items: center; gap: 4px; font-size: 10px; font-weight: 700; color: #f4d8a8; letter-spacing: 1px; margin-bottom: 3px; }
.live-prelude .prelude-label { color: #d49a4e; }
.prelude-text { font-size: 11px; color: var(--text-muted); line-height: 1.5; display: block; }

/* ── AI 正文 ── */
.ai-content { white-space: pre-wrap; word-break: break-word; overflow-wrap: break-word; }
.typing-cursor { color: #e8b974; animation: cursor-blink 0.8s step-end infinite; }
@keyframes cursor-blink { 0%, 50% { opacity: 1; } 51%, 100% { opacity: 0; } }

/* ── 思考中动画（柔和呼吸）── */
.ai-thinking { display: flex; gap: 4px; padding: 4px 0; }
.thinking-dot { width: 6px; height: 6px; border-radius: 50%; background: #e8b974; animation: thinking-bounce 1.4s infinite; }
.thinking-dot.d2 { animation-delay: 0.2s; }
.thinking-dot.d3 { animation-delay: 0.4s; }
@keyframes thinking-bounce { 0%, 60%, 100% { transform: translateY(0); opacity: 0.4; } 30% { transform: translateY(-3px); opacity: 1; } }

/* ── 来源 ── */
.ai-sources { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; padding-top: 6px; border-top: 1px solid rgba(255, 255, 255, 0.05); }
.source-label { font-size: 10px; color: #475569; }
.source-link { font-size: 10px; color: #e8b974; text-decoration: none; }
.source-link:hover { text-decoration: underline; }

/* ── 可信度 ── */
.ai-trust { margin-top: 6px; }
.trust-badge { font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 4px; font-family: "SF Mono", monospace; }
.trust-t1 { background: rgba(52, 211, 153, 0.12); color: #6ee7b7; }
.trust-t2 { background: rgba(232, 185, 116, 0.12); color: #f4d8a8; }
.trust-t3 { background: rgba(251, 191, 36, 0.12); color: #fde68a; }
.trust-t4 { background: rgba(148, 163, 184, 0.12); color: var(--text-secondary); }

/* ── 建议追问 ── */
.suggestions-bar { display: flex; gap: 6px; padding: 8px 16px; flex-wrap: wrap; border-top: 1px solid rgba(255, 255, 255, 0.04); position: relative; z-index: 1; }
.suggestion-chip { padding: 5px 12px; background: rgba(212, 154, 78, 0.1); border: 1px solid rgba(212, 154, 78, 0.2); border-radius: 16px; font-size: 11px; color: #d49a4e; cursor: pointer; transition: all 0.2s; }
.suggestion-chip:hover { background: rgba(212, 154, 78, 0.18); }
.suggestions-enter-active, .suggestions-leave-active { transition: all 0.3s ease; }
.suggestions-enter-from, .suggestions-leave-to { opacity: 0; transform: translateY(8px); }

/* ── 输入栏 ── */
.input-bar { display: flex; gap: 8px; padding: 12px 16px; border-top: 1px solid rgba(255, 255, 255, 0.06); position: relative; z-index: 1; }
.input-field { flex: 1; background: rgba(0, 0, 0, 0.3); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 10px 14px; font-size: 13px; color: var(--text-primary); outline: none; box-sizing: border-box; }
.input-field:focus { border-color: rgba(232, 185, 116, 0.4); }
.input-field::placeholder { color: #475569; }
.send-btn { width: 40px; height: 40px; background: linear-gradient(135deg, #e8b974, #d49a4e); border-radius: 10px; display: flex; align-items: center; justify-content: center; color: #fff; cursor: pointer; transition: all 0.2s; flex-shrink: 0; }
.send-btn:active { transform: scale(0.94); }
.send-btn.disabled { opacity: 0.3; pointer-events: none; }

@media (max-width: 768px) {
  .advisor-layout { min-height: 70vh; }
  .msg-bubble { max-width: 90%; font-size: 12px; padding: 10px 12px; }
  .quick-questions { max-width: 100%; }
  .quick-q { font-size: 12px; padding: 8px 12px; }
  .messages-scroll { padding: 12px; gap: 8px; }
  .input-field { font-size: 12px; }
  .empty-title { font-size: 16px; }
  .empty-desc { font-size: 11px; }
  .ai-prelude { padding: 5px 8px; }
  .prelude-text { font-size: 10px; }
}
</style>
