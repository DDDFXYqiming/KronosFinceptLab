import type { Market } from "@/lib/markets";

export type SymbolKind = "a_stock" | "us_stock" | "hk_stock" | "crypto" | "commodity" | "unknown";

export const DEFAULT_SYMBOL = "600036";
export const DEFAULT_SYMBOL_NAME = "招商银行";
export const DEFAULT_BATCH_SYMBOLS = "600036,000858,000001";
export const DEFAULT_BACKTEST_SYMBOLS = "600036,000858";

const SPLIT_SYMBOLS_PATTERN = /[,，\s]+/;

export function normalizeSymbol(symbol: string): string {
  return symbol.trim().toUpperCase();
}

export function normalizeSymbols(symbols: string[] | string): string[] {
  const parts = Array.isArray(symbols) ? symbols : symbols.split(SPLIT_SYMBOLS_PATTERN);
  return Array.from(new Set(parts.map(normalizeSymbol).filter(Boolean)));
}

export function detectSymbolKind(symbol: string): SymbolKind {
  const normalized = normalizeSymbol(symbol);
  if (/^\d{6}$/.test(normalized)) return "a_stock";
  if (/^\d{4,5}$/.test(normalized)) return "hk_stock";
  if (/^[A-Z]{1,6}=F$/.test(normalized)) return "commodity";
  if (/^[A-Z0-9]{2,12}[-/]?(USDT|USD|BTC|ETH)$/.test(normalized)) return "crypto";
  if (/^[A-Z]{1,6}([.-][A-Z])?$/.test(normalized)) return "us_stock";
  return "unknown";
}

export function inferMarketFromSymbol(symbol: string, fallback: Market = "cn"): Market {
  const kind = detectSymbolKind(symbol);
  if (kind === "a_stock") return "cn";
  if (kind === "hk_stock") return "hk";
  if (kind === "commodity") return "commodity";
  if (kind === "us_stock") return "us";
  return fallback;
}

export function formatSymbolList(symbols: string[] | string): string {
  return normalizeSymbols(symbols).join(",");
}
