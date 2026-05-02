"use client";

import { FormEvent, Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { api, formatApiError } from "@/lib/api";
import { normalizeMarket, type Market } from "@/lib/markets";
import { DEFAULT_SYMBOL, DEFAULT_SYMBOL_NAME, normalizeSymbol } from "@/lib/symbols";
import { queryKeys } from "@/lib/queryKeys";
import { useSessionState } from "@/lib/useSessionState";
import type { AgentAnalyzeResponse } from "@/types/api";

const LOADING_STEPS = ["理解问题", "获取行情", "调用预测模型", "网页检索", "汇总报告"];
const EXAMPLES = [
  `帮我看看${DEFAULT_SYMBOL_NAME}现在能不能买`,
  "比较招商银行和贵州茅台的中短期风险",
  "分析一下 AAPL 和 NVDA 最近走势",
];

function getConfidenceColor(value: number): string {
  const pct = value * 100;
  if (pct > 70) return "text-green-700";
  if (pct >= 40) return "text-amber-600";
  return "text-red-700";
}

function getConfidenceBg(value: number): string {
  const pct = value * 100;
  if (pct > 70) return "bg-green-500";
  if (pct >= 40) return "bg-yellow-500";
  return "bg-red-500";
}

function RecommendationBadge({ rec }: { rec: string }) {
  const lower = rec.toLowerCase();
  let bg = "bg-muted text-muted-foreground border-border";
  if (lower.includes("buy") || rec.includes("买")) {
    bg = "bg-green-50 text-green-700 border-green-200";
  } else if (lower.includes("sell") || rec.includes("卖")) {
    bg = "bg-red-50 text-red-700 border-red-200";
  } else if (lower.includes("hold") || rec.includes("持")) {
    bg = "bg-amber-50 text-amber-700 border-amber-200";
  } else if (rec.includes("拒绝") || rec.includes("失败")) {
    bg = "bg-red-50 text-red-700 border-red-200";
  }

  return (
    <span className={`px-3 py-1 rounded-full text-sm font-semibold border ${bg}`}>
      {rec}
    </span>
  );
}

function RiskBadge({ level }: { level: string }) {
  const lower = level.toLowerCase();
  let bg = "bg-muted text-muted-foreground";
  if (lower === "low" || level === "低") bg = "bg-green-50 text-green-700";
  else if (lower === "medium" || level === "中") bg = "bg-amber-50 text-amber-700";
  else if (lower === "high" || level === "高") bg = "bg-red-50 text-red-700";

  return <span className={`px-2 py-0.5 rounded text-xs font-medium ${bg}`}>{level}</span>;
}

function StepList({ result, loading }: { result: AgentAnalyzeResponse | null; loading: boolean }) {
  const steps = result?.steps || LOADING_STEPS.map((name, index) => ({
    name,
    status: loading && index === 0 ? "running" : loading ? "pending" : "pending",
    summary: "",
    elapsed_ms: 0,
  }));

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
      {steps.map((step) => {
        const active = step.status === "completed";
        const failed = ["failed", "blocked"].includes(step.status);
        return (
          <div
            key={step.name}
            className={`border rounded-lg px-3 py-2 ${
              failed
                ? "border-red-200 bg-red-50"
                : active
                  ? "border-green-200 bg-green-50"
                  : "border-border bg-muted"
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium text-foreground">{step.name}</span>
              <span className="text-xs text-muted-foreground">{step.status}</span>
            </div>
            {step.summary && <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{step.summary}</p>}
          </div>
        );
      })}
    </div>
  );
}

function ReportSection({ title, value }: { title: string; value?: string }) {
  if (!value) return null;
  return (
    <div className="border-b border-border last:border-b-0 py-4 first:pt-0 last:pb-0">
      <h3 className="text-sm font-semibold text-foreground mb-2">{title}</h3>
      <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">{value}</p>
    </div>
  );
}

function AnalysisContent() {
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const symbolParam = searchParams.get("symbol");
  const marketParam = searchParams.get("market");
  const normalizedMarketParam: Market | undefined = marketParam ? normalizeMarket(marketParam) : undefined;
  const normalizedSymbolParam = symbolParam ? normalizeSymbol(symbolParam) : undefined;
  const initialQuestion = symbolParam
    ? `分析 ${normalizedSymbolParam || symbolParam} 的短期走势和风险`
    : `帮我看看${DEFAULT_SYMBOL_NAME}现在能不能买`;
  const [question, setQuestion] = useSessionState(
    "kronos-analysis-question",
    initialQuestion,
    { preferInitial: Boolean(symbolParam) }
  );
  const [loading, setLoading] = useState(false);
  const inFlightRef = useRef(false);
  const [error, setError] = useSessionState("kronos-analysis-error", "");
  const [result, setResult] = useSessionState<AgentAnalyzeResponse | null>("kronos-analysis-result", null);

  const handleAnalyze = async (overrideQuestion?: string, forceRefresh = false) => {
    if (inFlightRef.current) return;
    const prompt = (overrideQuestion || question).trim();
    if (!prompt) return;
    const key = queryKeys.agent({
      question: prompt,
      symbol: normalizedSymbolParam,
      market: normalizedMarketParam,
    });
    const cached = forceRefresh ? undefined : queryClient.getQueryData<AgentAnalyzeResponse>(key);
    if (cached) {
      setResult(cached);
      setError("");
      return;
    }

    inFlightRef.current = true;
    setLoading(true);
    setError("");
    try {
      if (forceRefresh) {
        await queryClient.invalidateQueries({ queryKey: key });
      }
      const res = await queryClient.fetchQuery({
        queryKey: key,
        queryFn: ({ signal }) =>
          api.agentAnalyze({
            question: prompt,
            symbol: normalizedSymbolParam,
            market: normalizedMarketParam,
            context: {
              entry: "web-analysis",
              default_symbol: DEFAULT_SYMBOL,
            },
          }, { signal }),
      });
      setResult(res);
    } catch (e: any) {
      setError(formatApiError(e, "分析请求失败"));
    } finally {
      inFlightRef.current = false;
      setLoading(false);
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    handleAnalyze();
  };

  useEffect(() => {
    if (symbolParam) {
      handleAnalyze(initialQuestion);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const report = result?.report;

  return (
    <div className="page-shell space-y-6">
      <h1 className="page-title">AI 分析</h1>

      <Card>
        <form onSubmit={handleSubmit} className="space-y-4">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={4}
            className="app-input min-h-36 resize-none px-4 py-3"
            placeholder={`例如：帮我看看${DEFAULT_SYMBOL_NAME}现在能不能买`}
          />
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex min-w-0 flex-wrap gap-2">
              {EXAMPLES.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setQuestion(item)}
                  className="min-h-11 rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-accent hover:text-foreground"
                >
                  {item}
                </button>
              ))}
            </div>
            <Button type="submit" loading={loading} className="w-full lg:w-auto">
              开始分析
            </Button>
            {result && (
              <Button
                type="button"
                variant="secondary"
                loading={loading}
                onClick={() => handleAnalyze(undefined, true)}
                className="w-full lg:w-auto"
              >
                重新分析
              </Button>
            )}
          </div>
        </form>
      </Card>

      {(loading || result) && (
        <Card>
          <CardTitle>执行状态</CardTitle>
          <StepList result={result} loading={loading} />
        </Card>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          {error}
        </div>
      )}

      {result && (
        <>
          <Card>
            <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-3 mb-2">
                  <CardTitle>{result.symbols.length ? result.symbols.join(" / ") : "待澄清"}</CardTitle>
                  {result.market && (
                    <span className="px-2 py-0.5 text-xs rounded bg-muted text-muted-foreground">
                      {result.market}
                    </span>
                  )}
                </div>
                {typeof result.current_price === "number" && (
                  <p className="text-2xl font-bold text-foreground">
                    {result.current_price.toFixed(2)}
                  </p>
                )}
              </div>
              <RecommendationBadge rec={result.recommendation} />
            </div>

            <p className="text-muted-foreground leading-relaxed">{report?.conclusion}</p>

            <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-3">
              <div>
                <p className="text-sm text-muted-foreground mb-1">置信度</p>
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${getConfidenceBg(result.confidence)}`}
                      style={{ width: `${(result.confidence || 0) * 100}%` }}
                    />
                  </div>
                  <span className={`text-sm font-bold ${getConfidenceColor(result.confidence)}`}>
                    {(result.confidence * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
              <div>
                <p className="text-sm text-muted-foreground mb-1">风险等级</p>
                <RiskBadge level={result.risk_level} />
              </div>
              <div>
                <p className="text-sm text-muted-foreground mb-1">时间</p>
                <p className="text-sm text-foreground font-mono">{result.timestamp.slice(0, 19)}</p>
              </div>
            </div>
          </Card>

          <Card>
            <CardTitle>研究报告</CardTitle>
            <ReportSection title="短期预测" value={report?.short_term_prediction} />
            <ReportSection title="技术面" value={report?.technical} />
            <ReportSection title="基本面" value={report?.fundamentals} />
            <ReportSection title="风险指标" value={report?.risk} />
            <ReportSection title="关键不确定性" value={report?.uncertainties} />
            <ReportSection title="非投资建议声明" value={report?.disclaimer} />
          </Card>

          {result.tool_calls.length > 0 && (
            <Card>
              <CardTitle>工具调用</CardTitle>
              <div className="space-y-3">
                {result.tool_calls.map((call) => (
                  <div
                    key={`${call.name}-${call.status}-${call.elapsed_ms}-${call.summary.slice(0, 24)}`}
                    className="flex flex-col gap-1 border border-border rounded-lg px-3 py-2 bg-muted"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="break-all text-sm font-mono text-foreground">{call.name}</span>
                      <span className="text-xs text-muted-foreground">{call.status}</span>
                    </div>
                    <p className="break-words text-sm text-muted-foreground">{call.summary}</p>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {result.risk_metrics && (
            <Card>
              <CardTitle>风险指标</CardTitle>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                {Object.entries(result.risk_metrics).map(([key, value]) => (
                  <div key={key}>
                    <p className="text-sm text-muted-foreground">{key.replace(/_/g, " ")}</p>
                    <p className="text-lg font-bold text-foreground">
                      {typeof value === "number" ? value.toFixed(4) : String(value)}
                    </p>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {result.kronos_prediction?.forecast?.length ? (
            <Card>
              <CardTitle>
                Kronos 预测
                <span className="text-sm font-normal text-muted-foreground ml-3">
                  {result.kronos_prediction.model} · {result.kronos_prediction.prediction_days} days
                </span>
              </CardTitle>
              <div className="table-scroll max-h-80 overflow-y-auto">
                <table className="min-w-[36rem] w-full text-sm">
                  <thead className="sticky top-0 bg-muted">
                    <tr className="border-b border-border text-muted-foreground">
                      <th className="py-2 text-left">日期</th>
                      <th className="py-2 text-right">开盘</th>
                      <th className="py-2 text-right">最高</th>
                      <th className="py-2 text-right">最低</th>
                      <th className="py-2 text-right">收盘</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.kronos_prediction.forecast.map((row) => (
                      <tr key={`${row.timestamp}-${row.close}`} className="border-b border-border text-foreground hover:bg-muted">
                        <td className="py-1.5 font-mono text-xs">{String(row.timestamp).slice(0, 10)}</td>
                        <td className="py-1.5 text-right">{row.open.toFixed(2)}</td>
                        <td className="py-1.5 text-right">{row.high.toFixed(2)}</td>
                        <td className="py-1.5 text-right">{row.low.toFixed(2)}</td>
                        <td className="py-1.5 text-right font-semibold">{row.close.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ) : null}
        </>
      )}

      {!result && !error && !loading && (
        <Card>
          <div className="text-center py-12 text-muted-foreground">
            <p className="text-lg mb-2">输入一个自然语言问题</p>
            <p className="text-sm">例如：帮我看看招商银行现在能不能买。</p>
          </div>
        </Card>
      )}
    </div>
  );
}

export default function AnalysisPage() {
  return (
    <Suspense fallback={<div className="p-12 text-center text-muted-foreground">加载中...</div>}>
      <AnalysisContent />
    </Suspense>
  );
}
