"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ReturnComparisonChart } from "@/components/charts/ReturnComparisonChart";
import { ApiError, api, formatApiError } from "@/lib/api";
import { DEFAULT_MARKET, MARKET_OPTIONS, getMarketLabel, type Market } from "@/lib/markets";
import { DEFAULT_BATCH_SYMBOLS, normalizeSymbols } from "@/lib/symbols";
import { queryKeys } from "@/lib/queryKeys";
import { downloadTextFile, makeDatedFilename, toCsv } from "@/lib/exportUtils";
import { useSessionState } from "@/lib/useSessionState";
import { useAppStore } from "@/stores/app";
import type { ForecastRequest, ForecastRow, RankedSignal } from "@/types/api";

const BATCH_CONCURRENCY = 4;
const BATCH_START_DATE = "20250101";
const BATCH_END_DATE = "20260430";

type PoolPreset = "custom" | "a-core" | "watchlist";
type SortKey = "rank" | "predicted_return" | "risk" | "symbol";

type BatchFailure = {
  symbol: string;
  stage: "data" | "forecast";
  message: string;
  requestId: string | null;
  retryable: boolean;
};

interface BatchProgress {
  total: number;
  completed: number;
  success: number;
  failed: number;
  skipped: number;
  running: string[];
}

type BatchRunSnapshot = { results: RankedSignal[]; failures: BatchFailure[]; progress: BatchProgress };

function createInitialProgress(total = 0): BatchProgress {
  return { total, completed: 0, success: 0, failed: 0, skipped: 0, running: [] };
}

