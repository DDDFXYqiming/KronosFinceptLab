const API_BASE = "/api";

export interface ForecastRow {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  amount?: number;
}

export interface ForecastRequest {
  symbol: string;
  timeframe?: string;
  pred_len: number;
  rows: ForecastRow[];
  dry_run?: boolean;
  model_id?: string;
  tokenizer_id?: string;
  temperature?: number;
  top_k?: number;
  top_p?: number;
}

export interface ForecastResponse {
  ok: boolean;
  symbol: string;
  forecast: ForecastRow[];
  metadata: { device: string; elapsed_ms: number; backend: string; warning: string };
  error?: string;
  probability?: number;
  signal?: string;
}

export interface RankedSignal {
  rank: number;
  symbol: string;
  last_close: number;
  predicted_close: number;
  predicted_return: number;
  elapsed_ms: number;
}

export interface BatchResponse {
  ok: boolean;
  rankings: RankedSignal[];
  metadata: { device: string; elapsed_ms: number; warning: string };
}

export interface DataResponse {
  ok: boolean;
  symbol: string;
  count: number;
  rows: ForecastRow[];
}

export interface SearchResult {
  code: string;
  name: string;
  market: string;
}

export interface BacktestMetrics {
  total_return: number;
  annualized_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  total_trades: number;
  win_rate: number;
  avg_holding_days: number;
}

export interface BacktestResponse {
  ok: boolean;
  symbols: string[];
  metrics: BacktestMetrics;
  equity_curve: { date: string; equity: number; return: number; selected: string[] }[];
  metadata: { device: string; elapsed_ms: number; warning: string };
}

export interface HealthResponse {
  status: string;
  version: string;
  model_loaded: boolean;
  model_id: string;
  device: string;
  uptime_seconds: number;
}

export interface GlobalDataResponse {
  ok: boolean;
  symbol: string;
  market: string;
  count: number;
  rows: ForecastRow[];
}

// ── v8.0 New Types ───────────────────────────────────────────────

export interface AIAnalyzeRequest {
  symbol: string;
  market: string;
}

export interface AIAnalyzeResponse {
  ok: boolean;
  symbol: string;
  market: string;
  summary: string;
  detailed_analysis: string;
  recommendation: string;
  confidence: number;
  risk_level: string;
  current_price: number;
  risk_metrics: Record<string, number> | null;
  kronos_prediction: {
    model: string;
    prediction_days: number;
    forecast: ForecastRow[];
    probabilistic: Record<string, any> | null;
  } | null;
  timestamp: string;
  error?: string;
}

export interface AgentToolCall {
  name: string;
  status: string;
  summary: string;
  elapsed_ms: number;
  metadata: Record<string, any>;
}

export interface AgentStep {
  name: string;
  status: string;
  summary: string;
  elapsed_ms: number;
}

export interface AgentReport {
  conclusion: string;
  short_term_prediction: string;
  technical: string;
  fundamentals: string;
  risk: string;
  uncertainties: string;
  recommendation: string;
  confidence: number;
  risk_level: string;
  disclaimer: string;
}

export interface AgentAnalyzeRequest {
  question: string;
  symbol?: string;
  market?: string;
  context?: Record<string, any>;
  dry_run?: boolean;
}

export interface AgentAnalyzeResponse {
  ok: boolean;
  question: string;
  symbol: string | null;
  symbols: string[];
  market: string | null;
  report: AgentReport;
  final_report: string;
  recommendation: string;
  confidence: number;
  risk_level: string;
  current_price: number | null;
  risk_metrics: Record<string, number> | null;
  kronos_prediction: {
    model: string;
    prediction_days: number;
    forecast: ForecastRow[];
    probabilistic: Record<string, any> | null;
    metadata?: Record<string, any>;
  } | null;
  tool_calls: AgentToolCall[];
  steps: AgentStep[];
  timestamp: string;
  rejected: boolean;
  security_reason?: string | null;
  clarification_required: boolean;
  clarifying_question?: string | null;
  error?: string | null;
}

export interface IndicatorResponse {
  ok: boolean;
  symbol: string;
  market: string;
  current_price: number;
  indicators: Record<string, any>;
  data_points: number;
}

// ── Fetch Helper ─────────────────────────────────────────────────

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

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    const message = err.error || err.detail || `HTTP ${res.status}`;
    logApiFailure(path, res.status, res.headers.get("X-Request-ID"), message);
    throw new Error(message);
  }
  return res.json();
}

// ── API Client ───────────────────────────────────────────────────

export const api = {
  health: () => fetchApi<HealthResponse>("/health"),

  forecast: (req: ForecastRequest) =>
    fetchApi<ForecastResponse>("/forecast", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  batch: (assets: ForecastRequest[], pred_len: number, dry_run = false) =>
    fetchApi<BatchResponse>("/batch", {
      method: "POST",
      body: JSON.stringify({ assets, pred_len, dry_run }),
    }),

  getData: (symbol: string, startDate: string, endDate: string) =>
    fetchApi<DataResponse>(`/data/a-stock/${symbol}?start_date=${startDate}&end_date=${endDate}`),

  search: (query: string) =>
    fetchApi<{ ok: boolean; results: SearchResult[] }>(`/data/search?q=${encodeURIComponent(query)}`),

  backtest: (params: {
    symbols: string[];
    start_date: string;
    end_date: string;
    top_k: number;
    pred_len?: number;
    dry_run?: boolean;
  }) =>
    fetchApi<BacktestResponse>("/backtest/ranking", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  // v8.0: Global market data
  getGlobalData: (symbol: string, market: string, startDate: string, endDate: string) =>
    fetchApi<DataResponse>(
      `/data/global/${symbol}?market=${market}&start_date=${startDate}&end_date=${endDate}`
    ),

  // v8.0: Technical indicators
  getIndicators: (symbol: string, market: string = "cn") =>
    fetchApi<IndicatorResponse>(`/data/indicator/${symbol}?market=${market}`),

  // v8.0: AI-powered analysis
  aiAnalyze: (req: AIAnalyzeRequest) =>
    fetchApi<AIAnalyzeResponse>("/v1/analyze/ai", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  // v8.7: Stateless natural-language agent analysis
  agentAnalyze: (req: AgentAnalyzeRequest) =>
    fetchApi<AgentAnalyzeResponse>("/v1/analyze/agent", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  // CFA analysis endpoints
  analyzeDcf: (symbol: string, market: string) =>
    fetchApi<any>("/v1/analyze/dcf", {
      method: "POST",
      body: JSON.stringify({ symbol, market }),
    }),

  analyzeRisk: (symbol: string, market: string) =>
    fetchApi<any>("/v1/analyze/risk", {
      method: "POST",
      body: JSON.stringify({ symbol, market }),
    }),

  analyzePortfolio: (symbols: string[], market: string) =>
    fetchApi<any>("/v1/analyze/portfolio", {
      method: "POST",
      body: JSON.stringify({ symbols, market }),
    }),

  analyzeDerivative: (symbol: string, market: string) =>
    fetchApi<any>("/v1/analyze/derivative", {
      method: "POST",
      body: JSON.stringify({ symbol, market }),
    }),
};
