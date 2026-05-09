"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { PriceLineChart } from "@/components/charts/PriceLineChart";
import { api, formatApiError } from "@/lib/api";
import { MARKET_OPTIONS, getMarketLabel, normalizeMarket, type Market } from "@/lib/markets";
import { DEFAULT_SYMBOL, normalizeSymbol } from "@/lib/symbols";
import { ohlcvRowsToCsv, downloadTextFile, makeDatedFilename, validateDateRange } from "@/lib/exportUtils";
import { formatNumber } from "@/lib/utils";
import { queryKeys } from "@/lib/queryKeys";
import { useSessionState } from "@/lib/useSessionState";
import { useAppStore } from "@/stores/app";
import type { DataResponse, IndicatorResponse, SearchResult } from "@/types/api";

type RangePreset = "3m" | "6m" | "1y" | "custom";

const RANGE_PRESETS: Array<{ value: RangePreset; label: string; days: number | null }> = [
  { value: "3m", label: "近3个月", days: 90 },
  { value: "6m", label: "近6个月", days: 180 },
  { value: "1y", label: "近1年", days: 365 },
  { value: "custom", label: "自定义", days: null },
];

const ADJUST_OPTIONS = [
  { value: "qfq", label: "前复权" },
  { value: "hfq", label: "后复权" },
  { value: "", label: "不复权" },
];

