import type {
  AIAnalyzeRequest,
  AIAnalyzeResponse,
  AgentAnalyzeRequest,
  AgentAnalyzeResponse,
  BacktestResponse,
  BatchResponse,
  DataResponse,
  ForecastRequest,
  ForecastResponse,
  HealthResponse,
  IndicatorResponse,
  MacroAnalyzeRequest,
  SearchResult,
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
  BacktestMetrics,
  BacktestResponse,
  BatchResponse,
  DataResponse,
  ForecastRequest,
  ForecastResponse,
  ForecastRow,
  GlobalDataResponse,
  HealthResponse,
  IndicatorResponse,
  MacroAnalyzeRequest,
  MacroMonitoringSignal,
  MacroProbabilityScenario,
  MacroSignal,
  RankedSignal,
  SearchResult,
} from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "/api";
const DEFAULT_TIMEOUT_MS = 45000;
const AGENT_ANALYZE_TIMEOUT_MS = 120000;

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

function enrichGatewayError(status: number, message: string, path: string): string {
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

export const api = {
  health: (options?: ApiClientOptions) => get<HealthResponse>("/health", options),

  forecast: (req: ForecastRequest, options?: ApiClientOptions) =>
    post<ForecastResponse>("/forecast", req, options),

  batch: (assets: ForecastRequest[], pred_len: number, dry_run = false, options?: ApiClientOptions) =>
    post<BatchResponse>("/batch", { assets, pred_len, dry_run }, options),

  getData: (symbol: string, startDate: string, endDate: string, options?: ApiClientOptions) =>
    get<DataResponse>(`/data/a-stock/${symbol}?start_date=${startDate}&end_date=${endDate}`, options),

  search: (query: string, options?: ApiClientOptions) =>
    get<{ ok: boolean; results: SearchResult[] }>(`/data/search?q=${encodeURIComponent(query)}`, options),

  backtest: (
    params: {
      symbols: string[];
      start_date: string;
      end_date: string;
      top_k: number;
      pred_len?: number;
      dry_run?: boolean;
    },
    options?: ApiClientOptions
  ) => post<BacktestResponse>("/backtest/ranking", params, options),

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

  analyzeDcf: (symbol: string, market: string, options?: ApiClientOptions) =>
    post<any>("/v1/analyze/dcf", { symbol, market }, options),

  analyzeRisk: (symbol: string, market: string, options?: ApiClientOptions) =>
    post<any>("/v1/analyze/risk", { symbol, market }, options),

  analyzePortfolio: (symbols: string[], market: string, options?: ApiClientOptions) =>
    post<any>("/v1/analyze/portfolio", { symbols, market }, options),

  analyzeDerivative: (symbol: string, market: string, options?: ApiClientOptions) =>
    post<any>("/v1/analyze/derivative", { symbol, market }, options),
};
