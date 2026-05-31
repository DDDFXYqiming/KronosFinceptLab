import type {
  AIAnalyzeRequest,
  AIAnalyzeResponse,
  AgentAnalyzeRequest,
  AgentAnalyzeResponse,
  AlertCheckResponse,
  AlertPresetResponse,
  AlertRule,
  AlertRuleRequest,
  AlertRulesResponse,
  BacktestJobRequest,
  BacktestReportResponse,
  BacktestResponse,
  BatchJobRequest,
  BatchJobResult,
  BatchResponse,
  DataResponse,
  ForecastRequest,
  ForecastResponse,
  HealthResponse,
  IndicatorResponse,
  JobHistoryResponse,
  JobStatusResponse,
  JobSubmitResponse,
  MacroAnalyzeRequest,
  MacroProviderStatusResponse,
  ModelCacheClearResponse,
  ModelCacheResponse,
  ModelPrewarmResponse,
  PredictionDeviationAlertPresetRequest,
  RssFetchRequest,
  RssFetchResponse,
  SearchResult,
  SecuritySummaryResponse,
  StrategyBacktestRequest,
  StrategyBacktestResponse,
  StrategyRollingRequest,
  StrategyRollingResponse,
  StrategyScanRequest,
  StrategyScanResponse,
  WatchlistCollectionResponse,
  WatchlistListItem,
  WatchlistListRequest,
  WatchlistResearchRequest,
  WatchlistResearchResponse,
} from "@/types/api";

export type {
  AIAnalyzeRequest,
  AIAnalyzeResponse,
  AgentAnalyzeRequest,
  AgentAnalyzeResponse,
  AgentAssetResult,
  AgentReport,
  AgentStep,
  AgentToolCall,
  AlertCheckResponse,
  AlertEvent,
  AlertPresetResponse,
  AlertRule,
  AlertRuleRequest,
  AlertRulesResponse,
  BacktestJobRequest,
  BacktestMetrics,
  BacktestReportResponse,
  BacktestResponse,
  BatchJobFailure,
  BatchJobProgress,
  BatchJobRequest,
  BatchJobResult,
  BatchResponse,
  DataResponse,
  ForecastRequest,
  ForecastResponse,
  ForecastRow,
  GlobalDataResponse,
  HealthResponse,
  IndicatorResponse,
  JobHistoryResponse,
  JobStatusResponse,
  JobSubmitResponse,
  MacroAnalyzeRequest,
  MacroMonitoringSignal,
  MacroProviderStatusResponse,
  MacroProviderStatusRow,
  MacroProbabilityScenario,
  MacroSignal,
  ModelCacheClearResponse,
  ModelCacheResponse,
  ModelPrewarmResponse,
  PredictionDeviationAlertPresetRequest,
  RankedSignal,
  RssFeed,
  RssFetchRequest,
  RssFetchResponse,
  RssItem,
  SearchResult,
  SecuritySummaryResponse,
  StrategyBacktestRequest,
  StrategyBacktestResponse,
  StrategyName,
  StrategyResult,
  StrategyRollingRequest,
  StrategyRollingResponse,
  StrategyScanRequest,
  StrategyScanResponse,
  WatchlistCollectionResponse,
  WatchlistListItem,
  WatchlistListRequest,
  WatchlistRankingInput,
  WatchlistResearchRequest,
  WatchlistResearchResponse,
  WatchlistResearchRow,
} from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "/api";
const DEFAULT_TIMEOUT_MS = 45000;
const AGENT_ANALYZE_TIMEOUT_MS = 120000;
export const KRONOS_API_KEY_STORAGE_KEY = "kronos-api-key";

export interface ApiClientOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

export class ApiError extends Error {
  status: number;
  requestId: string | null;
  path: string;
  type: string;

  constructor(
    message: string,
    options: { status: number; requestId: string | null; path: string; type?: string }
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.requestId = options.requestId;
    this.path = options.path;
    this.type = options.type || "api_error";
  }
}

