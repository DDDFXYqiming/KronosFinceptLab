"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { api, AIAnalyzeResponse } from "@/lib/api";

type Market = "cn" | "us" | "hk" | "commodity";

const MARKET_OPTIONS: { value: Market; label: string }[] = [
  { value: "cn", label: "A股" },
  { value: "us", label: "美股" },
  { value: "hk", label: "港股" },
  { value: "commodity", label: "大宗商品" },
];

function getConfidenceColor(value: number): string {
  const pct = value * 100;
  if (pct > 70) return "text-green-400";
  if (pct >= 40) return "text-yellow-400";
  return "text-red-400";
}

function getConfidenceBg(value: number): string {
  const pct = value * 100;
  if (pct > 70) return "bg-green-500";
  if (pct >= 40) return "bg-yellow-500";
  return "bg-red-500";
}

function RecommendationBadge({ rec }: { rec: string }) {
  const lower = rec.toLowerCase();
  let bg = "bg-gray-700 text-gray-300 border-gray-600";
  if (lower === "buy") bg = "bg-green-900/40 text-green-400 border-green-700";
  else if (lower === "sell") bg = "bg-red-900/40 text-red-400 border-red-700";
  else if (lower === "hold") bg = "bg-yellow-900/40 text-yellow-400 border-yellow-700";

  return (
    <span className={`px-3 py-1 rounded-full text-sm font-semibold border ${bg}`}>
      {rec.toUpperCase()}
    </span>
  );
}

