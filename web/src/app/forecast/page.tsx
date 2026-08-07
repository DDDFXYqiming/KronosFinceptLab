"use client";

import { Suspense, useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/Card";
import { SectionLabel } from "@/components/ui/SectionLabel";
import { AntButton as Button } from "@/components/antd/AntButton";
import type { AppSelectOption } from "@/components/ui/AppSelect";
import { ApiKeyNotice } from "@/components/ui/ApiKeyNotice";
import { ApiError, api, formatApiError } from "@/lib/api";
import { demoForecastRows, demoHistoricalRows, DEMO_SYMBOL } from "@/lib/demoData";
import { DEFAULT_MODEL_ID, MODEL_SIZE_MAP } from "@/lib/defaults";
import { AntDatePicker } from "@/components/antd/AntDatePicker";
import { AntSelect } from "@/components/antd/AntSelect";
import { AntInput } from "@/components/antd/AntInput";
import { AntAlert } from "@/components/antd/AntAlert";
import { AntTable } from "@/components/antd/AntTable";
import { getMarketLabel, type Market } from "@/lib/markets";
import { inferMarketFromSymbol } from "@/lib/symbols";
import { DEFAULT_SYMBOL, DEFAULT_SYMBOL_NAME, normalizeSymbol } from "@/lib/symbols";
import type { Language } from "@/lib/i18n";
import { queryKeys } from "@/lib/queryKeys";
import { toCandlestickSeriesData, toForecastLineData } from "@/lib/chartData";
import { useSessionState } from "@/lib/useSessionState";
import { useAppStore } from "@/stores/app";
import type { DataResponse, ForecastResponse, ForecastRow, ForecastRuntimeConfig } from "@/types/api";
import {
  createChart,
  ColorType,
  CrosshairMode,
} from "lightweight-charts";
import type { IChartApi, ISeriesApi } from "lightweight-charts";

type ForecastDatasetSnapshot = {
  symbol: string;
  market: Market;
  startDate: string;
  endDate: string;
  rowsCount: number;
  contentHash: string;
  loadedAt: string;
};

function hashForecastRows(rows: ForecastRow[]): string {
  let hash = 2166136261;
  for (const row of rows) {
    const value = `${row.timestamp}|${row.open}|${row.high}|${row.low}|${row.close}|${row.volume ?? ""}|${row.amount ?? ""}`;
    for (let index = 0; index < value.length; index += 1) {
      hash ^= value.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
  }
  return (hash >>> 0).toString(16);
}

function localDateString(date: Date): string {
  return `${date.getFullYear()}${String(date.getMonth() + 1).padStart(2, "0")}${String(date.getDate()).padStart(2, "0")}`;
}

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
  const symbolParam = searchParams.get("symbol");
  const [symbol, setSymbol] = useSessionState(
    "kronos-forecast-symbol",
    symbolParam ? normalizeSymbol(symbolParam) : DEFAULT_SYMBOL,
    { preferInitial: Boolean(symbolParam) }
  );
  const market = useMemo(() => inferMarketFromSymbol(symbol), [symbol]);
  const todayStr = localDateString(new Date());
  const oneYearAgo = new Date();
  oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1);
  const oneYearAgoStr = localDateString(oneYearAgo);
  const [startDate, setStartDate] = useSessionState("kronos-forecast-start-v2", oneYearAgoStr);
  const [endDate, setEndDate] = useSessionState("kronos-forecast-end-v2", todayStr);
  const [modelId, setModelId] = useSessionState(
    "kronos-forecast-model-id",
    preferences.defaultModelId || DEFAULT_MODEL_ID
  );
  const [availableModelIds, setAvailableModelIds] = useState<string[]>([preferences.defaultModelId || DEFAULT_MODEL_ID]);
  const [data, setData] = useState<ForecastRow[]>([]);
  const [datasetSnapshot, setDatasetSnapshot] = useState<ForecastDatasetSnapshot | null>(null);
  const [prediction, setPrediction] = useState<ForecastRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [predLoading, setPredLoading] = useState(false);
  const [error, setError] = useSessionState("kronos-forecast-error", "");
  const [predResult, setPredResult] = useState<ForecastResponse | null>(null);
  const [sampleCount, setSampleCount] = useSessionState("kronos-forecast-sample-count", 8);
  const [temperature, setTemperature] = useSessionState("kronos-forecast-temperature", 0.5);
  const [runtimeConfig, setRuntimeConfig] = useState<ForecastRuntimeConfig | null>(null);
  const runtimeLookback = runtimeConfig?.lookback ?? 90;
  const runtimeTemperature = runtimeConfig?.temperature ?? 0.5;
  const runtimePredLen = runtimeConfig?.pred_len ?? 10;
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lineSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const dataHash = useMemo(() => (data.length ? hashForecastRows(data) : ""), [data]);
  const datasetMatchesCurrent = Boolean(
    datasetSnapshot
      && datasetSnapshot.symbol === normalizeSymbol(symbol)
      && datasetSnapshot.market === market
      && datasetSnapshot.startDate === startDate
      && datasetSnapshot.endDate === endDate
      && datasetSnapshot.rowsCount === data.length
      && datasetSnapshot.contentHash === dataHash
  );
  const hasChartData = data.length > 0 && datasetMatchesCurrent;
  const demoMode = searchParams.get("demo") === "1";
  const modelOptions = useMemo(() => {
    return Array.from(new Set((availableModelIds.length ? availableModelIds : [DEFAULT_MODEL_ID]).filter(Boolean)));
  }, [availableModelIds]);
  const modelSelectOptions: Array<AppSelectOption<string>> = useMemo(
    () => modelOptions.map((id) => ({ value: id, label: `${id.replace("NeoQuasar/", "")} \u00b7 ${MODEL_SIZE_MAP[id]?.memory || ""}` })),
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

  useEffect(() => {
    void queryClient.fetchQuery({
      queryKey: queryKeys.forecastConfig(),
      queryFn: ({ signal }) => api.forecastConfig({ signal }),
      staleTime: 60000,
    }).then((config) => {
      setRuntimeConfig(config);
      setSampleCount((current) => (current === 8 && config.sample_count !== 8 ? config.sample_count : current));
      setTemperature((current) => (current === 0.5 && config.temperature !== 0.5 ? config.temperature : current));
    }).catch(() => undefined);
  }, [queryClient, setSampleCount, setTemperature]);

  const clearForecastState = useCallback(() => {
    setData([]);
    setDatasetSnapshot(null);
    setPrediction(null);
    setPredResult(null);
  }, [setData, setDatasetSnapshot, setPrediction, setPredResult]);

  const applyDataResponse = useCallback((res: DataResponse, request: { symbol: string; market: Market; startDate: string; endDate: string }) => {
    if (res.rows && res.rows.length > 0) {
      setData(res.rows);
      setDatasetSnapshot({
        ...request,
        rowsCount: res.rows.length,
        contentHash: hashForecastRows(res.rows),
        loadedAt: new Date().toISOString(),
      });
      setError("");
    } else {
      setError(tx(
        language,
        `未找到 ${res.symbol || normalizeSymbol(symbol)} 在 ${startDate}~${endDate} 的K线数据。请确认代码、市场和日期范围。`,
        `No OHLC data was found for ${res.symbol || normalizeSymbol(symbol)} from ${startDate} to ${endDate}. Check the symbol, market, and date range.`
      ));
      clearForecastState();
    }
  }, [clearForecastState, language, setData, setDatasetSnapshot, setError, symbol, startDate, endDate]);

  const handleFetchData = useCallback(async (forceRefresh = false) => {
    const requestSymbol = normalizeSymbol(symbol);
    if (!requestSymbol) return;
    if (startDate > endDate) {
      setError(tx(language, "开始日期不能晚于结束日期。", "Start date must not be later than end date."));
      return;
    }
    setError("");
    setPrediction(null);
    setPredResult(null);
    const key = queryKeys.data({ symbol: requestSymbol, market, startDate, endDate });
    const cached = forceRefresh ? undefined : queryClient.getQueryData<DataResponse>(key);
    if (cached) {
      applyDataResponse(cached, { symbol: requestSymbol, market, startDate, endDate });
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
      applyDataResponse(res, { symbol: requestSymbol, market, startDate, endDate });
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
    setData(demoHistoricalRows);
    setDatasetSnapshot({
      symbol: DEMO_SYMBOL,
      market: "cn",
      startDate,
      endDate,
      rowsCount: demoHistoricalRows.length,
      contentHash: hashForecastRows(demoHistoricalRows),
      loadedAt: new Date().toISOString(),
    });
    setPrediction(demoForecastRows);
    setPredResult({
      ok: true,
      symbol: DEMO_SYMBOL,
      forecast: demoForecastRows,
      metadata: { device: "demo", elapsed_ms: 0, backend: "demo", warning: tx(language, "演示数据，不代表实时行情，不构成投资建议。", "Demo data only. Not real-time market data or investment advice.") },
    });
    setError("");
  }, [demoMode, endDate, language, setData, setDatasetSnapshot, setError, setPredResult, setPrediction, setSymbol, startDate]);

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
      upColor: "#EF4444",
      downColor: "#10B981",
      borderDownColor: "#10B981",
      borderUpColor: "#EF4444",
      wickDownColor: "#10B981",
      wickUpColor: "#EF4444",
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
    if (!datasetMatchesCurrent || !datasetSnapshot || data.length === 0) {
      setError(tx(language, "请先加载数据再运行预测。", "Load market data before running a forecast."));
      return;
    }
    const requestSymbol = datasetSnapshot.symbol;
    const requestMarket = datasetSnapshot.market;
    const forecastRows = data.slice(-runtimeLookback);
    const key = queryKeys.forecast({
      symbol: requestSymbol,
      market: requestMarket,
      predLen: runtimePredLen,
      modelId,
      rowCount: forecastRows.length,
      lastTimestamp: data[data.length - 1]?.timestamp,
      dataHash: datasetSnapshot.contentHash,
      sampleCount,
      temperature,
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
            pred_len: runtimePredLen,
            model_id: modelId,
            rows: forecastRows,
            dry_run: false,
            sample_count: sampleCount,
            temperature,
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
            <AntInput value={symbol} onChange={setSymbol} placeholder={DEFAULT_SYMBOL} />
          </div>
          <div>
            <label className="field-label">{tx(language, "开始日期", "Start date")}</label>
            <AntDatePicker value={startDate} onChange={setStartDate} />
          </div>
          <div>
            <label className="field-label">{tx(language, "结束日期", "End date")}</label>
            <AntDatePicker value={endDate} onChange={setEndDate} />
          </div>
          <div>
            <label className="field-label">采样数</label>
            <AntSelect
              value={`sc${sampleCount}`}
              onChange={(v) => setSampleCount(parseInt(v.replace("sc", ""), 10))}
              options={[
                { value: "sc8", label: "8 次（快速）" },
                { value: "sc16", label: "16 次" },
                { value: "sc32", label: "32 次" },
              { value: "sc64", label: "64 次（更多采样，更慢）" },
              ]}
              ariaLabel="采样数"
              className="mt-1"
            />
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
              disabled={!datasetMatchesCurrent || data.length === 0}
            >
              {tx(language, "运行预测", "Run Forecast")}
            </Button>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border pt-3 text-xs text-muted-foreground">
          <span>
            {tx(language, "模型", "Model")}: {modelId.replace("NeoQuasar/", "")}
          </span>
          <span>
            {tx(language, "最近", "Lookback")}: {runtimeLookback} {tx(language, "根K线", "bars")}
          </span>
          <span>T = {temperature}</span>
          <span>
            {tx(language, "预测", "Forecast")}: {runtimePredLen} {tx(language, "日", "days")}
          </span>
          <span>
            {tx(language, "采样", "Samples")}: {sampleCount}
          </span>
        </div>
        <details className="mt-3 rounded-lg border border-border bg-muted/30 p-3">
          <summary className="cursor-pointer text-xs font-medium text-muted-foreground select-none">
            {tx(language, "高级选项", "Advanced options")}
          </summary>
          <div className="mt-3 flex flex-wrap items-end gap-4">
            <div>
              <label className="field-label">
                {tx(language, "温度 T（仅本次会话实验）", "Temperature T (session experiment only)")}
              </label>
              <AntSelect
                value={`t${temperature}`}
                onChange={(v) => setTemperature(parseFloat(v.replace("t", "")))}
                options={[
                  { value: "t0.5", label: "0.5（确定性优先）" },
                  { value: "t0.6", label: "0.6" },
                  { value: "t0.8", label: "0.8" },
                  { value: "t1.0", label: "1.0（官方默认）" },
                ]}
                ariaLabel="温度"
                className="mt-1"
              />
            </div>
            <p className="pb-1 text-xs text-muted-foreground">
              {tx(
                language,
                "修改仅影响当前会话的请求，不改变服务端配置。",
                "Changes only affect this session's requests; the server configuration is unchanged."
              )}
            </p>
          </div>
        </details>
        {data.length > 0 && (
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 md:flex md:flex-wrap">
            <Button variant="secondary" onClick={() => handleFetchData(true)} loading={loading}>
              {tx(language, "刷新数据", "Refresh Data")}
            </Button>
            <Button
              variant="secondary"
              onClick={() => handleRunPrediction(true)}
              loading={predLoading}
              disabled={!datasetMatchesCurrent || data.length === 0}
            >
              {tx(language, "重新预测", "Rerun Forecast")}
            </Button>
          </div>
        )}
      </Card>

      {error && <AntAlert type="error" message={error} />}

      {data.length > 0 && !datasetMatchesCurrent && (
        <AntAlert
          type="warning"
          message={tx(language, "当前输入已改变，页面中的行情数据已过期，请重新获取后再预测。", "The inputs changed, so the displayed market data is stale. Reload data before forecasting.")}
        />
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
          <div className="mt-3 rounded-lg border border-blue-100 bg-blue-50/60 px-3 py-2 text-xs text-blue-800">
            {tx(language, `模型实际使用最近 ${Math.min(runtimeLookback, data.length)} 根K线；页面展示 ${data.length} 根。`, `The model uses the latest ${Math.min(runtimeLookback, data.length)} rows; the page displays ${data.length}.`)}
          </div>
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
          {predResult?.probabilistic && (
            <Card className="col-span-1 md:col-span-3">
              <p className="text-sm text-muted-foreground mb-2">{tx(language, "概率预测", "Probabilistic Forecast")}</p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-xs text-muted-foreground">{tx(language, "上涨概率", "Upside Prob.")}</p>
                  <p className="text-lg font-bold">{(predResult.probabilistic.upside_probability * 100).toFixed(0)}%</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">{tx(language, "预测区间", "Forecast Range")}</p>
                  <p className="text-lg font-bold">[{predResult.probabilistic.forecast_range.min.toFixed(2)}, {predResult.probabilistic.forecast_range.max.toFixed(2)}]</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">{tx(language, "均值收盘", "Mean Close")}</p>
                  <p className="text-lg font-bold">{predResult.probabilistic.mean_final_close.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">{tx(language, "波动放大", "Vol. Amplif.")}</p>
                  <p className="text-lg font-bold">{predResult.probabilistic.volatility_amplification.toFixed(2)}x</p>
                </div>
              </div>
            </Card>
          )}
        </div>
      )}

      {/* Data Table */}
      {data.length > 0 && (
        <Card>
          <CardTitle>{tx(language, "历史数据", "Historical Data")} ({data.length} {tx(language, "条", "rows")})</CardTitle>
          <AntTable
            columns={[
              { title: tx(language, "日期", "Date"), dataIndex: "timestamp", key: "date", render: (v: string) => <span className="font-mono text-xs">{String(v).slice(0, 10)}</span>, width: 120 },
              { title: tx(language, "开盘", "Open"), dataIndex: "open", key: "open", render: (v: number) => v.toFixed(2), align: "right", width: 90 },
              { title: tx(language, "最高", "High"), dataIndex: "high", key: "high", render: (v: number) => v.toFixed(2), align: "right", width: 90 },
              { title: tx(language, "最低", "Low"), dataIndex: "low", key: "low", render: (v: number) => v.toFixed(2), align: "right", width: 90 },
              { title: tx(language, "收盘", "Close"), dataIndex: "close", key: "close", render: (v: number) => <span className="font-semibold">{v.toFixed(2)}</span>, align: "right", width: 90 },
              { title: tx(language, "成交量", "Volume"), dataIndex: "volume", key: "volume", render: (v: number) => <span className="text-gray-400">{(v || 0).toLocaleString()}</span>, align: "right", width: 120 },
            ]}
            dataSource={data.slice(-50)}
            rowKey={(r: { timestamp: string }) => `${symbol}-${r.timestamp}`}
            scroll={{ y: 260 }}
            pagination={false}
          />
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
