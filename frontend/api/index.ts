/**
 * API 封装 — 统一请求入口
 *
 * 支持：用户档案 / V3 探雷(SSE) / V4 Agent(SSE) / 联网章程 / 捡漏雷达 / AI顾问(SSE) / 支付
 * BASE_URL 通过 Vite 环境变量 VITE_API_BASE_URL 配置：
 *   - 开发: 不设或设为 http://localhost:8000
 *   - 生产: 设为空字符串 "" → 走相对路径，由 nginx 反代 /api 到 backend
 */
import type { LeakageResult, LeakageOpportunity } from "../stores/leakage";
import type { RiskResult, RiskTarget } from "../stores/risk";
import type { UserProfile } from "../stores/profile";

// 生产构建时 VITE_API_BASE_URL="" → 走相对路径（nginx 反代）
// 开发时未设 → 默认 localhost:8000
const _envBase = import.meta.env.VITE_API_BASE_URL;
const BASE_URL = _envBase === undefined ? "http://localhost:8000" : _envBase;

// ── 基础 fetch 封装 ─────────────────────────────────────────────

/** 默认请求超时 30s */
const DEFAULT_REQUEST_TIMEOUT = 30_000;

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  // 拆出 headers/signal，避免 ...options 覆盖合并后的 headers
  const { headers: customHeaders, signal: callerSignal, ...rest } = options;

  // 内置 AbortController：默认 30s 超时；同时响应 caller 传入的 signal
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DEFAULT_REQUEST_TIMEOUT);
  if (callerSignal) {
    if (callerSignal.aborted) controller.abort();
    else callerSignal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  try {
    const res = await fetch(`${BASE_URL}${url}`, {
      ...rest,
      headers: { "Content-Type": "application/json", ...(customHeaders || {}) },
      signal: controller.signal,
    });

    if (!res.ok) {
      let detail = "请求失败";
      try {
        const body = await res.json();
        if (body?.detail) {
          // detail 可能是字符串或对象，统一转成字符串避免 [object Object]
          detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
        }
      } catch { /* ignore */ }
      throw new Error(detail);
    }

    return res.json() as Promise<T>;
  } catch (e: unknown) {
    if (e instanceof Error && e.name === "AbortError") {
      // 区分 caller 主动取消 vs 超时
      throw new Error(callerSignal?.aborted ? "请求已取消" : "请求超时，请稍后重试");
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

/** 构建 SSE URL 的辅助函数 */
function buildSSEUrl(path: string, params: Record<string, string>): string {
  const qs = new URLSearchParams(params).toString();
  return `${BASE_URL}${path}?${qs}`;
}

// ── 用户档案 ────────────────────────────────────────────────────

/** 保存档案的响应（后端只返回 user_id 与状态，不回传完整档案） */
export interface ProfileSaveResponse {
  user_id: string;
  status: "saved" | "updated" | "error";
  message?: string;
}

export function saveProfile(profile: UserProfile): Promise<ProfileSaveResponse> {
  return request<ProfileSaveResponse>("/api/profile", {
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
  profile: UserProfile,
  targets: RiskTarget[],
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
  profile: UserProfile,
  targets: RiskTarget[],
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
  source: string;             // "local" | "live"
  rules: Record<string, any>; // 嵌套对象，前端不要直接渲染为字符串（会显示 [object Object]）
  rules_text: string;         // ✅ 可读文本，前端用这个渲染
  message?: string;           // 辅助提示
  error?: string;             // 联网检索失败时的错误信息
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

// ── 定制化捡漏雷达（结合志愿草表） ─────────────────────────────

export interface CustomLeakageTarget {
  university: string;
  major: string;
}

export interface CustomLeakagePayload {
  profile: Omit<UserProfile, "user_id">;
  subject_group: string;
  targets: CustomLeakageTarget[];
  score_tolerance?: number;
}

export interface TargetLeakageSummary {
  university: string;
  major: string;
  opportunity_count: number;
  best_score: number | null;
  best_type: string | null;
}

export interface CustomLeakageResult {
  total: number;
  preview: LeakageOpportunity[];
  locked: boolean;
  locked_count: number;
  request_id: string | null;
  prompt_text: string;
  target_summary: TargetLeakageSummary[];
}

export interface CustomUnlockResult {
  unlocked: boolean;
  total: number;
  opportunities: LeakageOpportunity[];
}

/** POST /api/leakage-radar/customize — 基于志愿草表的定制化捡漏 */
export function customizeLeakageRadar(payload: CustomLeakagePayload): Promise<CustomLeakageResult> {
  return request("/api/leakage-radar/customize", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** POST /api/leakage-radar/customize/unlock — 解锁完整定制化报告（比赛期间跳过支付校验） */
export function unlockCustomLeakage(requestId: string, userId: string): Promise<CustomUnlockResult> {
  return request("/api/leakage-radar/customize/unlock", {
    method: "POST",
    body: JSON.stringify({ request_id: requestId, user_id: userId }),
  });
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

/** GET /api/advisor/stream — SSE 流式聊天（走 ReconnectingSSE，与 risk/agent 行为对齐） */
export function startAdvisorStream(
  message: string,
  history: ChatMessage[],
  profile: Omit<UserProfile, "user_id"> | null,
  callbacks: AdvisorSSECallbacks,
): EventSource {
  const params: Record<string, string> = { message };
  if (history.length) params.history_json = JSON.stringify(history);
  if (profile) params.profile_json = JSON.stringify(profile);

  const url = buildSSEUrl("/api/advisor/stream", params);
  const wrapper = new ReconnectingSSE({
    url,
    onMessage: (event) => {
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
            wrapper.close();
            break;
          case "error":
            callbacks.onError?.(data.data || "顾问服务异常");
            wrapper.close();
            break;
        }
      } catch { /* ignore non-JSON */ }
    },
    onFatalError: (msg) => callbacks.onError?.(msg),
  });
  return wrapper as unknown as EventSource;
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

export interface ReconnectingSSEOptions {
  url: string
  /** 收到消息时回调（caller 自行解析 data.type 并分发） */
  onMessage: (event: MessageEvent) => void
  /** 重试耗尽或不可恢复错误时的回调 */
  onFatalError?: (msg: string) => void
  /** 重连时的日志回调（可选，用于注入 [RECONNECT] 日志） */
  onRetry?: (msg: string) => void
  /** 收到结果标志位变更回调（caller 通知包装器已收到结果，不再重连） */
  onResultReceived?: () => void
  /** 是否已收到结果（caller 提供的 getter，用于判断是否需要重连） */
  isResultReceived?: () => boolean
  maxRetries?: number
  retryDelay?: number
}

/** 带重连能力的 SSE 连接包装器（通用版：消息分发由 caller 通过 onMessage 处理） */
class ReconnectingSSE {
  private options: ReconnectingSSEOptions
  private es: EventSource | null = null
  private retryCount = 0
  private maxRetries: number
  private retryDelay: number
  private closed = false

  constructor(options: ReconnectingSSEOptions) {
    this.options = options
    this.maxRetries = options.maxRetries ?? 2
    this.retryDelay = options.retryDelay ?? 1500
    this.connect()
  }

  /** 真实 EventSource 的 readyState：0=CONNECTING, 1=OPEN, 2=CLOSED */
  get readyState(): number {
    return this.es?.readyState ?? EventSource.CLOSED
  }

  private connect() {
    if (this.closed) return
    this.es = new EventSource(this.options.url)

    this.es.onmessage = (event: MessageEvent) => {
      this.options.onMessage(event)
    }

    this.es.onerror = () => {
      this.es?.close()
      this.es = null

      // 如果已经收到结果（由 caller 通过 isResultReceived 判定），说明是正常结束后的断开
      if (this.closed || (this.options.isResultReceived?.() ?? false)) {
        return
      }

      // 未收到结果 → 尝试重连
      if (this.retryCount < this.maxRetries) {
        this.retryCount++
        this.options.onRetry?.(`[RECONNECT] 第 ${this.retryCount}/${this.maxRetries} 次重连中...`)
        setTimeout(() => this.connect(), this.retryDelay)
      } else {
        this.options.onFatalError?.(`SSE 连接中断（已重试 ${this.maxRetries} 次失败）`)
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
  let resultReceived = false
  const wrapper = new ReconnectingSSE({
    url,
    onMessage: (event) => {
      try {
        const data = JSON.parse(event.data)
        switch (data.type) {
          case "log":
            callbacks.onLog(data.text, data.ts ?? Date.now())
            break
          case "result":
            resultReceived = true
            callbacks.onResult(data.data ?? [])
            break
          case "done":
            callbacks.onDone()
            wrapper.close()
            break
          default:
            break
        }
      } catch { /* non-JSON, ignore */ }
    },
    onRetry: (msg) => callbacks.onLog(msg, Date.now()),
    onFatalError: (msg) => callbacks.onError(msg),
    isResultReceived: () => resultReceived,
  })
  // 直接返回 wrapper（已暴露真实 readyState getter）
  return wrapper as unknown as EventSource
}
