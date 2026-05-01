"use client";

import { Suspense, useEffect, useRef, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { api, ForecastRow, ForecastResponse } from "@/lib/api";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  LineData,
  ColorType,
  CrosshairMode,
} from "lightweight-charts";

type Market = "cn" | "us" | "hk" | "commodity";

const MARKET_OPTIONS: { value: Market; label: string }[] = [
  { value: "cn", label: "A-Share" },
  { value: "us", label: "US Stock" },
  { value: "hk", label: "HK Stock" },
  { value: "commodity", label: "Commodity" },
];

function toChartTime(ts: string): string {
  return ts.slice(0, 10);
}

function ForecastContent() {
  const searchParams = useSearchParams();
  const [symbol, setSymbol] = useState(searchParams.get("symbol") || "600519");
  const [market, setMarket] = useState<Market>(
    (searchParams.get("market") as Market) || "cn"
  );
  const [startDate, setStartDate] = useState("20250101");
  const [endDate, setEndDate] = useState("20260430");
  const [data, setData] = useState<ForecastRow[]>([]);
  const [prediction, setPrediction] = useState<ForecastRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [predLoading, setPredLoading] = useState(false);
  const [error, setError] = useState("");
  const [predResult, setPredResult] = useState<ForecastResponse | null>(null);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lineSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  const handleFetchData = useCallback(async () => {
    if (!symbol) return;
    setLoading(true);
    setError("");
    setPrediction(null);
    setPredResult(null);
    try {
      let res;
      if (market === "cn") {
        res = await api.getData(symbol, startDate, endDate);
      } else {
        res = await api.getGlobalData(symbol, market, startDate, endDate);
      }
      if (res.rows && res.rows.length > 0) {
        setData(res.rows);
      } else {
        setError("No data returned for this symbol/date range.");
        setData([]);
      }
    } catch (e: any) {
      setError(e.message);
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [symbol, market, startDate, endDate]);

  // Load data from URL params on mount
  useEffect(() => {
    if (searchParams.get("symbol")) {
      handleFetchData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Create/destroy chart
  useEffect(() => {
    if (!chartContainerRef.current) return;
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0A0E1A" },
        textColor: "#9CA3AF",
      },
      grid: {
        vertLines: { color: "#1F2937" },
        horzLines: { color: "#1F2937" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      timeScale: {
        borderColor: "#374151",
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: "#374151",
      },
      width: chartContainerRef.current.clientWidth,
      height: 500,
    });

    chartRef.current = chart;

    const candlestickSeries = chart.addCandlestickSeries({
      upColor: "#10B981",
      downColor: "#EF4444",
      borderDownColor: "#EF4444",
      borderUpColor: "#10B981",
      wickDownColor: "#EF4444",
      wickUpColor: "#10B981",
    });
    candlestickSeriesRef.current = candlestickSeries;

    const lineSeries = chart.addLineSeries({
      color: "#0052FF",
      lineWidth: 2,
      lastValueVisible: true,
      priceFormat: {
        type: "price",
      },
    });
    lineSeriesRef.current = lineSeries;

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, []);

  // Update candlestick data
  useEffect(() => {
    if (!candlestickSeriesRef.current || data.length === 0) return;
    const ohlcData: CandlestickData[] = data.map((row) => ({
      time: toChartTime(row.timestamp),
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
    }));
    candlestickSeriesRef.current.setData(ohlcData);
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  // Update prediction line
  useEffect(() => {
    if (!lineSeriesRef.current || !prediction || prediction.length === 0) {
      lineSeriesRef.current?.setData([]);
      return;
    }
    const lineData: LineData[] = prediction.map((row) => ({
      time: toChartTime(row.timestamp),
      value: row.close,
    }));
    lineSeriesRef.current.setData(lineData);
    chartRef.current?.timeScale().fitContent();
  }, [prediction]);

  const handleRunPrediction = async () => {
    if (data.length === 0) {
      setError("Load data first before running prediction.");
      return;
    }
    setPredLoading(true);
    setError("");
    try {
      const res = await api.forecast({
        symbol,
        pred_len: 5,
        rows: data,
        dry_run: true,
      });
      if (res.forecast && res.forecast.length > 0) {
        setPrediction(res.forecast);
        setPredResult(res);
      } else {
        setError("No prediction data returned.");
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setPredLoading(false);
    }
  };

  const lastClose = data.length > 0 ? data[data.length - 1].close : 0;
  const predictedClose =
    prediction && prediction.length > 0
      ? prediction[prediction.length - 1].close
      : null;
  const changePct =
    predictedClose !== null && lastClose !== 0
      ? ((predictedClose - lastClose) / lastClose) * 100
      : null;

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-display">Forecast</h1>

      {/* Controls */}
      <Card>
        <div className="grid grid-cols-1 md:grid-cols-6 gap-4">
          <div>
            <label className="text-sm text-gray-400">Symbol</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white font-mono"
              placeholder="e.g. 600519"
            />
          </div>
          <div>
            <label className="text-sm text-gray-400">Market</label>
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
            <label className="text-sm text-gray-400">Start Date</label>
            <input
              type="text"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white font-mono"
              placeholder="YYYYMMDD"
            />
          </div>
          <div>
            <label className="text-sm text-gray-400">End Date</label>
            <input
              type="text"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white font-mono"
              placeholder="YYYYMMDD"
            />
          </div>
          <div className="flex items-end">
            <Button
              onClick={handleFetchData}
              loading={loading}
              className="w-full"
            >
              Fetch Data
            </Button>
          </div>
          <div className="flex items-end">
            <Button
              onClick={handleRunPrediction}
              loading={predLoading}
              className="w-full"
              disabled={data.length === 0}
            >
              Run Prediction
            </Button>
          </div>
        </div>
      </Card>

      {error && (
        <div className="p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-300">
          {error}
        </div>
      )}

      {/* Chart */}
      <Card>
        <CardTitle>
          {symbol} -- {data.length} bars
          {predResult && (
            <span className="text-sm font-normal text-gray-400 ml-4">
              Prediction: {predResult.forecast?.length || 0} steps
              {predResult.metadata.elapsed_ms &&
                ` (${predResult.metadata.elapsed_ms}ms)`}
            </span>
          )}
        </CardTitle>
        <div ref={chartContainerRef} className="w-full h-[500px]" />
      </Card>

      {/* Prediction Stats */}
      {predResult && predictedClose !== null && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <p className="text-sm text-gray-400">Last Close</p>
            <p className="text-xl font-bold">{lastClose.toFixed(2)}</p>
          </Card>
          <Card>
            <p className="text-sm text-gray-400">Predicted Close</p>
            <p className="text-xl font-bold text-blue-400">
              {predictedClose.toFixed(2)}
            </p>
          </Card>
          {changePct !== null && (
            <Card>
              <p className="text-sm text-gray-400">Change %</p>
              <p
                className={`text-xl font-bold ${
                  changePct >= 0 ? "text-green-400" : "text-red-400"
                }`}
              >
                {changePct >= 0 ? "+" : ""}
                {changePct.toFixed(2)}%
              </p>
            </Card>
          )}
        </div>
      )}

      {/* Data Table */}
      {data.length > 0 && (
        <Card>
          <CardTitle>Historical Data</CardTitle>
          <div className="overflow-x-auto max-h-64 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface-raised">
                <tr className="border-b border-gray-700 text-gray-400">
                  <th className="py-2 text-left">Date</th>
                  <th className="py-2 text-right">Open</th>
                  <th className="py-2 text-right">High</th>
                  <th className="py-2 text-right">Low</th>
                  <th className="py-2 text-right">Close</th>
                  <th className="py-2 text-right">Volume</th>
                </tr>
              </thead>
              <tbody>
                {data.slice(-50).map((row, i) => (
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
                    <td className="py-1.5 text-right text-gray-400">
                      {(row.volume || 0).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.length > 50 && (
            <p className="text-xs text-gray-500 mt-2">
              Showing last 50 of {data.length} rows
            </p>
          )}
        </Card>
      )}
    </div>
  );
}

export default function ForecastPage() {
  return (
    <Suspense
      fallback={
        <div className="p-12 text-center text-gray-500">Loading...</div>
      }
    >
      <ForecastContent />
    </Suspense>
  );
}
