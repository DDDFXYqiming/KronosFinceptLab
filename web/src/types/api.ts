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
  metadata: {
    device: string;
    elapsed_ms: number;
    backend: string;
    warning: string;
    model_cached?: boolean;
    cache_key?: string;
    load_wait_ms?: number;
    inference_wait_ms?: number;
  };
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
  app_version: string;
  build_commit: string;
  build_ref: string;
  build_source: string;
  model_loaded: boolean;
  model_id: string;
  tokenizer_id?: string | null;
  device: string;
  uptime_seconds: number;
  runtime_mode: string;
  model_enabled: boolean;
  deep_check: boolean;
  capabilities?: Record<string, boolean>;
  model_error?: string | null;
}

export interface GlobalDataResponse {
  ok: boolean;
  symbol: string;
  market: string;
  count: number;
  rows: ForecastRow[];
}

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
  macro_analysis?: string;
  macro_signals?: MacroSignal[];
  cross_validation?: string;
  contradictions?: string;
  probability_scenarios?: MacroProbabilityScenario[];
  monitoring_signals?: MacroMonitoringSignal[];
}

export interface MacroSignal {
  source: string;
  signal_type: string;
  value: unknown;
  interpretation: string;
  time_horizon: string;
  confidence: number;
  observed_at?: string | null;
  source_url?: string | null;
  metadata?: Record<string, any>;
}

export interface MacroProbabilityScenario {
  scenario: string;
  probability: number;
  basis: string;
}

export interface MacroMonitoringSignal {
  signal: string;
  current_value: unknown;
  threshold: string;
  meaning: string;
}

export interface AgentAssetResult {
  symbol: string;
  market: string;
  name?: string | null;
  report: AgentReport;
  final_report: string;
  recommendation: string;
  confidence: number;
  risk_level: string;
  current_price: number | null;
  data_points?: number;
  risk_metrics: Record<string, number> | null;
  kronos_prediction: {
    model: string;
    prediction_days: number;
    forecast: ForecastRow[];
    probabilistic: Record<string, any> | null;
    metadata?: Record<string, any>;
  } | null;
  kronos_prediction_error?: string | null;
  tool_status?: Record<string, string>;
}

export interface AgentAnalyzeRequest {
  question: string;
  symbol?: string;
  market?: string;
  context?: Record<string, any>;
  dry_run?: boolean;
}

export interface MacroAnalyzeRequest {
  question: string;
  symbols?: string[];
  market?: string;
  provider_ids?: string[];
  context?: Record<string, any>;
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
  asset_results: AgentAssetResult[];
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
