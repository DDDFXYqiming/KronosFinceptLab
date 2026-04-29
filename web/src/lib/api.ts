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

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

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
};
