export type Language = "zh-CN" | "en-US";

export const LANGUAGE_OPTIONS: Array<{ value: Language; label: string }> = [
  { value: "zh-CN", label: "简体中文" },
  { value: "en-US", label: "English" },
];

const messages = {
  "zh-CN": {
    "nav.dashboard": "仪表盘",
    "nav.forecast": "预测",
    "nav.analysis": "分析",
    "nav.macro": "宏观洞察",
    "nav.news": "新闻",
    "nav.watchlist": "自选股",
    "nav.batch": "批量对比",
    "nav.backtest": "回测",
    "nav.data": "数据",
    "nav.settings": "设置",
    "nav.alerts": "告警",
    "common.researchOnly": "仅供研究",
  },
  "en-US": {
    "nav.dashboard": "Dashboard",
    "nav.forecast": "Forecast",
    "nav.analysis": "Analysis",
    "nav.macro": "Macro",
    "nav.news": "News",
    "nav.watchlist": "Watchlist",
    "nav.batch": "Batch",
    "nav.backtest": "Backtest",
    "nav.data": "Data",
    "nav.settings": "Settings",
    "nav.alerts": "Alerts",
    "common.researchOnly": "Research only",
  },
} satisfies Record<Language, Record<string, string>>;

export function normalizeLanguage(value: unknown): Language {
  return value === "en-US" ? "en-US" : "zh-CN";
}

export function t(language: Language, key: keyof typeof messages["zh-CN"]): string {
  return messages[language][key] || messages["zh-CN"][key] || key;
}
