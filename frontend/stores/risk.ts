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

  async function runTerminalAnimation(targets: { university: string; major: string }[]) {
    log("[INIT] 正在建立与招生办大数据库的安全连接...", "info");
    await delay(300);
    log("[AUTH] 获取 2026 最新《高考招生章程》PDF 权限 [SUCCESS]", "success");
    await delay(400);
    log(`[PARSE] 装载考生档案 | 待审目标: ${targets.length} 个`, "highlight");
    await delay(300);
    log("————————————————————————————", "info");
    await delay(200);

    for (const t of targets) {
      log(`>>> 开始提取目标: 【${t.university}】${t.major}`, "highlight");
      await delay(350);
      log(`[RAG] 正在向量化检索《${t.university}2026招生章程》...`, "info");
      await delay(450 + Math.random() * 300);
      log(`[AI-REASON] 匹配条款中... 核对单科、体检、语种限制`, "info");
      await delay(300 + Math.random() * 350);
      log(`✓ 【${t.university}】审查完毕`, "success");
    }

    await delay(400);
    log("————————————————————————————", "info");
    log("[COMPLETE] 逻辑推理完毕，正在生成可视化报告...", "highlight");
    await delay(500);
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
    log, resetTerminal, runTerminalAnimation, setResults, setLastTargets, clear,
  };
});

function delay(ms: number) { return new Promise(r => setTimeout(r, ms)); }
