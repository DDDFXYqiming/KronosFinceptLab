"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/Card";
import { SectionLabel } from "@/components/ui/SectionLabel";
import { Button } from "@/components/ui/Button";
import { ReturnComparisonChart } from "@/components/charts/ReturnComparisonChart";
import { ApiError, api, formatApiError } from "@/lib/api";
import { DEFAULT_MODEL_ID, SUPPORTED_MODEL_IDS } from "@/lib/defaults";
import { DEFAULT_MARKET, getMarketLabel, getMarketOptions, type Market } from "@/lib/markets";
import { DEFAULT_BATCH_SYMBOLS, normalizeSymbols } from "@/lib/symbols";
import { queryKeys } from "@/lib/queryKeys";
import { downloadTextFile, makeDatedFilename, toCsv } from "@/lib/exportUtils";
import { useSessionState } from "@/lib/useSessionState";
import { useAppStore } from "@/stores/app";
import type { BatchJobResult, ForecastRequest, ForecastRow, JobStatusResponse, RankedSignal } from "@/types/api";

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

function BatchContent() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const activeAbortRef = useRef<AbortController | null>(null);
  const { watchlist, addToWatchlist, preferences, setPreferences } = useAppStore();
  const marketOptions = getMarketOptions(preferences.language);
  const [poolPreset, setPoolPreset] = useSessionState<PoolPreset>("kronos-batch-pool-preset", "custom");
  const [input, setInput] = useSessionState("kronos-batch-input", DEFAULT_BATCH_SYMBOLS);
  const [market, setMarket] = useSessionState<Market>("kronos-batch-market", DEFAULT_MARKET);
  const [predLen, setPredLen] = useSessionState("kronos-batch-pred-len", 5);
  const [modelId, setModelId] = useSessionState("kronos-batch-model-id", preferences.defaultModelId || DEFAULT_MODEL_ID);
  const [availableModelIds, setAvailableModelIds] = useState<string[]>([...SUPPORTED_MODEL_IDS]);
  const [sortKey, setSortKey] = useSessionState<SortKey>("kronos-batch-sort-key", "rank");
  const [results, setResults] = useSessionState<RankedSignal[]>("kronos-batch-results", []);
  const [failures, setFailures] = useSessionState<BatchFailure[]>("kronos-batch-failures", []);
  const [progress, setProgress] = useState<BatchProgress>(createInitialProgress());
  const [loading, setLoading] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobHistory, setJobHistory] = useState<JobStatusResponse[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [error, setError] = useSessionState("kronos-batch-error", "");

  useEffect(() => {
    const symbols = searchParams.get("symbols");
    if (symbols) {
      setPoolPreset("custom");
      setInput(symbols);
    }
  }, [searchParams, setInput, setPoolPreset]);

  useEffect(() => {
    void queryClient.fetchQuery({
      queryKey: queryKeys.health(),
      queryFn: ({ signal }) => api.health({ signal }),
      staleTime: 60000,
    }).then((health) => {
      if (health.supported_model_ids?.length) setAvailableModelIds(health.supported_model_ids);
      if (!modelId && health.default_model_id) setModelId(health.default_model_id);
    }).catch(() => undefined);
  }, [modelId, queryClient, setModelId]);

  const refreshJobHistory = async () => {
    setHistoryLoading(true);
    try {
      const response = await api.listJobs({ limit: 8, kind: "batch", timeoutMs: 15000 });
      setJobHistory(response.jobs);
    } catch {
      setJobHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    void refreshJobHistory();
  }, []);

  const selectedSymbols = useMemo(() => normalizeSymbols(input), [input]);
  const modelOptions = useMemo(() => Array.from(new Set([...availableModelIds, preferences.defaultModelId, modelId].filter(Boolean))), [availableModelIds, modelId, preferences.defaultModelId]);
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
    setProgress(createInitialProgress(symbols.length));
    const submitted = await api.submitBatchJob({
      symbols,
      market,
      start_date: BATCH_START_DATE,
      end_date: BATCH_END_DATE,
      adjust: "qfq",
      pred_len: predLen,
      model_id: modelId,
      dry_run: false,
    }, { signal, timeoutMs: 30000 });
    setActiveJobId(submitted.job_id);

    let lastStatus: JobStatusResponse<BatchJobResult> | null = null;
    while (!signal.aborted) {
      const status = await api.getJob<BatchJobResult>(submitted.job_id, { signal, timeoutMs: 30000 });
      lastStatus = status;
      const jobProgress = status.result?.progress;
      if (jobProgress) {
        setProgress({ ...jobProgress, skipped: 0 });
      } else {
        const completedSteps = status.steps.filter((step) => step.status === "completed").length;
        setProgress((current) => ({ ...current, total: symbols.length, completed: Math.min(current.completed, symbols.length), skipped: 0, running: status.status === "running" ? [`${completedSteps}/${status.steps.length}`] : [] }));
      }
      if (["completed", "failed", "cancelled"].includes(status.status)) break;
      await new Promise((resolve) => window.setTimeout(resolve, 1200));
    }

    if (signal.aborted) return { results: [], failures: [], progress: { total: symbols.length, completed: 0, success: 0, failed: 0, skipped: 0, running: [] } };
    if (!lastStatus) throw new Error("批量任务没有返回状态。");
    if (lastStatus.status === "cancelled") throw new Error("任务已取消");
    if (lastStatus.status === "failed") throw new Error(lastStatus.error || "批量任务失败");
    const result = lastStatus.result;
    if (!result) throw new Error("批量任务没有返回结果。");

    const ranked = [...result.rankings]
      .sort((a, b) => b.predicted_return - a.predicted_return)
      .map((item, index) => ({ ...item, rank: index + 1, market: item.market || market, risk_label: item.risk_label || riskLabel(item.predicted_return) }));
    const progressNext = { ...result.progress, skipped: 0 };
    const failuresNext = (result.failures || []).map((failure) => ({ ...failure, requestId: failure.requestId ?? null }));
    return { results: ranked, failures: failuresNext, progress: progressNext };
  };

  const handleCompare = async (forceRefresh = false, overrideSymbols?: string[]) => {
    const symbols = normalizeSymbols(overrideSymbols || input);
    if (symbols.length === 0) { setError("请至少输入一个股票代码。"); return; }
    const key = queryKeys.batch({ symbols, market, predLen, modelId });
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
      setActiveJobId(null);
      setLoading(false);
    }
  };

  const handleCancel = () => {
    if (activeJobId) void api.cancelJob(activeJobId).catch(() => undefined);
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
    downloadTextFile(makeDatedFilename("batch", selectedSymbols, BATCH_START_DATE, BATCH_END_DATE), csv);
  };

  return (
    <div className="page-shell space-y-6">
      <SectionLabel>批量对比</SectionLabel>
      <h1 className="page-title">批量对比</h1>
      <Card>
        <CardTitle subtitle="支持常用股票池、自选股、排序、导出和失败重试。">多标的对比</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-6">
          <div><label className="field-label">股票池</label><select value={poolPreset} onChange={(e) => applyPoolPreset(e.target.value as PoolPreset)} className="app-input mt-1">{POOL_PRESETS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>
          <div className="md:col-span-2"><label className="field-label">股票代码（逗号分隔）</label><input value={input} onChange={(e) => { setPoolPreset("custom"); setInput(e.target.value); }} className="app-input mt-1 font-mono" placeholder={DEFAULT_BATCH_SYMBOLS} /></div>
          <div><label className="field-label">市场</label><select value={market} onChange={(e) => setMarket(e.target.value as Market)} className="app-input mt-1">{marketOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>
          <div><label className="field-label">预测天数</label><input type="number" value={predLen} onChange={(e) => setPredLen(Math.max(1, Number(e.target.value)))} className="app-input mt-1" min={1} max={60} /></div>
          <div><label className="field-label">模型</label><select value={modelId} onChange={(e) => { setModelId(e.target.value); setPreferences({ defaultModelId: e.target.value }); }} className="app-input mt-1">{modelOptions.map((id) => <option key={id} value={id}>{id.replace("NeoQuasar/", "")}</option>)}</select></div>
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row md:flex-wrap"><Button onClick={() => handleCompare(false)} loading={loading}>开始对比</Button><Button variant="secondary" onClick={() => handleCompare(true)} disabled={loading}>刷新对比</Button>{loading && <Button variant="danger" onClick={handleCancel}>取消任务</Button>}<Button variant="secondary" onClick={downloadBatchCsv} disabled={results.length === 0}>导出 CSV</Button><Button variant="secondary" onClick={retryFailed} disabled={failures.length === 0 || loading}>重试失败项</Button><Link className="btn-secondary flex h-12 items-center justify-center rounded-xl px-6 text-sm font-medium" href={`/backtest?symbols=${selectedSymbols.join(",")}`}>组合回测</Link></div>
      </Card>

      {(loading || progress.total > 0) && <Card><CardTitle>执行进度</CardTitle><div className="grid grid-cols-2 gap-3 md:grid-cols-6"><div>total {progress.total}</div><div>completed {progress.completed}</div><div>success {progress.success}</div><div>failed {progress.failed}</div><div>skipped {progress.skipped}</div><div>running {progress.running.join(", ") || "-"}</div></div></Card>}
      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">{error}</div>}
      {results.length > 0 && <><Card><CardTitle>预测收益率对比</CardTitle><ReturnComparisonChart data={chartData} /></Card><Card><CardTitle action={<select value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)} className="app-input h-10"><option value="rank">按排名</option><option value="predicted_return">按收益率</option><option value="risk">按风险</option><option value="symbol">按代码</option></select>}>排名</CardTitle><div className="table-scroll"><table className="min-w-[44rem] w-full text-sm md:min-w-[56rem]"><thead><tr className="border-b border-gray-700 text-gray-400"><th className="py-2 text-left">排名</th><th className="py-2 text-left">代码</th><th className="py-2 text-left">市场</th><th className="py-2 text-right">最新收盘</th><th className="py-2 text-right">预测收盘</th><th className="py-2 text-right">预测收益率</th><th className="py-2 text-left">风险</th><th className="py-2 text-right">操作</th></tr></thead><tbody>{sortedResults.map((result) => <tr key={result.symbol} className="border-b border-gray-800 hover:bg-surface-overlay"><td className="py-2">{result.rank}</td><td className="py-2 font-mono font-bold text-white">{result.symbol}</td><td className="py-2">{getMarketLabel(result.market || market, preferences.language)}</td><td className="py-2 text-right">{result.last_close.toFixed(2)}</td><td className="py-2 text-right">{result.predicted_close.toFixed(2)}</td><td className={result.predicted_return >= 0 ? "py-2 text-right text-accent-green" : "py-2 text-right text-accent-red"}>{(result.predicted_return * 100).toFixed(2)}%</td><td className="py-2">{result.risk_label || riskLabel(result.predicted_return)}</td><td className="py-2 text-right"><div className="flex justify-end gap-2"><button className="rounded bg-surface-overlay px-2 py-1 text-xs" onClick={() => addToWatchlist({ symbol: result.symbol, market: (result.market as Market) || market, addedAt: new Date().toISOString() })}>加入自选</button><Link className="rounded bg-surface-overlay px-2 py-1 text-xs" href={`/forecast?symbol=${result.symbol}&market=${result.market || market}`}>预测</Link><Link className="rounded bg-primary/20 px-2 py-1 text-xs text-primary-light" href={`/analysis?symbol=${result.symbol}&market=${result.market || market}`}>分析</Link></div></td></tr>)}</tbody></table></div></Card></>}
      {failures.length > 0 && <Card><CardTitle>失败项</CardTitle><div className="space-y-2">{failures.map((failure) => <div key={`${failure.symbol}-${failure.stage}`} className="rounded-lg border border-border p-3 text-sm"><span className="font-mono font-bold">{failure.symbol}</span> · {failure.stage} · {failure.message}{failure.requestId ? ` request_id=${failure.requestId}` : ""}</div>)}</div></Card>}
      <Card>
        <CardTitle action={<Button variant="secondary" onClick={refreshJobHistory} loading={historyLoading}>刷新</Button>}>批量任务历史</CardTitle>
        <div className="space-y-2 text-sm">
          {jobHistory.length === 0 && <p className="text-gray-500">暂无持久化批量任务记录。</p>}
          {jobHistory.map((job) => (
            <div key={job.job_id} className="flex flex-col gap-1 rounded-lg border border-border p-3 md:flex-row md:items-center md:justify-between">
              <div><span className="font-mono text-xs text-gray-400">{job.job_id.slice(0, 12)}</span> · {job.status} · {new Date(job.updated_at * 1000).toLocaleString()}</div>
              <Link className="text-sm text-accent-blue" href={`/batch?job=${job.job_id}`}>查看任务</Link>
            </div>
          ))}
        </div>
      </Card>
      {results.length === 0 && failures.length === 0 && !loading && !error && <Card><div className="py-12 text-center text-gray-500"><p className="mb-2 text-lg">批量标的对比</p><p className="text-sm">输入多个股票代码，对比预测收益率。</p></div></Card>}
    </div>
  );
}
export default function BatchPage() {
  return (
    <Suspense fallback={<div className="p-12 text-center text-gray-500">加载中...</div>}>
      <BatchContent />
    </Suspense>
  );
}
