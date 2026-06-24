/**
 * API 封装 — 统一请求入口
 *
 * 支持：用户档案 / V3 探雷(SSE) / V4 Agent(SSE) / 联网章程 / 捡漏雷达 / AI顾问(SSE) / 支付
 * BASE_URL 通过 Vite 环境变量 VITE_API_BASE_URL 配置：
 *   - 开发: 不设或设为 http://localhost:8000
 *   - 生产: 设为空字符串 "" → 走相对路径，由 nginx 反代 /api 到 backend
 */
import type { LeakageResult } from "../stores/leakage";
import type { RiskResult, RiskTarget } from "../stores/risk";
import type { UserProfile } from "../stores/profile";

// 生产构建时 VITE_API_BASE_URL="" → 走相对路径（nginx 反代）
// 开发时未设 → 默认 localhost:8000
const _envBase = import.meta.env.VITE_API_BASE_URL;
const BASE_URL = _envBase === undefined ? "http://localhost:8000" : _envBase;

// ── 基础 fetch 封装 ─────────────────────────────────────────────

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${url}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  if (!res.ok) {
    let detail = "请求失败";
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }

  return res.json() as Promise<T>;
}

/** 构建 SSE URL 的辅助函数 */
function buildSSEUrl(path: string, params: Record<string, string>): string {
  const qs = new URLSearchParams(params).toString();
  return `${BASE_URL}${path}?${qs}`;
}

// ── 用户档案 ────────────────────────────────────────────────────

export function saveProfile(profile: UserProfile) {
  return request<any>("/api/profile", {
    method: "POST",
    body: JSON.stringify(profile),
  });
}

export function getProfile(userId: string): Promise<UserProfile> {
  return request<UserProfile>(`/api/profile/${userId}`);
}

// ── V3 志愿探雷 ─────────────────────────────────────────────────

export interface CheckRiskPayload {
  profile: Omit<UserProfile, "user_id">;
  targets: RiskTarget[];
}

