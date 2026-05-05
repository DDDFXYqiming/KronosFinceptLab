"use client";

import { FormEvent, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { api, formatApiError } from "@/lib/api";
import { queryKeys } from "@/lib/queryKeys";
import { useSessionState } from "@/lib/useSessionState";
import type {
  AgentAnalyzeResponse,
  AgentToolCall,
  MacroMonitoringSignal,
  MacroProbabilityScenario,
  MacroSignal,
} from "@/types/api";

const VERSION = "v10.8.3";
const MAX_MACRO_TURNS = 5;
const DEFAULT_QUESTION = "现在适合买黄金吗";
const EXAMPLES = [
  "WW3 的概率是多少",
  "现在适合买黄金吗",
  "AI 是不是泡沫",
  "比特币到底了吗",
];
const LOADING_STEPS = [
  "理解宏观问题",
  "范围/安全检查",
  "选择宏观数据源",
  "获取宏观信号",
  "OpenRouter/DeepSeek 汇总",
  "生成宏观报告",
];

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

function isFinishedStepStatus(status: string): boolean {
  return ["completed", "fallback", "skipped"].includes(status);
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
  }
  return <span className={`rounded-full border px-3 py-1 text-sm font-semibold ${bg}`}>{rec}</span>;
}

function RiskBadge({ level }: { level: string }) {
  const lower = level.toLowerCase();
  let bg = "bg-muted text-muted-foreground";
  if (lower === "low" || level === "低") bg = "bg-green-50 text-green-700";
  else if (lower === "medium" || level === "中") bg = "bg-amber-50 text-amber-700";
  else if (lower === "high" || level === "高") bg = "bg-red-50 text-red-700";
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${bg}`}>{level}</span>;
}

function formatUnknownValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") return Number.isFinite(value) ? value.toFixed(4).replace(/\.?0+$/, "") : "-";
  if (typeof value === "string") return value;
  if (typeof value === "boolean") return value ? "true" : "false";
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function signalLayer(signal: MacroSignal): string {
  const text = `${signal.signal_type} ${signal.source}`.toLowerCase();
  if (/(polymarket|kalshi|prediction|event)/.test(text)) return "预测市场";
  if (/(gold|silver|oil|commodity|coingecko|btc|crypto|deribit)/.test(text)) return "商品/加密";
  if (/(yield|rate|treasury|fed|bis|cme)/.test(text)) return "利率/收益率";
  if (/(cot|position|持仓|option|edgar)/.test(text)) return "持仓/衍生品";
  if (/(sentiment|fear|greed|search|news|web)/.test(text)) return "情绪/舆情";
  return "其他";
}

function normalizeSignals(value: MacroSignal[] | undefined): MacroSignal[] {
  return Array.isArray(value) ? value : [];
}

function normalizeScenarios(value: MacroProbabilityScenario[] | undefined): MacroProbabilityScenario[] {
  return Array.isArray(value) ? value : [];
}

function normalizeMonitoring(value: MacroMonitoringSignal[] | undefined): MacroMonitoringSignal[] {
  return Array.isArray(value) ? value : [];
}

function StepStrip({ result, loading }: { result: AgentAnalyzeResponse | null; loading: boolean }) {
  const steps = result?.steps?.length
    ? result.steps
    : LOADING_STEPS.map((name, index) => ({
      name,
      status: loading ? (index === 0 ? "running" : "pending") : "pending",
      summary: "",
      elapsed_ms: 0,
    }));

  const completed = steps.filter((step) => isFinishedStepStatus(step.status)).length;
  const progress = result
    ? completed / Math.max(steps.length, 1)
    : loading
      ? Math.max(0.1, 1 / Math.max(steps.length, 1))
      : 0;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          进度 {Math.min(completed, steps.length)}/{steps.length}
        </p>
        <p className="text-xs text-muted-foreground">{loading ? "执行中..." : "已完成"}</p>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className={`h-full rounded-full transition-all duration-500 ${loading && !result ? "timeline-progress-live" : "bg-accent"}`}
          style={{ width: `${Math.max(0, Math.min(100, progress * 100))}%` }}
        />
      </div>
      <div className="table-scroll">
        <div className="grid grid-flow-col auto-cols-[minmax(9.5rem,1fr)] gap-2 pb-1 sm:auto-cols-[minmax(12rem,1fr)]">
          {steps.map((step, index) => {
            const failed = ["failed", "blocked"].includes(step.status);
            const completedStep = isFinishedStepStatus(step.status);
            const running = step.status === "running";
            return (
              <div
                key={`${step.name}-${index}`}
                className={`rounded-lg border px-3 py-2 ${
                  failed
                    ? "border-red-200 bg-red-50"
                    : completedStep
                      ? "border-green-200 bg-green-50"
                      : running
                        ? "border-blue-200 bg-blue-50"
                        : "border-border bg-muted"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
                      failed
                        ? "bg-red-100 text-red-700"
                        : completedStep
                          ? "bg-green-100 text-green-700"
                          : running
                            ? "bg-blue-100 text-blue-700"
                            : "bg-background text-muted-foreground"
                    }`}
                  >
                    {index + 1}
                  </span>
                  <span className="line-clamp-1 text-sm font-semibold text-foreground">{step.name}</span>
                </div>
                <p className="mt-1 text-xs font-mono text-muted-foreground">
                  {statusLabel(step.status)} · {formatElapsedMs(step.elapsed_ms)}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function ToolCalls({ calls }: { calls: AgentToolCall[] }) {
  if (!calls.length) return null;
  return (
    <div className="space-y-2">
      {calls.map((call) => (
        <details key={`${call.name}-${call.status}-${call.elapsed_ms}`} className="rounded-lg border border-border bg-muted px-3 py-2">
          <summary className="cursor-pointer list-none">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm font-semibold text-foreground">{call.name}</span>
                  <span className="rounded bg-background px-2 py-0.5 text-xs text-muted-foreground">
                    {statusLabel(call.status)}
                  </span>
                </div>
                <p className="mt-1 break-words text-sm text-muted-foreground">{call.summary}</p>
              </div>
              <p className="shrink-0 text-xs text-muted-foreground font-mono">{formatElapsedMs(call.elapsed_ms)}</p>
            </div>
          </summary>
          <pre className="mt-3 max-h-52 overflow-auto whitespace-pre-wrap break-words rounded bg-surface-raised p-3 text-xs text-muted-foreground">
            {JSON.stringify(call.metadata || {}, null, 2)}
          </pre>
        </details>
      ))}
    </div>
  );
}

function MacroSignalsTable({ signals }: { signals: MacroSignal[] }) {
  if (!signals.length) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700">
        当前没有可展示的宏观信号。
      </div>
    );
  }

  const grouped = signals.reduce<Record<string, MacroSignal[]>>((acc, signal) => {
    const key = signalLayer(signal);
    if (!acc[key]) acc[key] = [];
    acc[key].push(signal);
    return acc;
  }, {});

  return (
    <div className="space-y-3">
      {Object.entries(grouped).map(([group, groupSignals]) => (
        <div key={group} className="rounded-lg border border-border bg-background p-3">
          <p className="mb-2 text-sm font-semibold text-foreground">{group}</p>
          <div className="table-scroll">
            <table className="min-w-[42rem] w-full text-xs sm:min-w-[56rem] sm:text-sm">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  <th className="py-2 text-left">来源</th>
                  <th className="py-2 text-left">信号类型</th>
                  <th className="py-2 text-left">当前值</th>
                  <th className="py-2 text-left">解释</th>
                  <th className="py-2 text-left">期限</th>
                  <th className="py-2 text-right">置信度</th>
                  <th className="py-2 text-left">链接</th>
                </tr>
              </thead>
              <tbody>
                {groupSignals.map((signal, index) => (
                  <tr key={`${group}-${signal.source}-${index}`} className="border-b border-border last:border-b-0">
                    <td className="py-1.5 font-medium text-foreground">{signal.source}</td>
                    <td className="py-1.5 text-muted-foreground">{signal.signal_type}</td>
                    <td className="py-1.5 text-muted-foreground">{formatUnknownValue(signal.value)}</td>
                    <td className="py-1.5 text-muted-foreground">{signal.interpretation}</td>
                    <td className="py-1.5 text-muted-foreground">{signal.time_horizon || "-"}</td>
                    <td className="py-1.5 text-right font-mono text-foreground">
                      {(Math.max(0, Math.min(1, Number(signal.confidence) || 0)) * 100).toFixed(0)}%
                    </td>
                    <td className="py-1.5 text-muted-foreground">
                      {signal.source_url ? (
                        <a href={signal.source_url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                          source
                        </a>
                      ) : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}

function ProbabilityTable({ scenarios }: { scenarios: MacroProbabilityScenario[] }) {
  if (!scenarios.length) return null;
  return (
    <div className="table-scroll rounded-lg border border-border bg-background">
      <table className="min-w-[30rem] w-full text-xs sm:min-w-[40rem] sm:text-sm">
        <thead>
          <tr className="border-b border-border text-muted-foreground">
            <th className="py-2 text-left">场景</th>
            <th className="py-2 text-right">概率</th>
            <th className="py-2 text-left">依据</th>
          </tr>
        </thead>
        <tbody>
          {scenarios.map((item, index) => (
            <tr key={`${item.scenario}-${index}`} className="border-b border-border last:border-b-0">
              <td className="py-1.5 font-medium text-foreground">{item.scenario}</td>
              <td className="py-1.5 text-right font-mono text-foreground">
                {(Math.max(0, Math.min(1, Number(item.probability) || 0)) * 100).toFixed(0)}%
              </td>
              <td className="py-1.5 text-muted-foreground">{item.basis}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MonitoringTable({ rows }: { rows: MacroMonitoringSignal[] }) {
  if (!rows.length) return null;
  return (
    <div className="table-scroll rounded-lg border border-border bg-background">
      <table className="min-w-[32rem] w-full text-xs sm:min-w-[42rem] sm:text-sm">
        <thead>
          <tr className="border-b border-border text-muted-foreground">
            <th className="py-2 text-left">监控信号</th>
            <th className="py-2 text-left">当前值</th>
            <th className="py-2 text-left">阈值</th>
            <th className="py-2 text-left">含义</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((item, index) => (
            <tr key={`${item.signal}-${index}`} className="border-b border-border last:border-b-0">
              <td className="py-1.5 font-medium text-foreground">{item.signal}</td>
              <td className="py-1.5 text-muted-foreground">{formatUnknownValue(item.current_value)}</td>
              <td className="py-1.5 text-muted-foreground">{item.threshold}</td>
              <td className="py-1.5 text-muted-foreground">{item.meaning}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function MacroPage() {
  const queryClient = useQueryClient();
  const inFlightRef = useRef(false);
  const [question, setQuestion] = useSessionState("kronos-macro-question", DEFAULT_QUESTION);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useSessionState("kronos-macro-error", "");
  const [result, setResult] = useSessionState<AgentAnalyzeResponse | null>("kronos-macro-result", null);
  const [history, setHistory] = useSessionState<AgentAnalyzeResponse[]>("kronos-macro-history", []);

  const appendHistory = (entry: AgentAnalyzeResponse) => {
    setHistory((current) => {
      const deduped = current.filter(
        (item) => !(item.timestamp === entry.timestamp && item.question === entry.question)
      );
      return [...deduped, entry].slice(-MAX_MACRO_TURNS);
    });
  };

  const handleAnalyze = async (overrideQuestion?: string, forceRefresh = false) => {
    if (inFlightRef.current) return;
    const prompt = (overrideQuestion || question).trim();
    if (!prompt) return;
    const key = queryKeys.macro({ question: prompt });
    const cached = forceRefresh ? undefined : queryClient.getQueryData<AgentAnalyzeResponse>(key);
    if (cached) {
      setResult(cached);
      appendHistory(cached);
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
          api.macroAnalyze(
            {
              question: prompt,
              context: {
                entry: "web-macro",
                version: VERSION,
                turn_index: Math.min(history.length + 1, MAX_MACRO_TURNS),
                max_turns: MAX_MACRO_TURNS,
              },
            },
            { signal }
          ),
      });
      setResult(res);
      appendHistory(res);
    } catch (e) {
      setError(formatApiError(e, "宏观分析请求失败"));
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
    queryClient.removeQueries({ queryKey: [...queryKeys.all, "macro"] });
    setQuestion(DEFAULT_QUESTION);
    setResult(null);
    setHistory([]);
    setError("");
  };

  const report = result?.report;
  const macroSignals = normalizeSignals(report?.macro_signals);
  const scenarios = normalizeScenarios(report?.probability_scenarios);
  const monitoring = normalizeMonitoring(report?.monitoring_signals);

  return (
    <div className="page-shell space-y-6">
      <h1 className="page-title">宏观洞察</h1>

      <Card>
        <form onSubmit={handleSubmit} className="space-y-4">
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={4}
            className="app-input min-h-36 resize-none px-4 py-3"
            placeholder="例如：现在适合买黄金吗？"
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
              开始洞察
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
          <CardTitle>宏观执行进度</CardTitle>
          <StepStrip result={result} loading={loading} />
        </Card>
      )}

      {history.length > 1 && (
        <Card>
          <div className="mb-3 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
            <CardTitle>本轮历史</CardTitle>
            <p className="text-sm text-muted-foreground">
              保留最近 {MAX_MACRO_TURNS} 轮临时结果，不写入长期记忆。
            </p>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {[...history].reverse().map((item, index) => (
              <button
                key={`${item.timestamp}-${index}`}
                type="button"
                onClick={() => {
                  setResult(item);
                  setQuestion(item.question);
                  setError("");
                }}
                className="rounded-lg border border-border bg-surface px-3 py-2 text-left transition-colors hover:border-accent"
              >
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium text-foreground">{item.question}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {(item.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="line-clamp-2 text-xs text-muted-foreground">
                  {item.report?.macro_analysis || item.report?.conclusion || "无摘要"}
                </p>
              </button>
            ))}
          </div>
        </Card>
      )}

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">{error}</div>}

      {result && (
        <>
          <Card>
            <CardTitle>宏观结论</CardTitle>
            <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <p className="text-sm text-muted-foreground">
                  {report?.macro_analysis || report?.conclusion || "暂无结论。"}
                </p>
              </div>
              <RecommendationBadge rec={result.recommendation} />
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div>
                <p className="mb-1 text-sm text-muted-foreground">置信度</p>
                <div className="flex items-center gap-2">
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
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
                <p className="mb-1 text-sm text-muted-foreground">风险等级</p>
                <RiskBadge level={result.risk_level} />
              </div>
              <div>
                <p className="mb-1 text-sm text-muted-foreground">时间</p>
                <p className="text-sm font-mono text-foreground">{result.timestamp.slice(0, 19)}</p>
              </div>
            </div>
          </Card>

          <Card>
            <CardTitle>信号来源（分层）</CardTitle>
            <MacroSignalsTable signals={macroSignals} />
          </Card>

          <Card>
            <CardTitle>信号一致性评估</CardTitle>
            <div className="space-y-4">
              <div className="rounded-lg border border-border bg-background p-3">
                <p className="mb-1 text-sm font-semibold text-foreground">共振信号</p>
                <p className="text-sm text-muted-foreground">
                  {report?.cross_validation || "暂无交叉验证结论。"}
                </p>
              </div>
              <div className="rounded-lg border border-border bg-background p-3">
                <p className="mb-1 text-sm font-semibold text-foreground">矛盾信号</p>
                <p className="text-sm text-muted-foreground">
                  {report?.contradictions || "暂无矛盾信号说明。"}
                </p>
              </div>
            </div>
          </Card>

          <Card>
            <CardTitle>概率估计</CardTitle>
            {scenarios.length ? (
              <ProbabilityTable scenarios={scenarios} />
            ) : (
              <p className="text-sm text-muted-foreground">暂无概率场景。</p>
            )}
          </Card>

          <Card>
            <CardTitle>待监控信号</CardTitle>
            {monitoring.length ? (
              <MonitoringTable rows={monitoring} />
            ) : (
              <p className="text-sm text-muted-foreground">暂无监控信号。</p>
            )}
          </Card>

          {result.tool_calls.length > 0 && (
            <Card>
              <CardTitle>工具调用时间线</CardTitle>
              <ToolCalls calls={result.tool_calls} />
            </Card>
          )}
        </>
      )}

      {!result && !error && !loading && (
        <Card>
          <div className="py-12 text-center text-muted-foreground">
            <p className="mb-2 text-lg">输入一个宏观问题</p>
            <p className="text-sm">例如：现在适合买黄金吗、WW3 的概率是多少。</p>
          </div>
        </Card>
      )}
    </div>
  );
}
