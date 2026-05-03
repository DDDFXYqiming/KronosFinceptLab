"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { BacktestEquityChart } from "@/components/charts/BacktestEquityChart";
import { api, formatApiError } from "@/lib/api";
import { formatPercent, formatNumber } from "@/lib/utils";
import { DEFAULT_BACKTEST_SYMBOLS, normalizeSymbols } from "@/lib/symbols";
import { queryKeys } from "@/lib/queryKeys";
import { useSessionState } from "@/lib/useSessionState";
import type { BacktestResponse } from "@/types/api";

export default function BacktestPage() {
  const queryClient = useQueryClient();
  const [symbols, setSymbols] = useSessionState("kronos-backtest-symbols", DEFAULT_BACKTEST_SYMBOLS);
  const [startDate, setStartDate] = useSessionState("kronos-backtest-start-date", "20250101");
  const [endDate, setEndDate] = useSessionState("kronos-backtest-end-date", "20260430");
  const [topK, setTopK] = useSessionState("kronos-backtest-top-k", 1);
  const [result, setResult] = useSessionState<BacktestResponse | null>("kronos-backtest-result", null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useSessionState("kronos-backtest-error", "");

  const handleBacktest = async (forceRefresh = false) => {
    const symbolList = normalizeSymbols(symbols);
    const key = queryKeys.backtest({ symbols: symbolList, startDate, endDate, topK });
    const cached = forceRefresh ? undefined : queryClient.getQueryData<BacktestResponse>(key);
    if (cached) {
      setResult(cached);
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
        queryFn: ({ signal }) =>
          api.backtest({
            symbols: symbolList,
            start_date: startDate,
            end_date: endDate,
            top_k: topK,
            dry_run: false,
          }, { signal }),
      });
      setResult(res);
    } catch (e: any) {
      setError(formatApiError(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-shell space-y-6">
      <h1 className="page-title">策略回测</h1>

      <Card>
        <CardTitle>策略配置</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className="field-label">股票代码（逗号分隔）</label>
            <input
              type="text"
              value={symbols}
              onChange={(e) => setSymbols(e.target.value)}
              className="app-input mt-1"
            />
          </div>
          <div>
            <label className="field-label">开始日期</label>
            <input
              type="text"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="app-input mt-1 font-mono"
            />
          </div>
          <div>
            <label className="field-label">结束日期</label>
            <input
              type="text"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="app-input mt-1 font-mono"
            />
          </div>
          <div>
            <label className="field-label">Top K</label>
            <input
              type="number"
              value={topK}
              onChange={(e) => setTopK(+e.target.value)}
              min={1}
              className="app-input mt-1"
            />
          </div>
        </div>
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 md:flex">
          <Button onClick={() => handleBacktest(false)} loading={loading} className="w-full md:w-auto">运行回测</Button>
          {result && (
            <Button
              variant="secondary"
              onClick={() => handleBacktest(true)}
              loading={loading}
              className="w-full md:ml-3 md:w-auto"
            >
              刷新回测
            </Button>
          )}
        </div>
      </Card>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">{error}</div>}

      {result && (
        <>
          {/* Metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card>
              <p className="text-sm text-muted-foreground">总收益率</p>
              <p className={`text-2xl font-bold ${result.metrics.total_return >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                {formatPercent(result.metrics.total_return)}
              </p>
            </Card>
            <Card>
              <p className="text-sm text-muted-foreground">夏普比率</p>
              <p className="text-2xl font-bold">{formatNumber(result.metrics.sharpe_ratio, 4)}</p>
            </Card>
            <Card>
              <p className="text-sm text-muted-foreground">最大回撤</p>
              <p className="text-2xl font-bold text-accent-red">{formatPercent(result.metrics.max_drawdown)}</p>
            </Card>
            <Card>
              <p className="text-sm text-muted-foreground">胜率</p>
              <p className="text-2xl font-bold">{formatPercent(result.metrics.win_rate)}</p>
            </Card>
          </div>

          {/* Equity curve */}
          <Card>
            <CardTitle>权益曲线</CardTitle>
            <BacktestEquityChart equityCurve={result.equity_curve} />
          </Card>

          <p className="text-xs text-gray-500 text-center">提示：{result.metadata.warning}</p>
        </>
      )}
    </div>
  );
}
