const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function assertIncludes(source, needle, label) {
  if (!source.includes(needle)) {
    throw new Error(`${label} is missing: ${needle}`);
  }
}

const api = read("src/lib/api.ts");
for (const needle of [
  "DEFAULT_TIMEOUT_MS",
  "AbortController",
  "ApiClientOptions",
  "function get<T>",
  "function post<T>",
  "X-Request-ID",
  "enrichGatewayError",
  "request_id",
  "macroAnalyze",
  "/v1/analyze/macro",
]) {
  assertIncludes(api, needle, "api client contract");
}

const markets = read("src/lib/markets.ts");
for (const needle of ["MARKET_OPTIONS", "normalizeMarket", "toBackendMarket", "getMarketLabel"]) {
  assertIncludes(markets, needle, "market utility contract");
}

const symbols = read("src/lib/symbols.ts");
for (const needle of [
  "DEFAULT_SYMBOL = \"600036\"",
  "normalizeSymbol",
  "normalizeSymbols",
  "inferMarketFromSymbol",
  "detectSymbolKind",
]) {
  assertIncludes(symbols, needle, "symbol utility contract");
}

const queryKeys = read("src/lib/queryKeys.ts");
for (const needle of ["health:", "data:", "forecast:", "batch:", "backtest:", "agent:", "macro:", "normalizeSymbols"]) {
  assertIncludes(queryKeys, needle, "query key contract");
}

const sessionState = read("src/lib/useSessionState.ts");
for (const needle of ["window.sessionStorage.getItem", "window.sessionStorage.setItem", "preferInitial"]) {
  assertIncludes(sessionState, needle, "session state contract");
}

const header = read("src/components/layout/Header.tsx");
for (const needle of ["absolute left-0 top-0", "border-r border-border", "w-[min(88vw,22rem)]"]) {
  assertIncludes(header, needle, "mobile drawer contract");
}

const card = read("src/components/ui/Card.tsx");
for (const needle of ["flex-col", "sm:flex-row", "break-words text-base"]) {
  assertIncludes(card, needle, "mobile card title contract");
}

const globals = read("src/app/globals.css");
for (const needle of ["@media (max-width: 767px)", ".card {", "padding: 1rem", ".chart-frame"]) {
  assertIncludes(globals, needle, "mobile card CSS contract");
}

const analysis = read("src/app/analysis/page.tsx");
for (const needle of [
  "新建对话/清空本轮",
  "queryKeys.agent",
  "Agent 执行进度",
  "Kronos 预测（未来",
  "KronosMiniKline",
  "ToolCallList",
  "request_id",
  "auto-cols-[minmax(9.5rem,1fr)]",
]) {
  assertIncludes(analysis, needle, "analysis workspace contract");
}

const macro = read("src/app/macro/page.tsx");
for (const needle of [
  "宏观洞察",
  "queryKeys.macro",
  "macroAnalyze",
  "WW3 的概率是多少",
  "信号来源（分层）",
  "信号一致性评估",
  "概率估计",
  "待监控信号",
  "auto-cols-[minmax(9.5rem,1fr)]",
]) {
  assertIncludes(macro, needle, "macro workspace contract");
}

console.log("Frontend contract tests passed.");
