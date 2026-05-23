import type { AgentAnalyzeResponse, ForecastRow } from "@/types/api";

export const DEMO_SYMBOL = "600036";
export const DEMO_MARKET = "cn";

export const demoHistoricalRows: ForecastRow[] = [
  { timestamp: "2026-04-20T00:00:00Z", open: 37.2, high: 38.1, low: 36.9, close: 37.8, volume: 218000 },
  { timestamp: "2026-04-21T00:00:00Z", open: 37.8, high: 38.5, low: 37.4, close: 38.2, volume: 231000 },
  { timestamp: "2026-04-22T00:00:00Z", open: 38.1, high: 38.6, low: 37.7, close: 37.9, volume: 196000 },
  { timestamp: "2026-04-23T00:00:00Z", open: 37.9, high: 39.0, low: 37.8, close: 38.7, volume: 255000 },
  { timestamp: "2026-04-24T00:00:00Z", open: 38.6, high: 39.2, low: 38.2, close: 39.0, volume: 243000 },
  { timestamp: "2026-04-27T00:00:00Z", open: 39.0, high: 39.5, low: 38.4, close: 38.8, volume: 207000 },
  { timestamp: "2026-04-28T00:00:00Z", open: 38.8, high: 39.7, low: 38.5, close: 39.4, volume: 267000 },
  { timestamp: "2026-04-29T00:00:00Z", open: 39.3, high: 39.9, low: 38.9, close: 39.6, volume: 252000 },
];

export const demoForecastRows: ForecastRow[] = [
  { timestamp: "2026-04-30T00:00:00Z", open: 39.6, high: 40.1, low: 39.2, close: 39.9, volume: 240000 },
  { timestamp: "2026-05-01T00:00:00Z", open: 39.9, high: 40.5, low: 39.5, close: 40.2, volume: 238000 },
  { timestamp: "2026-05-04T00:00:00Z", open: 40.1, high: 40.8, low: 39.8, close: 40.4, volume: 246000 },
];

export const demoAgentResult: AgentAnalyzeResponse = {
  ok: true,
  question: "帮我看看招商银行现在能不能买",
  symbol: DEMO_SYMBOL,
  symbols: [DEMO_SYMBOL],
  market: DEMO_MARKET,
  report: {
    conclusion: "演示结论：趋势温和偏强，但不适合无条件追高。",
    short_term_prediction: "Kronos 样例预测显示未来数日价格中枢小幅上移。",
    technical: "均线结构修复，量能仍需继续确认。",
    fundamentals: "银行股估值偏低，但盈利弹性有限。",
    risk: "主要风险来自利率、地产敞口和市场风险偏好回落。",
    uncertainties: "样例数据不代表实时行情。",
    recommendation: "观察/分批",
    confidence: 0.64,
    risk_level: "中",
    disclaimer: "演示数据，不构成投资建议。",
  },
  final_report: "演示报告：招商银行样例显示短期动能略有修复，但证据不足以支持重仓追买。更合理的动作是设置价格与风险阈值，分批观察。",
  recommendation: "观察/分批",
  confidence: 0.64,
  risk_level: "中",
  current_price: 39.6,
  risk_metrics: { volatility: 0.18, max_drawdown: -0.08 },
  kronos_prediction: { forecast: demoForecastRows, model: "demo", prediction_days: demoForecastRows.length, probabilistic: null },
  asset_results: [],
  tool_calls: [
    { name: "market_data", status: "completed", summary: "读取固定演示行情。", elapsed_ms: 0, metadata: {} },
    { name: "kronos_forecast", status: "completed", summary: "生成固定演示预测。", elapsed_ms: 0, metadata: {} },
  ],
  steps: [
    { name: "理解问题", status: "completed", summary: "识别为单标的研究问题。", elapsed_ms: 0 },
    { name: "生成报告", status: "completed", summary: "返回固定演示报告。", elapsed_ms: 0 },
  ],
  timestamp: "2026-05-24T00:00:00Z",
  rejected: false,
  clarification_required: false,
};

export const demoMacroResult: AgentAnalyzeResponse = {
  ...demoAgentResult,
  question: "现在适合买黄金吗",
  symbol: null,
  symbols: ["GC=F", "GLD"],
  market: "commodity",
  report: {
    ...demoAgentResult.report,
    conclusion: "演示结论：黄金中期仍有避险支撑，但短期需防止拥挤交易回撤。",
    recommendation: "观察/轻仓",
    macro_analysis: "实际功能会聚合利率、美元、商品、情绪和预测市场信号；这里仅展示固定样例。",
    macro_signals: [
      { source: "demo", signal_type: "real_rate", value: "down", interpretation: "实际利率下行通常利多黄金。", time_horizon: "medium", confidence: 0.62 },
      { source: "demo", signal_type: "risk_sentiment", value: "mixed", interpretation: "避险需求存在但不是单边信号。", time_horizon: "short", confidence: 0.55 },
    ],
    probability_scenarios: [
      { scenario: "震荡上行", probability: 0.45, basis: "利率和避险信号支撑。" },
      { scenario: "高位回撤", probability: 0.3, basis: "拥挤交易和美元反弹风险。" },
      { scenario: "横盘", probability: 0.25, basis: "多空信号相互抵消。" },
    ],
    monitoring_signals: [
      { signal: "10Y real yield", current_value: "watch", threshold: "连续上行", meaning: "黄金压力增加" },
      { signal: "DXY", current_value: "watch", threshold: "突破前高", meaning: "美元走强压制黄金" },
    ],
  },
  final_report: "演示报告：黄金样例显示中期支撑仍在，但短期信号并不单边。真实分析需要 API Key 才会调用宏观 provider 与 LLM。",
  recommendation: "观察/轻仓",
  confidence: 0.58,
  risk_level: "中",
  macro_provider_coverage: { demo: { provider_id: "demo", status: "completed", signal_count: 2, elapsed_ms: 0 } },
};
