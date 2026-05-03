"use client";

import { useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ReturnComparisonChart } from "@/components/charts/ReturnComparisonChart";
import { ApiError, api, formatApiError } from "@/lib/api";
import { DEFAULT_MARKET, MARKET_OPTIONS, type Market } from "@/lib/markets";
import { DEFAULT_BATCH_SYMBOLS, normalizeSymbols } from "@/lib/symbols";
import { queryKeys } from "@/lib/queryKeys";
import { useSessionState } from "@/lib/useSessionState";
import type { ForecastRequest, ForecastRow, RankedSignal } from "@/types/api";
const BATCH_CONCURRENCY = 4;
const BATCH_START_DATE = "20250101";
const BATCH_END_DATE = "20260430";

type FailureStage = "data" | "forecast" | "cancelled";

interface BatchFailure {
  symbol: string;
  stage: FailureStage;
  message: string;
  requestId: string | null;
  retryable: boolean;
}

interface BatchProgress {
  total: number;
  completed: number;
  success: number;
  failed: number;
  skipped: number;
  running: string[];
}

interface BatchRunSnapshot {
  results: RankedSignal[];
  failures: BatchFailure[];
  progress: BatchProgress;
}

interface DataOutcome {
  symbol: string;
  rows: ForecastRow[];
}

function createInitialProgress(total = 0): BatchProgress {
  return {
    total,
    completed: 0,
    success: 0,
    failed: 0,
    skipped: 0,
    running: [],
  };
}

function rankResults(results: RankedSignal[]): RankedSignal[] {
  return [...results]
    .sort((a, b) => b.predicted_return - a.predicted_return)
    .map((result, index) => ({ ...result, rank: index + 1 }));
}

function mergeResults(current: RankedSignal[], incoming: RankedSignal[]): RankedSignal[] {
  const bySymbol = new Map<string, RankedSignal>();
  current.forEach((result) => bySymbol.set(result.symbol, result));
  incoming.forEach((result) => bySymbol.set(result.symbol, result));
  return rankResults(Array.from(bySymbol.values()));
}

function toFailure(symbol: string, stage: FailureStage, error: unknown): BatchFailure {
  const requestId = error instanceof ApiError ? error.requestId : null;
  return {
    symbol,
    stage,
    message: formatApiError(error, stage === "data" ? "行情获取失败" : "预测失败"),
    requestId,
    retryable: stage !== "cancelled",
  };
}

async function runWithConcurrency<T, R>(
  items: T[],
  limit: number,
  signal: AbortSignal,
  worker: (item: T) => Promise<R>
): Promise<R[]> {
  const results: R[] = [];
  let nextIndex = 0;

  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (nextIndex < items.length && !signal.aborted) {
      const item = items[nextIndex];
      nextIndex += 1;
      results.push(await worker(item));
    }
  });

  await Promise.allSettled(workers);
  return results;
}

