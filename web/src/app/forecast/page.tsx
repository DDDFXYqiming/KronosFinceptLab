"use client";

import { Suspense, useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/Card";
import { SectionLabel } from "@/components/ui/SectionLabel";
import { Button } from "@/components/ui/Button";
import { AppSelect, type AppSelectOption } from "@/components/ui/AppSelect";
import { ApiKeyNotice } from "@/components/ui/ApiKeyNotice";
import { ApiError, api, formatApiError } from "@/lib/api";
import { demoForecastRows, demoHistoricalRows, DEMO_MARKET, DEMO_SYMBOL } from "@/lib/demoData";
import { DEFAULT_MODEL_ID } from "@/lib/defaults";
import { DEFAULT_MARKET, getMarketLabel, getMarketOptions, normalizeMarket, type Market } from "@/lib/markets";
import { DEFAULT_SYMBOL, DEFAULT_SYMBOL_NAME, normalizeSymbol } from "@/lib/symbols";
import type { Language } from "@/lib/i18n";
import { queryKeys } from "@/lib/queryKeys";
import { toCandlestickSeriesData, toForecastLineData } from "@/lib/chartData";
import { useSessionState } from "@/lib/useSessionState";
import { useAppStore } from "@/stores/app";
import type { DataResponse, ForecastResponse, ForecastRow } from "@/types/api";
import {
  createChart,
  ColorType,
  CrosshairMode,
} from "lightweight-charts";
import type { IChartApi, ISeriesApi } from "lightweight-charts";

function formatForecastDataError(
  error: unknown,
  symbol: string,
  market: Market,
  startDate: string,
  endDate: string,
  language: Language
): string {
  if (error instanceof ApiError && error.status === 404) {
    const requestId = error.requestId ? ` request_id=${error.requestId}` : "";
    const marketLabel = getMarketLabel(market, language);
    const defaultHint = symbol !== DEFAULT_SYMBOL
      ? tx(language, `如果要看${DEFAULT_SYMBOL_NAME}，请使用代码 ${DEFAULT_SYMBOL}。`, `Use ${DEFAULT_SYMBOL} for ${DEFAULT_SYMBOL_NAME}.`)
      : "";
    return tx(
      language,
      `未找到 ${symbol} 在 ${startDate}~${endDate} 的${marketLabel}K线数据。请确认代码、市场和日期范围。${defaultHint}${requestId}`,
      `No ${marketLabel} OHLC data was found for ${symbol} from ${startDate} to ${endDate}. Check the symbol, market, and date range. ${defaultHint}${requestId}`
    );
  }
  return formatApiError(error, tx(language, "行情获取失败", "Failed to load market data"));
}

function tx(language: Language, zh: string, en: string): string {
  return language === "en-US" ? en : zh;
}

function ForecastEmptyState({ symbol, language }: { symbol: string; language: Language }) {
  return (
    <Card>
      <CardTitle>{tx(language, "未加载行情", "No Market Data Loaded")}</CardTitle>
      <div className="py-12 text-center">
        <p className="text-base font-medium text-foreground">
          {tx(language, "当前没有可显示的 K 线数据", "There is no OHLC data to display.")}
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          {tx(
            language,
            `请确认 ${symbol || "该标的"} 的代码、市场和日期范围；${DEFAULT_SYMBOL_NAME}代码为 ${DEFAULT_SYMBOL}。`,
            `Check the symbol, market, and date range for ${symbol || "this asset"}. ${DEFAULT_SYMBOL_NAME} uses ${DEFAULT_SYMBOL}.`
          )}
        </p>
      </div>
    </Card>
  );
}

function ForecastContent() {
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { preferences, setPreferences } = useAppStore();
  const language = preferences.language;
  const marketOptions = getMarketOptions(language);
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
  const [modelId, setModelId] = useSessionState(
    "kronos-forecast-model-id",
    preferences.defaultModelId || DEFAULT_MODEL_ID
  );
  const [availableModelIds, setAvailableModelIds] = useState<string[]>([preferences.defaultModelId || DEFAULT_MODEL_ID]);
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
  const demoMode = searchParams.get("demo") === "1";
  const modelOptions = useMemo(() => {
    return Array.from(new Set((availableModelIds.length ? availableModelIds : [DEFAULT_MODEL_ID]).filter(Boolean)));
  }, [availableModelIds]);
  const modelSelectOptions: Array<AppSelectOption<string>> = useMemo(
    () => modelOptions.map((id) => ({ value: id, label: id.replace("NeoQuasar/", "") })),
    [modelOptions]
  );

  useEffect(() => {
    void queryClient.fetchQuery({
      queryKey: queryKeys.health(),
      queryFn: ({ signal }) => api.health({ signal }),
      staleTime: 60000,
    }).then((health) => {
      const supported = health.supported_model_ids?.length
        ? health.supported_model_ids
        : [health.model_id || health.default_model_id || DEFAULT_MODEL_ID];
      setAvailableModelIds(supported);
      const nextModelId = supported.includes(modelId) ? modelId : supported[0];
      if (nextModelId && nextModelId !== modelId) {
        setModelId(nextModelId);
        setPreferences({ defaultModelId: nextModelId });
      }
    }).catch(() => undefined);
  }, [modelId, queryClient, setModelId, setPreferences]);

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
      setError(tx(
        language,
        `未找到 ${res.symbol || normalizeSymbol(symbol)} 在 ${startDate}~${endDate} 的K线数据。请确认代码、市场和日期范围。`,
        `No OHLC data was found for ${res.symbol || normalizeSymbol(symbol)} from ${startDate} to ${endDate}. Check the symbol, market, and date range.`
      ));
      clearForecastState();
    }
  }, [clearForecastState, language, setData, setError, symbol, startDate, endDate]);

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
      setError(formatForecastDataError(e, requestSymbol, market, startDate, endDate, language));
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
    language,
  ]);

  // Load data from URL params on mount
  useEffect(() => {
    if (searchParams.get("symbol")) {
      handleFetchData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!demoMode) return;
    setSymbol(DEMO_SYMBOL);
    setMarket(DEMO_MARKET as Market);
    setData(demoHistoricalRows);
    setPrediction(demoForecastRows);
    setPredResult({
      ok: true,
      symbol: DEMO_SYMBOL,
      forecast: demoForecastRows,
      metadata: { device: "demo", elapsed_ms: 0, backend: "demo", warning: tx(language, "演示数据，不代表实时行情，不构成投资建议。", "Demo data only. Not real-time market data or investment advice.") },
    });
    setError("");
  }, [demoMode, language, setData, setError, setMarket, setPredResult, setPrediction, setSymbol]);

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
      height: window.innerWidth < 768 ? 360 : 500,
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
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: window.innerWidth < 768 ? 360 : 500,
        });
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
    const ohlcData = toCandlestickSeriesData(data);
    candlestickSeriesRef.current.setData(ohlcData);
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  // Update prediction line
  useEffect(() => {
    if (!lineSeriesRef.current || !prediction || prediction.length === 0) {
      lineSeriesRef.current?.setData([]);
      lineSeriesRef.current?.setMarkers([]);
      return;
    }
    const lineData = toForecastLineData(data, prediction);
    lineSeriesRef.current.setData(lineData);
    lineSeriesRef.current.setMarkers(
      lineData.length > 1
        ? [{
          time: lineData[0].time,
          position: "inBar",
          color: "#60A5FA",
          shape: "circle",
          text: tx(language, "预测起点", "Forecast start"),
        }]
        : []
    );
    chartRef.current?.timeScale().fitContent();
  }, [prediction, data, language]);

  const applyForecastResponse = useCallback((res: ForecastResponse) => {
    if (res.forecast && res.forecast.length > 0) {
      setPrediction(res.forecast);
      setPredResult(res);
      setError("");
    } else {
      setError(tx(language, "未返回预测数据。", "No forecast data was returned."));
    }
  }, [language, setError, setPredResult, setPrediction]);

  const handleRunPrediction = async (forceRefresh = false) => {
    if (data.length === 0) {
      setError(tx(language, "请先加载数据再运行预测。", "Load market data before running a forecast."));
      return;
    }
    const requestSymbol = normalizeSymbol(symbol);
    if (!requestSymbol) return;
    const key = queryKeys.forecast({
      symbol: requestSymbol,
      market,
      predLen: 5,
      modelId,
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
            model_id: modelId,
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
    <div className="page-shell space-y-6">
      <SectionLabel>{tx(language, "价格预测", "Price Forecast")}</SectionLabel>
      <h1 className="page-title">{tx(language, "价格预测", "Price Forecast")}</h1>
      <ApiKeyNotice />
      {demoMode && (
        <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">
          {tx(language, "当前展示固定演示数据，不调用后端模型，不代表实时行情。", "Showing fixed demo data. Backend models are not called and this is not real-time market data.")}
        </div>
      )}

      {/* Controls */}
      <Card>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-6">
          <div>
            <label className="field-label">{tx(language, "代码", "Symbol")}</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="app-input mt-1 font-mono"
              placeholder={tx(language, `例如 ${DEFAULT_SYMBOL}`, `e.g. ${DEFAULT_SYMBOL}`)}
            />
          </div>
          <div>
            <label className="field-label">{tx(language, "市场", "Market")}</label>
            <AppSelect value={market} onChange={setMarket} options={marketOptions} ariaLabel={tx(language, "市场", "Market")} className="mt-1" />
          </div>
          <div>
            <label className="field-label">{tx(language, "开始日期", "Start date")}</label>
            <input
              type="text"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="app-input mt-1 font-mono"
              placeholder="YYYYMMDD"
            />
          </div>
          <div>
            <label className="field-label">{tx(language, "结束日期", "End date")}</label>
            <input
              type="text"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="app-input mt-1 font-mono"
              placeholder="YYYYMMDD"
            />
          </div>
          <div>
            <label className="field-label">{tx(language, "模型", "Model")}</label>
            {modelSelectOptions.length > 1 ? (
              <AppSelect
                value={modelOptions.includes(modelId) ? modelId : modelOptions[0]}
                onChange={(nextModelId) => {
                  setModelId(nextModelId);
                  setPreferences({ defaultModelId: nextModelId });
                }}
                options={modelSelectOptions}
                ariaLabel={tx(language, "模型", "Model")}
                className="mt-1"
              />
            ) : (
              <div className="mt-1 flex min-h-11 items-center rounded-[10px] border border-slate-700 bg-slate-800 px-3 text-sm text-white">
                {modelSelectOptions[0]?.label || DEFAULT_MODEL_ID.replace("NeoQuasar/", "")}
              </div>
            )}
          </div>
          <div className="flex items-end">
            <Button
              onClick={() => handleFetchData(false)}
              loading={loading}
              className="w-full"
            >
              {tx(language, "获取数据", "Load Data")}
            </Button>
          </div>
          <div className="flex items-end">
            <Button
              onClick={() => handleRunPrediction(false)}
              loading={predLoading}
              className="w-full"
              disabled={data.length === 0}
            >
              {tx(language, "运行预测", "Run Forecast")}
            </Button>
          </div>
        </div>
        {data.length > 0 && (
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 md:flex md:flex-wrap">
            <Button variant="secondary" onClick={() => handleFetchData(true)} loading={loading}>
              {tx(language, "刷新数据", "Refresh Data")}
            </Button>
            <Button
              variant="secondary"
              onClick={() => handleRunPrediction(true)}
              loading={predLoading}
              disabled={data.length === 0}
            >
              {tx(language, "重新预测", "Rerun Forecast")}
            </Button>
          </div>
        )}
      </Card>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      {hasChartData ? (
        <Card>
          <CardTitle>
            {/* Legacy test anchor: {symbol} — {data.length} 根K线 */}
            {symbol} — {tx(language, `${data.length} 根K线`, `${data.length} OHLC rows`)}
            {predResult && (
              <span className="ml-0 block text-sm font-normal text-muted-foreground md:ml-4 md:inline">
                {tx(language, "预测", "Forecast")}: {predResult.forecast?.length || 0} {tx(language, "步", "steps")}
                {predResult.metadata.elapsed_ms &&
                  ` (${predResult.metadata.elapsed_ms}ms)`}
              </span>
            )}
          </CardTitle>
          <div ref={chartContainerRef} className="chart-frame h-[360px] md:h-[500px]" />
          <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-accent-green" />
              {tx(language, "实际 OHLC", "Actual OHLC")}
            </span>
            <span className="inline-flex items-center gap-2">
              <span className="h-2 w-5 rounded-full bg-accent" />
              {tx(language, "Kronos 预测路径", "Kronos forecast path")}
            </span>
            {prediction && prediction.length > 0 && (
              <span>{tx(language, `预测区间：未来 ${prediction.length} 步`, `Forecast horizon: next ${prediction.length} steps`)}</span>
            )}
          </div>
        </Card>
      ) : (
        <ForecastEmptyState symbol={normalizeSymbol(symbol)} language={language} />
      )}

      {/* Prediction Stats */}
      {predResult && predictedClose !== null && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <p className="text-sm text-muted-foreground">{tx(language, "最新收盘", "Latest Close")}</p>
            <p className="text-xl font-bold">{lastClose.toFixed(2)}</p>
          </Card>
          <Card>
            <p className="text-sm text-muted-foreground">{tx(language, "预测收盘", "Forecast Close")}</p>
            <p className="text-xl font-bold text-blue-400">
              {predictedClose.toFixed(2)}
            </p>
          </Card>
          {changePct !== null && (
            <Card>
              <p className="text-sm text-muted-foreground">{tx(language, "涨跌幅", "Change")}</p>
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
          <CardTitle>{tx(language, "历史数据", "Historical Data")}</CardTitle>
          <div className="table-scroll max-h-64 overflow-y-auto">
            <table className="min-w-[42rem] w-full text-sm">
              <thead className="sticky top-0 bg-surface-raised">
                <tr className="border-b border-gray-700 text-gray-400">
                  <th className="py-2 text-left">{tx(language, "日期", "Date")}</th>
                  <th className="py-2 text-right">{tx(language, "开盘", "Open")}</th>
                  <th className="py-2 text-right">{tx(language, "最高", "High")}</th>
                  <th className="py-2 text-right">{tx(language, "最低", "Low")}</th>
                  <th className="py-2 text-right">{tx(language, "收盘", "Close")}</th>
                  <th className="py-2 text-right">{tx(language, "成交量", "Volume")}</th>
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
              {tx(language, `显示最近50条，共${data.length}条`, `Showing latest 50 of ${data.length} rows`)}
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
