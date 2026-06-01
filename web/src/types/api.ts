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
  sample_count?: number;
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
  market?: string;
  last_close: number;
  predicted_close: number;
  predicted_return: number;
  elapsed_ms: number;
  risk_label?: string;
  failure_reason?: string;
}

export interface BatchResponse {
  ok: boolean;
  rankings: RankedSignal[];
  metadata: { device: string; elapsed_ms: number; warning: string };
}

export interface BatchJobRequest {
  symbols: string[];
  market?: string;
  start_date: string;
  end_date: string;
  adjust?: string;
  pred_len: number;
  model_id?: string;
  dry_run?: boolean;
  start_immediately?: boolean;
}

export interface BatchJobFailure {
  symbol: string;
  stage: "data" | "forecast";
  message: string;
  requestId?: string | null;
  retryable: boolean;
}

export interface BatchJobProgress {
  total: number;
  completed: number;
  success: number;
  failed: number;
  running: string[];
}

export interface BatchJobResult {
  ok: boolean;
  rankings: RankedSignal[];
  failures: BatchJobFailure[];
  progress: BatchJobProgress;
}

export interface DataResponse {
  ok: boolean;
  symbol: string;
  market?: string;
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
  start_date?: string;
  end_date?: string;
  top_k?: number;
  metrics: BacktestMetrics;
  equity_curve: { date: string; equity: number; return: number; selected: string[] }[];
  metadata: { device: string; elapsed_ms: number; warning: string; backend?: string };
}

export type StrategyName = "equal_weight" | "momentum" | "mean_reversion" | "top_k_ranking";

export interface StrategyBacktestRequest extends BacktestJobRequest {
  strategies?: StrategyName[];
}

export interface StrategyResult {
  strategy: StrategyName | string;
  metrics: BacktestMetrics;
  equity_curve: { date: string; equity: number; return: number; selected: string[] }[];
  metadata: Record<string, any>;
}

export interface StrategyBacktestResponse {
  ok: boolean;
  symbols: string[];
  start_date: string;
  end_date: string;
  best_strategy: string;
  results: StrategyResult[];
  metadata: { device: string; elapsed_ms: number; warning: string; backend?: string };
}

export interface StrategyScanRequest extends BacktestJobRequest {
  strategy: StrategyName;
  top_k_values?: number[];
  step_values?: number[];
}

export interface StrategyScanRow {
  rank: number;
  strategy: string;
  params: Record<string, any>;
  metrics: BacktestMetrics;
  score: number;
}

export interface StrategyScanResponse {
  ok: boolean;
  best: StrategyScanRow;
  results: StrategyScanRow[];
  metadata: { device: string; elapsed_ms: number; warning: string; backend?: string };
}

export interface StrategyRollingRequest extends BacktestJobRequest {
  strategy: StrategyName;
  folds?: number;
}

export interface StrategyRollingResponse {
  ok: boolean;
  strategy: string;
  folds: { fold: number; start_index: number; end_index: number; metrics: BacktestMetrics; score: number }[];
  summary: Record<string, any>;
  metadata: { device: string; elapsed_ms: number; warning: string; backend?: string };
}

export interface BacktestReportResponse {
  ok: boolean;
  html: string;
  filename: string;
}

export interface BacktestJobRequest {
  symbols: string[];
  start_date: string;
  end_date: string;
  top_k?: number;
  pred_len?: number;
  window_size?: number;
  step?: number;
  initial_equity?: number;
  benchmark?: string;
  fee_bps?: number;
  slippage_bps?: number;
  dry_run?: boolean;
  start_immediately?: boolean;
}

export interface WatchlistRankingInput {
  symbol: string;
  predicted_return: number;
  last_close?: number | null;
  predicted_close?: number | null;
}

export interface WatchlistResearchRequest {
  name?: string;
  symbols: string[];
  weights?: Record<string, number>;
  rankings?: WatchlistRankingInput[];
}

export interface WatchlistResearchRow {
  symbol: string;
  weight: number;
  predicted_return: number;
  weighted_contribution: number;
  last_close?: number | null;
  predicted_close?: number | null;
  covered: boolean;
}

export interface WatchlistResearchResponse {
  ok: boolean;
  name: string;
  symbol_count: number;
  expected_return: number;
  weighted_return: number;
  top_symbols: string[];
  risk_flags: string[];
  rows: WatchlistResearchRow[];
  metadata: Record<string, any>;
}

export interface WatchlistListRequest {
  name: string;
  market?: string;
  symbols: string[];
  weights?: Record<string, number>;
  tags?: string[];
  note?: string | null;
}

export interface WatchlistListItem {
  ok: boolean;
  id: string;
  name: string;
  market: string;
  symbols: string[];
  weights: Record<string, number>;
  tags: string[];
  note?: string | null;
  created_at: number;
  updated_at: number;
}

export interface WatchlistCollectionResponse {
  ok: boolean;
  watchlists: WatchlistListItem[];
  total: number;
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
  default_model_id?: string;
  supported_model_ids?: string[];
  deep_check: boolean;
  site_api_configured?: boolean;
  capabilities?: Record<string, boolean>;
  model_error?: string | null;
}

export interface RssFeed {
  id?: string | null;
  title?: string | null;
  url: string;
}

export interface RssFetchRequest {
  feeds: RssFeed[];
  limit_per_feed?: number;
}

export interface RssItem {
  feed_id: string;
  feed_title: string;
  title: string;
  url: string;
  published_at?: string | null;
  summary?: string | null;
}

export interface RssFetchResponse {
  ok: boolean;
  items: RssItem[];
  errors: Record<string, string>;
}

