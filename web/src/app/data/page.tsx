"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { api, DataResponse, SearchResult, formatApiError } from "@/lib/api";
import { DEFAULT_MARKET, DEFAULT_SYMBOL } from "@/lib/defaults";
import { queryKeys } from "@/lib/queryKeys";
import { useSessionState } from "@/lib/useSessionState";

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
    if (!query) return;
    const key = queryKeys.search(query);
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
        queryFn: () => api.search(query),
      });
      setSearchResults(res.results);
    } catch (e: any) {
      setError(formatApiError(e, "搜索失败"));
    } finally {
      setSearchLoading(false);
    }
  };

  const handleFetch = async (forceRefresh = false) => {
    if (!symbol) return;
    const key = queryKeys.data({
      symbol,
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
        queryFn: () => api.getData(symbol, startDate, endDate),
      });
      setData(res);
    } catch (e: any) {
      setError(formatApiError(e, "获取数据失败"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-display">数据浏览</h1>

      {/* Search */}
      <Card>
        <CardTitle>搜索股票</CardTitle>
        <div className="flex gap-4">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            className="flex-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white"
            placeholder="输入代码或名称搜索..."
          />
          <Button onClick={() => handleSearch(false)} loading={searchLoading}>搜索</Button>
        </div>
        {error && (
          <div className="mt-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}
        {searchResults.length > 0 && (
          <div className="mt-4 space-y-1">
            {searchResults.map((r) => (
              <button
                key={r.code}
                onClick={() => { setSymbol(r.code); setSearchResults([]); }}
                className="w-full text-left px-3 py-2 rounded hover:bg-surface-overlay flex justify-between"
              >
                <span className="font-mono">{r.code}</span>
                <span>{r.name}</span>
                <span className="text-gray-500 text-sm">{r.market}</span>
              </button>
            ))}
          </div>
        )}
      </Card>

      {/* Fetch */}
      <Card>
        <CardTitle>获取数据</CardTitle>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="text-sm text-gray-400">代码</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white font-mono"
              placeholder={DEFAULT_SYMBOL}
            />
          </div>
          <div>
            <label className="text-sm text-gray-400">开始日期</label>
            <input type="text" value={startDate} onChange={(e) => setStartDate(e.target.value)}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white font-mono" />
          </div>
          <div>
            <label className="text-sm text-gray-400">结束日期</label>
            <input type="text" value={endDate} onChange={(e) => setEndDate(e.target.value)}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white font-mono" />
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
          <div className="overflow-x-auto max-h-96 overflow-y-auto">
            <table className="w-full text-sm">
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
                  <tr key={`${row.timestamp}-${row.close}`} className="border-b border-gray-800 hover:bg-surface-overlay">
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