export function checkRisks(payload: CheckRiskPayload): Promise<{
  total: number;
  results: RiskResult[];
}> {
  return request("/api/check-risk", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface SSECallbacks {
  onLog: (text: string, ts: number) => void;
  onResult: (results: RiskResult[]) => void;
  onDone: () => void;
  onError: (message: string) => void;
}

/** V3 SSE 流式探雷 GET /api/check-risk/stream */
export function startRiskStream(
  profile: Record<string, any>,
  targets: Record<string, string>[],
  callbacks: SSECallbacks,
): EventSource {
  const url = buildSSEUrl("/api/check-risk/stream", {
    profile_json: JSON.stringify(profile),
    targets_json: JSON.stringify(targets),
  });

  return createSSEConnection(url, callbacks);
}

// ── V4 Agent 探雷 ───────────────────────────────────────────────

export interface AgentSSECallbacks extends SSECallbacks {}

/** V4 Agent SSE 流式探雷 GET /api/check-risk/agent/stream */
export function startAgentStream(
  profile: Record<string, any>,
  targets: Record<string, string>[],
  callbacks: AgentSSECallbacks,
  options?: { provider?: string; prompt_mode?: string },
): EventSource {
  const params: Record<string, string> = {
    profile_json: JSON.stringify(profile),
    targets_json: JSON.stringify(targets),
  };
  if (options?.provider) params.provider = options.provider;
  if (options?.prompt_mode) params.prompt_mode = options.prompt_mode;

  const url = buildSSEUrl("/api/check-risk/agent/stream", params);
  return createSSEConnection(url, callbacks);
}

// ── 联网章程实时检索 ────────────────────────────────────────────

export interface LiveCheckResult {
  university: string;
  major: string;
  status: string;
  reason: string;
  matched_clause: string;
  source: string;
}

/** POST /api/check-risk/live — 联网检索非核心高校章程 */
export function checkRiskLive(target: RiskTarget): Promise<LiveCheckResult> {
  return request("/api/check-risk/live", {
    method: "POST",
    body: JSON.stringify(target),
  });
}

// ── 捡漏雷达 ────────────────────────────────────────────────────

export interface LeakageRadarParams {
  province: string;
  subject_group: string;
  batch?: string;
  school_types?: string[];
  min_score?: number;
  max_score?: number;
  user_score?: number;
  user_subjects_detail?: string;
  score_tolerance?: number;
}

export function runLeakageRadar(params: LeakageRadarParams): Promise<LeakageResult> {
  return request("/api/leakage-radar", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function refreshRadarCache(): Promise<{ status: string; deleted_keys: number }> {
  return request("/api/leakage-radar/refresh-cache", { method: "POST" });
}

// ── AI 顾问 ─────────────────────────────────────────────────────

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AdvisorRequest {
  message: string;
  history?: ChatMessage[];
  profile?: Omit<UserProfile, "user_id">;
}

export interface AdvisorResponse {
  reply: string;
  sources?: string[];
  data_trust_level?: string;
  suggestions?: string[];
}

/** POST /api/advisor — 同步聊天 */
export function advisorChat(payload: AdvisorRequest): Promise<AdvisorResponse> {
  return request("/api/advisor", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface AdvisorSSECallbacks {
  onKnowledge?: (text: string) => void;
  onLive?: (text: string) => void;
  onToken?: (token: string) => void;
  onDone?: (data: { sources?: string[]; data_trust_level?: string; suggestions?: string[] }) => void;
  onError?: (message: string) => void;
}

/** GET /api/advisor/stream — SSE 流式聊天 */
export function startAdvisorStream(
  message: string,
  history: ChatMessage[],
  profile: Record<string, any> | null,
  callbacks: AdvisorSSECallbacks,
): EventSource {
  const params: Record<string, string> = { message };
  if (history.length) params.history_json = JSON.stringify(history);
  if (profile) params.profile_json = JSON.stringify(profile);

  const url = buildSSEUrl("/api/advisor/stream", params);
  const es = new EventSource(url);

  es.onmessage = (event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data);
      switch (data.type) {
        case "knowledge":
          callbacks.onKnowledge?.(data.data);
          break;
        case "live":
          callbacks.onLive?.(data.data);
          break;
        case "token":
          callbacks.onToken?.(data.data);
          break;
        case "done":
          callbacks.onDone?.(data.data || {});
          es.close();
          break;
        case "error":
          callbacks.onError?.(data.data || "顾问服务异常");
          es.close();
          break;
      }
    } catch { /* ignore non-JSON */ }
  };

  es.onerror = () => {
    // readyState === CLOSED 表示连接已彻底断开
    if (es.readyState === EventSource.CLOSED) {
      callbacks.onError?.("顾问连接已断开，请重新提问");
    }
    // CONNECTING 状态表示浏览器正在自动重连，不报错
  };

  return es;
}

// ── 支付 ────────────────────────────────────────────────────────

export interface QrcodeResponse {
  order_id: string;
  qrcode_url: string;
  code_url?: string | null;  // 真实模式的 weixin:// 链接
  amount: number;            // 单位：分
  mode: string;              // real | mock
}

export interface PaymentStatus {
  order_id: string;
  status: string;
  poll_count: number;
  mode: string;
}

export interface PayMode {
  mode: string;  // real | mock
}

export function generateQrcode(userId: string): Promise<QrcodeResponse> {
  return request("/api/pay/qrcode", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export function pollPaymentStatus(orderId: string): Promise<PaymentStatus> {
  return request(`/api/pay/status/${orderId}`);
}

/** 查询当前支付模式（real=真实微信支付 / mock=演示模式） */
export function getPayMode(): Promise<PayMode> {
  return request("/api/pay/mode");
}

// ── 分数-位次映射 ──────────────────────────────────────────────

export interface ScoreRankResult {
  score: number
  rank: number
  subject_group: string
  year: number
  province: string
}

export interface ScoreRangeResult {
  score: number
  rank: number
  min_score: number
  max_score: number
  min_rank: number
  max_rank: number
  tolerance: number
  subject_group: string
  year: number
  province: string
}

/** 分数 → 位次 */
export function scoreToRank(score: number, subjectGroup: string, year = 2025): Promise<ScoreRankResult> {
  return request(`/api/score-rank/convert?score=${score}&subject_group=${encodeURIComponent(subjectGroup)}&year=${year}`)
}

/** 分数区间 → 位次区间 */
export function scoreToRankRange(score: number, subjectGroup: string, tolerance = 5, year = 2025): Promise<ScoreRangeResult> {
  return request(`/api/score-rank/range?score=${score}&subject_group=${encodeURIComponent(subjectGroup)}&tolerance=${tolerance}&year=${year}`)
}

/** 位次 → 分数（反查） */
export function rankToScore(rank: number, subjectGroup: string, year = 2025): Promise<ScoreRankResult> {
  return request(`/api/score-rank/reverse?rank=${rank}&subject_group=${encodeURIComponent(subjectGroup)}&year=${year}`)
}

// ── SSE 连接通用工厂（带自动重连） ──────────────────────────────

/** 带重连能力的 SSE 连接包装器 */
class ReconnectingSSE {
  private url: string
  private callbacks: SSECallbacks
  private es: EventSource | null = null
  private retryCount = 0
  private maxRetries = 2
  private retryDelay = 1500
  private closed = false
  private resultReceived = false

  constructor(url: string, callbacks: SSECallbacks) {
    this.url = url
    this.callbacks = callbacks
    this.connect()
  }

  private connect() {
    if (this.closed) return
    this.es = new EventSource(this.url)

    this.es.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data)
        switch (data.type) {
          case "log":
            this.callbacks.onLog(data.text, data.ts ?? Date.now())
            break
          case "result":
            this.resultReceived = true
            this.callbacks.onResult(data.data ?? [])
            break
          case "done":
            this.callbacks.onDone()
            this.close()
            break
          default:
            break
        }
      } catch { /* non-JSON, ignore */ }
    }

    this.es.onerror = () => {
      this.es?.close()
      this.es = null

      // 如果已经收到结果，说明是正常结束后的断开，不重连
      if (this.resultReceived || this.closed) {
        return
      }

      // 未收到结果 → 尝试重连
      if (this.retryCount < this.maxRetries) {
        this.retryCount++
        this.callbacks.onLog(`[RECONNECT] 第 ${this.retryCount}/${this.maxRetries} 次重连中...`, Date.now())
        setTimeout(() => this.connect(), this.retryDelay)
      } else {
        this.callbacks.onError(`SSE 连接中断（已重试 ${this.maxRetries} 次失败）`)
      }
    }
  }

  close() {
    this.closed = true
    this.es?.close()
    this.es = null
  }
}

function createSSEConnection(url: string, callbacks: SSECallbacks): EventSource {
  const wrapper = new ReconnectingSSE(url, callbacks)
  // 返回一个伪 EventSource 以兼容现有调用（close 方法可用）
  const fakeES = {
    close: () => wrapper.close(),
    readyState: 0,
  } as unknown as EventSource
  return fakeES
}