export function formatApiError(error: unknown, fallback = "请求失败"): string {
  if (error instanceof ApiError) {
    const requestId = error.requestId ? ` request_id=${error.requestId}` : "";
    return `${error.message}${requestId}`;
  }
  if (error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}

function logApiFailure(path: string, status: number, requestId: string | null, message: string) {
  if (typeof window === "undefined") return;
  const safePath = path.split("?")[0];
  console.warn("[kronos-api]", {
    path: safePath,
    status,
    request_id: requestId || undefined,
    error: message,
  });
}

function createClientRequestId(): string {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `web-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function getConfiguredTestRunId(): string | null {
  const envValue = process.env.NEXT_PUBLIC_TEST_RUN_ID?.trim();
  if (envValue) return envValue;
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem("kronos-test-run-id");
  } catch {
    return null;
  }
}

export function getConfiguredApiKey(): string | null {
  const envValue = process.env.NEXT_PUBLIC_KRONOS_API_KEY?.trim();
  if (envValue) return envValue;
  if (typeof window === "undefined") return null;
  try {
    return (
      window.localStorage.getItem(KRONOS_API_KEY_STORAGE_KEY) ||
      window.sessionStorage.getItem(KRONOS_API_KEY_STORAGE_KEY)
    );
  } catch {
    return null;
  }
}

export function saveConfiguredApiKey(value: string): void {
  if (typeof window === "undefined") return;
  const key = value.trim();
  if (key) {
    window.localStorage.setItem(KRONOS_API_KEY_STORAGE_KEY, key);
  } else {
    window.localStorage.removeItem(KRONOS_API_KEY_STORAGE_KEY);
    window.sessionStorage.removeItem(KRONOS_API_KEY_STORAGE_KEY);
  }
}

function enrichGatewayError(status: number, message: string, path: string): string {
  if (status === 401) {
    return "需要配置 Kronos API Key 后才能使用该功能。请前往设置页保存密钥。";
  }
  if (status === 403) {
    return "该操作需要 Admin API Key；普通 API Key 不能执行告警管理或安全诊断。";
  }
  if (status === 429) {
    return "请求过于频繁，已触发限流。请稍后重试，或降低分析/预测频率。";
  }
  const isAgentAnalyze = path.includes("/v1/analyze/agent");
  const isMacroAnalyze = path.includes("/v1/analyze/macro");
  if (![502, 503, 504].includes(status) && !((isAgentAnalyze || isMacroAnalyze) && status === 500)) return message;
  const prefix = message || `HTTP ${status}`;
  if (isAgentAnalyze) {
    return (
      `${prefix}。` +
      "Agent 分析包含行情、Kronos、网页检索和 LLM 汇总，线上偶发 500/502 通常表示后端进程、Zeabur 代理或上游模型调用被中断；请重试并用 Runtime Logs 对照 request_id。"
    );
  }
  if (isMacroAnalyze) {
    return (
      `${prefix}。` +
      "宏观洞察包含宏观 provider、公开数据和 LLM 汇总，线上偶发 500/502 通常表示代理等待超时、后端进程或上游数据源被中断；请重试并用 Runtime Logs 对照 request_id。"
    );
  }
  return (
    `${prefix}。` +
    "这通常表示 Zeabur 网关、容器重启、推理超时或内存压力中断了请求；请稍后重试并用 Runtime Logs 对照 request_id。"
  );
}

function joinUrl(base: string, path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  return `${base.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
}

function createRequestSignal(options: ApiClientOptions): { signal: AbortSignal; cleanup: () => void } {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  const timeoutId = globalThis.setTimeout(() => controller.abort(), timeoutMs);

  const abortFromCaller = () => controller.abort();
  if (options.signal) {
    if (options.signal.aborted) {
      controller.abort();
    } else {
      options.signal.addEventListener("abort", abortFromCaller, { once: true });
    }
  }

  return {
    signal: controller.signal,
    cleanup: () => {
      globalThis.clearTimeout(timeoutId);
      options.signal?.removeEventListener("abort", abortFromCaller);
    },
  };
}

async function parseErrorResponse(res: Response): Promise<Record<string, any>> {
  const text = await res.text().catch(() => "");
  if (!text) return { error: res.statusText };
  try {
    return JSON.parse(text);
  } catch {
    return { error: text };
  }
}

async function fetchApi<T>(
  path: string,
  options: RequestInit & ApiClientOptions = {}
): Promise<T> {
  const { timeoutMs, signal: callerSignal, ...requestOptions } = options;
  const headers = new Headers(requestOptions.headers);
  if (requestOptions.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const clientRequestId = headers.get("X-Request-ID") || createClientRequestId();
  headers.set("X-Request-ID", clientRequestId);
  const testRunId = getConfiguredTestRunId();
  if (testRunId && !headers.has("X-Test-Run-ID")) {
    headers.set("X-Test-Run-ID", testRunId);
  }
  const apiKey = getConfiguredApiKey();
  if (apiKey && !headers.has("X-Kronos-Api-Key") && !headers.has("Authorization")) {
    headers.set("X-Kronos-Api-Key", apiKey);
  }

  const { signal, cleanup } = createRequestSignal({ timeoutMs, signal: callerSignal });
  try {
    const res = await fetch(joinUrl(API_BASE, path), {
      ...requestOptions,
      headers,
      signal,
    });

    if (!res.ok) {
      const err = await parseErrorResponse(res);
      const message = enrichGatewayError(res.status, err.error || err.detail || `HTTP ${res.status}`, path);
      const requestId = res.headers.get("X-Request-ID") || err.request_id || err.requestId || clientRequestId;
      const type = err.type || err.code || "api_error";
      logApiFailure(path, res.status, requestId, message);
      throw new ApiError(message, { status: res.status, requestId, path, type });
    }

    return res.json();
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      const cancelledByCaller = callerSignal?.aborted === true;
      const message = cancelledByCaller ? "请求已取消" : "请求超时或已取消";
      if (!cancelledByCaller) {
        logApiFailure(path, 0, clientRequestId, message);
      }
      throw new ApiError(message, { status: 0, requestId: clientRequestId, path, type: "request_aborted" });
    }
    throw error;
  } finally {
    cleanup();
  }
}

function get<T>(path: string, options?: ApiClientOptions): Promise<T> {
  return fetchApi<T>(path, { method: "GET", ...options });
}

function post<T>(path: string, body: unknown, options?: ApiClientOptions): Promise<T> {
  return fetchApi<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
    ...options,
  });
}

