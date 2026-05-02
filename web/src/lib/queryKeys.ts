import type { Market } from "@/lib/defaults";

function normalizeSymbol(symbol: string): string {
  return symbol.trim().toUpperCase();
}

export function normalizeSymbols(symbols: string[] | string): string[] {
  const parts = Array.isArray(symbols) ? symbols : symbols.split(",");
  return parts.map(normalizeSymbol).filter(Boolean);
}

export const queryKeys = {
  all: ["kronos"] as const,
  health: () => [...queryKeys.all, "health"] as const,
  search: (query: string) => [...queryKeys.all, "search", query.trim()] as const,
  data: (params: { symbol: string; market: Market | string; startDate: string; endDate: string }) =>
    [
      ...queryKeys.all,
      "data",
      normalizeSymbol(params.symbol),
      params.market,
      params.startDate,
      params.endDate,
    ] as const,
  forecast: (params: {
    symbol: string;
    market?: Market | string;
    predLen: number;
    rowCount: number;
    lastTimestamp?: string;
    dryRun?: boolean;
  }) =>
    [
      ...queryKeys.all,
      "forecast",
      normalizeSymbol(params.symbol),
      params.market || "cn",
      params.predLen,
      params.rowCount,
      params.lastTimestamp || "",
      Boolean(params.dryRun),
    ] as const,
  batch: (params: { symbols: string[] | string; market: Market | string; predLen: number }) =>
    [
      ...queryKeys.all,
      "batch",
      normalizeSymbols(params.symbols).join(","),
      params.market,
      params.predLen,
    ] as const,
  backtest: (params: { symbols: string[] | string; startDate: string; endDate: string; topK: number }) =>
    [
      ...queryKeys.all,
      "backtest",
      normalizeSymbols(params.symbols).join(","),
      params.startDate,
      params.endDate,
      params.topK,
    ] as const,
  agent: (params: { question: string; symbol?: string | null; market?: Market | string | null }) =>
    [
      ...queryKeys.all,
      "agent",
      params.question.trim(),
      params.symbol ? normalizeSymbol(params.symbol) : "",
      params.market || "",
    ] as const,
};
