"use client";

import { Suspense, useEffect, useRef, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { api, DataResponse, ForecastRow, ForecastResponse, formatApiError } from "@/lib/api";
import { DEFAULT_MARKET, DEFAULT_SYMBOL, MARKET_OPTIONS, type Market } from "@/lib/defaults";
import { queryKeys } from "@/lib/queryKeys";
import { useSessionState } from "@/lib/useSessionState";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  LineData,
  ColorType,
  CrosshairMode,
} from "lightweight-charts";

function toChartTime(ts: string, baseDate?: string): string {
  // Handle relative dates like "D1", "D2", etc.
  const match = ts.match(/^D(\d+)$/);
  if (match) {
    const days = parseInt(match[1], 10);
    const base = baseDate ? new Date(baseDate) : new Date();
    base.setDate(base.getDate() + days);
    return base.toISOString().slice(0, 10);
  }
  return ts.slice(0, 10);
}

function ForecastContent() {
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const symbolParam = searchParams.get("symbol");
  const marketParam = searchParams.get("market") as Market | null;
  const [symbol, setSymbol] = useSessionState(
    "kronos-forecast-symbol",
    symbolParam || DEFAULT_SYMBOL,
    { preferInitial: Boolean(symbolParam) }
  );
  const [market, setMarket] = useSessionState<Market>(
    "kronos-forecast-market",
    marketParam || DEFAULT_MARKET,
    { preferInitial: Boolean(marketParam) }
  );
  const [startDate, setStartDate] = useSessionState("kronos-forecast-start-date", "20250101");
  const [endDate, setEndDate] = useSessionState("kronos-forecast-end-date", "20260430");
  const [data, setData] = useSessionState<ForecastRow[]>("kronos-forecast-data", []);
  const [prediction, setPrediction] = useSessionState<ForecastRow[] | null>("kronos-forecast-prediction", null);
  const [loading, setLoading] = useState(false);
  const [predLoading, setPredLoading] = useState(false);
  const [error, setError] = useSessionState("kronos-forecast-error", "");
  const [predResult, setPredResult] = useSessionState<ForecastResponse | null>("kronos-forecast-result", null);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lineSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  const applyDataResponse = useCallback((res: DataResponse) => {
    if (res.rows && res.rows.length > 0) {
      setData(res.rows);
      setError("");
    } else {
      setError("该代码/日期范围无数据返回。");
      setData([]);
    }
  }, [setData, setError]);

  const handleFetchData = useCallback(async (forceRefresh = false) => {
    if (!symbol) return;
    setError("");
    setPrediction(null);
    setPredResult(null);
    const key = queryKeys.data({ symbol, market, startDate, endDate });
    const cached = forceRefresh ? undefined : queryClient.getQueryData<DataResponse>(key);
    if (cached) {
      applyDataResponse(cached);
      return;
    }

    setLoading(true);
    try {
      if (forceRefresh) {
        await queryClient.invalidateQueries({ queryKey: key });
      }
      const res = await queryClient.fetchQuery({
        queryKey: key,
        queryFn: () =>
          market === "cn"
            ? api.getData(symbol, startDate, endDate)
            : api.getGlobalData(symbol, market, startDate, endDate),
      });
      applyDataResponse(res);
    } catch (e: any) {
      setError(formatApiError(e));
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [
    symbol,
    market,
    startDate,
    endDate,
    queryClient,
    applyDataResponse,
    setError,
    setPrediction,
    setPredResult,
    setData,
  ]);

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
    // Use the last date from historical data as base for relative dates
    const baseDate = data.length > 0 ? data[data.length - 1].timestamp : undefined;
    const lineData: LineData[] = prediction.map((row) => ({
      time: toChartTime(row.timestamp, baseDate),
      value: row.close,
    }));
    lineSeriesRef.current.setData(lineData);
    chartRef.current?.timeScale().fitContent();
  }, [prediction, data]);

  const applyForecastResponse = useCallback((res: ForecastResponse) => {
    if (res.forecast && res.forecast.length > 0) {
      setPrediction(res.forecast);
      setPredResult(res);
      setError("");
    } else {
      setError("未返回预测数据。");
    }
  }, [setError, setPredResult, setPrediction]);

  const handleRunPrediction = async (forceRefresh = false) => {
    if (data.length === 0) {
      setError("请先加载数据再运行预测。");
      return;
    }
    const key = queryKeys.forecast({
      symbol,
      market,
      predLen: 5,
      rowCount: data.length,
      lastTimestamp: data[data.length - 1]?.timestamp,
      dryRun: true,
    });
    const cached = forceRefresh ? undefined : queryClient.getQueryData<ForecastResponse>(key);
    if (cached) {
      applyForecastResponse(cached);
      return;
    }

    setPredLoading(true);
    setError("");
    try {
      if (forceRefresh) {
        await queryClient.invalidateQueries({ queryKey: key });
      }
      const res = await queryClient.fetchQuery({
        queryKey: key,
        queryFn: () =>
          api.forecast({
            symbol,
            pred_len: 5,
            rows: data,
            dry_run: true,
          }),
      });
      applyForecastResponse(res);
    } catch (e: any) {
      setError(formatApiError(e));
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
      <h1 className="text-3xl font-display">价格预测</h1>

      {/* Controls */}
      <Card>
        <div className="grid grid-cols-1 md:grid-cols-6 gap-4">
          <div>
            <label className="text-sm text-gray-400">代码</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white font-mono"
              placeholder={`例如 ${DEFAULT_SYMBOL}`}
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
            <label className="text-sm text-gray-400">开始日期</label>
            <input
              type="text"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white font-mono"
              placeholder="YYYYMMDD"
            />
          </div>
          <div>
            <label className="text-sm text-gray-400">结束日期</label>
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
              onClick={() => handleFetchData(false)}
              loading={loading}
              className="w-full"
            >
              获取数据
            </Button>
          </div>
          <div className="flex items-end">
            <Button
              onClick={() => handleRunPrediction(false)}
              loading={predLoading}
              className="w-full"
              disabled={data.length === 0}
            >
              运行预测
            </Button>
          </div>
        </div>
        {data.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-3">
            <Button variant="secondary" onClick={() => handleFetchData(true)} loading={loading}>
              刷新数据
            </Button>
            <Button
              variant="secondary"
              onClick={() => handleRunPrediction(true)}
              loading={predLoading}
              disabled={data.length === 0}
            >
              重新预测
            </Button>
          </div>
        )}
      </Card>

      {error && (
        <div className="p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-300">
          {error}
        </div>
      )}

      {/* Chart */}
      <Card>
        <CardTitle>
          {symbol} — {data.length} 根K线
          {predResult && (
            <span className="text-sm font-normal text-gray-400 ml-4">
              预测: {predResult.forecast?.length || 0} 步
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
            <p className="text-sm text-gray-400">最新收盘</p>
            <p className="text-xl font-bold">{lastClose.toFixed(2)}</p>
          </Card>
          <Card>
            <p className="text-sm text-gray-400">预测收盘</p>
            <p className="text-xl font-bold text-blue-400">
              {predictedClose.toFixed(2)}
            </p>
          </Card>
          {changePct !== null && (
            <Card>
              <p className="text-sm text-gray-400">涨跌幅</p>
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
          <CardTitle>历史数据</CardTitle>
          <div className="overflow-x-auto max-h-64 overflow-y-auto">
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
                {data.slice(-50).map((row) => (
                  <tr
                    key={`${row.timestamp}-${row.close}`}
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
              显示最近50条，共{data.length}条
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
        <div className="p-12 text-center text-gray-500">加载中...</div>
      }
    >
      <ForecastContent />
    </Suspense>
  );
}
