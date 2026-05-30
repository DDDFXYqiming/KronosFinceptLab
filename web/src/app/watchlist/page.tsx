"use client";

import Link from "next/link";
import { type ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/Card";
import { SectionLabel } from "@/components/ui/SectionLabel";
import { Button } from "@/components/ui/Button";
import { useAppStore, type WatchlistItem } from "@/stores/app";
import { DEFAULT_MARKET, MARKET_OPTIONS, getMarketLabel, type Market } from "@/lib/markets";
import { DEFAULT_SYMBOL, normalizeSymbol } from "@/lib/symbols";
import { api, formatApiError } from "@/lib/api";
import { downloadTextFile, makeDatedFilename, parseCsv, toCsv } from "@/lib/exportUtils";
import { formatCompactNumber, formatNumber } from "@/lib/utils";
import { queryKeys } from "@/lib/queryKeys";
import { useSessionState } from "@/lib/useSessionState";
import type { DataResponse, IndicatorResponse, WatchlistListItem } from "@/types/api";

interface QuoteSummary {
  symbol: string;
  market: Market;
  latestPrice: number | null;
  changePct: number | null;
  volume: number | null;
  rsi: number | null;
  macd: number | null;
  error?: string;
}

interface ResearchSummary {
  conclusion?: string;
  recommendation?: string;
  risk_level?: string;
  timestamp?: string;
}

type SortKey = "symbol" | "market" | "latestPrice" | "changePct" | "volume" | "rsi" | "macd" | "addedAt";
type SortDirection = "asc" | "desc";

function itemKey(item: Pick<WatchlistItem, "market" | "symbol">): string {
  return `${item.market}:${item.symbol}`;
}

function parseTags(value: string): string[] {
  return value.split(/[,，|\s]+/).map((tag) => tag.trim()).filter(Boolean);
}

function extractIndicatorNumber(response: IndicatorResponse | null, key: string, child?: string): number | null {
  const value = response?.indicators?.[key];
  const raw = child && value && typeof value === "object" ? (value as Record<string, unknown>)[child] : value;
  return typeof raw === "number" && Number.isFinite(raw) ? raw : null;
}

function ymd(date: Date): string {
  return `${date.getFullYear()}${String(date.getMonth() + 1).padStart(2, "0")}${String(date.getDate()).padStart(2, "0")}`;
}

function isMarket(value: string): value is Market {
  return MARKET_OPTIONS.some((option) => option.value === value);
}

function riskTags(quote?: QuoteSummary, summary?: ResearchSummary): string[] {
  const tags: string[] = [];
  if (summary?.risk_level) tags.push(`风险:${summary.risk_level}`);
  if (quote?.changePct != null && Math.abs(quote.changePct) > 0.15) tags.push("高波动");
  if (quote?.rsi != null && quote.rsi > 70) tags.push("超买");
  if (quote?.rsi != null && quote.rsi < 30) tags.push("超卖");
  return tags;
}

function loadResearchSummary(key: string): ResearchSummary | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(`kronos-research-summary-${key}`);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function parseImportedWatchlist(text: string): WatchlistItem[] {
  const rows = parseCsv(text).filter((row) => row.some((cell) => cell.trim()));
  if (rows.length === 0) return [];
  const first = rows[0].map((cell) => cell.trim().toLowerCase());
  const hasHeader = first.includes("symbol") || first.includes("market");
  const headers = hasHeader ? first : ["symbol", "market", "name", "note", "tags", "addedat"];
  const body = hasHeader ? rows.slice(1) : rows;

  return body.map((row) => {
    const values = Object.fromEntries(headers.map((header, index) => [header, row[index]?.trim() || ""]));
    const rawMarket = values.market || DEFAULT_MARKET;
    return {
      symbol: normalizeSymbol(values.symbol || row[0] || ""),
      market: isMarket(rawMarket) ? rawMarket : DEFAULT_MARKET,
      name: values.name || undefined,
      note: values.note || undefined,
      tags: parseTags(values.tags || ""),
      addedAt: values.addedat || values.addedAt || new Date().toISOString(),
    };
  }).filter((item) => Boolean(item.symbol));
}

function getSortValue(item: WatchlistItem, quote: QuoteSummary | undefined, key: SortKey): string | number {
  if (key === "symbol") return item.symbol;
  if (key === "market") return item.market;
  if (key === "addedAt") return item.addedAt || "";
  return quote?.[key] ?? Number.NEGATIVE_INFINITY;
}

function compareValues(a: string | number, b: string | number, direction: SortDirection): number {
  const sign = direction === "asc" ? 1 : -1;
  if (typeof a === "number" && typeof b === "number") return (a - b) * sign;
  return String(a).localeCompare(String(b), "zh-CN") * sign;
}

export default function WatchlistPage() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { watchlist, addToWatchlist, removeFromWatchlist, updateWatchlistItem, replaceWatchlist } = useAppStore();
  const [symbol, setSymbol] = useSessionState("kronos-watchlist-symbol", "");
  const [market, setMarket] = useSessionState<Market>("kronos-watchlist-market", DEFAULT_MARKET);
  const [name, setName] = useSessionState("kronos-watchlist-name", "");
  const [note, setNote] = useSessionState("kronos-watchlist-note", "");
  const [tags, setTags] = useSessionState("kronos-watchlist-tags", "");
  const [selectedKeys, setSelectedKeys] = useSessionState<string[]>("kronos-watchlist-selected", []);
  const [sortKey, setSortKey] = useSessionState<SortKey>("kronos-watchlist-sort-key", "symbol");
  const [sortDirection, setSortDirection] = useSessionState<SortDirection>("kronos-watchlist-sort-direction", "asc");
  const [quoteSummaries, setQuoteSummaries] = useSessionState<Record<string, QuoteSummary>>("kronos-watchlist-quotes", {});
  const [researchSummaries, setResearchSummaries] = useState<Record<string, ResearchSummary>>({});
  const [loadingQuotes, setLoadingQuotes] = useState(false);
  const [serverLists, setServerLists] = useState<WatchlistListItem[]>([]);
  const [syncingServer, setSyncingServer] = useState(false);
  const [error, setError] = useSessionState("kronos-watchlist-error", "");

  const selectedItems = useMemo(() => watchlist.filter((item) => selectedKeys.includes(itemKey(item))), [selectedKeys, watchlist]);
  const selectedSymbols = selectedItems.map((item) => item.symbol);
  const selectedSymbolsParam = selectedSymbols.join(",");
  const sortedWatchlist = useMemo(() => {
    return [...watchlist].sort((a, b) => {
      const aQuote = quoteSummaries[itemKey(a)];
      const bQuote = quoteSummaries[itemKey(b)];
      return compareValues(getSortValue(a, aQuote, sortKey), getSortValue(b, bQuote, sortKey), sortDirection);
    });
  }, [quoteSummaries, sortDirection, sortKey, watchlist]);

  useEffect(() => {
    setResearchSummaries(Object.fromEntries(watchlist.map((item) => {
      const key = itemKey(item);
      return [key, loadResearchSummary(key) || {}];
    })));
  }, [watchlist]);

  const handleAdd = () => {
    const requestSymbol = normalizeSymbol(symbol || DEFAULT_SYMBOL);
    if (!requestSymbol) return;
    addToWatchlist({
      symbol: requestSymbol,
      market,
      name: name.trim() || undefined,
      note: note.trim() || undefined,
      tags: parseTags(tags),
      addedAt: new Date().toISOString(),
    });
    setSymbol("");
    setName("");
    setNote("");
    setTags("");
  };

  const toggleSelected = (item: WatchlistItem) => {
    const key = itemKey(item);
    setSelectedKeys((current) => current.includes(key) ? current.filter((candidate) => candidate !== key) : [...current, key]);
  };

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDirection((current) => current === "asc" ? "desc" : "asc");
      return;
    }
    setSortKey(key);
    setSortDirection(key === "symbol" || key === "market" ? "asc" : "desc");
  };

  const selectAll = () => setSelectedKeys(watchlist.map(itemKey));
  const clearSelection = () => setSelectedKeys([]);

  const fetchQuote = async (item: WatchlistItem): Promise<QuoteSummary> => {
    const end = new Date();
    const start = new Date(end);
    start.setDate(start.getDate() - 90);
    const startDate = ymd(start);
    const endDate = ymd(end);
    try {
      const dataKey = queryKeys.data({ symbol: item.symbol, market: item.market, startDate, endDate, adjust: "qfq" });
      const indicatorKey = queryKeys.indicator({ symbol: item.symbol, market: item.market });
      const [data, indicators] = await Promise.all([
        queryClient.fetchQuery({
          queryKey: dataKey,
          queryFn: ({ signal }) => item.market === "cn"
            ? api.getData(item.symbol, startDate, endDate, "qfq", { signal })
            : api.getGlobalData(item.symbol, item.market, startDate, endDate, { signal }),
        }),
        queryClient.fetchQuery({
          queryKey: indicatorKey,
          queryFn: ({ signal }) => api.getIndicators(item.symbol, item.market, { signal }),
        }).catch(() => null),
      ]) as [DataResponse, IndicatorResponse | null];
      const rows = data.rows || [];
      const first = rows[0];
      const last = rows[rows.length - 1];
      return {
        symbol: item.symbol,
        market: item.market,
        latestPrice: last?.close ?? null,
        changePct: first && last && first.close > 0 ? last.close / first.close - 1 : null,
        volume: last?.volume ?? null,
        rsi: extractIndicatorNumber(indicators, "rsi", "value") ?? extractIndicatorNumber(indicators, "rsi"),
        macd: extractIndicatorNumber(indicators, "macd", "macd"),
      };
    } catch (exc) {
      return {
        symbol: item.symbol,
        market: item.market,
        latestPrice: null,
        changePct: null,
        volume: null,
        rsi: null,
        macd: null,
        error: formatApiError(exc, "行情获取失败"),
      };
    }
  };

  const refreshQuoteSummaries = async () => {
    if (watchlist.length === 0) return;
    setLoadingQuotes(true);
    setError("");
    try {
      const rows = await Promise.all(watchlist.map(fetchQuote));
      setQuoteSummaries(Object.fromEntries(rows.map((row) => [`${row.market}:${row.symbol}`, row])));
    } catch (exc) {
      setError(formatApiError(exc, "刷新自选行情失败"));
    } finally {
      setLoadingQuotes(false);
    }
  };

  const refreshServerLists = async () => {
    setSyncingServer(true);
    try {
      const response = await api.watchlistList({ timeoutMs: 15000 });
      setServerLists(response.watchlists);
    } catch (exc) {
      setError(formatApiError(exc, "加载服务端自选失败"));
    } finally {
      setSyncingServer(false);
    }
  };

  useEffect(() => {
    void refreshServerLists();
  }, []);

  const saveCurrentWatchlist = async () => {
    if (watchlist.length === 0) return;
    setSyncingServer(true);
    try {
      await api.watchlistCreate({
        name: name.trim() || "本地自选",
        market: market,
        symbols: watchlist.map((item) => item.symbol),
        tags: ["frontend"],
        note: "Saved from watchlist page",
      }, { timeoutMs: 15000 });
      await refreshServerLists();
      setError("");
    } catch (exc) {
      setError(formatApiError(exc, "保存服务端自选失败"));
    } finally {
      setSyncingServer(false);
    }
  };

  const loadServerWatchlist = (item: WatchlistListItem) => {
    replaceWatchlist(item.symbols.map((symbol) => ({
      symbol,
      market: isMarket(item.market) ? item.market : DEFAULT_MARKET,
      tags: item.tags || [],
      note: item.note || undefined,
      addedAt: new Date(item.updated_at * 1000).toISOString(),
    })));
  };

  const deleteServerWatchlist = async (id: string) => {
    setSyncingServer(true);
    try {
      await api.watchlistDelete(id, { timeoutMs: 15000 });
      await refreshServerLists();
    } catch (exc) {
      setError(formatApiError(exc, "删除服务端自选失败"));
    } finally {
      setSyncingServer(false);
    }
  };

  const handleExportWatchlist = () => {
    const csv = toCsv(
      ["symbol", "market", "name", "note", "tags", "addedAt"],
      watchlist.map((item) => [item.symbol, item.market, item.name || "", item.note || "", (item.tags || []).join("|"), item.addedAt])
    );
    downloadTextFile(makeDatedFilename("watchlist", watchlist.map((item) => item.symbol)), csv);
  };

  const handleImportWatchlist = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const imported = parseImportedWatchlist(await file.text());
      replaceWatchlist([...watchlist, ...imported]);
      setError(imported.length === 0 ? "未在 CSV 中找到有效股票代码。" : "");
    } catch (exc) {
      setError(formatApiError(exc, "导入自选失败"));
    } finally {
      event.target.value = "";
    }
  };

  const copySymbol = async (item: WatchlistItem) => {
    if (typeof navigator === "undefined" || !navigator.clipboard) return;
    await navigator.clipboard.writeText(item.symbol);
  };

  const sortMark = (key: SortKey) => sortKey === key ? (sortDirection === "asc" ? " ↑" : " ↓") : "";

  return (
    <div className="page-shell space-y-6">
      <SectionLabel>自选股</SectionLabel>
      <h1 className="page-title">自选股</h1>

      <Card>
        <CardTitle subtitle="保存研究备注、标签，并对选中标的批量预测/批量分析。">添加股票</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-6">
          <div>
            <label className="field-label">代码</label>
            <input type="text" value={symbol} onChange={(e) => setSymbol(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleAdd()} className="app-input mt-1 font-mono" placeholder={`例如 ${DEFAULT_SYMBOL}`} />
          </div>
          <div>
            <label className="field-label">市场</label>
            <select value={market} onChange={(e) => setMarket(e.target.value as Market)} className="app-input mt-1">{MARKET_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}</select>
          </div>
          <div>
            <label className="field-label">名称</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} className="app-input mt-1" placeholder="可选" />
          </div>
          <div>
            <label className="field-label">标签</label>
            <input type="text" value={tags} onChange={(e) => setTags(e.target.value)} className="app-input mt-1" placeholder="低估, 银行" />
          </div>
          <div className="xl:col-span-2">
            <label className="field-label">备注</label>
            <input type="text" value={note} onChange={(e) => setNote(e.target.value)} className="app-input mt-1" placeholder="研究假设或跟踪理由" />
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row md:flex-wrap">
          <Button onClick={handleAdd}>添加</Button>
          <Button variant="secondary" onClick={refreshQuoteSummaries} loading={loadingQuotes}>刷新行情/指标</Button>
          <Button variant="secondary" onClick={handleExportWatchlist} disabled={watchlist.length === 0}>导出自选</Button>
          <Button variant="secondary" onClick={() => fileInputRef.current?.click()}>导入自选</Button>
          <Button variant="secondary" onClick={saveCurrentWatchlist} loading={syncingServer} disabled={watchlist.length === 0}>保存到服务端</Button>
          <Button variant="secondary" onClick={refreshServerLists} loading={syncingServer}>刷新服务端</Button>
          <input ref={fileInputRef} className="hidden" type="file" accept=".csv,text/csv" onChange={handleImportWatchlist} />
        </div>
      </Card>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">{error}</div>}

      <Card>
        <CardTitle subtitle="服务端 SQLite 持久化，重启后仍可恢复。">服务端自选列表</CardTitle>
        <div className="space-y-2 text-sm">
          {serverLists.length === 0 && <p className="text-gray-500">暂无服务端自选列表。</p>}
          {serverLists.map((item) => (
            <div key={item.id} className="flex flex-col gap-2 rounded-lg border border-border p-3 md:flex-row md:items-center md:justify-between">
              <div>
                <div className="font-semibold text-white">{item.name} <span className="font-mono text-xs text-gray-500">{item.id.slice(0, 8)}</span></div>
                <div className="text-xs text-muted-foreground">{item.market} · {item.symbols.join(", ")} · {new Date(item.updated_at * 1000).toLocaleString()}</div>
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => loadServerWatchlist(item)}>加载</Button>
                <Button variant="danger" onClick={() => deleteServerWatchlist(item.id)}>删除</Button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {watchlist.length === 0 ? (
        <Card>
          <div className="py-12 text-center text-gray-500">
            <p className="mb-2 text-lg">自选股列表为空</p>
            <p className="text-sm">添加股票开始追踪</p>
          </div>
        </Card>
      ) : (
        <Card>
          <CardTitle action={<div className="flex flex-col gap-2 sm:flex-row"><Button variant="ghost" onClick={selectAll}>全选</Button><Button variant="ghost" onClick={clearSelection}>清空</Button></div>}>已保存股票 ({watchlist.length})</CardTitle>
          <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-3">
            <Link href={`/batch?symbols=${selectedSymbolsParam}`} className="btn-primary flex h-12 items-center justify-center rounded-xl px-6 text-sm font-medium">批量预测</Link>
            <Link href={`/analysis?symbol=${selectedSymbols[0] || ""}`} className="btn-secondary flex h-12 items-center justify-center rounded-xl px-6 text-sm font-medium">批量分析</Link>
            <Link href={`/backtest?symbols=${selectedSymbolsParam}`} className="btn-secondary flex h-12 items-center justify-center rounded-xl px-6 text-sm font-medium">组合回测</Link>
          </div>
          <div className="table-scroll">
            <table className="min-w-[82rem] w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 text-gray-400">
                  <th className="py-2 text-left">选择</th>
                  <th className="py-2 text-left"><button type="button" onClick={() => toggleSort("symbol")}>代码{sortMark("symbol")}</button></th>
                  <th className="py-2 text-left"><button type="button" onClick={() => toggleSort("market")}>名称/市场{sortMark("market")}</button></th>
                  <th className="py-2 text-right"><button type="button" onClick={() => toggleSort("latestPrice")}>最新价{sortMark("latestPrice")}</button></th>
                  <th className="py-2 text-right"><button type="button" onClick={() => toggleSort("changePct")}>区间涨跌{sortMark("changePct")}</button></th>
                  <th className="py-2 text-right"><button type="button" onClick={() => toggleSort("volume")}>成交量{sortMark("volume")}</button></th>
                  <th className="py-2 text-right"><button type="button" onClick={() => toggleSort("rsi")}>RSI{sortMark("rsi")}</button></th>
                  <th className="py-2 text-right"><button type="button" onClick={() => toggleSort("macd")}>MACD{sortMark("macd")}</button></th>
                  <th className="py-2 text-left">标签/最近结论</th>
                  <th className="py-2 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {sortedWatchlist.map((item) => {
                  const key = itemKey(item);
                  const quote = quoteSummaries[key];
                  const summary = researchSummaries[key];
                  const tags = riskTags(quote, summary);
                  return (
                    <tr key={key} onContextMenu={(event) => { event.preventDefault(); void copySymbol(item); }} className="border-b border-gray-800 hover:bg-surface-overlay/50">
                      <td className="py-3"><input type="checkbox" checked={selectedKeys.includes(key)} onChange={() => toggleSelected(item)} /></td>
                      <td className="py-3 font-mono font-bold text-white">{item.symbol}</td>
                      <td className="py-3">
                        <input className="app-input h-9" value={item.name || ""} onChange={(e) => updateWatchlistItem(item.symbol, item.market, { name: e.target.value })} placeholder={getMarketLabel(item.market)} />
                        <p className="mt-1 text-xs text-muted-foreground">{getMarketLabel(item.market)}</p>
                      </td>
                      <td className="py-3 text-right">{quote?.latestPrice == null ? "-" : formatNumber(quote.latestPrice, 2)}</td>
                      <td className={`py-3 text-right ${quote?.changePct == null ? "" : quote.changePct >= 0 ? "text-accent-green" : "text-accent-red"}`}>{quote?.changePct == null ? "-" : `${(quote.changePct * 100).toFixed(2)}%`}</td>
                      <td className="py-3 text-right">{formatCompactNumber(quote?.volume)}</td>
                      <td className="py-3 text-right">{quote?.rsi == null ? "-" : formatNumber(quote.rsi, 2)}</td>
                      <td className="py-3 text-right">{quote?.macd == null ? "-" : formatNumber(quote.macd, 4)}</td>
                      <td className="py-3">
                        <div className="mb-2 flex flex-wrap gap-1">{[...(item.tags || []), ...tags].map((tag) => <span key={tag} className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{tag}</span>)}</div>
                        <input className="app-input h-9" value={(item.tags || []).join(", ")} onChange={(e) => updateWatchlistItem(item.symbol, item.market, { tags: parseTags(e.target.value) })} placeholder="标签" />
                        <input className="app-input mt-2 h-9" value={item.note || ""} onChange={(e) => updateWatchlistItem(item.symbol, item.market, { note: e.target.value })} placeholder="备注" />
                        {summary?.conclusion && <p className="mt-2 max-w-sm text-xs text-muted-foreground">{summary.recommendation ? `${summary.recommendation}：` : ""}{summary.conclusion}</p>}
                        {quote?.error && <p className="mt-2 max-w-sm text-xs text-error">{quote.error}</p>}
                      </td>
                      <td className="py-3 text-right">
                        <div className="flex flex-wrap justify-end gap-2">
                          <button onClick={() => copySymbol(item)} className="rounded bg-surface-overlay px-2 py-1 text-xs text-gray-300">复制</button>
                          <Link href={`/forecast?symbol=${item.symbol}&market=${item.market}`} className="rounded bg-surface-overlay px-2 py-1 text-xs text-gray-300">预测</Link>
                          <Link href={`/analysis?symbol=${item.symbol}&market=${item.market}`} className="rounded bg-primary/20 px-2 py-1 text-xs text-primary-light">分析</Link>
                          <Link href={`/alerts?symbol=${item.symbol}&market=${item.market}`} className="rounded bg-amber-100 px-2 py-1 text-xs text-amber-700">告警</Link>
                          <button onClick={() => removeFromWatchlist(item.symbol, item.market)} className="rounded bg-red-900/30 px-2 py-1 text-xs text-red-400">移除</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
