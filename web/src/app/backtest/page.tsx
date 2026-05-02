"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { api, BacktestResponse, formatApiError } from "@/lib/api";
import { formatPercent, formatNumber } from "@/lib/utils";
import { DEFAULT_BACKTEST_SYMBOLS } from "@/lib/defaults";
import { queryKeys } from "@/lib/queryKeys";
import { useSessionState } from "@/lib/useSessionState";

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
    const symbolList = symbols.split(",").map((s) => s.trim()).filter(Boolean);
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
        queryFn: () =>
          api.backtest({
            symbols: symbolList,
            start_date: startDate,
            end_date: endDate,
            top_k: topK,
            dry_run: false,
          }),
      });
      setResult(res);
    } catch (e: any) {
      setError(formatApiError(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-display">策略回测</h1>

      <Card>
        <CardTitle>策略配置</CardTitle>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label className="text-sm text-gray-400">股票代码（逗号分隔）</label>
            <input
              type="text"
              value={symbols}
              onChange={(e) => setSymbols(e.target.value)}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white"
            />
          </div>
          <div>
            <label className="text-sm text-gray-400">开始日期</label>
            <input
              type="text"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white font-mono"
            />
          </div>
          <div>
            <label className="text-sm text-gray-400">结束日期</label>
            <input
              type="text"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white font-mono"
            />
          </div>
          <div>
            <label className="text-sm text-gray-400">Top K</label>
            <input
              type="number"
              value={topK}
              onChange={(e) => setTopK(+e.target.value)}
              min={1}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white"
            />
          </div>
        </div>
        <div className="mt-4">
          <Button onClick={() => handleBacktest(false)} loading={loading}>运行回测</Button>
          {result && (
            <Button
              variant="secondary"
              onClick={() => handleBacktest(true)}
              loading={loading}
              className="ml-3"
            >
              刷新回测
            </Button>
          )}
        </div>
      </Card>

      {error && <div className="p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-300">{error}</div>}

      {result && (
        <>
          {/* Metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card>
              <p className="text-sm text-gray-400">总收益率</p>
              <p className={`text-2xl font-bold ${result.metrics.total_return >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                {formatPercent(result.metrics.total_return)}
              </p>
            </Card>
            <Card>
              <p className="text-sm text-gray-400">夏普比率</p>
              <p className="text-2xl font-bold">{formatNumber(result.metrics.sharpe_ratio, 4)}</p>
            </Card>
            <Card>
              <p className="text-sm text-gray-400">最大回撤</p>
              <p className="text-2xl font-bold text-accent-red">{formatPercent(result.metrics.max_drawdown)}</p>
            </Card>
            <Card>
              <p className="text-sm text-gray-400">胜率</p>
              <p className="text-2xl font-bold">{formatPercent(result.metrics.win_rate)}</p>
            </Card>
          </div>

          {/* Equity curve */}
          <Card>
            <CardTitle>权益曲线</CardTitle>
            <div className="h-64 overflow-x-auto">
              <div className="flex items-end gap-1 h-full min-w-max">
                {result.equity_curve.map((point, i) => {
                  const minEq = Math.min(...result.equity_curve.map((p) => p.equity));
                  const maxEq = Math.max(...result.equity_curve.map((p) => p.equity));
                  const range = maxEq - minEq || 1;
                  const height = ((point.equity - minEq) / range) * 100;
                  return (
                    <div
                      key={`${point.date}-${point.equity}`}
                      className="flex-1 min-w-[4px] rounded-t"
                      style={{
                        height: `${Math.max(height, 2)}%`,
                        backgroundColor: point.return >= 0 ? "#10B981" : "#EF4444",
                        opacity: 0.7 + (i / result.equity_curve.length) * 0.3,
                      }}
                      title={`${point.date}: ${point.equity.toFixed(0)} (${(point.return * 100).toFixed(2)}%)`}
                    />
                  );
                })}
              </div>
            </div>
            <div className="flex justify-between text-xs text-gray-500 mt-2">
              <span>{result.equity_curve[0]?.date}</span>
              <span>{result.equity_curve[result.equity_curve.length - 1]?.date}</span>
            </div>
          </Card>

          <p className="text-xs text-gray-500 text-center">提示：{result.metadata.warning}</p>
        </>
      )}
    </div>
  );
}
