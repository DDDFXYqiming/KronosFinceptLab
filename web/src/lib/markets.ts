import { DEFAULT_LANGUAGE, t, type Language } from "@/lib/i18n";

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

export function getMarketLabel(market: Market | string, language: Language = DEFAULT_LANGUAGE): string {
  return t(language, `market.${market}`) || MARKET_OPTIONS.find((option) => option.value === market)?.label || String(market);
}

export function getMarketOptions(language: Language = DEFAULT_LANGUAGE): MarketOption[] {
  return MARKET_OPTIONS.map((option) => ({
    ...option,
    label: getMarketLabel(option.value, language),
  }));
}

export function toBackendMarket(market: Market): string {
  return MARKET_OPTIONS.find((option) => option.value === market)?.backendValue || market;
}
