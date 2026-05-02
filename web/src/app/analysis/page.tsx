"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { api, AgentAnalyzeResponse, formatApiError } from "@/lib/api";
import { DEFAULT_SYMBOL, DEFAULT_SYMBOL_NAME, type Market } from "@/lib/defaults";
import { queryKeys } from "@/lib/queryKeys";
import { useSessionState } from "@/lib/useSessionState";

const LOADING_STEPS = ["理解问题", "获取行情", "调用预测模型", "汇总报告"];
const EXAMPLES = [
  `帮我看看${DEFAULT_SYMBOL_NAME}现在能不能买`,
  "比较招商银行和贵州茅台的中短期风险",
  "分析一下 AAPL 和 NVDA 最近走势",
];

function getConfidenceColor(value: number): string {
  const pct = value * 100;
  if (pct > 70) return "text-green-400";
  if (pct >= 40) return "text-yellow-400";
  return "text-red-400";
}

function getConfidenceBg(value: number): string {
  const pct = value * 100;
  if (pct > 70) return "bg-green-500";
  if (pct >= 40) return "bg-yellow-500";
  return "bg-red-500";
}

function RecommendationBadge({ rec }: { rec: string }) {
  const lower = rec.toLowerCase();
  let bg = "bg-gray-700 text-gray-300 border-gray-600";
  if (lower.includes("buy") || rec.includes("买")) {
    bg = "bg-green-900/40 text-green-400 border-green-700";
  } else if (lower.includes("sell") || rec.includes("卖")) {
    bg = "bg-red-900/40 text-red-400 border-red-700";
  } else if (lower.includes("hold") || rec.includes("持")) {
    bg = "bg-yellow-900/40 text-yellow-400 border-yellow-700";
  } else if (rec.includes("拒绝") || rec.includes("失败")) {
    bg = "bg-red-900/40 text-red-300 border-red-700";
  }

  return (
    <span className={`px-3 py-1 rounded-full text-sm font-semibold border ${bg}`}>
      {rec}
    </span>
  );
}

