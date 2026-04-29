"use client";

import { useState } from "react";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { api, ForecastResponse, ForecastRow } from "@/lib/api";
import { formatCurrency, formatPercent } from "@/lib/utils";

function _makeSampleData(): ForecastRow[] {
  const rows: ForecastRow[] = [];
  let price = 100;
  for (let i = 0; i < 60; i++) {
    const open = price;
    const close = price * (1 + ((i % 5) - 2) * 0.002);
    rows.push({
      timestamp: `2026-01-${String((i % 28) + 1).padStart(2, "0")}T00:00:00Z`,
      open: +open.toFixed(2),
      high: +(Math.max(open, close) * 1.005).toFixed(2),
      low: +(Math.min(open, close) * 0.995).toFixed(2),
      close: +close.toFixed(2),
      volume: 1000000 + i * 1000,
    });
    price = close;
  }
  return rows;
}

export default function ForecastPage() {
  const [symbol, setSymbol] = useState("600519");
  const [predLen, setPredLen] = useState(5);
  const [result, setResult] = useState<ForecastResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleForecast = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.forecast({
        symbol,
        pred_len: predLen,
        rows: _makeSampleData(),
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
      <h1 className="text-3xl font-display">🔮 Forecast</h1>

      {/* Config */}
      <Card>
        <CardTitle>Configuration</CardTitle>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="text-sm text-gray-400">Symbol</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white"
              placeholder="e.g. 600519"
            />
          </div>
          <div>
            <label className="text-sm text-gray-400">Prediction Length</label>
            <input
              type="number"
              value={predLen}
              onChange={(e) => setPredLen(+e.target.value)}
              min={1}
              max={60}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white"
            />
          </div>
          <div className="flex items-end">
            <Button onClick={handleForecast} loading={loading} className="w-full">
              Run Forecast
            </Button>
          </div>
        </div>
      </Card>

      {error && (
        <div className="p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-300">{error}</div>
      )}

      {/* Results */}
      {result && (
        <Card>
          <CardTitle>Results — {result.symbol}</CardTitle>
          <div className="grid grid-cols-3 gap-4 mb-4">
            <div>
              <p className="text-sm text-gray-400">Last Close</p>
              <p className="text-xl font-bold">{formatCurrency(result.forecast[0]?.open || 0)}</p>
            </div>
            <div>
              <p className="text-sm text-gray-400">Predicted Close</p>
              <p className="text-xl font-bold text-primary-light">
                {formatCurrency(result.forecast[result.forecast.length - 1]?.close || 0)}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-400">Elapsed</p>
              <p className="text-xl font-mono">{result.metadata.elapsed_ms}ms</p>
            </div>
          </div>

          {/* Forecast table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 text-gray-400">
                  <th className="py-2 text-left">#</th>
                  <th className="py-2 text-left">Timestamp</th>
                  <th className="py-2 text-right">Open</th>
                  <th className="py-2 text-right">High</th>
                  <th className="py-2 text-right">Low</th>
                  <th className="py-2 text-right">Close</th>
                </tr>
              </thead>
              <tbody>
                {result.forecast.map((bar, i) => (
                  <tr key={i} className="border-b border-gray-800 hover:bg-surface-overlay">
                    <td className="py-2 text-gray-500">{i + 1}</td>
                    <td className="py-2 font-mono text-xs">{bar.timestamp}</td>
                    <td className="py-2 text-right">{bar.open.toFixed(2)}</td>
                    <td className="py-2 text-right">{bar.high.toFixed(2)}</td>
                    <td className="py-2 text-right">{bar.low.toFixed(2)}</td>
                    <td className="py-2 text-right font-semibold">{bar.close.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-xs text-gray-500 mt-4">⚠️ {result.metadata.warning}</p>
        </Card>
      )}
    </div>
  );
}