function formatYmd(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}${m}${d}`;
}

function getIndicatorNumber(response: IndicatorResponse | null, key: string, child?: string): number | null {
  const value = response?.indicators?.[key];
  const raw = child && value && typeof value === "object" ? (value as Record<string, unknown>)[child] : value;
  return typeof raw === "number" && Number.isFinite(raw) ? raw : null;
}

export default function DataPage() {
  const queryClient = useQueryClient();
  const { addToWatchlist } = useAppStore();
  const [query, setQuery] = useSessionState("kronos-data-query", "");
  const [searchResults, setSearchResults] = useSessionState<SearchResult[]>("kronos-data-search-results", []);
  const [symbol, setSymbol] = useSessionState("kronos-data-symbol", DEFAULT_SYMBOL);
  const [market, setMarket] = useSessionState<Market>("kronos-data-market", "cn");
  const [startDate, setStartDate] = useSessionState("kronos-data-start-date", "20250101");
  const [endDate, setEndDate] = useSessionState("kronos-data-end-date", "20260430");
  const [adjust, setAdjust] = useSessionState("kronos-data-adjust", "qfq");
  const [rangePreset, setRangePreset] = useSessionState<RangePreset>("kronos-data-range-preset", "1y");
  const [data, setData] = useSessionState<DataResponse | null>("kronos-data-result", null);
  const [indicators, setIndicators] = useSessionState<IndicatorResponse | null>("kronos-data-indicators", null);
  const [loading, setLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [error, setError] = useSessionState("kronos-data-error", "");

  const summary = useMemo(() => {
    const rows = data?.rows || [];
    if (rows.length === 0) return null;
    const first = rows[0];
    const last = rows[rows.length - 1];
    const highs = rows.map((row) => row.high).filter(Number.isFinite);
    const lows = rows.map((row) => row.low).filter(Number.isFinite);
    const ret = first.close > 0 ? last.close / first.close - 1 : 0;
    return { first, last, high: Math.max(...highs), low: Math.min(...lows), returnPct: ret };
  }, [data]);

  const applyRangePreset = (value: RangePreset) => {
    setRangePreset(value);
    const preset = RANGE_PRESETS.find((item) => item.value === value);
    if (!preset?.days) return;
    const end = new Date();
    const start = new Date(end);
    start.setDate(start.getDate() - preset.days);
    setStartDate(formatYmd(start));
    setEndDate(formatYmd(end));
  };

  const handleSearch = async (forceRefresh = false) => {
    const trimmedQuery = query.trim();
    if (!trimmedQuery) return;
    const key = queryKeys.search(trimmedQuery);
    const cached = forceRefresh ? undefined : queryClient.getQueryData<{ ok: boolean; results: SearchResult[] }>(key);
    if (cached) {
      setSearchResults(cached.results);
      setError("");
      return;
    }
    setSearchLoading(true);
    setError("");
    try {
      if (forceRefresh) await queryClient.invalidateQueries({ queryKey: key });
      const res = await queryClient.fetchQuery({ queryKey: key, queryFn: ({ signal }) => api.search(trimmedQuery, { signal }) });
      setSearchResults(res.results);
    } catch (e: any) {
      setError(formatApiError(e, "搜索失败"));
    } finally {
      setSearchLoading(false);
    }
  };

  const handleFetch = async (forceRefresh = false) => {
    const requestSymbol = normalizeSymbol(symbol);
    if (!requestSymbol) return;
    const dateError = validateDateRange(startDate, endDate);
    if (dateError) {
      setError(dateError);
      return;
    }
    const key = queryKeys.data({ symbol: requestSymbol, market, startDate, endDate, adjust });
    const indicatorKey = queryKeys.indicator({ symbol: requestSymbol, market });
    const cached = forceRefresh ? undefined : queryClient.getQueryData<DataResponse>(key);
    const cachedIndicators = forceRefresh ? undefined : queryClient.getQueryData<IndicatorResponse>(indicatorKey);
    if (cached) {
      setData({ ...cached, market });
      if (cachedIndicators) setIndicators(cachedIndicators);
      setError("");
      return;
    }
    setLoading(true);
    setError("");
    try {
      if (forceRefresh) {
        await queryClient.invalidateQueries({ queryKey: key });
        await queryClient.invalidateQueries({ queryKey: indicatorKey });
      }
      const [res, indicatorRes] = await Promise.all([
        queryClient.fetchQuery({
          queryKey: key,
          queryFn: ({ signal }) =>
            market === "cn"
              ? api.getData(requestSymbol, startDate, endDate, adjust, { signal })
              : api.getGlobalData(requestSymbol, market, startDate, endDate, { signal }),
        }),
        queryClient.fetchQuery({
          queryKey: indicatorKey,
          queryFn: ({ signal }) => api.getIndicators(requestSymbol, market, { signal }),
        }).catch(() => null),
      ]);
      setData({ ...res, market });
      setIndicators(indicatorRes);
    } catch (e: any) {
      setError(formatApiError(e, "获取数据失败"));
    } finally {
      setLoading(false);
    }
  };

  const downloadDataCsv = () => {
    if (!data) return;
    downloadTextFile(makeDatedFilename("data", `${data.market || market}_${data.symbol}`, startDate, endDate), ohlcvRowsToCsv(data.rows));
  };

  const handleSelectSearchResult = (result: SearchResult) => {
    setSymbol(normalizeSymbol(result.code));
    setMarket(normalizeMarket(result.market, "cn"));
    setSearchResults([]);
  };

  const handleAddToWatchlist = () => {
    const requestSymbol = normalizeSymbol(symbol);
    if (!requestSymbol) return;
    addToWatchlist({ symbol: requestSymbol, market, addedAt: new Date().toISOString() });
  };

  const rsi = getIndicatorNumber(indicators, "rsi", "value") ?? getIndicatorNumber(indicators, "rsi");
  const macd = getIndicatorNumber(indicators, "macd", "macd");
  const signal = getIndicatorNumber(indicators, "macd", "signal");

  return (
    <div className="page-shell space-y-6">
      <h1 className="page-title">数据浏览</h1>
      <Card>
        <CardTitle subtitle="搜索、跨市场拉取、查看指标，并一键跳转预测/分析。">搜索股票</CardTitle>
        <div className="grid grid-cols-1 gap-3 md:flex md:gap-4">
          <input type="text" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleSearch()} className="app-input flex-1" placeholder="输入代码或名称搜索..." />
          <Button onClick={() => handleSearch(false)} loading={searchLoading} className="w-full md:w-auto">搜索</Button>
        </div>
        {searchResults.length > 0 && <div className="mt-4 space-y-1">{searchResults.map((r) => <button key={`${r.market}-${r.code}`} onClick={() => handleSelectSearchResult(r)} className="flex min-h-11 w-full flex-col gap-1 rounded px-3 py-2 text-left hover:bg-muted sm:flex-row sm:justify-between"><span className="font-mono">{r.code}</span><span>{r.name}</span><span className="text-sm text-muted-foreground">{r.market}</span></button>)}</div>}
      </Card>
      <Card>
        <CardTitle>获取数据</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-6">
          <div><label className="field-label">代码</label><input type="text" value={symbol} onChange={(e) => setSymbol(e.target.value)} className="app-input mt-1 font-mono" placeholder={DEFAULT_SYMBOL} /></div>
          <div><label className="field-label">市场</label><select value={market} onChange={(e) => setMarket(e.target.value as Market)} className="app-input mt-1">{MARKET_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}</select></div>
          <div><label className="field-label">周期</label><select value={rangePreset} onChange={(e) => applyRangePreset(e.target.value as RangePreset)} className="app-input mt-1">{RANGE_PRESETS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}</select></div>
          <div><label className="field-label">开始日期</label><input type="text" value={startDate} onChange={(e) => { setRangePreset("custom"); setStartDate(e.target.value); }} className="app-input mt-1 font-mono" /></div>
          <div><label className="field-label">结束日期</label><input type="text" value={endDate} onChange={(e) => { setRangePreset("custom"); setEndDate(e.target.value); }} className="app-input mt-1 font-mono" /></div>
          <div><label className="field-label">复权 adjust</label><select value={adjust} onChange={(e) => setAdjust(e.target.value)} disabled={market !== "cn"} className="app-input mt-1">{ADJUST_OPTIONS.map((opt) => <option key={opt.value || "none"} value={opt.value}>{opt.label}</option>)}</select></div>
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row">
          <Button onClick={() => handleFetch(false)} loading={loading} className="w-full md:w-auto">获取</Button><Button variant="secondary" onClick={() => handleFetch(true)} loading={loading} className="w-full md:w-auto">刷新数据</Button><Button variant="secondary" onClick={downloadDataCsv} disabled={!data} className="w-full md:w-auto">导出 CSV</Button><Button variant="secondary" onClick={handleAddToWatchlist} className="w-full md:w-auto">加入自选</Button><Link className="btn-secondary flex h-12 items-center justify-center rounded-xl px-6 text-sm font-medium" href={`/forecast?symbol=${normalizeSymbol(symbol)}&market=${market}`}>去预测</Link><Link className="btn-secondary flex h-12 items-center justify-center rounded-xl px-6 text-sm font-medium" href={`/analysis?symbol=${normalizeSymbol(symbol)}&market=${market}`}>去分析</Link>
        </div>
      </Card>
      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">{error}</div>}
      {data && summary && <><div className="grid grid-cols-2 gap-4 md:grid-cols-5"><Card><p className="text-sm text-muted-foreground">数据摘要</p><p className="text-xl font-bold">{getMarketLabel(data.market || market)} / {data.count}条</p></Card><Card><p className="text-sm text-muted-foreground">最新收盘</p><p className="text-xl font-bold">{formatNumber(summary.last.close, 2)}</p></Card><Card><p className="text-sm text-muted-foreground">区间收益</p><p className={summary.returnPct >= 0 ? "text-xl font-bold text-accent-green" : "text-xl font-bold text-accent-red"}>{(summary.returnPct * 100).toFixed(2)}%</p></Card><Card><p className="text-sm text-muted-foreground">区间最高</p><p className="text-xl font-bold">{formatNumber(summary.high, 2)}</p></Card><Card><p className="text-sm text-muted-foreground">区间最低</p><p className="text-xl font-bold">{formatNumber(summary.low, 2)}</p></Card></div><Card><CardTitle>收盘价走势</CardTitle><PriceLineChart rows={data.rows} /></Card><Card><CardTitle>技术指标</CardTitle><div className="grid grid-cols-2 gap-4 md:grid-cols-4"><div><p className="text-sm text-muted-foreground">RSI</p><p className="text-xl font-bold">{rsi === null ? "-" : formatNumber(rsi, 2)}</p></div><div><p className="text-sm text-muted-foreground">MACD</p><p className="text-xl font-bold">{macd === null ? "-" : formatNumber(macd, 4)}</p></div><div><p className="text-sm text-muted-foreground">Signal</p><p className="text-xl font-bold">{signal === null ? "-" : formatNumber(signal, 4)}</p></div><div><p className="text-sm text-muted-foreground">指标样本</p><p className="text-xl font-bold">{indicators?.data_points || "-"}</p></div></div></Card><Card><CardTitle>{data.symbol} — 行情明细</CardTitle><div className="table-scroll max-h-96 overflow-y-auto"><table className="min-w-[48rem] w-full text-sm"><thead className="sticky top-0 bg-surface-raised"><tr className="border-b border-gray-700 text-gray-400"><th className="py-2 text-left">日期</th><th className="py-2 text-right">开盘</th><th className="py-2 text-right">最高</th><th className="py-2 text-right">最低</th><th className="py-2 text-right">收盘</th><th className="py-2 text-right">成交量</th></tr></thead><tbody>{data.rows.slice(-120).map((row) => <tr key={`${data.symbol}-${row.timestamp}`} className="border-b border-gray-800 hover:bg-surface-overlay"><td className="py-1.5 font-mono text-xs">{String(row.timestamp).slice(0, 10)}</td><td className="py-1.5 text-right">{row.open.toFixed(2)}</td><td className="py-1.5 text-right">{row.high.toFixed(2)}</td><td className="py-1.5 text-right">{row.low.toFixed(2)}</td><td className="py-1.5 text-right font-semibold">{row.close.toFixed(2)}</td><td className="py-1.5 text-right text-gray-400">{(row.volume || 0).toLocaleString()}</td></tr>)}</tbody></table></div></Card></>}
    </div>
  );
}
