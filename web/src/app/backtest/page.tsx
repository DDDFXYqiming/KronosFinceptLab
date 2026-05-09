"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { BacktestEquityChart } from "@/components/charts/BacktestEquityChart";
import { api, formatApiError } from "@/lib/api";
import { downloadTextFile, makeDatedFilename, toCsv, validateDateRange } from "@/lib/exportUtils";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";
import { DEFAULT_BACKTEST_SYMBOLS, normalizeSymbols } from "@/lib/symbols";
import { queryKeys } from "@/lib/queryKeys";
import { useSessionState } from "@/lib/useSessionState";
import type { BacktestReportResponse, BacktestResponse } from "@/types/api";

const CSV_HEADERS = "date,equity,return,selected";

export default function BacktestPage() {
  const queryClient = useQueryClient();
  const [symbols, setSymbols] = useSessionState("kronos-backtest-symbols", DEFAULT_BACKTEST_SYMBOLS);
  const [startDate, setStartDate] = useSessionState("kronos-backtest-start-date", "20250101");
  const [endDate, setEndDate] = useSessionState("kronos-backtest-end-date", "20260430");
  const [topK, setTopK] = useSessionState("kronos-backtest-top-k", 1);
  const [predLen, setPredLen] = useSessionState("kronos-backtest-pred-len", 5);
  const [windowSize, setWindowSize] = useSessionState("kronos-backtest-window-size", 60);
  const [step, setStep] = useSessionState("kronos-backtest-step", 5);
  const [initialEquity, setInitialEquity] = useSessionState("kronos-backtest-initial-equity", 100000);
  const [benchmark, setBenchmark] = useSessionState("kronos-backtest-benchmark", "000300");
  const [feeBps, setFeeBps] = useSessionState("kronos-backtest-fee-bps", 1);
  const [slippageBps, setSlippageBps] = useSessionState("kronos-backtest-slippage-bps", 1);
  const [result, setResult] = useSessionState<BacktestResponse | null>("kronos-backtest-result", null);
  const [report, setReport] = useSessionState<BacktestReportResponse | null>("kronos-backtest-report", null);
  const [loading, setLoading] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [error, setError] = useSessionState("kronos-backtest-error", "");

  const requestPayload = () => ({
    symbols: normalizeSymbols(symbols),
    start_date: startDate,
    end_date: endDate,
    top_k: topK,
    pred_len: predLen,
    window_size: windowSize,
    step,
    initial_equity: initialEquity,
    benchmark: benchmark.trim() || undefined,
    fee_bps: feeBps,
    slippage_bps: slippageBps,
    dry_run: false,
  });

  const handleBacktest = async (forceRefresh = false) => {
    const symbolList = normalizeSymbols(symbols);
    if (symbolList.length === 0) {
      setError("请至少输入一个股票代码。");
      return;
    }
    const dateError = validateDateRange(startDate, endDate);
    if (dateError) {
      setError(dateError);
      return;
    }
    const key = queryKeys.backtest({
      symbols: symbolList,
      startDate,
      endDate,
      topK,
      predLen,
      windowSize,
      step,
      initialEquity,
      benchmark,
    });
    const cached = forceRefresh ? undefined : queryClient.getQueryData<BacktestResponse>(key);
    if (cached) {
      setResult(cached);
      setError("");
      return;
    }

    setLoading(true);
    setError("");
    setReport(null);
    try {
      if (forceRefresh) {
        await queryClient.invalidateQueries({ queryKey: key });
      }
      const res = await queryClient.fetchQuery({
        queryKey: key,
        queryFn: ({ signal }) => api.backtest(requestPayload(), { signal }),
      });
      setResult(res);
    } catch (e: any) {
      setError(formatApiError(e, "回测失败"));
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateReport = async () => {
    setReportLoading(true);
    setError("");
    try {
      const res = await api.backtestReport({ ...requestPayload(), strategy_name: "Kronos Ranking Strategy" });
      setReport(res);
      downloadTextFile(res.filename, res.html, "text/html;charset=utf-8");
    } catch (e: any) {
      setError(formatApiError(e, "报告生成失败"));
    } finally {
      setReportLoading(false);
    }
  };

  const downloadBacktestCsv = () => {
    if (!result) return;
    const content = toCsv(
      CSV_HEADERS.split(","),
      result.equity_curve.map((point) => [
        point.date,
        point.equity,
        point.return,
        point.selected.join("|"),
      ])
    );
    downloadTextFile(makeDatedFilename("backtest", result.symbols, startDate, endDate), content);
  };

  const latestHolding = result?.equity_curve[result.equity_curve.length - 1]?.selected || [];

  return (
    <div className="page-shell space-y-6">
      <h1 className="page-title">策略回测</h1>

      <Card>
        <CardTitle subtitle="参数与 CLI/API 保持一致，可导出 CSV/HTML 报告。">策略配置</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div>
            <label className="field-label">股票代码（逗号分隔）</label>
            <input type="text" value={symbols} onChange={(e) => setSymbols(e.target.value)} className="app-input mt-1" />
          </div>
          <div>
            <label className="field-label">开始日期</label>
            <input type="text" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="app-input mt-1 font-mono" />
          </div>
          <div>
            <label className="field-label">结束日期</label>
            <input type="text" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="app-input mt-1 font-mono" />
          </div>
          <div>
            <label className="field-label">Top K</label>
            <input type="number" value={topK} onChange={(e) => setTopK(Number(e.target.value))} min={1} className="app-input mt-1" />
          </div>
          <div>
            <label className="field-label">预测长度 predLen</label>
            <input type="number" value={predLen} onChange={(e) => setPredLen(Number(e.target.value))} min={1} max={60} className="app-input mt-1" />
          </div>
          <div>
            <label className="field-label">回看窗口 windowSize</label>
            <input type="number" value={windowSize} onChange={(e) => setWindowSize(Number(e.target.value))} min={10} max={250} className="app-input mt-1" />
          </div>
          <div>
            <label className="field-label">调仓步长 step</label>
            <input type="number" value={step} onChange={(e) => setStep(Number(e.target.value))} min={1} className="app-input mt-1" />
          </div>
          <div>
            <label className="field-label">初始权益 initialEquity</label>
            <input type="number" value={initialEquity} onChange={(e) => setInitialEquity(Number(e.target.value))} min={1} className="app-input mt-1" />
          </div>
          <div>
            <label className="field-label">基准 benchmark</label>
            <input type="text" value={benchmark} onChange={(e) => setBenchmark(e.target.value)} className="app-input mt-1 font-mono" />
          </div>
          <div>
            <label className="field-label">手续费 feeBps</label>
            <input type="number" value={feeBps} onChange={(e) => setFeeBps(Number(e.target.value))} min={0} className="app-input mt-1" />
          </div>
          <div>
            <label className="field-label">滑点 slippageBps</label>
            <input type="number" value={slippageBps} onChange={(e) => setSlippageBps(Number(e.target.value))} min={0} className="app-input mt-1" />
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row">
          <Button onClick={() => handleBacktest(false)} loading={loading} className="w-full md:w-auto">运行回测</Button>
          <Button variant="secondary" onClick={() => handleBacktest(true)} loading={loading} className="w-full md:w-auto">刷新回测</Button>
          <Button variant="secondary" onClick={downloadBacktestCsv} disabled={!result} className="w-full md:w-auto">导出 CSV</Button>
          <Button variant="secondary" onClick={handleGenerateReport} loading={reportLoading} disabled={!result} className="w-full md:w-auto">生成 HTML 报告</Button>
        </div>
      </Card>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">{error}</div>}

      {result && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
            <Card><p className="text-sm text-muted-foreground">总收益率</p><p className={`text-2xl font-bold ${result.metrics.total_return >= 0 ? "text-accent-green" : "text-accent-red"}`}>{formatPercent(result.metrics.total_return)}</p></Card>
            <Card><p className="text-sm text-muted-foreground">年化收益</p><p className="text-2xl font-bold">{formatPercent(result.metrics.annualized_return)}</p></Card>
            <Card><p className="text-sm text-muted-foreground">夏普比率</p><p className="text-2xl font-bold">{formatNumber(result.metrics.sharpe_ratio, 4)}</p></Card>
            <Card><p className="text-sm text-muted-foreground">最大回撤</p><p className="text-2xl font-bold text-accent-red">{formatPercent(result.metrics.max_drawdown)}</p></Card>
            <Card><p className="text-sm text-muted-foreground">最新权益</p><p className="text-2xl font-bold">{formatCurrency(result.equity_curve.at(-1)?.equity || initialEquity)}</p></Card>
          </div>

          <Card>
            <CardTitle subtitle={`初始权益 ${formatCurrency(initialEquity)}；交易成本 ${(feeBps + slippageBps).toFixed(2)} bps/边。`}>权益曲线</CardTitle>
            <BacktestEquityChart equityCurve={result.equity_curve} />
          </Card>

          <Card>
            <CardTitle>持仓明细</CardTitle>
            <div className="table-scroll max-h-96 overflow-y-auto">
              <table className="min-w-[44rem] w-full text-sm">
                <thead className="sticky top-0 bg-surface-raised text-muted-foreground">
                  <tr><th className="py-2 text-left">日期</th><th className="py-2 text-right">权益</th><th className="py-2 text-right">阶段收益</th><th className="py-2 text-left">持仓</th></tr>
                </thead>
                <tbody>
                  {result.equity_curve.slice(-80).map((point) => (
                    <tr key={point.date} className="border-b border-gray-800 hover:bg-surface-overlay">
                      <td className="py-2 font-mono text-xs">{String(point.date).slice(0, 10)}</td>
                      <td className="py-2 text-right">{formatNumber(point.equity, 2)}</td>
                      <td className={`py-2 text-right ${point.return >= 0 ? "text-accent-green" : "text-accent-red"}`}>{formatPercent(point.return)}</td>
                      <td className="py-2 font-mono text-xs">{point.selected.join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">最新持仓：{latestHolding.join(", ") || "暂无"}</p>
          </Card>

          {report && (
            <Card>
              <CardTitle>HTML 报告已生成</CardTitle>
              <p className="text-sm text-muted-foreground">{report.filename}</p>
            </Card>
          )}
          <p className="text-center text-xs text-gray-500">提示：{result.metadata.warning}</p>
        </>
      )}
    </div>
  );
}
