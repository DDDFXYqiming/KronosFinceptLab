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
for (const needle of ["health:", "data:", "forecast:", "batch:", "backtest:", "agent:", "normalizeSymbols"]) {
  assertIncludes(queryKeys, needle, "query key contract");
}

const sessionState = read("src/lib/useSessionState.ts");
for (const needle of ["window.sessionStorage.getItem", "window.sessionStorage.setItem", "preferInitial"]) {
  assertIncludes(sessionState, needle, "session state contract");
}

const analysis = read("src/app/analysis/page.tsx");
for (const needle of [
  "新建对话/清空本轮",
  "queryKeys.agent",
  "Agent 执行时间线",
  "ToolCallList",
  "request_id",
]) {
  assertIncludes(analysis, needle, "analysis workspace contract");
}

console.log("Frontend contract tests passed.");
