"use client";

import { useState } from "react";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { api, BacktestResponse } from "@/lib/api";
import { formatPercent, formatNumber } from "@/lib/utils";

export default function BacktestPage() {
  const [symbols, setSymbols] = useState("600519,000858");
  const [startDate, setStartDate] = useState("20250101");
  const [endDate, setEndDate] = useState("20260430");
  const [topK, setTopK] = useState(1);
  const [result, setResult] = useState<BacktestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleBacktest = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.backtest({
        symbols: symbols.split(",").map((s) => s.trim()),
        start_date: startDate,
        end_date: endDate,
        top_k: topK,
        dry_run: true,
      });
      setResult(res);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-display">📈 Backtest</h1>

      <Card>
        <CardTitle>Strategy Configuration</CardTitle>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label className="text-sm text-gray-400">Symbols (comma-separated)</label>
            <input
              type="text"
              value={symbols}
              onChange={(e) => setSymbols(e.target.value)}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white"
            />
          </div>
          <div>
            <label className="text-sm text-gray-400">Start Date</label>
            <input
              type="text"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white font-mono"
            />
          </div>
          <div>
            <label className="text-sm text-gray-400">End Date</label>
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
          <Button onClick={handleBacktest} loading={loading}>Run Backtest</Button>
        </div>
      </Card>

      {error && <div className="p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-300">{error}</div>}

      {result && (
        <>
          {/* Metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card>
              <p className="text-sm text-gray-400">Total Return</p>
              <p className={`text-2xl font-bold ${result.metrics.total_return >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                {formatPercent(result.metrics.total_return)}
              </p>
            </Card>
            <Card>
              <p className="text-sm text-gray-400">Sharpe Ratio</p>
              <p className="text-2xl font-bold">{formatNumber(result.metrics.sharpe_ratio, 4)}</p>
            </Card>
            <Card>
              <p className="text-sm text-gray-400">Max Drawdown</p>
              <p className="text-2xl font-bold text-accent-red">{formatPercent(result.metrics.max_drawdown)}</p>
            </Card>
            <Card>
              <p className="text-sm text-gray-400">Win Rate</p>
              <p className="text-2xl font-bold">{formatPercent(result.metrics.win_rate)}</p>
            </Card>
          </div>

          {/* Equity curve */}
          <Card>
            <CardTitle>Equity Curve</CardTitle>
            <div className="h-64 overflow-x-auto">
              <div className="flex items-end gap-1 h-full min-w-max">
                {result.equity_curve.map((point, i) => {
                  const minEq = Math.min(...result.equity_curve.map((p) => p.equity));
                  const maxEq = Math.max(...result.equity_curve.map((p) => p.equity));
                  const range = maxEq - minEq || 1;
                  const height = ((point.equity - minEq) / range) * 100;
                  return (
                    <div
                      key={i}
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

          <p className="text-xs text-gray-500 text-center">⚠️ {result.metadata.warning}</p>
        </>
      )}
    </div>
  );
}