function RiskBadge({ level }: { level: string }) {
  const lower = level.toLowerCase();
  let bg = "bg-gray-700 text-gray-300";
  if (lower === "low") bg = "bg-green-900/40 text-green-400";
  else if (lower === "medium") bg = "bg-yellow-900/40 text-yellow-400";
  else if (lower === "high") bg = "bg-red-900/40 text-red-400";

  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${bg}`}>
      {level}
    </span>
  );
}

function AnalysisContent() {
  const searchParams = useSearchParams();
  const [symbol, setSymbol] = useState(searchParams.get("symbol") || "600519");
  const [market, setMarket] = useState<Market>(
    (searchParams.get("market") as Market) || "cn"
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<AIAnalyzeResponse | null>(null);

  const handleAnalyze = async () => {
    if (!symbol) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await api.aiAnalyze({ symbol, market });
      setResult(res);
    } catch (e: any) {
      setError(e.message || "分析请求失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (searchParams.get("symbol")) {
      handleAnalyze();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-display">AI 分析</h1>

      {/* Input Controls */}
      <Card>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="text-sm text-gray-400">代码</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white font-mono"
              placeholder="例如 600519"
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
          <div className="flex items-end">
            <Button onClick={handleAnalyze} loading={loading} className="w-full">
              开始分析
            </Button>
          </div>
        </div>
      </Card>

      {error && (
        <div className="p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-300">
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <>
          {/* Summary Card */}
          <Card>
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="flex items-center gap-3 mb-1">
                  <CardTitle>{result.symbol}</CardTitle>
                  <span className="px-2 py-0.5 text-xs rounded bg-gray-700 text-gray-300">
                    {result.market}
                  </span>
                </div>
                <p className="text-2xl font-bold text-white">
                  {result.current_price.toFixed(2)}
                </p>
              </div>
              <RecommendationBadge rec={result.recommendation} />
            </div>
            <p className="text-gray-300 leading-relaxed">{result.summary}</p>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
              {/* Confidence */}
              <div>
                <p className="text-sm text-gray-400 mb-1">置信度</p>
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${getConfidenceBg(result.confidence)}`}
                      style={{ width: `${(result.confidence || 0) * 100}%` }}
                    />
                  </div>
                  <span
                    className={`text-sm font-bold ${getConfidenceColor(result.confidence)}`}
                  >
                    {(result.confidence * 100).toFixed(1)}%
                  </span>
                </div>
              </div>

              {/* Risk Level */}
              <div>
                <p className="text-sm text-gray-400 mb-1">风险等级</p>
                <RiskBadge level={result.risk_level} />
              </div>

              {/* Current Price */}
              <div>
                <p className="text-sm text-gray-400 mb-1">当前价格</p>
                <p className="text-lg font-bold text-white">
                  {result.current_price.toFixed(2)}
                </p>
              </div>
            </div>
          </Card>

          {/* Detailed Analysis */}
          <Card>
            <CardTitle>详细分析</CardTitle>
            <div className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap max-h-96 overflow-y-auto pr-2">
              {result.detailed_analysis}
            </div>
          </Card>

          {/* Risk Metrics Card */}
          {result.risk_metrics && (
            <Card>
              <CardTitle>风险指标</CardTitle>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {Object.entries(result.risk_metrics).map(([key, value]) => {
                  let displayValue = "";
                  if (typeof value === "number") {
                    if (
                      key.toLowerCase().includes("sharpe") ||
                      key.toLowerCase().includes("ratio")
                    ) {
                      displayValue = value.toFixed(3);
                    } else if (
                      key.toLowerCase().includes("var") ||
                      key.toLowerCase().includes("drawdown") ||
                      key.toLowerCase().includes("volatility")
                    ) {
                      displayValue = (value * 100).toFixed(2) + "%";
                    } else {
                      displayValue = value.toFixed(2);
                    }
                  } else {
                    displayValue = String(value);
                  }

                  const label = key
                    .replace(/_/g, " ")
                    .replace(/\b\w/g, (c) => c.toUpperCase());

                  return (
                    <div key={key}>
                      <p className="text-sm text-gray-400">{label}</p>
                      <p className="text-lg font-bold text-white">
                        {displayValue}
                      </p>
                    </div>
                  );
                })}
              </div>
            </Card>
          )}

          {/* Prediction Section */}
          {result.kronos_prediction && (
            <Card>
              <CardTitle>
                Kronos 预测
                <span className="text-sm font-normal text-gray-400 ml-3">
                  {result.kronos_prediction.model} -- {result.kronos_prediction.prediction_days} days
                </span>
              </CardTitle>
              {result.kronos_prediction.forecast &&
                result.kronos_prediction.forecast.length > 0 && (
                  <div className="overflow-x-auto max-h-80 overflow-y-auto">
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 bg-surface-raised">
                        <tr className="border-b border-gray-700 text-gray-400">
                          <th className="py-2 text-left">日期</th>
                          <th className="py-2 text-right">开盘</th>
                          <th className="py-2 text-right">最高</th>
                          <th className="py-2 text-right">最低</th>
                          <th className="py-2 text-right">收盘</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.kronos_prediction.forecast.map((row, i) => (
                          <tr
                            key={i}
                            className="border-b border-gray-800 hover:bg-surface-overlay"
                          >
                            <td className="py-1.5 font-mono text-xs">
                              {String(row.timestamp).slice(0, 10)}
                            </td>
                            <td className="py-1.5 text-right">
                              {row.open.toFixed(2)}
                            </td>
                            <td className="py-1.5 text-right">
                              {row.high.toFixed(2)}
                            </td>
                            <td className="py-1.5 text-right">
                              {row.low.toFixed(2)}
                            </td>
                            <td className="py-1.5 text-right font-semibold">
                              {row.close.toFixed(2)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              {result.kronos_prediction.probabilistic && (
                <div className="mt-4 p-3 bg-surface-overlay rounded-lg">
                  <p className="text-sm text-gray-400 mb-1">
                    概率预测可用
                  </p>
                  <pre className="text-xs text-gray-500 overflow-x-auto">
                    {JSON.stringify(result.kronos_prediction.probabilistic, null, 2)}
                  </pre>
                </div>
              )}
            </Card>
          )}
        </>
      )}

      {/* No results state */}
      {!result && !error && !loading && (
        <Card>
          <div className="text-center py-12 text-gray-500">
            <p className="text-lg mb-2">AI 智能股票分析</p>
            <p className="text-sm">
              输入股票代码，点击分析获取 AI 驱动的分析报告。
            </p>
          </div>
        </Card>
      )}
    </div>
  );
}

export default function AnalysisPage() {
  return (
    <Suspense
      fallback={
        <div className="p-12 text-center text-gray-500">加载中...</div>
      }
    >
      <AnalysisContent />
    </Suspense>
  );
}
