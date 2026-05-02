"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { api, formatApiError } from "@/lib/api";
import { DEFAULT_MARKET } from "@/lib/markets";
import { DEFAULT_SYMBOL, normalizeSymbol } from "@/lib/symbols";
import { queryKeys } from "@/lib/queryKeys";
import { useSessionState } from "@/lib/useSessionState";
import type { DataResponse, SearchResult } from "@/types/api";

export default function DataPage() {
  const queryClient = useQueryClient();
  const [query, setQuery] = useSessionState("kronos-data-query", "");
  const [searchResults, setSearchResults] = useSessionState<SearchResult[]>("kronos-data-search-results", []);
  const [symbol, setSymbol] = useSessionState("kronos-data-symbol", DEFAULT_SYMBOL);
  const [startDate, setStartDate] = useSessionState("kronos-data-start-date", "20250101");
  const [endDate, setEndDate] = useSessionState("kronos-data-end-date", "20260430");
  const [data, setData] = useSessionState<DataResponse | null>("kronos-data-result", null);
  const [loading, setLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [error, setError] = useSessionState("kronos-data-error", "");

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
      if (forceRefresh) {
        await queryClient.invalidateQueries({ queryKey: key });
      }
      const res = await queryClient.fetchQuery({
        queryKey: key,
        queryFn: ({ signal }) => api.search(trimmedQuery, { signal }),
      });
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
    const key = queryKeys.data({
      symbol: requestSymbol,
      market: DEFAULT_MARKET,
      startDate,
      endDate,
    });
    const cached = forceRefresh ? undefined : queryClient.getQueryData<DataResponse>(key);
    if (cached) {
      setData(cached);
      setError("");
      return;
    }

    setLoading(true);
    setError("");
    try {
      if (forceRefresh) {
        await queryClient.invalidateQueries({ queryKey: key });
      }
      const res = await queryClient.fetchQuery({
        queryKey: key,
        queryFn: ({ signal }) => api.getData(requestSymbol, startDate, endDate, { signal }),
      });
      setData(res);
    } catch (e: any) {
      setError(formatApiError(e, "获取数据失败"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-shell space-y-6">
      <h1 className="page-title">数据浏览</h1>

      {/* Search */}
      <Card>
        <CardTitle>搜索股票</CardTitle>
        <div className="grid grid-cols-1 gap-3 md:flex md:gap-4">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            className="app-input flex-1"
            placeholder="输入代码或名称搜索..."
          />
          <Button onClick={() => handleSearch(false)} loading={searchLoading} className="w-full md:w-auto">搜索</Button>
        </div>
        {error && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}
        {searchResults.length > 0 && (
          <div className="mt-4 space-y-1">
            {searchResults.map((r) => (
              <button
                key={`${r.market}-${r.code}`}
                onClick={() => { setSymbol(normalizeSymbol(r.code)); setSearchResults([]); }}
                className="flex min-h-11 w-full flex-col gap-1 rounded px-3 py-2 text-left hover:bg-muted sm:flex-row sm:justify-between"
              >
                <span className="font-mono">{r.code}</span>
                <span>{r.name}</span>
                <span className="text-sm text-muted-foreground">{r.market}</span>
              </button>
            ))}
          </div>
        )}
      </Card>

      {/* Fetch */}
      <Card>
        <CardTitle>获取数据</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <div>
            <label className="field-label">代码</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="app-input mt-1 font-mono"
              placeholder={DEFAULT_SYMBOL}
            />
          </div>
          <div>
            <label className="field-label">开始日期</label>
            <input type="text" value={startDate} onChange={(e) => setStartDate(e.target.value)}
              className="app-input mt-1 font-mono" />
          </div>
          <div>
            <label className="field-label">结束日期</label>
            <input type="text" value={endDate} onChange={(e) => setEndDate(e.target.value)}
              className="app-input mt-1 font-mono" />
          </div>
          <div className="flex items-end">
            <Button onClick={() => handleFetch(false)} loading={loading} className="w-full">获取</Button>
          </div>
        </div>
        {data && (
          <div className="mt-4">
            <Button variant="secondary" onClick={() => handleFetch(true)} loading={loading}>
              刷新数据
            </Button>
          </div>
        )}
      </Card>

      {/* Data table */}
      {data && (
        <Card>
          <CardTitle>{data.symbol} — {data.count} rows</CardTitle>
          <div className="table-scroll max-h-96 overflow-y-auto">
            <table className="min-w-[42rem] w-full text-sm">
              <thead className="sticky top-0 bg-surface-raised">
                <tr className="border-b border-gray-700 text-gray-400">
                  <th className="py-2 text-left">日期</th>
                  <th className="py-2 text-right">开盘</th>
                  <th className="py-2 text-right">最高</th>
                  <th className="py-2 text-right">最低</th>
                  <th className="py-2 text-right">收盘</th>
                  <th className="py-2 text-right">成交量</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => (
                  <tr key={`${data.symbol}-${row.timestamp}`} className="border-b border-gray-800 hover:bg-surface-overlay">
                    <td className="py-1.5 font-mono text-xs">{String(row.timestamp).slice(0, 10)}</td>
                    <td className="py-1.5 text-right">{row.open.toFixed(2)}</td>
                    <td className="py-1.5 text-right">{row.high.toFixed(2)}</td>
                    <td className="py-1.5 text-right">{row.low.toFixed(2)}</td>
                    <td className="py-1.5 text-right font-semibold">{row.close.toFixed(2)}</td>
                    <td className="py-1.5 text-right text-gray-400">{(row.volume || 0).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
