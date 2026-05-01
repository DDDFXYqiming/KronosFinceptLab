export type Market = "cn" | "us" | "hk" | "commodity";

export const DEFAULT_SYMBOL = "600036";
export const DEFAULT_SYMBOL_NAME = "招商银行";
export const DEFAULT_MARKET: Market = "cn";
export const DEFAULT_BATCH_SYMBOLS = "600036,000858,000001";
export const DEFAULT_BACKTEST_SYMBOLS = "600036,000858";

export const DEFAULT_MODEL_ID = "NeoQuasar/Kronos-base";
export const DEFAULT_TOKENIZER_ID = "NeoQuasar/Kronos-Tokenizer-base";

export const MARKET_OPTIONS: { value: Market; label: string }[] = [
  { value: "cn", label: "A股" },
  { value: "us", label: "美股" },
  { value: "hk", label: "港股" },
  { value: "commodity", label: "大宗商品" },
];