export interface JobSubmitResponse {
  ok: boolean;
  job_id: string;
  status: string;
}

export interface JobStatusResponse<T = any> {
  ok: boolean;
  job_id: string;
  kind: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  steps: AgentStep[];
  result?: T | null;
  error?: string | null;
  created_at: number;
  updated_at: number;
}

export interface JobHistoryResponse<T = any> {
  ok: boolean;
  jobs: JobStatusResponse<T>[];
  total: number;
}

export interface SecuritySummaryResponse {
  ok: boolean;
  started_at: number;
  uptime_seconds: number;
  counters: Record<string, number>;
  rate_bucket_count: number;
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
  language?: "zh-CN" | "en-US";
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
  macro_evidence?: MacroEvidenceCoverage;
}

export interface MacroEvidenceCoverage {
  required_dimension_count: number;
  dimension_count: number;
  sufficient_evidence: boolean;
  dimensions: string[];
  dimension_labels?: string[];
  dimension_counts?: Record<string, number>;
  dimension_sources?: Record<string, string[]>;
  missing_dimensions?: string[];
  missing_dimension_labels?: string[];
  provider_status_counts?: Record<string, number>;
  confidence_cap?: number;
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

export interface MacroProviderResultView {
  provider_id: string;
  status: string;
  signals?: MacroSignal[];
  signal_count?: number;
  elapsed_ms?: number;
  error?: string | null;
  metadata?: Record<string, any>;
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
  language?: "zh-CN" | "en-US";
}

export interface MacroAnalyzeRequest {
  question: string;
  symbols?: string[];
  market?: string;
  provider_ids?: string[];
  mode?: "fast" | "complete";
  rss_feeds?: RssFeed[];
  context?: Record<string, any>;
  language?: "zh-CN" | "en-US";
}

export interface ModelCacheResponse {
  ok: boolean;
  cache: { size: number; keys: string[] };
  checked_at: number;
}

export interface ModelCacheClearResponse {
  ok: boolean;
  before: { size: number; keys: string[] };
  after: { size: number; keys: string[] };
  checked_at: number;
}

export interface ModelPrewarmResponse {
  ok: boolean;
  result: Record<string, any>;
  checked_at: number;
}

export interface MacroProviderStatusRow {
  provider_id: string;
  name?: string;
  status: string;
  dimensions?: string[];
  description?: string;
  failure_count: number;
  suspended_remaining_seconds: number;
  cached_entries: number;
  cache_ttl_seconds: number;
  timeout_seconds: number;
}

export interface MacroProviderStatusResponse {
  ok: boolean;
  mode: "fast" | "complete";
  providers: MacroProviderStatusRow[];
}


export interface EvidenceItem {
  id: string;
  category: string;
  title: string;
  summary: string;
  source: string;
  payload: Record<string, any>;
}

export interface EvidencePack {
  version: string;
  items: EvidenceItem[];
  categories: string[];
}

export interface CitedClaim {
  claim: string;
  evidence_ids: string[];
  confidence: number;
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
  macro_provider_coverage?: Record<string, MacroProviderCoverage> | null;
  macro_data_quality?: MacroDataQualitySummary | null;
  macro_dimension_coverage?: MacroEvidenceCoverage | null;
  macro_evidence_insufficiency?: MacroEvidenceInsufficiency | null;
  evidence_pack?: EvidencePack | null;
  cited_claims?: CitedClaim[];
  confidence_breakdown?: Record<string, number> | null;
}

export interface MacroProviderCoverage {
  provider_id: string;
  status: string;
  signal_count: number;
  elapsed_ms: number;
  error?: string | null;
  data_quality?: string | null;
  freshness?: string | null;
  source_url?: string | null;
  reason?: string | null;
}

export interface MacroDataQualitySummary {
  provider_total: number;
  success_count: number;
  empty_count: number;
  failed_count: number;
  skipped_count: number;
  unavailable_count: number;
  signal_count: number;
  last_updated?: string | null;
  source: string;
}

export interface MacroEvidenceInsufficiency {
  insufficient: boolean;
  dimension_count: number;
  required_dimension_count: number;
  missing_dimensions: string[];
  missing_dimension_labels: string[];
  reason: string;
}

export interface IndicatorResponse {
  ok: boolean;
  symbol: string;
  market: string;
  current_price: number;
  indicators: Record<string, any>;
  data_points: number;
}

export interface AlertRule {
  id: string;
  name: string;
  alert_type: string;
  symbol: string;
  market: string;
  params: Record<string, any>;
  enabled: boolean;
  channel: string;
  webhook_url?: string | null;
  email_to?: string | null;
}

export interface AlertRulesResponse {
  ok: boolean;
  rules: AlertRule[];
}

export interface PredictionDeviationAlertPresetRequest {
  symbols: string[];
  deviation_pct?: number;
  market?: string;
  channel?: string;
}

export interface AlertPresetResponse {
  ok: boolean;
  created: number;
  rules: AlertRule[];
}

export interface AlertRuleRequest {
  name: string;
  alert_type: string;
  symbol: string;
  market?: string;
  params?: Record<string, any>;
  enabled?: boolean;
  channel?: string;
  webhook_url?: string | null;
  email_to?: string | null;
}

export interface AlertEvent {
  rule_id: string;
  rule_name: string;
  alert_type: string;
  symbol: string;
  message: string;
  current_value: number;
  threshold_value: number;
  timestamp: string;
  severity: string;
}

export interface AlertCheckResponse {
  ok: boolean;
  checked: number;
  triggered: number;
  events: AlertEvent[];
}