function put<T>(path: string, body: unknown, options?: ApiClientOptions): Promise<T> {
  return fetchApi<T>(path, {
    method: "PUT",
    body: JSON.stringify(body),
    ...options,
  });
}

function del<T>(path: string, options?: ApiClientOptions): Promise<T> {
  return fetchApi<T>(path, { method: "DELETE", ...options });
}

export const api = {
  health: (options?: ApiClientOptions) => get<HealthResponse>("/health", options),

  fetchRss: (req: RssFetchRequest, options?: ApiClientOptions) =>
    post<RssFetchResponse>("/news/rss", req, options),

  forecast: (req: ForecastRequest, options?: ApiClientOptions) =>
    post<ForecastResponse>("/forecast", req, options),

  batch: (assets: ForecastRequest[], pred_len: number, dry_run = false, options?: ApiClientOptions) =>
    post<BatchResponse>("/batch", { assets, pred_len, dry_run }, options),

  getData: (
    symbol: string,
    startDate: string,
    endDate: string,
    adjustOrOptions: string | ApiClientOptions = "qfq",
    maybeOptions?: ApiClientOptions
  ) => {
    const adjust = typeof adjustOrOptions === "string" ? adjustOrOptions : "qfq";
    const options = typeof adjustOrOptions === "string" ? maybeOptions : adjustOrOptions;
    const params = new URLSearchParams({ start_date: startDate, end_date: endDate });
    return get<DataResponse>(`/data/a-stock/${symbol}?${params.toString()}&adjust=${encodeURIComponent(adjust)}`, options);
  },

  search: (query: string, options?: ApiClientOptions) =>
    get<{ ok: boolean; results: SearchResult[] }>(`/data/search?q=${encodeURIComponent(query)}`, options),

  backtest: (
    params: {
      symbols: string[];
      start_date: string;
      end_date: string;
      top_k: number;
      pred_len?: number;
      window_size?: number;
      step?: number;
      initial_equity?: number;
      benchmark?: string;
      fee_bps?: number;
      slippage_bps?: number;
      dry_run?: boolean;
    },
    options?: ApiClientOptions
  ) => post<BacktestResponse>("/backtest/ranking", params, options),

  backtestReport: (
    params: {
      symbols: string[];
      start_date: string;
      end_date: string;
      top_k: number;
      pred_len?: number;
      window_size?: number;
      step?: number;
      initial_equity?: number;
      benchmark?: string;
      fee_bps?: number;
      slippage_bps?: number;
      strategy_name?: string;
      dry_run?: boolean;
    },
    options?: ApiClientOptions
  ) => post<BacktestReportResponse>("/backtest/report", params, options),

  strategyBacktest: (req: StrategyBacktestRequest, options?: ApiClientOptions) =>
    post<StrategyBacktestResponse>("/backtest/strategy", req, options),

  strategyScan: (req: StrategyScanRequest, options?: ApiClientOptions) =>
    post<StrategyScanResponse>("/backtest/strategy/scan", req, options),

  strategyRolling: (req: StrategyRollingRequest, options?: ApiClientOptions) =>
    post<StrategyRollingResponse>("/backtest/strategy/rolling", req, options),

  getGlobalData: (
    symbol: string,
    market: string,
    startDate: string,
    endDate: string,
    options?: ApiClientOptions
  ) =>
    get<DataResponse>(
      `/data/global/${symbol}?market=${market}&start_date=${startDate}&end_date=${endDate}`,
      options
    ),

  getIndicators: (symbol: string, market = "cn", options?: ApiClientOptions) =>
    get<IndicatorResponse>(`/data/indicator/${symbol}?market=${market}`, options),

  getMoneyFlow: (symbol: string, options?: ApiClientOptions & { limit?: number; startDate?: string; endDate?: string }) => {
    const params = new URLSearchParams();
    if (options?.limit) params.set("limit", String(options.limit));
    if (options?.startDate) params.set("start_date", options.startDate);
    if (options?.endDate) params.set("end_date", options.endDate);
    const qs = params.toString();
    return get<any>(`/data/money-flow/${encodeURIComponent(symbol)}${qs ? `?${qs}` : ""}`, options);
  },

  getSectorFlow: (sectorType: "industry" | "concept" | "region" = "industry", options?: ApiClientOptions) =>
    get<any>(`/data/sector-flow?sector_type=${encodeURIComponent(sectorType)}`, options),

  getHsgtFlow: (options?: ApiClientOptions & { startDate?: string; endDate?: string }) => {
    const params = new URLSearchParams();
    if (options?.startDate) params.set("start_date", options.startDate);
    if (options?.endDate) params.set("end_date", options.endDate);
    const qs = params.toString();
    return get<any>(`/data/hsgt-flow${qs ? `?${qs}` : ""}`, options);
  },

  getSourceMarketArtifact: (
    artifact: string,
    options?: ApiClientOptions & { date?: string; limit?: number }
  ) => {
    const params = new URLSearchParams();
    if (options?.date) params.set("date", options.date);
    if (options?.limit !== undefined) params.set("limit", String(options.limit));
    const qs = params.toString();
    return get<any>(`/data/source-market/${encodeURIComponent(artifact)}${qs ? `?${qs}` : ""}`, options);
  },

  aiAnalyze: (req: AIAnalyzeRequest, options?: ApiClientOptions) =>
    post<AIAnalyzeResponse>("/v1/analyze/ai", req, options),

  agentAnalyze: (req: AgentAnalyzeRequest, options?: ApiClientOptions) =>
    post<AgentAnalyzeResponse>("/v1/analyze/agent", req, {
      timeoutMs: AGENT_ANALYZE_TIMEOUT_MS,
      ...options,
    }),

  macroAnalyze: (req: MacroAnalyzeRequest, options?: ApiClientOptions) =>
    post<AgentAnalyzeResponse>("/v1/analyze/macro", req, {
      timeoutMs: AGENT_ANALYZE_TIMEOUT_MS,
      ...options,
    }),

  macroProviderStatus: (mode: "fast" | "complete" = "fast", options?: ApiClientOptions) =>
    get<MacroProviderStatusResponse>(`/v1/analyze/macro/providers/status?mode=${mode}`, options),

  analyzeDcf: (symbol: string, market: string, options?: ApiClientOptions) =>
    post<any>("/v1/analyze/dcf", { symbol, market }, options),

  analyzeRisk: (symbol: string, market: string, options?: ApiClientOptions) =>
    post<any>("/v1/analyze/risk", { symbol, market }, options),

  analyzePortfolio: (symbols: string[], market: string, options?: ApiClientOptions) =>
    post<any>("/v1/analyze/portfolio", { symbols, market }, options),

  analyzeDerivative: (symbol: string, market: string, options?: ApiClientOptions) =>
    post<any>("/v1/analyze/derivative", { symbol, market }, options),

  alertList: (options?: ApiClientOptions) => get<AlertRulesResponse>("/alert/rules", options),

  alertCreate: (req: AlertRuleRequest, options?: ApiClientOptions) =>
    post<AlertRule>("/alert/rules", req, options),

  alertDelete: (ruleId: string, options?: ApiClientOptions) =>
    del<{ ok: boolean; message: string }>(`/alert/rules/${encodeURIComponent(ruleId)}`, options),

  alertCheck: (ruleId?: string | null, options?: ApiClientOptions) =>
    post<AlertCheckResponse>("/alert/check", ruleId ? { rule_id: ruleId } : {}, options),

  alertCreatePredictionDeviationPreset: (req: PredictionDeviationAlertPresetRequest, options?: ApiClientOptions) =>
    post<AlertPresetResponse>("/alert/presets/prediction-deviation", req, options),

  getSuggestions: (type: "analysis" | "macro" = "analysis", options?: ApiClientOptions) =>
    get<{ questions: string[]; generated_at: number; source: string }>(`/v1/suggestions?type=${type}`, options),

  submitForecastJob: (req: ForecastRequest, options?: ApiClientOptions) =>
    post<JobSubmitResponse>("/jobs/forecast", req, options),

  submitAnalyzeJob: (req: AgentAnalyzeRequest, options?: ApiClientOptions) =>
    post<JobSubmitResponse>("/jobs/analyze", req, options),

  submitBatchJob: (req: BatchJobRequest, options?: ApiClientOptions) =>
    post<JobSubmitResponse>("/jobs/batch", req, options),

  submitBacktestJob: (req: BacktestJobRequest, options?: ApiClientOptions) =>
    post<JobSubmitResponse>("/jobs/backtest", req, options),

  watchlistResearch: (req: WatchlistResearchRequest, options?: ApiClientOptions) =>
    post<WatchlistResearchResponse>("/watchlist/research", req, options),

  getJob: <T = any>(jobId: string, options?: ApiClientOptions) =>
    get<JobStatusResponse<T>>(`/jobs/${encodeURIComponent(jobId)}`, options),

  listJobs: <T = any>(options?: ApiClientOptions & { limit?: number; status?: string; kind?: string }) => {
    const params = new URLSearchParams();
    if (options?.limit) params.set("limit", String(options.limit));
    if (options?.status) params.set("status", options.status);
    if (options?.kind) params.set("kind", options.kind);
    const qs = params.toString();
    return get<JobHistoryResponse<T>>(`/jobs${qs ? `?${qs}` : ""}`, options);
  },

  watchlistList: (options?: ApiClientOptions) =>
    get<WatchlistCollectionResponse>("/watchlist/lists", options),

  watchlistCreate: (req: WatchlistListRequest, options?: ApiClientOptions) =>
    post<WatchlistListItem>("/watchlist/lists", req, options),

  watchlistUpdate: (id: string, req: WatchlistListRequest, options?: ApiClientOptions) =>
    put<WatchlistListItem>(`/watchlist/lists/${encodeURIComponent(id)}`, req, options),

  watchlistDelete: (id: string, options?: ApiClientOptions) =>
    del<{ ok: boolean; id: string; deleted: boolean }>(`/watchlist/lists/${encodeURIComponent(id)}`, options),

  cancelJob: (jobId: string, options?: ApiClientOptions) =>
    post<{ ok: boolean; job_id: string; status: string }>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {}, options),

  securitySummary: (options?: ApiClientOptions) =>
    get<SecuritySummaryResponse>("/admin/security/summary", options),

  modelCache: (options?: ApiClientOptions) =>
    get<ModelCacheResponse>("/admin/model/cache", options),

  modelClearCache: (options?: ApiClientOptions) =>
    post<ModelCacheClearResponse>("/admin/model/clear-cache", {}, options),

  modelPrewarm: (force = false, options?: ApiClientOptions) =>
    post<ModelPrewarmResponse>("/admin/model/prewarm", { force }, { timeoutMs: AGENT_ANALYZE_TIMEOUT_MS, ...options }),
};