async function runWithConcurrency<T, R>(items: T[], limit: number, signal: AbortSignal, worker: (item: T) => Promise<R>): Promise<R[]> {
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

const POOL_PRESETS: Array<{ value: PoolPreset; label: string; symbols: string }> = [
  { value: "custom", label: "自定义", symbols: DEFAULT_BATCH_SYMBOLS },
  { value: "a-core", label: "常用A股组合", symbols: "600036,000858,000001,601318,600519,300750" },
  { value: "watchlist", label: "自选股", symbols: "" },
];

function riskLabel(value: number): string {
  if (value < -0.03) return "高风险";
  if (Math.abs(value) > 0.05) return "中风险";
  return "低风险";
}

function toFailure(symbol: string, stage: BatchFailure["stage"], err: unknown): BatchFailure {
  return {
    symbol,
    stage,
    message: formatApiError(err, stage === "data" ? "行情获取失败" : "预测失败"),
    requestId: err instanceof ApiError ? err.requestId : null,
    retryable: true,
  };
}

export default function BatchPage() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const activeAbortRef = useRef<AbortController | null>(null);
  const { watchlist, addToWatchlist } = useAppStore();
  const [poolPreset, setPoolPreset] = useSessionState<PoolPreset>("kronos-batch-pool-preset", "custom");
  const [input, setInput] = useSessionState("kronos-batch-input", DEFAULT_BATCH_SYMBOLS);
  const [market, setMarket] = useSessionState<Market>("kronos-batch-market", DEFAULT_MARKET);
  const [predLen, setPredLen] = useSessionState("kronos-batch-pred-len", 5);
  const [sortKey, setSortKey] = useSessionState<SortKey>("kronos-batch-sort-key", "rank");
  const [results, setResults] = useSessionState<RankedSignal[]>("kronos-batch-results", []);
  const [failures, setFailures] = useSessionState<BatchFailure[]>("kronos-batch-failures", []);
  const [progress, setProgress] = useState<BatchProgress>(createInitialProgress());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useSessionState("kronos-batch-error", "");

  useEffect(() => {
    const symbols = searchParams.get("symbols");
    if (symbols) {
      setPoolPreset("custom");
      setInput(symbols);
    }
  }, [searchParams, setInput, setPoolPreset]);

  const selectedSymbols = useMemo(() => normalizeSymbols(input), [input]);
  const chartData = useMemo(() => results.map((item) => ({
    name: item.symbol,
    return: +(item.predicted_return * 100).toFixed(2),
    fill: item.predicted_return >= 0 ? "#10B981" : "#EF4444",
  })), [results]);

  const sortedResults = useMemo(() => {
    const ranked = [...results];
    if (sortKey === "predicted_return") ranked.sort((a, b) => b.predicted_return - a.predicted_return);
    if (sortKey === "risk") ranked.sort((a, b) => String(a.risk_label || "").localeCompare(String(b.risk_label || "")));
    if (sortKey === "symbol") ranked.sort((a, b) => a.symbol.localeCompare(b.symbol));
    if (sortKey === "rank") ranked.sort((a, b) => a.rank - b.rank);
    return ranked;
  }, [results, sortKey]);

  const applyPoolPreset = (value: PoolPreset) => {
    setPoolPreset(value);
    if (value === "watchlist") {
      setInput(watchlist.map((item) => item.symbol).join(","));
      return;
    }
    const preset = POOL_PRESETS.find((item) => item.value === value);
    if (preset && preset.symbols) setInput(preset.symbols);
  };

  const buildSnapshot = async (symbols: string[], signal: AbortSignal): Promise<BatchRunSnapshot> => {
    const failuresNext: BatchFailure[] = [];
    setProgress(createInitialProgress(symbols.length));
    const dataOutcomes = await runWithConcurrency(symbols, BATCH_CONCURRENCY, signal, async (symbol) => {
      try {
        setProgress((current) => ({ ...current, running: Array.from(new Set([...current.running, symbol])) }));
        const dataKey = queryKeys.data({ symbol, market, startDate: BATCH_START_DATE, endDate: BATCH_END_DATE, adjust: "qfq" });
        const dataRes = await queryClient.fetchQuery({
          queryKey: dataKey,
          queryFn: () => market === "cn"
            ? api.getData(symbol, BATCH_START_DATE, BATCH_END_DATE, "qfq", { signal })
            : api.getGlobalData(symbol, market, BATCH_START_DATE, BATCH_END_DATE, { signal }),
        });
        const rows = dataRes.rows || [];
        if (rows.length === 0) throw new Error("没有可用行情数据");
        setProgress((current) => ({ ...current, completed: current.completed + 1, success: current.success + 1, running: current.running.filter((item) => item !== symbol) }));
        return { symbol, rows };
      } catch (err) {
        failuresNext.push(toFailure(symbol, "data", err));
        setProgress((current) => ({ ...current, completed: current.completed + 1, failed: current.failed + 1, running: current.running.filter((item) => item !== symbol) }));
        return null;
      }
    });

    const assets: ForecastRequest[] = dataOutcomes
      .filter((item): item is { symbol: string; rows: ForecastRow[] } => Boolean(item))
      .map((item) => ({ symbol: item.symbol, pred_len: predLen, rows: item.rows.slice(-120), dry_run: false }));
    if (assets.length === 0) return { results: [], failures: failuresNext, progress: { total: symbols.length, completed: symbols.length, success: 0, failed: failuresNext.length, skipped: Math.max(0, symbols.length - dataOutcomes.length), running: [] } };

    try {
      const response = await api.batch(assets, predLen, false, { signal, timeoutMs: 120000 });
      const returnedSymbols = new Set(response.rankings.map((item) => item.symbol));
      assets.forEach((asset) => {
        if (!returnedSymbols.has(asset.symbol)) {
          failuresNext.push({ symbol: asset.symbol, stage: "forecast", message: "后端批量预测未返回该标的结果。", requestId: null, retryable: true });
        }
      });
      const ranked = [...response.rankings]
        .sort((a, b) => b.predicted_return - a.predicted_return)
        .map((item, index) => ({ ...item, rank: index + 1, market, risk_label: item.risk_label || riskLabel(item.predicted_return) }));
      return { results: ranked, failures: failuresNext, progress: { total: symbols.length, completed: symbols.length, success: ranked.length, failed: failuresNext.length, skipped: 0, running: [] } };
    } catch (err) {
      assets.forEach((asset) => failuresNext.push(toFailure(asset.symbol, "forecast", err)));
      return { results: [], failures: failuresNext, progress: { total: symbols.length, completed: symbols.length, success: 0, failed: failuresNext.length, skipped: 0, running: [] } };
    }
  };

  const handleCompare = async (forceRefresh = false, overrideSymbols?: string[]) => {
    const symbols = normalizeSymbols(overrideSymbols || input);
    if (symbols.length === 0) { setError("请至少输入一个股票代码。"); return; }
    const key = queryKeys.batch({ symbols, market, predLen });
    const cached = forceRefresh ? undefined : queryClient.getQueryData<BatchRunSnapshot>(key);
    if (cached) {
      setResults(cached.results);
      setFailures(cached.failures);
      setProgress(cached.progress);
      setError("");
      return;
    }
    const abortController = new AbortController();
    activeAbortRef.current = abortController;
    setLoading(true);
    setError("");
    try {
      if (forceRefresh) await queryClient.invalidateQueries({ queryKey: key });
      const snapshot = await queryClient.fetchQuery({
        queryKey: key,
        queryFn: () => buildSnapshot(symbols, abortController.signal),
      });
      if (abortController.signal.aborted) {
        queryClient.removeQueries({ queryKey: key, exact: true });
        setError("任务已取消");
        return;
      }
      setResults(snapshot.results);
      setFailures(snapshot.failures);
      setProgress(snapshot.progress);
      if (snapshot.results.length === 0 && snapshot.failures.length > 0) setError("本批次没有成功预测的标的，请查看失败列表。");
    } catch (err) {
      setError(abortController.signal.aborted ? "任务已取消" : formatApiError(err, "批量对比失败"));
    } finally {
      activeAbortRef.current = null;
      setLoading(false);
    }
  };

  const handleCancel = () => {
    activeAbortRef.current?.abort();
    setProgress((current) => ({ ...current, running: [] }));
  };

  const retryFailed = () => {
    const retrySymbols = failures.filter((item) => item.retryable).map((item) => item.symbol);
    void handleCompare(true, retrySymbols);
  };

  const downloadBatchCsv = () => {
    const csv = toCsv(
      ["rank", "symbol", "market", "last_close", "predicted_close", "predicted_return", "risk_label"],
      sortedResults.map((item) => [item.rank, item.symbol, item.market || market, item.last_close, item.predicted_close, item.predicted_return, item.risk_label || riskLabel(item.predicted_return)])
    );
    downloadTextFile(makeDatedFilename("batch", selectedSymbols), csv);
  };

  return (
    <div className="page-shell space-y-6">
      <h1 className="page-title">批量对比</h1>
      <Card>
        <CardTitle subtitle="支持常用股票池、自选股、排序、导出和失败重试。">多标的对比</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-5">
          <div><label className="field-label">股票池</label><select value={poolPreset} onChange={(e) => applyPoolPreset(e.target.value as PoolPreset)} className="app-input mt-1">{POOL_PRESETS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>
          <div className="md:col-span-2"><label className="field-label">股票代码（逗号分隔）</label><input value={input} onChange={(e) => { setPoolPreset("custom"); setInput(e.target.value); }} className="app-input mt-1 font-mono" placeholder={DEFAULT_BATCH_SYMBOLS} /></div>
          <div><label className="field-label">市场</label><select value={market} onChange={(e) => setMarket(e.target.value as Market)} className="app-input mt-1">{MARKET_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>
          <div><label className="field-label">预测天数</label><input type="number" value={predLen} onChange={(e) => setPredLen(Math.max(1, Number(e.target.value)))} className="app-input mt-1" min={1} max={60} /></div>
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row md:flex-wrap"><Button onClick={() => handleCompare(false)} loading={loading}>开始对比</Button><Button variant="secondary" onClick={() => handleCompare(true)} disabled={loading}>刷新对比</Button>{loading && <Button variant="danger" onClick={handleCancel}>取消任务</Button>}<Button variant="secondary" onClick={downloadBatchCsv} disabled={results.length === 0}>导出 CSV</Button><Button variant="secondary" onClick={retryFailed} disabled={failures.length === 0 || loading}>重试失败项</Button><Link className="btn-secondary flex h-12 items-center justify-center rounded-xl px-6 text-sm font-medium" href={`/backtest?symbols=${selectedSymbols.join(",")}`}>组合回测</Link></div>
      </Card>

      {(loading || progress.total > 0) && <Card><CardTitle>执行进度</CardTitle><div className="grid grid-cols-2 gap-3 md:grid-cols-6"><div>total {progress.total}</div><div>completed {progress.completed}</div><div>success {progress.success}</div><div>failed {progress.failed}</div><div>skipped {progress.skipped}</div><div>running {progress.running.join(", ") || "-"}</div></div></Card>}
      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">{error}</div>}
      {results.length > 0 && <><Card><CardTitle>预测收益率对比</CardTitle><ReturnComparisonChart data={chartData} /></Card><Card><CardTitle action={<select value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)} className="app-input h-10"><option value="rank">按排名</option><option value="predicted_return">按收益率</option><option value="risk">按风险</option><option value="symbol">按代码</option></select>}>排名</CardTitle><div className="table-scroll"><table className="min-w-[44rem] w-full text-sm md:min-w-[56rem]"><thead><tr className="border-b border-gray-700 text-gray-400"><th className="py-2 text-left">排名</th><th className="py-2 text-left">代码</th><th className="py-2 text-left">市场</th><th className="py-2 text-right">最新收盘</th><th className="py-2 text-right">预测收盘</th><th className="py-2 text-right">预测收益率</th><th className="py-2 text-left">风险</th><th className="py-2 text-right">操作</th></tr></thead><tbody>{sortedResults.map((result) => <tr key={result.symbol} className="border-b border-gray-800 hover:bg-surface-overlay"><td className="py-2">{result.rank}</td><td className="py-2 font-mono font-bold text-white">{result.symbol}</td><td className="py-2">{getMarketLabel(result.market || market)}</td><td className="py-2 text-right">{result.last_close.toFixed(2)}</td><td className="py-2 text-right">{result.predicted_close.toFixed(2)}</td><td className={result.predicted_return >= 0 ? "py-2 text-right text-accent-green" : "py-2 text-right text-accent-red"}>{(result.predicted_return * 100).toFixed(2)}%</td><td className="py-2">{result.risk_label || riskLabel(result.predicted_return)}</td><td className="py-2 text-right"><div className="flex justify-end gap-2"><button className="rounded bg-surface-overlay px-2 py-1 text-xs" onClick={() => addToWatchlist({ symbol: result.symbol, market: (result.market as Market) || market, addedAt: new Date().toISOString() })}>加入自选</button><Link className="rounded bg-surface-overlay px-2 py-1 text-xs" href={`/forecast?symbol=${result.symbol}&market=${result.market || market}`}>预测</Link><Link className="rounded bg-primary/20 px-2 py-1 text-xs text-primary-light" href={`/analysis?symbol=${result.symbol}&market=${result.market || market}`}>分析</Link></div></td></tr>)}</tbody></table></div></Card></>}
      {failures.length > 0 && <Card><CardTitle>失败项</CardTitle><div className="space-y-2">{failures.map((failure) => <div key={`${failure.symbol}-${failure.stage}`} className="rounded-lg border border-border p-3 text-sm"><span className="font-mono font-bold">{failure.symbol}</span> · {failure.stage} · {failure.message}{failure.requestId ? ` request_id=${failure.requestId}` : ""}</div>)}</div></Card>}
      {results.length === 0 && failures.length === 0 && !loading && !error && <Card><div className="py-12 text-center text-gray-500"><p className="mb-2 text-lg">批量标的对比</p><p className="text-sm">输入多个股票代码，对比预测收益率。</p></div></Card>}
    </div>
  );
}
