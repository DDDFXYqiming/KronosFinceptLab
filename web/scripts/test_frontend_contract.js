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

function assertNotIncludes(source, needle, label) {
  if (source.includes(needle)) {
    throw new Error(`${label} must not include: ${needle}`);
  }
}

function assertBefore(source, first, second, label) {
  const firstIndex = source.indexOf(first);
  const secondIndex = source.indexOf(second);
  if (firstIndex < 0 || secondIndex < 0 || firstIndex >= secondIndex) {
    throw new Error(`${label} order is wrong: expected ${first} before ${second}`);
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
for (const needle of ["absolute left-0 top-0", "border-r border-border", "w-[min(82vw,18rem)]"]) {
  assertIncludes(header, needle, "mobile drawer contract");
}
assertBefore(header, "aria-label=\"打开导航菜单\"", "href=\"/\" className=\"flex min-w-0 items-center gap-2 md:hidden\"", "mobile header open button");
assertBefore(header, "aria-label=\"关闭导航菜单\"", "mt-0.5 text-xs font-mono text-muted-foreground", "mobile drawer close button");
assertNotIncludes(header, "grid grid-cols-3 gap-2 border-b border-border p-4 text-xs", "mobile drawer status card contract");

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
  "cleanUserVisibleText",
  "依据与工具调用",
  "auto-cols-[minmax(9.5rem,1fr)]",
]) {
  assertIncludes(analysis, needle, "analysis workspace contract");
}
assertBefore(analysis, "汇总研究报告", "依据与工具调用", "analysis evidence placement");
for (const forbidden of ["request_id", "JSON.stringify(call.metadata", "{call.name}"]) {
  assertNotIncludes(analysis, forbidden, "analysis public tool details");
}

const macro = read("src/app/macro/page.tsx");
for (const needle of [
  "宏观洞察",
  "queryKeys.macro",
  "macroAnalyze",
  "macro_provider_coverage",
  "macro_data_quality",
  "macro_dimension_coverage",
  "WW3 的概率是多少",
  "数据质量与覆盖率",
  "Provider 覆盖矩阵",
  "信号来源（分层）",
  "信号一致性评估",
  "概率估计",
  "待监控信号",
  "auto-cols-[minmax(9.5rem,1fr)]",
  "sm:hidden",
  "独立维度",
]) {
  assertIncludes(macro, needle, "macro workspace contract");
}

console.log("Frontend contract tests passed.");
