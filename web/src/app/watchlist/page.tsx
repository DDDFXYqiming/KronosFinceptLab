"use client";

import Link from "next/link";
import { type ChangeEvent, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { useAppStore, type WatchlistItem } from "@/stores/app";
import { DEFAULT_MARKET, MARKET_OPTIONS, getMarketLabel, type Market } from "@/lib/markets";
import { DEFAULT_SYMBOL, normalizeSymbol } from "@/lib/symbols";
import { api, formatApiError } from "@/lib/api";
import { downloadTextFile, toCsv } from "@/lib/exportUtils";
import { formatNumber } from "@/lib/utils";
import { queryKeys } from "@/lib/queryKeys";
import { useSessionState } from "@/lib/useSessionState";
import type { DataResponse, IndicatorResponse } from "@/types/api";

interface QuoteSummary { symbol: string; market: Market; latestPrice: number | null; changePct: number | null; rsi: number | null; macd: number | null; error?: string; }
function itemKey(item: Pick<WatchlistItem, "market" | "symbol">): string { return `${item.market}:${item.symbol}`; }
function parseTags(value: string): string[] { return value.split(/[,，\s]+/).map((tag) => tag.trim()).filter(Boolean); }
function extractIndicatorNumber(response: IndicatorResponse | null, key: string, child?: string): number | null { const value = response?.indicators?.[key]; const raw = child && value && typeof value === "object" ? (value as Record<string, unknown>)[child] : value; return typeof raw === "number" && Number.isFinite(raw) ? raw : null; }
function ymd(date: Date): string { return `${date.getFullYear()}${String(date.getMonth() + 1).padStart(2, "0")}${String(date.getDate()).padStart(2, "0")}`; }

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
  const [quoteSummaries, setQuoteSummaries] = useSessionState<Record<string, QuoteSummary>>("kronos-watchlist-quotes", {});
  const [loadingQuotes, setLoadingQuotes] = useState(false);
  const [error, setError] = useSessionState("kronos-watchlist-error", "");
  const selectedItems = useMemo(() => watchlist.filter((item) => selectedKeys.includes(itemKey(item))), [selectedKeys, watchlist]);
  const selectedSymbols = selectedItems.map((item) => item.symbol);
  const selectedSymbolsParam = selectedSymbols.join(",");

  const handleAdd = () => { const requestSymbol = normalizeSymbol(symbol || DEFAULT_SYMBOL); if (!requestSymbol) return; addToWatchlist({ symbol: requestSymbol, market, name: name.trim() || undefined, note: note.trim() || undefined, tags: parseTags(tags), addedAt: new Date().toISOString() }); setSymbol(""); setName(""); setNote(""); setTags(""); };
  const toggleSelected = (item: WatchlistItem) => { const key = itemKey(item); setSelectedKeys((current) => current.includes(key) ? current.filter((k) => k !== key) : [...current, key]); };
  const selectAll = () => setSelectedKeys(watchlist.map(itemKey));
  const clearSelection = () => setSelectedKeys([]);

  const fetchQuote = async (item: WatchlistItem): Promise<QuoteSummary> => {
    const end = new Date(); const start = new Date(end); start.setDate(start.getDate() - 90); const startDate = ymd(start); const endDate = ymd(end);
    try {
      const dataKey = queryKeys.data({ symbol: item.symbol, market: item.market, startDate, endDate, adjust: "qfq" });
      const indicatorKey = queryKeys.indicator({ symbol: item.symbol, market: item.market });
      const [data, indicators] = await Promise.all([
        queryClient.fetchQuery({ queryKey: dataKey, queryFn: ({ signal }) => item.market === "cn" ? api.getData(item.symbol, startDate, endDate, "qfq", { signal }) : api.getGlobalData(item.symbol, item.market, startDate, endDate, { signal }) }),
        queryClient.fetchQuery({ queryKey: indicatorKey, queryFn: ({ signal }) => api.getIndicators(item.symbol, item.market, { signal }) }).catch(() => null),
      ]) as [DataResponse, IndicatorResponse | null];
      const rows = data.rows || []; const first = rows[0]; const last = rows[rows.length - 1];
      return { symbol: item.symbol, market: item.market, latestPrice: last?.close ?? null, changePct: first && last && first.close > 0 ? last.close / first.close - 1 : null, rsi: extractIndicatorNumber(indicators, "rsi", "value") ?? extractIndicatorNumber(indicators, "rsi"), macd: extractIndicatorNumber(indicators, "macd", "macd") };
    } catch (exc: any) { return { symbol: item.symbol, market: item.market, latestPrice: null, changePct: null, rsi: null, macd: null, error: formatApiError(exc, "行情获取失败") }; }
  };

  const refreshQuoteSummaries = async () => { if (watchlist.length === 0) return; setLoadingQuotes(true); setError(""); try { const rows = await Promise.all(watchlist.map(fetchQuote)); setQuoteSummaries(Object.fromEntries(rows.map((row) => [`${row.market}:${row.symbol}`, row]))); } catch (exc: any) { setError(formatApiError(exc, "刷新自选行情失败")); } finally { setLoadingQuotes(false); } };
  const handleExportWatchlist = () => { const csv = toCsv(["symbol", "market", "name", "note", "tags", "addedAt"], watchlist.map((item) => [item.symbol, item.market, item.name || "", item.note || "", (item.tags || []).join("|"), item.addedAt])); downloadTextFile("kronos_watchlist.csv", csv); };
  const handleImportWatchlist = async (event: ChangeEvent<HTMLInputElement>) => { const file = event.target.files?.[0]; if (!file) return; const text = await file.text(); const imported = text.split(/\r?\n/).slice(1).map((line) => { const [rawSymbol, rawMarket, rawName, rawNote, rawTags, rawAddedAt] = line.split(","); return { symbol: normalizeSymbol(rawSymbol || ""), market: (rawMarket || "cn") as Market, name: rawName || undefined, note: rawNote || undefined, tags: rawTags ? rawTags.split("|") : [], addedAt: rawAddedAt || new Date().toISOString() }; }).filter((item) => item.symbol); replaceWatchlist([...watchlist, ...imported]); event.target.value = ""; };

  return <div className="page-shell space-y-6"><h1 className="page-title">自选股</h1><Card><CardTitle subtitle="保存研究备注、标签，并对选中标的批量预测/批量分析。">添加股票</CardTitle><div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-6"><div><label className="field-label">代码</label><input type="text" value={symbol} onChange={(e) => setSymbol(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleAdd()} className="app-input mt-1 font-mono" placeholder={`例如 ${DEFAULT_SYMBOL}`} /></div><div><label className="field-label">市场</label><select value={market} onChange={(e) => setMarket(e.target.value as Market)} className="app-input mt-1">{MARKET_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}</select></div><div><label className="field-label">名称</label><input type="text" value={name} onChange={(e) => setName(e.target.value)} className="app-input mt-1" placeholder="可选" /></div><div><label className="field-label">标签</label><input type="text" value={tags} onChange={(e) => setTags(e.target.value)} className="app-input mt-1" placeholder="低估, 银行" /></div><div className="xl:col-span-2"><label className="field-label">备注</label><input type="text" value={note} onChange={(e) => setNote(e.target.value)} className="app-input mt-1" placeholder="研究假设或跟踪理由" /></div></div><div className="mt-4 flex flex-col gap-3 md:flex-row"><Button onClick={handleAdd}>添加</Button><Button variant="secondary" onClick={refreshQuoteSummaries} loading={loadingQuotes}>刷新行情/指标</Button><Button variant="secondary" onClick={handleExportWatchlist} disabled={watchlist.length === 0}>导出自选</Button><Button variant="secondary" onClick={() => fileInputRef.current?.click()}>导入自选</Button><input ref={fileInputRef} className="hidden" type="file" accept=".csv,text/csv" onChange={handleImportWatchlist} /></div></Card>{error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">{error}</div>}{watchlist.length === 0 ? <Card><div className="py-12 text-center text-gray-500"><p className="mb-2 text-lg">自选股列表为空</p><p className="text-sm">添加股票开始追踪</p></div></Card> : <Card><CardTitle action={<div className="flex flex-col gap-2 sm:flex-row"><Button variant="ghost" onClick={selectAll}>全选</Button><Button variant="ghost" onClick={clearSelection}>清空</Button></div>}>已保存股票 ({watchlist.length})</CardTitle><div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-3"><Link href={`/batch?symbols=${selectedSymbolsParam}`} className="btn-primary flex h-12 items-center justify-center rounded-xl px-6 text-sm font-medium">批量预测</Link><Link href={`/analysis?symbol=${selectedSymbols[0] || ""}`} className="btn-secondary flex h-12 items-center justify-center rounded-xl px-6 text-sm font-medium">批量分析</Link><Link href={`/backtest?symbols=${selectedSymbolsParam}`} className="btn-secondary flex h-12 items-center justify-center rounded-xl px-6 text-sm font-medium">组合回测</Link></div><div className="table-scroll"><table className="min-w-[64rem] w-full text-sm"><thead><tr className="border-b border-gray-700 text-gray-400"><th className="py-2 text-left">选择</th><th className="py-2 text-left">代码</th><th className="py-2 text-left">名称/市场</th><th className="py-2 text-right">最新价</th><th className="py-2 text-right">区间涨跌</th><th className="py-2 text-right">RSI</th><th className="py-2 text-right">MACD</th><th className="py-2 text-left">标签/备注</th><th className="py-2 text-right">操作</th></tr></thead><tbody>{watchlist.map((item) => { const key = itemKey(item); const quote = quoteSummaries[key]; return <tr key={key} className="border-b border-gray-800 hover:bg-surface-overlay/50"><td className="py-3"><input type="checkbox" checked={selectedKeys.includes(key)} onChange={() => toggleSelected(item)} /></td><td className="py-3 font-mono font-bold text-white">{item.symbol}</td><td className="py-3"><input className="app-input h-9" value={item.name || ""} onChange={(e) => updateWatchlistItem(item.symbol, item.market, { name: e.target.value })} placeholder={getMarketLabel(item.market)} /><p className="mt-1 text-xs text-muted-foreground">{getMarketLabel(item.market)}</p></td><td className="py-3 text-right">{quote?.latestPrice == null ? "-" : formatNumber(quote.latestPrice, 2)}</td><td className={`py-3 text-right ${quote?.changePct && quote.changePct >= 0 ? "text-accent-green" : "text-accent-red"}`}>{quote?.changePct == null ? "-" : `${(quote.changePct * 100).toFixed(2)}%`}</td><td className="py-3 text-right">{quote?.rsi == null ? "-" : formatNumber(quote.rsi, 2)}</td><td className="py-3 text-right">{quote?.macd == null ? "-" : formatNumber(quote.macd, 4)}</td><td className="py-3"><input className="app-input h-9" value={(item.tags || []).join(", ")} onChange={(e) => updateWatchlistItem(item.symbol, item.market, { tags: parseTags(e.target.value) })} placeholder="标签" /><input className="app-input mt-2 h-9" value={item.note || ""} onChange={(e) => updateWatchlistItem(item.symbol, item.market, { note: e.target.value })} placeholder="备注" /></td><td className="py-3 text-right"><div className="flex justify-end gap-2"><Link href={`/forecast?symbol=${item.symbol}&market=${item.market}`} className="rounded bg-surface-overlay px-2 py-1 text-xs text-gray-300">预测</Link><Link href={`/analysis?symbol=${item.symbol}&market=${item.market}`} className="rounded bg-primary/20 px-2 py-1 text-xs text-primary-light">分析</Link><button onClick={() => removeFromWatchlist(item.symbol, item.market)} className="rounded bg-red-900/30 px-2 py-1 text-xs text-red-400">移除</button></div></td></tr>; })}</tbody></table></div></Card>}</div>;
}
