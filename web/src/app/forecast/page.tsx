"use client";

import { Suspense, useEffect, useRef, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ApiError, api, formatApiError } from "@/lib/api";
import { DEFAULT_MARKET, MARKET_OPTIONS, normalizeMarket, type Market } from "@/lib/markets";
import { DEFAULT_SYMBOL, DEFAULT_SYMBOL_NAME, normalizeSymbol } from "@/lib/symbols";
import { queryKeys } from "@/lib/queryKeys";
import { useSessionState } from "@/lib/useSessionState";
import type { DataResponse, ForecastResponse, ForecastRow } from "@/types/api";
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

function formatForecastDataError(
  error: unknown,
  symbol: string,
  market: Market,
  startDate: string,
  endDate: string
): string {
  if (error instanceof ApiError && error.status === 404) {
    const requestId = error.requestId ? ` request_id=${error.requestId}` : "";
    const marketLabel = MARKET_OPTIONS.find((option) => option.value === market)?.label || market;
    const defaultHint = symbol !== DEFAULT_SYMBOL
      ? `如果要看${DEFAULT_SYMBOL_NAME}，请使用代码 ${DEFAULT_SYMBOL}。`
      : "";
    return (
      `未找到 ${symbol} 在 ${startDate}~${endDate} 的${marketLabel}K线数据。` +
      `请确认代码、市场和日期范围。${defaultHint}${requestId}`
    );
  }
  return formatApiError(error, "行情获取失败");
}

function ForecastEmptyState({ symbol }: { symbol: string }) {
  return (
    <Card>
      <CardTitle>未加载行情</CardTitle>
      <div className="py-12 text-center">
        <p className="text-base font-medium text-foreground">
          当前没有可显示的 K 线数据
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          请确认 {symbol || "该标的"} 的代码、市场和日期范围；{DEFAULT_SYMBOL_NAME}代码为 {DEFAULT_SYMBOL}。
        </p>
      </div>
    </Card>
  );
}

function ForecastContent() {
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const symbolParam = searchParams.get("symbol");
  const marketParam = searchParams.get("market");
  const hasMarketParam = marketParam !== null;
  const [symbol, setSymbol] = useSessionState(
    "kronos-forecast-symbol",
    symbolParam ? normalizeSymbol(symbolParam) : DEFAULT_SYMBOL,
    { preferInitial: Boolean(symbolParam) }
  );
  const [market, setMarket] = useSessionState<Market>(
    "kronos-forecast-market",
    normalizeMarket(marketParam, DEFAULT_MARKET),
    { preferInitial: hasMarketParam }
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
  const hasChartData = data.length > 0;

  const clearForecastState = useCallback(() => {
    setData([]);
    setPrediction(null);
    setPredResult(null);
  }, [setData, setPrediction, setPredResult]);

  const applyDataResponse = useCallback((res: DataResponse) => {
    if (res.rows && res.rows.length > 0) {
      setData(res.rows);
      setError("");
    } else {
      setError(`未找到 ${res.symbol || normalizeSymbol(symbol)} 在 ${startDate}~${endDate} 的K线数据。请确认代码、市场和日期范围。`);
      clearForecastState();
    }
  }, [clearForecastState, setData, setError, symbol, startDate, endDate]);

  const handleFetchData = useCallback(async (forceRefresh = false) => {
    const requestSymbol = normalizeSymbol(symbol);
    if (!requestSymbol) return;
    setError("");
    setPrediction(null);
    setPredResult(null);
    const key = queryKeys.data({ symbol: requestSymbol, market, startDate, endDate });
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
        queryFn: ({ signal }) =>
          market === "cn"
            ? api.getData(requestSymbol, startDate, endDate, { signal })
            : api.getGlobalData(requestSymbol, market, startDate, endDate, { signal }),
      });
      applyDataResponse(res);
    } catch (e: any) {
      setError(formatForecastDataError(e, requestSymbol, market, startDate, endDate));
      clearForecastState();
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
    clearForecastState,
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
    if (!hasChartData) return;
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
      chartRef.current = null;
      candlestickSeriesRef.current = null;
      lineSeriesRef.current = null;
    };
  }, [hasChartData]);

  // Update candlestick data
  useEffect(() => {
    if (!candlestickSeriesRef.current) return;
    if (data.length === 0) {
      candlestickSeriesRef.current.setData([]);
      return;
    }
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
    const requestSymbol = normalizeSymbol(symbol);
    if (!requestSymbol) return;
    const key = queryKeys.forecast({
      symbol: requestSymbol,
      market,
      predLen: 5,
      rowCount: data.length,
      lastTimestamp: data[data.length - 1]?.timestamp,
      dryRun: false,
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
        queryFn: ({ signal }) =>
          api.forecast({
            symbol: requestSymbol,
            pred_len: 5,
            rows: data,
            dry_run: false,
          }, { signal }),
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

      {hasChartData ? (
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
      ) : (
        <ForecastEmptyState symbol={normalizeSymbol(symbol)} />
      )}

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
                    key={`${symbol}-${row.timestamp}`}
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
