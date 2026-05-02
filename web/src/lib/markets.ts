export type Market = "cn" | "us" | "hk" | "commodity";

export interface MarketOption {
  value: Market;
  label: string;
  backendValue: string;
}

export const DEFAULT_MARKET: Market = "cn";

export const MARKET_OPTIONS: MarketOption[] = [
  { value: "cn", label: "A股", backendValue: "cn" },
  { value: "us", label: "美股", backendValue: "us" },
  { value: "hk", label: "港股", backendValue: "hk" },
  { value: "commodity", label: "大宗商品", backendValue: "commodity" },
];

const MARKET_SET = new Set<Market>(MARKET_OPTIONS.map((option) => option.value));

export function isMarket(value: unknown): value is Market {
  return typeof value === "string" && MARKET_SET.has(value as Market);
}

export function normalizeMarket(value: string | null | undefined, fallback: Market = DEFAULT_MARKET): Market {
  return isMarket(value) ? value : fallback;
}

export function getMarketLabel(market: Market | string): string {
  return MARKET_OPTIONS.find((option) => option.value === market)?.label || String(market);
}

export function toBackendMarket(market: Market): string {
  return MARKET_OPTIONS.find((option) => option.value === market)?.backendValue || market;
}
