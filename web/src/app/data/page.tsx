"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/Card";
import { SectionLabel } from "@/components/ui/SectionLabel";
import { AntButton as Button } from "@/components/antd/AntButton";
import { AntSelect as AppSelect } from "@/components/antd/AntSelect";
import type { AppSelectOption } from "@/components/ui/AppSelect";
import { AntDatePicker } from "@/components/antd/AntDatePicker";
import { AntInput } from "@/components/antd/AntInput";
import { AntAlert } from "@/components/antd/AntAlert";
import { AntTable } from "@/components/antd/AntTable";
import { PriceLineChart } from "@/components/charts/PriceLineChart";
import { api, formatApiError } from "@/lib/api";
import { MARKET_OPTIONS, getMarketLabel, getMarketOptions, normalizeMarket, type Market } from "@/lib/markets";
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
type AdjustValue = "qfq" | "hfq" | "";

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

function DataPageInner() {
  const queryClient = useQueryClient();
  const { addToWatchlist, preferences } = useAppStore();
  const marketOptions = getMarketOptions(preferences.language);
  const rangeOptions: Array<AppSelectOption<RangePreset>> = RANGE_PRESETS.map((option) => ({ value: option.value, label: option.label }));
  const adjustOptions: Array<AppSelectOption<AdjustValue>> = ADJUST_OPTIONS.map((option) => ({ value: option.value as AdjustValue, label: option.label }));
  const [query, setQuery] = useSessionState("kronos-data-query", "");
  const [searchResults, setSearchResults] = useSessionState<SearchResult[]>("kronos-data-search-results", []);
  const [symbol, setSymbol] = useSessionState("kronos-data-symbol", DEFAULT_SYMBOL);
  const [market, setMarket] = useSessionState<Market>("kronos-data-market", "cn");
  const _dToday = new Date(); const _dYmd = (d: Date) => d.toISOString().slice(0, 10).replace(/-/g, "");
  const _dY1 = new Date(); _dY1.setFullYear(_dY1.getFullYear() - 1);
  const [startDate, setStartDate] = useSessionState("kronos-data-start-v2", _dYmd(_dY1));
  const [endDate, setEndDate] = useSessionState("kronos-data-end-v2", _dYmd(_dToday));
  const [adjust, setAdjust] = useSessionState("kronos-data-adjust", "qfq");
  const [rangePreset, setRangePreset] = useSessionState<RangePreset>("kronos-data-range-preset", "1y");
  const [data, setData] = useSessionState<DataResponse | null>("kronos-data-result", null);
  const [indicators, setIndicators] = useSessionState<IndicatorResponse | null>("kronos-data-indicators", null);
  const [loading, setLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [indicatorError, setIndicatorError] = useSessionState("kronos-data-indicator-error", "");
  const [error, setError] = useSessionState("kronos-data-error", "");
  const params = useSearchParams();
  const handleFetchRef = useRef<(() => Promise<void>) | null>(null);

  // URL deep linking: read symbol/market from query params on mount
  useEffect(() => {
    const urlSymbol = params.get("symbol");
    const urlMarket = params.get("market");
    if (urlSymbol) setSymbol(normalizeSymbol(urlSymbol));
    if (urlMarket && MARKET_OPTIONS.some((opt) => opt.value === urlMarket)) setMarket(urlMarket as Market);
    if (urlSymbol) {
      // Auto-fetch if symbol is provided in URL
      const timer = setTimeout(() => handleFetchRef.current?.(), 100);
      return () => clearTimeout(timer);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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
          queryFn: ({ signal }) => api.getIndicators(requestSymbol, market, startDate, endDate, { signal }),
        }).catch((e) => { setIndicatorError(formatApiError(e, "指标获取失败")); return null; }),
      ]);
      setData({ ...res, market });
      setIndicators(indicatorRes);
    } catch (e: any) {
      setError(formatApiError(e, "获取数据失败"));
    } finally {
      setLoading(false);
    }
  };

  // Expose handleFetch to ref for URL deep linking auto-fetch
  useEffect(() => { handleFetchRef.current = handleFetch; });

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

  const rsi = getIndicatorNumber(indicators, "rsi_14", "current") ?? getIndicatorNumber(indicators, "rsi", "value") ?? getIndicatorNumber(indicators, "rsi");
  const kdjK = getIndicatorNumber(indicators, "kdj", "current_k") ?? getIndicatorNumber(indicators, "kdj", "k");
  const kdjD = getIndicatorNumber(indicators, "kdj", "current_d") ?? getIndicatorNumber(indicators, "kdj", "d");
  const kdjJ = getIndicatorNumber(indicators, "kdj", "current_j") ?? getIndicatorNumber(indicators, "kdj", "j");
  const cci = getIndicatorNumber(indicators, "cci", "current") ?? getIndicatorNumber(indicators, "cci");

  return (
    <div className="page-shell space-y-6">
      <SectionLabel>数据浏览</SectionLabel>
      <h1 className="page-title">数据浏览</h1>
      <Card>
        <CardTitle subtitle="跨市场拉取行情、查看指标，并一键跳转预测/分析。">获取数据</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-6">
          <div><label className="field-label">代码</label><AntInput value={symbol} onChange={setSymbol} placeholder={DEFAULT_SYMBOL} /></div>
          <div><label className="field-label">市场</label><AppSelect value={market} onChange={setMarket} options={marketOptions} ariaLabel="市场" className="mt-1" /></div>
          <div><label className="field-label">周期</label><AppSelect value={rangePreset} onChange={applyRangePreset} options={rangeOptions} ariaLabel="周期" className="mt-1" /></div>
          <div><label className="field-label">开始日期</label><AntDatePicker value={startDate} onChange={(v) => { setRangePreset("custom"); setStartDate(v); }} /></div>
          <div><label className="field-label">结束日期</label><AntDatePicker value={endDate} onChange={(v) => { setRangePreset("custom"); setEndDate(v); }} /></div>
          <div><label className="field-label">复权 adjust</label><AppSelect value={adjust as AdjustValue} onChange={setAdjust} options={adjustOptions} ariaLabel="复权 adjust" className="mt-1" disabled={market !== "cn"} /></div>
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row">
          <Button onClick={() => handleFetch(false)} loading={loading} className="w-full md:w-auto">获取</Button><Button variant="secondary" onClick={() => handleFetch(true)} loading={loading} className="w-full md:w-auto">刷新数据</Button><Button variant="secondary" onClick={downloadDataCsv} disabled={!data} className="w-full md:w-auto">导出 CSV</Button><Button variant="secondary" onClick={handleAddToWatchlist} className="w-full md:w-auto">加入自选</Button><Link className="btn-secondary flex h-12 items-center justify-center rounded-xl px-6 text-sm font-medium" href={`/forecast?symbol=${normalizeSymbol(symbol)}&market=${market}`}>去预测</Link><Link className="btn-secondary flex h-12 items-center justify-center rounded-xl px-6 text-sm font-medium" href={`/analysis?symbol=${normalizeSymbol(symbol)}&market=${market}`}>去分析</Link>
        </div>
      </Card>
      {error && <AntAlert type="error" message={error} />}
      {data && summary && <><div className="grid grid-cols-2 gap-4 md:grid-cols-5"><Card><p className="text-sm text-muted-foreground">数据摘要</p><p className="text-xl font-bold">{getMarketLabel(data.market || market, preferences.language)} / {data.count}条</p></Card><Card><p className="text-sm text-muted-foreground">最新收盘</p><p className="text-xl font-bold">{formatNumber(summary.last.close, 2)}</p></Card><Card><p className="text-sm text-muted-foreground">区间收益</p><p className={summary.returnPct >= 0 ? "text-xl font-bold text-accent-green" : "text-xl font-bold text-accent-red"}>{(summary.returnPct * 100).toFixed(2)}%</p></Card><Card><p className="text-sm text-muted-foreground">区间最高</p><p className="text-xl font-bold">{formatNumber(summary.high, 2)}</p></Card><Card><p className="text-sm text-muted-foreground">区间最低</p><p className="text-xl font-bold">{formatNumber(summary.low, 2)}</p></Card></div><Card><CardTitle>收盘价走势</CardTitle><PriceLineChart rows={data.rows} /></Card><Card><CardTitle>技术指标</CardTitle><div className="grid grid-cols-2 gap-4 md:grid-cols-5"><div><p className="text-sm text-muted-foreground">RSI(14)</p><p className="text-xl font-bold">{rsi === null ? "-" : formatNumber(rsi, 2)}</p></div><div><p className="text-sm text-muted-foreground">KDJ - K</p><p className="text-xl font-bold">{kdjK === null ? "-" : formatNumber(kdjK, 2)}</p></div><div><p className="text-sm text-muted-foreground">KDJ - D</p><p className="text-xl font-bold">{kdjD === null ? "-" : formatNumber(kdjD, 2)}</p></div><div><p className="text-sm text-muted-foreground">KDJ - J</p><p className="text-xl font-bold">{kdjJ === null ? "-" : formatNumber(kdjJ, 2)}</p></div><div><p className="text-sm text-muted-foreground">CCI(20)</p><p className="text-xl font-bold">{cci === null ? "-" : formatNumber(cci, 2)}</p></div></div>{indicatorError && <p className="mt-3 text-sm text-amber-400">⚠ {indicatorError}</p>}</Card><Card><CardTitle>{data.symbol} — 行情明细</CardTitle><AntTable
  columns={[
    { title: "日期", dataIndex: "timestamp", key: "date", render: (v: string) => String(v).slice(0, 10), width: 120 },
    { title: "开盘", dataIndex: "open", key: "open", render: (v: number) => formatNumber(v, 2), align: "right", width: 100 },
    { title: "收盘", dataIndex: "close", key: "close", render: (v: number) => <span className="font-semibold">{formatNumber(v, 2)}</span>, align: "right", width: 100 },
    { title: "最高", dataIndex: "high", key: "high", render: (v: number) => formatNumber(v, 2), align: "right", width: 100 },
    { title: "最低", dataIndex: "low", key: "low", render: (v: number) => formatNumber(v, 2), align: "right", width: 100 },
    { title: "成交量", dataIndex: "volume", key: "volume", render: (v: number) => formatNumber(v ?? 0, 0), align: "right", width: 120 },
    { title: "成交额", dataIndex: "amount", key: "amount", render: (v: number) => formatNumber(v ?? 0, 0), align: "right", width: 120 },
  ]}
  dataSource={data.rows}
  rowKey="timestamp"
  scroll={{ y: 400 }}
  pagination={{ pageSize: 50, showSizeChanger: true }}
/></Card></>}
    </div>
  );
}
export default function DataPage() {
  return (
    <Suspense fallback={<div className="page-shell"><p>Loading...</p></div>}>
      <DataPageInner />
    </Suspense>
  );
}
