/**
 * AI 顾问 Store — 聊天历史 + SSE 流式接收
 */
import { defineStore } from "pinia";
import { ref, computed } from "vue";
import type { ChatMessage } from "../api";

export interface AdvisorMessage extends ChatMessage {
  id: string;
  /** 流式输出中 */
  streaming?: boolean;
  /** 联网检索到的知识（前置展示） */
  knowledge?: string;
  /** 联网搜索结果（前置展示） */
  live?: string;
  /** 引用来源 */
  sources?: string[];
  /** 数据可信度 */
  data_trust_level?: string;
  /** 后续建议问题 */
  suggestions?: string[];
}

export const useAdvisorStore = defineStore("advisor", () => {
  const messages = ref<AdvisorMessage[]>([]);
  const loading = ref(false);
  const error = ref("");

  const history = computed(() =>
    messages.value
      .filter(m => !m.streaming)
      .map(m => ({ role: m.role, content: m.content }))
  );

  const lastSuggestions = computed(() => {
    const last = [...messages.value].reverse().find(m => m.role === "assistant" && m.suggestions?.length);
    return last?.suggestions ?? [];
  });

  function addMessage(msg: AdvisorMessage) {
    messages.value.push(msg);
  }

  function updateLastAssistant(updates: Partial<AdvisorMessage>) {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].role === "assistant") {
        messages.value[i] = { ...messages.value[i], ...updates };
        return;
      }
    }
  }

  function appendToLastAssistant(text: string) {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].role === "assistant" && messages.value[i].streaming) {
        messages.value[i].content += text;
        return;
      }
    }
  }

  function clear() {
    messages.value = [];
    error.value = "";
    loading.value = false;
  }

  function genId() {
    return "msg_" + Date.now() + "_" + Math.random().toString(36).slice(2, 6);
  }

  return {
    messages, loading, error, history, lastSuggestions,
    addMessage, updateLastAssistant, appendToLastAssistant, clear, genId,
  };
});