function RiskBadge({ level }: { level: string }) {
  const lower = level.toLowerCase();
  let bg = "bg-gray-700 text-gray-300";
  if (lower === "low" || level === "低") bg = "bg-green-900/40 text-green-400";
  else if (lower === "medium" || level === "中") bg = "bg-yellow-900/40 text-yellow-400";
  else if (lower === "high" || level === "高") bg = "bg-red-900/40 text-red-400";

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
    <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
      {steps.map((step) => {
        const active = step.status === "completed";
        const failed = ["failed", "blocked"].includes(step.status);
        return (
          <div
            key={step.name}
            className={`border rounded-lg px-3 py-2 ${
              failed
                ? "border-red-700 bg-red-900/20"
                : active
                  ? "border-green-700 bg-green-900/20"
                  : "border-gray-700 bg-surface-overlay"
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium text-white">{step.name}</span>
              <span className="text-xs text-gray-400">{step.status}</span>
            </div>
            {step.summary && <p className="text-xs text-gray-400 mt-1 line-clamp-2">{step.summary}</p>}
          </div>
        );
      })}
    </div>
  );
}

function ReportSection({ title, value }: { title: string; value?: string }) {
  if (!value) return null;
  return (
    <div className="border-b border-gray-800 last:border-b-0 py-4 first:pt-0 last:pb-0">
      <h3 className="text-sm font-semibold text-gray-200 mb-2">{title}</h3>
      <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">{value}</p>
    </div>
  );
}

function AnalysisContent() {
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const symbolParam = searchParams.get("symbol");
  const marketParam = searchParams.get("market") as Market | null;
  const initialQuestion = symbolParam
    ? `分析 ${symbolParam} 的短期走势和风险`
    : `帮我看看${DEFAULT_SYMBOL_NAME}现在能不能买`;
  const [question, setQuestion] = useSessionState(
    "kronos-analysis-question",
    initialQuestion,
    { preferInitial: Boolean(symbolParam) }
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useSessionState("kronos-analysis-error", "");
  const [result, setResult] = useSessionState<AgentAnalyzeResponse | null>("kronos-analysis-result", null);

  const handleAnalyze = async (overrideQuestion?: string, forceRefresh = false) => {
    const prompt = (overrideQuestion || question).trim();
    if (!prompt) return;
    const key = queryKeys.agent({
      question: prompt,
      symbol: symbolParam || undefined,
      market: marketParam || undefined,
    });
    const cached = forceRefresh ? undefined : queryClient.getQueryData<AgentAnalyzeResponse>(key);
    if (cached) {
      setResult(cached);
      setError("");
      return;
    }

    setLoading(true);
    setError("");
    try {
      if (forceRefresh) {
        await queryClient.invalidateQueries({ queryKey: key });
      }
      const res = await queryClient.fetchQuery({
        queryKey: key,
        queryFn: () =>
          api.agentAnalyze({
            question: prompt,
            symbol: symbolParam || undefined,
            market: marketParam || undefined,
            context: {
              entry: "web-analysis",
              default_symbol: DEFAULT_SYMBOL,
            },
          }),
      });
      setResult(res);
    } catch (e: any) {
      setError(formatApiError(e, "分析请求失败"));
    } finally {
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
    <div className="space-y-6">
      <h1 className="text-3xl font-display">AI 分析</h1>

      <Card>
        <form onSubmit={handleSubmit} className="space-y-4">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={4}
            className="w-full px-4 py-3 bg-surface-overlay border border-gray-700 rounded-lg text-white resize-none focus:outline-none focus:border-accent"
            placeholder={`例如：帮我看看${DEFAULT_SYMBOL_NAME}现在能不能买`}
          />
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setQuestion(item)}
                  className="px-3 py-1.5 rounded-lg border border-gray-700 text-xs text-gray-300 hover:border-accent hover:text-white transition-colors"
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
        <div className="p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-300">
          {error}
        </div>
      )}

      {result && (
        <>
          <Card>
            <div className="flex items-start justify-between gap-4 mb-4">
              <div>
                <div className="flex flex-wrap items-center gap-3 mb-2">
                  <CardTitle>{result.symbols.length ? result.symbols.join(" / ") : "待澄清"}</CardTitle>
                  {result.market && (
                    <span className="px-2 py-0.5 text-xs rounded bg-gray-700 text-gray-300">
                      {result.market}
                    </span>
                  )}
                </div>
                {typeof result.current_price === "number" && (
                  <p className="text-2xl font-bold text-white">
                    {result.current_price.toFixed(2)}
                  </p>
                )}
              </div>
              <RecommendationBadge rec={result.recommendation} />
            </div>

            <p className="text-gray-300 leading-relaxed">{report?.conclusion}</p>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-5">
              <div>
                <p className="text-sm text-gray-400 mb-1">置信度</p>
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
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
                <p className="text-sm text-gray-400 mb-1">风险等级</p>
                <RiskBadge level={result.risk_level} />
              </div>
              <div>
                <p className="text-sm text-gray-400 mb-1">时间</p>
                <p className="text-sm text-gray-300 font-mono">{result.timestamp.slice(0, 19)}</p>
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
                {result.tool_calls.map((call, index) => (
                  <div
                    key={`${call.name}-${index}`}
                    className="flex flex-col gap-1 border border-gray-800 rounded-lg px-3 py-2 bg-surface-overlay"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm font-mono text-white">{call.name}</span>
                      <span className="text-xs text-gray-400">{call.status}</span>
                    </div>
                    <p className="text-sm text-gray-300">{call.summary}</p>
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
                    <p className="text-sm text-gray-400">{key.replace(/_/g, " ")}</p>
                    <p className="text-lg font-bold text-white">
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
                <span className="text-sm font-normal text-gray-400 ml-3">
                  {result.kronos_prediction.model} · {result.kronos_prediction.prediction_days} days
                </span>
              </CardTitle>
              <div className="overflow-x-auto max-h-80 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-surface-raised">
                    <tr className="border-b border-gray-700 text-gray-400">
                      <th className="py-2 text-left">日期</th>
                      <th className="py-2 text-right">开盘</th>
                      <th className="py-2 text-right">最高</th>
                      <th className="py-2 text-right">最低</th>
                      <th className="py-2 text-right">收盘</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.kronos_prediction.forecast.map((row) => (
                      <tr key={`${row.timestamp}-${row.close}`} className="border-b border-gray-800 hover:bg-surface-overlay">
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
          <div className="text-center py-12 text-gray-500">
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
    <Suspense fallback={<div className="p-12 text-center text-gray-500">加载中...</div>}>
      <AnalysisContent />
    </Suspense>
  );
}