export default function BatchPage() {
  const queryClient = useQueryClient();
  const activeAbortRef = useRef<AbortController | null>(null);
  const [input, setInput] = useSessionState("kronos-batch-input", DEFAULT_BATCH_SYMBOLS);
  const [market, setMarket] = useSessionState<Market>("kronos-batch-market", DEFAULT_MARKET);
  const [predLen, setPredLen] = useSessionState("kronos-batch-pred-len", 5);
  const [results, setResults] = useSessionState<RankedSignal[]>("kronos-batch-results", []);
  const [failures, setFailures] = useSessionState<BatchFailure[]>("kronos-batch-failures", []);
  const [progress, setProgress] = useState<BatchProgress>(createInitialProgress());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useSessionState("kronos-batch-error", "");

  const updateProgress = (symbol: string, status: "start" | "success" | "failed") => {
    setProgress((current) => {
      if (status === "start") {
        return {
          ...current,
          running: Array.from(new Set([...current.running, symbol])),
        };
      }

      return {
        ...current,
        completed: current.completed + 1,
        success: current.success + (status === "success" ? 1 : 0),
        failed: current.failed + (status === "failed" ? 1 : 0),
        running: current.running.filter((item) => item !== symbol),
      };
    });
  };

  const fetchRowsForSymbol = async (
    symbol: string,
    signal: AbortSignal
  ): Promise<DataOutcome | BatchFailure> => {
    updateProgress(symbol, "start");
    try {
      const dataKey = queryKeys.data({
        symbol,
        market,
        startDate: BATCH_START_DATE,
        endDate: BATCH_END_DATE,
      });
      const dataRes = await queryClient.fetchQuery({
        queryKey: dataKey,
        queryFn: () =>
          market === "cn"
            ? api.getData(symbol, BATCH_START_DATE, BATCH_END_DATE, { signal })
            : api.getGlobalData(symbol, market, BATCH_START_DATE, BATCH_END_DATE, { signal }),
      });
      const rows = dataRes.rows || [];
      if (rows.length === 0) {
        throw new Error("该标的没有返回可用 K 线。");
      }
      updateProgress(symbol, "success");
      return { symbol, rows };
    } catch (err) {
      const failure = toFailure(symbol, signal.aborted ? "cancelled" : "data", err);
      updateProgress(symbol, "failed");
      return failure;
    }
  };

  const executeBatch = async (symbols: string[], signal: AbortSignal): Promise<BatchRunSnapshot> => {
    const outcomes = await runWithConcurrency(
      symbols,
      BATCH_CONCURRENCY,
      signal,
      (symbol) => fetchRowsForSymbol(symbol, signal)
    );

    const startedSymbols = new Set(outcomes.map((outcome) => outcome.symbol));
    const skippedFailures: BatchFailure[] = symbols
      .filter((symbol) => !startedSymbols.has(symbol))
      .map((symbol) => ({
        symbol,
        stage: "cancelled",
        message: "任务已取消，未继续发起该标的请求。",
        requestId: null,
        retryable: true,
      }));

    const dataOutcomes = outcomes.filter((outcome): outcome is DataOutcome => "rows" in outcome);
    const dataFailures = outcomes.filter((outcome): outcome is BatchFailure => "message" in outcome);

    setProgress((current) => ({
      ...current,
      skipped: skippedFailures.length,
      failed: current.failed + skippedFailures.length,
      completed: Math.min(current.total, current.completed + skippedFailures.length),
      running: [],
    }));

    if (signal.aborted) {
      return {
        results: [],
        failures: [...dataFailures, ...skippedFailures],
        progress: {
          total: symbols.length,
          completed: outcomes.length + skippedFailures.length,
          success: dataOutcomes.length,
          failed: dataFailures.length + skippedFailures.length,
          skipped: skippedFailures.length,
          running: [],
        },
      };
    }

    if (dataOutcomes.length === 0) {
      return {
        results: [],
        failures: [...dataFailures, ...skippedFailures],
        progress: {
          total: symbols.length,
          completed: symbols.length,
          success: 0,
          failed: dataFailures.length + skippedFailures.length,
          skipped: skippedFailures.length,
          running: [],
        },
      };
    }

    const assets: ForecastRequest[] = dataOutcomes.map((outcome) => ({
      symbol: outcome.symbol,
      pred_len: predLen,
      rows: outcome.rows.slice(-120),
      dry_run: false,
    }));

    let ranked: RankedSignal[] = [];
    let forecastFailures: BatchFailure[] = [];
    try {
      const response = await api.batch(assets, predLen, false, { signal, timeoutMs: 120000 });
      ranked = rankResults(response.rankings || []);
      const returnedSymbols = new Set(ranked.map((item) => item.symbol));
      forecastFailures = dataOutcomes
        .filter((outcome) => !returnedSymbols.has(outcome.symbol))
        .map((outcome) => ({
          symbol: outcome.symbol,
          stage: "forecast",
          message: "后端批量预测未返回该标的结果。",
          requestId: null,
          retryable: true,
        }));
    } catch (err) {
      forecastFailures = dataOutcomes.map((outcome) =>
        toFailure(outcome.symbol, signal.aborted ? "cancelled" : "forecast", err)
      );
    }

    const allFailures = [...dataFailures, ...skippedFailures, ...forecastFailures];
    return {
      results: ranked,
      failures: allFailures,
      progress: {
        total: symbols.length,
        completed: symbols.length,
        success: ranked.length,
        failed: allFailures.length,
        skipped: skippedFailures.length,
        running: [],
      },
    };
  };

  const handleCompare = async (
    forceRefresh = false,
    overrideSymbols?: string[],
    mergeWithCurrent = false
  ) => {
    if (loading) return;
    const symbols = overrideSymbols ? normalizeSymbols(overrideSymbols) : normalizeSymbols(input);
    if (symbols.length === 0) {
      setError("请至少输入一个股票代码。");
      return;
    }
    if (symbols.length > 20) {
      setError("每批最多20个股票代码。");
      return;
    }

    const key = queryKeys.batch({ symbols, market, predLen });
    const cached = forceRefresh ? undefined : queryClient.getQueryData<BatchRunSnapshot>(key);
    if (cached) {
      setResults(mergeWithCurrent ? mergeResults(results, cached.results) : cached.results);
      setFailures(mergeWithCurrent
        ? [...failures.filter((failure) => !symbols.includes(failure.symbol)), ...cached.failures]
        : cached.failures);
      setProgress(cached.progress);
      setError("");
      return;
    }

    const abortController = new AbortController();
    activeAbortRef.current = abortController;
    setLoading(true);
    setError("");
    setProgress(createInitialProgress(symbols.length));
    if (!mergeWithCurrent) {
      setResults([]);
      setFailures([]);
    }

    try {
      if (forceRefresh) {
        await queryClient.invalidateQueries({ queryKey: key });
      }
      const snapshot = await queryClient.fetchQuery({
        queryKey: key,
        queryFn: () => executeBatch(symbols, abortController.signal),
      });

      if (abortController.signal.aborted) {
        queryClient.removeQueries({ queryKey: key, exact: true });
        setFailures((current) => [
          ...current.filter((failure) => !symbols.includes(failure.symbol)),
          ...snapshot.failures,
        ]);
        setProgress(snapshot.progress);
        setError("批量任务已取消，已停止继续发起新请求。");
        return;
      }

      setResults(mergeWithCurrent ? mergeResults(results, snapshot.results) : snapshot.results);
      setFailures(mergeWithCurrent
        ? [...failures.filter((failure) => !symbols.includes(failure.symbol)), ...snapshot.failures]
        : snapshot.failures);
      setProgress(snapshot.progress);
      if (snapshot.results.length === 0 && snapshot.failures.length > 0) {
        setError("本批次没有成功预测的标的，请查看失败列表。");
      }
    } catch (err) {
      if (abortController.signal.aborted) {
        setError("批量任务已取消，已停止继续发起新请求。");
      } else {
        setError(formatApiError(err, "批量对比失败"));
      }
    } finally {
      activeAbortRef.current = null;
      setLoading(false);
    }
  };

  const handleCancel = () => {
    activeAbortRef.current?.abort();
    setProgress((current) => ({ ...current, running: [] }));
  };

  const chartData = useMemo(() => results.map((result) => ({
    name: result.symbol,
    return: +(result.predicted_return * 100).toFixed(2),
    fill: result.predicted_return >= 0 ? "#10B981" : "#EF4444",
  })), [results]);

  const progressPct = progress.total > 0
    ? Math.min(100, Math.round((progress.completed / progress.total) * 100))
    : 0;

  return (
    <div className="page-shell space-y-6">
      <h1 className="page-title">批量对比</h1>

      <Card>
        <CardTitle>多标的对比</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <div className="md:col-span-2">
            <label className="field-label">
              股票代码（逗号分隔）
            </label>
            <input
              type="text"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              className="app-input mt-1 font-mono"
              placeholder={`例如 ${DEFAULT_BATCH_SYMBOLS}`}
            />
          </div>
          <div>
            <label className="field-label">市场</label>
            <select
              value={market}
              onChange={(event) => setMarket(event.target.value as Market)}
              className="app-input mt-1"
            >
              {MARKET_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="field-label">
              预测天数
            </label>
            <input
              type="number"
              value={predLen}
              onChange={(event) => setPredLen(Math.max(1, +event.target.value))}
              min={1}
              max={60}
              className="app-input mt-1"
            />
          </div>
        </div>
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3 md:flex md:flex-wrap">
          <Button onClick={() => handleCompare(false)} loading={loading} className="w-full md:w-auto">
            开始对比
          </Button>
          {results.length > 0 && (
            <Button
              variant="secondary"
              onClick={() => handleCompare(true)}
              disabled={loading}
              className="w-full md:w-auto"
            >
              刷新对比
            </Button>
          )}
          {loading && (
            <Button variant="danger" onClick={handleCancel} className="w-full md:w-auto">
              取消任务
            </Button>
          )}
        </div>
      </Card>

      {(loading || progress.total > 0) && (
        <Card>
          <CardTitle>执行进度</CardTitle>
          <div className="space-y-3">
            <div className="h-2 bg-muted rounded-full overflow-hidden">
              <div className="h-full bg-accent transition-all" style={{ width: `${progressPct}%` }} />
            </div>
            <div className="grid grid-cols-2 md:grid-cols-6 gap-3 text-sm">
              <div>
                <p className="text-muted-foreground">总数</p>
                <p className="font-bold text-foreground">{progress.total}</p>
              </div>
              <div>
                <p className="text-muted-foreground">已完成</p>
                <p className="font-bold text-foreground">{progress.completed}</p>
              </div>
              <div>
                <p className="text-muted-foreground">成功</p>
                <p className="font-bold text-green-600">{progress.success}</p>
              </div>
              <div>
                <p className="text-muted-foreground">失败</p>
                <p className="font-bold text-red-600">{progress.failed}</p>
              </div>
              <div>
                <p className="text-muted-foreground">跳过</p>
                <p className="font-bold text-amber-600">{progress.skipped}</p>
              </div>
              <div>
                <p className="text-muted-foreground">处理中</p>
                <p className="font-mono text-xs text-foreground truncate">
                  {progress.running.length ? progress.running.join(", ") : "-"}
                </p>
              </div>
            </div>
          </div>
        </Card>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      {results.length > 0 && (
        <>
          <Card>
            <CardTitle>预测收益率对比</CardTitle>
            <ReturnComparisonChart data={chartData} />
          </Card>

          <Card>
            <CardTitle>排名</CardTitle>
            <div className="table-scroll">
              <table className="min-w-[42rem] w-full text-sm">
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
                  {results.map((result) => {
                    const returnPct = result.predicted_return * 100;
                    const isBest = result.rank === 1;
                    const isWorst = result.rank === results.length;
                    return (
                      <tr
                        key={result.symbol}
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
                            {result.rank}
                          </span>
                        </td>
                        <td className="py-2 font-mono font-bold text-white">
                          {result.symbol}
                        </td>
                        <td className="py-2 text-right">
                          {result.last_close.toFixed(2)}
                        </td>
                        <td className="py-2 text-right font-semibold">
                          {result.predicted_close.toFixed(2)}
                        </td>
                        <td
                          className={`py-2 text-right font-semibold ${
                            returnPct >= 0 ? "text-green-400" : "text-red-400"
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

      {failures.length > 0 && (
        <Card>
          <CardTitle>失败项</CardTitle>
          <div className="table-scroll">
            <table className="min-w-[44rem] w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 text-gray-400">
                  <th className="py-2 text-left">代码</th>
                  <th className="py-2 text-left">阶段</th>
                  <th className="py-2 text-left">错误</th>
                  <th className="py-2 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {failures.map((failure) => (
                  <tr key={`${failure.symbol}-${failure.stage}`} className="border-b border-gray-800">
                    <td className="py-2 font-mono font-bold text-white">{failure.symbol}</td>
                    <td className="py-2 text-gray-300">{failure.stage}</td>
                    <td className="py-2 text-gray-400">
                      {failure.message}
                      {failure.requestId && (
                        <span className="ml-2 font-mono text-xs">request_id={failure.requestId}</span>
                      )}
                    </td>
                    <td className="py-2 text-right">
                      {failure.retryable && (
                        <Button
                          variant="ghost"
                          disabled={loading}
                          onClick={() => handleCompare(true, [failure.symbol], true)}
                        >
                          重试
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {results.length === 0 && failures.length === 0 && !loading && !error && (
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
