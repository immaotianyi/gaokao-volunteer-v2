/**
 * 志愿探雷器 Store — V4 PC Terminal 版
 *
 * 新增 terminalLogs: 不限长度、带类型标识的日志列表，供右侧 Terminal 面板渲染。
 */
import { defineStore } from "pinia";
import { ref } from "vue";

export interface TerminalEntry {
  text: string;
  type: "info" | "success" | "warn" | "error" | "highlight";
  ts: number;
}

export interface RiskTarget {
  university: string;
  major: string;
}

export interface RiskResult extends RiskTarget {
  status: "PASS" | "WARNING" | "DANGER" | "UNKNOWN";
  reason: string;
  matched_clause: string;
  /** 就业风险等级: low / medium / high / null */
  career_risk?: string | null;
  /** AI 替代风险等级: low / medium / high / null */
  ai_risk?: string | null;
  /** 数据来源: local / live */
  source?: string;
}

export const useRiskStore = defineStore("risk", () => {
  const results = ref<RiskResult[]>([]);
  const loading = ref(false);
  const error = ref("");
  const checked = ref(false);
  const terminalLogs = ref<TerminalEntry[]>([]);
  // 最近一次提交的志愿草表（供 RadarBoard 判断是否可做定制化捡漏）
  const lastTargets = ref<RiskTarget[]>([]);

  function log(text: string, type: TerminalEntry["type"] = "info") {
    terminalLogs.value.push({ text, type, ts: Date.now() });
  }

  function resetTerminal() {
    terminalLogs.value = [];
  }

  const setResults = (data: RiskResult[]) => {
    results.value = data;
    checked.value = true;
  };

  const setLastTargets = (targets: RiskTarget[]) => {
    lastTargets.value = targets;
  };

  const clear = () => {
    results.value = [];
    checked.value = false;
    error.value = "";
    loading.value = false;
    terminalLogs.value = [];
  };

  return {
    results, loading, error, checked, terminalLogs, lastTargets,
    log, resetTerminal, setResults, setLastTargets, clear,
  };
});
