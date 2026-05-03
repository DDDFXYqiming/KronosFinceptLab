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
import type { AgentAnalyzeResponse, AgentAssetResult } from "@/types/api";

const LOADING_STEPS = [
  "理解问题",
  "范围/安全检查",
  "解析标的",
  "获取行情",
  "调用 Kronos",
  "网页检索",
  "DeepSeek 汇总",
  "生成报告",
];
const EXAMPLES = [
  `帮我看看${DEFAULT_SYMBOL_NAME}现在能不能买`,
  "比较招商银行和贵州茅台的中短期风险",
  "分析一下 AAPL 和 NVDA 最近走势",
];

const DEFAULT_QUESTION = `帮我看看${DEFAULT_SYMBOL_NAME}现在能不能买`;

function formatElapsedMs(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "-";
  if (value < 1000) return `${Math.round(value)}ms`;
  return `${(value / 1000).toFixed(1)}s`;
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    completed: "完成",
    running: "进行中",
    pending: "等待",
    failed: "失败",
    blocked: "阻断",
    skipped: "跳过",
    fallback: "降级",
    needs_clarification: "需澄清",
  };
  return labels[status] || status;
}

function buildEvidenceSummary(result: AgentAnalyzeResponse): string {
  const completed = result.tool_calls
    .filter((call) => ["completed", "fallback", "skipped"].includes(call.status))
    .map((call) => {
      const symbol = call.metadata?.symbol ? ` ${call.metadata.symbol}` : "";
      const requestId = call.metadata?.request_id ? ` request_id=${call.metadata.request_id}` : "";
      return `${call.name}${symbol}：${call.summary}${requestId}`;
    });
  return completed.length
    ? completed.join("\n")
    : "本轮没有可用工具依据；请查看执行状态和错误信息。";
}

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
    <div className="space-y-3">
      {steps.map((step, index) => {
        const active = step.status === "completed";
        const failed = ["failed", "blocked"].includes(step.status);
        const running = step.status === "running";
        return (
          <div
            key={step.name}
            className={`grid grid-cols-[2rem_1fr] gap-3 rounded-lg border px-3 py-3 ${
              failed
                ? "border-red-200 bg-red-50"
                : active || running
                  ? "border-green-200 bg-green-50"
                  : "border-border bg-muted"
            }`}
          >
            <div
              className={`mt-0.5 flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold ${
                failed
                  ? "bg-red-100 text-red-700"
                  : active || running
                    ? "bg-green-100 text-green-700"
                    : "bg-background text-muted-foreground"
              }`}
            >
              {index + 1}
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-semibold text-foreground">{step.name}</span>
                <span className="font-mono text-xs text-muted-foreground">
                  {statusLabel(step.status)} · {formatElapsedMs(step.elapsed_ms)}
                </span>
              </div>
              {step.summary && <p className="mt-1 break-words text-xs leading-relaxed text-muted-foreground">{step.summary}</p>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ToolCallList({ result }: { result: AgentAnalyzeResponse }) {
  return (
    <div className="space-y-3">
      {result.tool_calls.map((call) => {
        const symbol = call.metadata?.symbol ? String(call.metadata.symbol) : "";
        const market = call.metadata?.market ? String(call.metadata.market) : "";
        const requestId = call.metadata?.request_id ? String(call.metadata.request_id) : "";
        return (
          <details
            key={`${call.name}-${call.status}-${call.elapsed_ms}-${call.summary.slice(0, 24)}`}
            className="rounded-lg border border-border bg-muted px-3 py-2"
          >
            <summary className="cursor-pointer list-none">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="break-all font-mono text-sm font-semibold text-foreground">{call.name}</span>
                    <span className="rounded bg-background px-2 py-0.5 text-xs text-muted-foreground">{statusLabel(call.status)}</span>
                    {symbol && <span className="rounded bg-background px-2 py-0.5 font-mono text-xs text-muted-foreground">{symbol}</span>}
                    {market && <span className="rounded bg-background px-2 py-0.5 text-xs text-muted-foreground">{market}</span>}
                  </div>
                  <p className="mt-1 break-words text-sm text-muted-foreground">{call.summary}</p>
                </div>
                <div className="shrink-0 text-xs text-muted-foreground">
                  <span className="font-mono">{formatElapsedMs(call.elapsed_ms)}</span>
                </div>
              </div>
            </summary>
            <div className="mt-3 rounded-md border border-border bg-background p-3">
              <div className="grid grid-cols-1 gap-2 text-xs text-muted-foreground md:grid-cols-2">
                <p><span className="font-semibold text-foreground">symbol：</span>{symbol || "-"}</p>
                <p><span className="font-semibold text-foreground">market：</span>{market || "-"}</p>
                <p><span className="font-semibold text-foreground">request_id：</span><span className="font-mono">{requestId || "-"}</span></p>
                <p><span className="font-semibold text-foreground">elapsed：</span>{formatElapsedMs(call.elapsed_ms)}</p>
              </div>
              <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded bg-surface-raised p-3 text-xs text-muted-foreground">
                {JSON.stringify(call.metadata || {}, null, 2)}
              </pre>
            </div>
          </details>
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

function getAssetResults(result: AgentAnalyzeResponse): AgentAssetResult[] {
  if (result.asset_results?.length) return result.asset_results;
  if (!result.symbol) return [];
  return [
    {
      symbol: result.symbol,
      market: result.market || "",
      name: null,
      report: result.report,
      final_report: result.final_report,
      recommendation: result.recommendation,
      confidence: result.confidence,
      risk_level: result.risk_level,
      current_price: result.current_price,
      risk_metrics: result.risk_metrics,
      kronos_prediction: result.kronos_prediction,
      tool_status: {},
    },
  ];
}

function ForecastTable({ asset }: { asset: AgentAssetResult }) {
  const forecast = asset.kronos_prediction?.forecast || [];
  if (!forecast.length) {
    return asset.kronos_prediction_error ? (
      <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700">
        {asset.kronos_prediction_error}
      </p>
    ) : null;
  }

  return (
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
          {forecast.map((row) => (
            <tr key={`${asset.symbol}-${row.timestamp}-${row.close}`} className="border-b border-border text-foreground hover:bg-muted">
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
  );
}

function AssetAnalysisCard({ asset }: { asset: AgentAssetResult }) {
  const report = asset.report;
  return (
    <Card>
      <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-3">
            <CardTitle>{asset.name ? `${asset.name} ${asset.symbol}` : asset.symbol}</CardTitle>
            {asset.market && (
              <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                {asset.market}
              </span>
            )}
            {asset.data_points ? (
              <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                {asset.data_points} 根K线
              </span>
            ) : null}
          </div>
          {typeof asset.current_price === "number" && (
            <p className="text-2xl font-bold text-foreground">{asset.current_price.toFixed(2)}</p>
          )}
        </div>
        <RecommendationBadge rec={asset.recommendation} />
      </div>

      <div className="mb-5 grid grid-cols-1 gap-4 md:grid-cols-3">
        <div>
          <p className="mb-1 text-sm text-muted-foreground">置信度</p>
          <div className="flex items-center gap-2">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
              <div
                className={`h-full rounded-full transition-all ${getConfidenceBg(asset.confidence)}`}
                style={{ width: `${(asset.confidence || 0) * 100}%` }}
              />
            </div>
            <span className={`text-sm font-bold ${getConfidenceColor(asset.confidence)}`}>
              {(asset.confidence * 100).toFixed(1)}%
            </span>
          </div>
        </div>
        <div>
          <p className="mb-1 text-sm text-muted-foreground">风险等级</p>
          <RiskBadge level={asset.risk_level} />
        </div>
        <div>
          <p className="mb-1 text-sm text-muted-foreground">模型</p>
          <p className="truncate text-sm font-mono text-foreground">
            {asset.kronos_prediction?.model || "未返回"}
          </p>
        </div>
      </div>

      <div className="mb-5">
        <ReportSection title="结论" value={report?.conclusion} />
        <ReportSection title="短期预测" value={report?.short_term_prediction} />
        <ReportSection title="技术面" value={report?.technical} />
        <ReportSection title="基本面" value={report?.fundamentals} />
        <ReportSection title="风险指标" value={report?.risk} />
        <ReportSection title="关键不确定性" value={report?.uncertainties} />
      </div>

      {asset.risk_metrics && (
        <div className="mb-5 grid grid-cols-2 gap-4 md:grid-cols-5">
          {Object.entries(asset.risk_metrics).map(([key, value]) => (
            <div key={`${asset.symbol}-${key}`}>
              <p className="text-sm text-muted-foreground">{key.replace(/_/g, " ")}</p>
              <p className="text-lg font-bold text-foreground">
                {typeof value === "number" ? value.toFixed(4) : String(value)}
              </p>
            </div>
          ))}
        </div>
      )}

      <ForecastTable asset={asset} />
    </Card>
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
    : DEFAULT_QUESTION;
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

  const handleNewChat = () => {
    queryClient.removeQueries({ queryKey: [...queryKeys.all, "agent"] });
    setQuestion(DEFAULT_QUESTION);
    setResult(null);
    setError("");
  };

  useEffect(() => {
    if (symbolParam) {
      handleAnalyze(initialQuestion);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const report = result?.report;
  const assetResults = result ? getAssetResults(result) : [];

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
            <Button
              type="button"
              variant="secondary"
              disabled={loading}
              onClick={handleNewChat}
              className="w-full lg:w-auto"
            >
              新建对话/清空本轮
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
          <CardTitle>Agent 执行时间线</CardTitle>
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
            <CardTitle>汇总结论</CardTitle>
            <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-3 mb-2">
                  <CardTitle>{result.symbols.length ? result.symbols.join(" / ") : "待澄清"}</CardTitle>
                  <span className="px-2 py-0.5 text-xs rounded bg-muted text-muted-foreground">
                    {assetResults.length} 个标的
                  </span>
                </div>
                <p className="text-sm text-muted-foreground">
                  多标的请求按标的拆分展示，顶部仅保留整体比较结论。
                </p>
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
            <CardTitle>汇总研究报告</CardTitle>
            <ReportSection title="结论" value={report?.conclusion} />
            <ReportSection title="依据" value={buildEvidenceSummary(result)} />
            <ReportSection title="短期预测" value={report?.short_term_prediction} />
            <ReportSection title="技术面" value={report?.technical} />
            <ReportSection title="基本面" value={report?.fundamentals} />
            <ReportSection title="风险指标" value={report?.risk} />
            <ReportSection title="关键不确定性" value={report?.uncertainties} />
            <ReportSection title="非投资建议声明" value={report?.disclaimer} />
          </Card>

          {assetResults.length > 0 && (
            <div className="space-y-4">
              <h2 className="text-xl font-semibold text-foreground">各标的分析</h2>
              {assetResults.map((asset) => (
                <AssetAnalysisCard key={`${asset.market}-${asset.symbol}`} asset={asset} />
              ))}
            </div>
          )}

          {result.tool_calls.length > 0 && (
            <Card>
              <CardTitle>工具调用</CardTitle>
              <ToolCallList result={result} />
            </Card>
          )}
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
