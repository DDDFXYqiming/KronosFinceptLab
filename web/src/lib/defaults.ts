export type { Market, MarketOption } from "@/lib/markets";
export {
  DEFAULT_MARKET,
  MARKET_OPTIONS,
  getMarketLabel,
  isMarket,
  normalizeMarket,
  toBackendMarket,
} from "@/lib/markets";
export {
  DEFAULT_BACKTEST_SYMBOLS,
  DEFAULT_BATCH_SYMBOLS,
  DEFAULT_SYMBOL,
  DEFAULT_SYMBOL_NAME,
  detectSymbolKind,
  formatSymbolList,
  inferMarketFromSymbol,
  normalizeSymbol,
  normalizeSymbols,
} from "@/lib/symbols";

export const DEFAULT_MODEL_ID = "NeoQuasar/Kronos-base";
export const DEFAULT_TOKENIZER_ID = "NeoQuasar/Kronos-Tokenizer-base";
export const SUPPORTED_MODEL_IDS = [
  "NeoQuasar/Kronos-mini",
  "NeoQuasar/Kronos-small",
  "NeoQuasar/Kronos-base",
] as const;

export interface ModelSizeInfo {
  label: string;
  memory: string;
  speed: string;
  hint: string;
}

export const MODEL_SIZE_MAP: Record<string, ModelSizeInfo> = {
  "NeoQuasar/Kronos-mini": {
    label: "Mini",
    memory: "~2 GB",
    speed: "Fast",
    hint: "Minimum latency; best for batch inference and rapid prototyping.",
  },
  "NeoQuasar/Kronos-small": {
    label: "Small",
    memory: "~4 GB",
    speed: "Moderate",
    hint: "Balanced accuracy/memory for single-symbol forecasts.",
  },
  "NeoQuasar/Kronos-base": {
    label: "Base",
    memory: "~8 GB",
    speed: "Standard",
    hint: "Highest accuracy; recommended for multi-asset analysis and backtests.",
  },
};
