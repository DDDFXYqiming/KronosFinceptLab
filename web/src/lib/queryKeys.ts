import type { Market } from "@/lib/markets";
import { normalizeSymbol, normalizeSymbols } from "@/lib/symbols";

export const queryKeys = {
  all: ["kronos"] as const,
  health: () => [...queryKeys.all, "health"] as const,
  search: (query: string) => [...queryKeys.all, "search", query.trim()] as const,
  data: (params: { symbol: string; market: Market | string; startDate: string; endDate: string; adjust?: string }) =>
    [
      ...queryKeys.all,
      "data",
      normalizeSymbol(params.symbol),
      params.market,
      params.startDate,
      params.endDate,
      params.adjust || "",
    ] as const,
  forecast: (params: {
    symbol: string;
    market?: Market | string;
    predLen: number;
    rowCount: number;
    lastTimestamp?: string;
    modelId?: string;
    dryRun?: boolean;
  }) =>
    [
      ...queryKeys.all,
      "forecast",
      normalizeSymbol(params.symbol),
      params.market || "cn",
      params.predLen,
      params.modelId || "",
      params.rowCount,
      params.lastTimestamp || "",
      Boolean(params.dryRun),
    ] as const,
  batch: (params: { symbols: string[] | string; market: Market | string; predLen: number; modelId?: string }) =>
    [
      ...queryKeys.all,
      "batch",
      normalizeSymbols(params.symbols).join(","),
      params.market,
      params.predLen,
      params.modelId || "",
    ] as const,
  backtest: (params: {
    symbols: string[] | string;
    startDate: string;
    endDate: string;
    topK: number;
    predLen?: number;
    windowSize?: number;
    step?: number;
    initialEquity?: number;
    benchmark?: string;
  }) =>
    [
      ...queryKeys.all,
      "backtest",
      normalizeSymbols(params.symbols).join(","),
      params.startDate,
      params.endDate,
      params.topK,
      params.predLen || 5,
      params.windowSize || 120,
      params.step || params.predLen || 5,
      params.initialEquity || 100000,
      params.benchmark || "",
    ] as const,
  indicator: (params: { symbol: string; market: Market | string }) =>
    [...queryKeys.all, "indicator", normalizeSymbol(params.symbol), params.market] as const,
  alerts: () => [...queryKeys.all, "alerts"] as const,
  agent: (params: { question: string; symbol?: string | null; market?: Market | string | null; language?: string | null }) =>
    [
      ...queryKeys.all,
      "agent",
      params.question.trim(),
      params.symbol ? normalizeSymbol(params.symbol) : "",
      params.market || "",
      params.language || "",
    ] as const,
  macro: (params: { question: string; market?: Market | string | null; providers?: string[]; language?: string | null; rssFeeds?: string[] }) =>
    [
      ...queryKeys.all,
      "macro",
      params.question.trim(),
      params.market || "",
      (params.providers || []).join(","),
      (params.rssFeeds || []).join(","),
      params.language || "",
    ] as const,
};
