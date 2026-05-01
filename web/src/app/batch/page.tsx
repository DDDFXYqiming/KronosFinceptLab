"use client";

import { useState } from "react";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { api, ForecastRow } from "@/lib/api";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

type Market = "cn" | "us" | "hk" | "commodity";

const MARKET_OPTIONS: { value: Market; label: string }[] = [
  { value: "cn", label: "A股" },
  { value: "us", label: "美股" },
  { value: "hk", label: "港股" },
  { value: "commodity", label: "大宗商品" },
];

interface BatchResult {
  symbol: string;
  last_close: number;
  predicted_close: number;
  predicted_return: number;
  rank: number;
}

export default function BatchPage() {
  const [input, setInput] = useState("600519,000858,000001");
  const [market, setMarket] = useState<Market>("cn");
  const [predLen, setPredLen] = useState(5);
  const [results, setResults] = useState<BatchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleCompare = async () => {
    const symbols = input
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (symbols.length === 0) {
      setError("请至少输入一个股票代码。");
      return;
    }
    if (symbols.length > 20) {
      setError("每批最多20个股票代码。");
      return;
    }

    setLoading(true);
    setError("");
    setResults([]);

    try {
      const collected: BatchResult[] = [];

      for (let i = 0; i < symbols.length; i++) {
        const sym = symbols[i];

        try {
          // Fetch historical data
          let rows: ForecastRow[] = [];
          try {
            const dataRes =
              market === "cn"
                ? await api.getData(sym, "20250101", "20260430")
                : await api.getGlobalData(sym, market, "20250101", "20260430");
            rows = dataRes.rows || [];
          } catch {
            // proceed with empty rows
          }

          // Run forecast
          const res = await api.forecast({
            symbol: sym,
            pred_len: predLen,
            rows: rows.slice(-120),
          });

          if (res.forecast && res.forecast.length > 0) {
            const lastClose =
              rows.length > 0
                ? rows[rows.length - 1].close
                : res.forecast[0].open;
            const predClose =
              res.forecast[res.forecast.length - 1].close;
            collected.push({
              symbol: sym,
              last_close: lastClose,
              predicted_close: predClose,
              predicted_return:
                lastClose !== 0 ? (predClose - lastClose) / lastClose : 0,
              rank: 0,
            });
          }
        } catch {
          // skip failed symbols
        }
      }

      // Sort by predicted return descending
      collected.sort((a, b) => b.predicted_return - a.predicted_return);
      collected.forEach((r, i) => {
        r.rank = i + 1;
      });

      setResults(collected);
    } catch (e: any) {
      setError(e.message || "批量对比失败");
    } finally {
      setLoading(false);
    }
  };

  const chartData = results.map((r) => ({
    name: r.symbol,
    return: +(r.predicted_return * 100).toFixed(2),
    fill: r.predicted_return >= 0 ? "#10B981" : "#EF4444",
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-display">批量对比</h1>

      {/* Controls */}
      <Card>
        <CardTitle>多标的对比</CardTitle>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="md:col-span-2">
            <label className="text-sm text-gray-400">
              股票代码（逗号分隔）
            </label>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white font-mono"
              placeholder="例如 600519,000858,000001"
            />
          </div>
          <div>
            <label className="text-sm text-gray-400">市场</label>
            <select
              value={market}
              onChange={(e) => setMarket(e.target.value as Market)}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white"
            >
              {MARKET_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-sm text-gray-400">
              预测天数
            </label>
            <input
              type="number"
              value={predLen}
              onChange={(e) => setPredLen(Math.max(1, +e.target.value))}
              min={1}
              max={60}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white"
            />
          </div>
        </div>
        <div className="mt-4">
          <Button onClick={handleCompare} loading={loading}>
            开始对比
          </Button>
        </div>
      </Card>

      {error && (
        <div className="p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-300">
          {error}
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <>
          {/* Bar Chart */}
          <Card>
            <CardTitle>预测收益率对比</CardTitle>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="#1F2937"
                  />
                  <XAxis
                    dataKey="name"
                    tick={{ fill: "#9CA3AF", fontSize: 12 }}
                  />
                  <YAxis
                    tick={{ fill: "#9CA3AF", fontSize: 12 }}
                    tickFormatter={(v: number) => `${v}%`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#111827",
                      border: "1px solid #374151",
                      borderRadius: "8px",
                      color: "#E5E7EB",
                    }}
                    formatter={(value: number) => [
                      `${value.toFixed(2)}%`,
                      "预测收益率",
                    ]}
                  />
                  <Bar dataKey="return" radius={[4, 4, 0, 0]}>
                    {chartData.map((entry, index) => (
                      <rect
                        key={`cell-${index}`}
                        fill={entry.fill}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {/* Results Table */}
          <Card>
            <CardTitle>排名</CardTitle>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-700 text-gray-400">
                    <th className="py-2 text-left w-12">排名</th>
                    <th className="py-2 text-left">代码</th>
                    <th className="py-2 text-right">最新收盘</th>
                    <th className="py-2 text-right">预测收盘</th>
                    <th className="py-2 text-right">预测收益率</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r, i) => {
                    const returnPct = r.predicted_return * 100;
                    const isBest = i === 0;
                    const isWorst = i === results.length - 1;
                    return (
                      <tr
                        key={r.symbol}
                        className={`border-b border-gray-800 hover:bg-surface-overlay ${
                          isBest
                            ? "bg-green-900/10"
                            : isWorst
                            ? "bg-red-900/10"
                            : ""
                        }`}
                      >
                        <td className="py-2">
                          <span
                            className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${
                              isBest
                                ? "bg-green-900/40 text-green-400"
                                : isWorst
                                ? "bg-red-900/40 text-red-400"
                                : "bg-gray-700 text-gray-300"
                            }`}
                          >
                            {r.rank}
                          </span>
                        </td>
                        <td className="py-2 font-mono font-bold text-white">
                          {r.symbol}
                        </td>
                        <td className="py-2 text-right">
                          {r.last_close.toFixed(2)}
                        </td>
                        <td className="py-2 text-right font-semibold">
                          {r.predicted_close.toFixed(2)}
                        </td>
                        <td
                          className={`py-2 text-right font-semibold ${
                            returnPct >= 0
                              ? "text-green-400"
                              : "text-red-400"
                          }`}
                        >
                          {returnPct >= 0 ? "+" : ""}
                          {returnPct.toFixed(2)}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      {/* Empty state */}
      {results.length === 0 && !loading && !error && (
        <Card>
          <div className="text-center py-12 text-gray-500">
            <p className="text-lg mb-2">批量标的对比</p>
            <p className="text-sm">
              输入多个股票代码，对比预测收益率。
            </p>
          </div>
        </Card>
      )}
    </div>
  );
}
