"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { api, formatApiError } from "@/lib/api";
import { queryKeys } from "@/lib/queryKeys";
import { useSessionState } from "@/lib/useSessionState";
import type {
  AgentAnalyzeResponse,
  AgentToolCall,
  MacroEvidenceCoverage,
  MacroMonitoringSignal,
  MacroProbabilityScenario,
  MacroProviderResultView,
  MacroSignal,
} from "@/types/api";

const VERSION = "v10.8.8";
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

function getMacroToolCall(result: AgentAnalyzeResponse | null): AgentToolCall | undefined {
  return result?.tool_calls?.find((call) => call.name === "macro_signal");
}

function getMacroProviderRows(result: AgentAnalyzeResponse | null): MacroProviderResultView[] {
  const coverage = result?.macro_provider_coverage;
  if (coverage && typeof coverage === "object" && !Array.isArray(coverage)) {
    return Object.entries(coverage).map(([providerId, row]) => ({
      provider_id: row?.provider_id || providerId,
      status: row?.status || "unknown",
      signals: [],
      signal_count: row?.signal_count,
      elapsed_ms: row?.elapsed_ms,
      error: row?.error,
      metadata: {
        data_quality: row?.data_quality,
        source_time: row?.freshness,
        source_url: row?.source_url,
        reason: row?.reason,
      },
    }));
  }
  const raw = getMacroToolCall(result)?.metadata?.provider_results;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return [];
  return Object.entries(raw as Record<string, MacroProviderResultView>).map(([providerId, row]) => ({
    provider_id: row?.provider_id || providerId,
    status: row?.status || "unknown",
    signals: normalizeSignals(row?.signals),
    signal_count: row?.signal_count,
    elapsed_ms: row?.elapsed_ms,
    error: row?.error,
    metadata: row?.metadata || {},
  }));
}

function signalDataQuality(signal: MacroSignal): string {
  const metadata = signal.metadata || {};
  return String(metadata.data_quality || metadata.source_quality || metadata.provider_quality || "-");
}

function signalFreshness(signal: MacroSignal): string {
  const metadata = signal.metadata || {};
  return String(
    signal.observed_at ||
      metadata.source_time ||
      metadata.updated_at ||
      metadata.update_time ||
      metadata.expiration ||
      "-"
  );
}

function providerReason(row: MacroProviderResultView): string {
  if (row.error) return row.error;
  const metadata = row.metadata || {};
  return String(metadata.reason || metadata.message || (row.signals?.length ? "returned signals" : "-"));
}

function MacroDataQuality({
  result,
  signals,
}: {
  result: AgentAnalyzeResponse;
  signals: MacroSignal[];
}) {
  const evidence: MacroEvidenceCoverage | undefined = result.macro_dimension_coverage || result.report?.macro_evidence;
  const macroCall = getMacroToolCall(result);
  const providerRows = getMacroProviderRows(result);
  const statusCounts = evidence?.provider_status_counts || {};
  const quality = result.macro_data_quality;
  const providerTotal =
    quality?.provider_total ||
    providerRows.length ||
    Object.values(statusCounts).reduce((sum, count) => sum + Number(count || 0), 0) ||
    Number(macroCall?.metadata?.provider_ids?.length || 0);
  const successCount = Number(quality?.success_count ?? statusCounts.completed ?? 0);
  const emptyCount = Number(quality?.empty_count ?? statusCounts.empty ?? 0);
  const degradedCount =
    Number(quality?.failed_count ?? statusCounts.failed ?? 0) +
    Number(quality?.skipped_count ?? statusCounts.skipped ?? 0) +
    Number(quality?.unavailable_count ?? statusCounts.unavailable ?? 0);
  const dimensionLabel = evidence
    ? `${evidence.dimension_count}/${evidence.required_dimension_count}`
    : "-";
  const evidenceText = evidence?.sufficient_evidence ? "满足交叉验证" : "证据不足";

  return (
    <Card>
      <CardTitle>数据质量与覆盖率</CardTitle>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-lg border border-border bg-background p-3">
          <p className="text-xs text-muted-foreground">Provider 覆盖</p>
          <p className="mt-1 font-mono text-2xl text-foreground">{providerTotal}</p>
          <p className="mt-1 text-xs text-muted-foreground">成功 {successCount} · 空结果 {emptyCount} · 降级 {degradedCount}</p>
        </div>
        <div className="rounded-lg border border-border bg-background p-3">
          <p className="text-xs text-muted-foreground">有效信号</p>
          <p className="mt-1 font-mono text-2xl text-foreground">{quality?.signal_count ?? signals.length}</p>
          <p className="mt-1 text-xs text-muted-foreground">按来源输出真实结构化信号</p>
        </div>
        <div className="rounded-lg border border-border bg-background p-3">
          <p className="text-xs text-muted-foreground">证据维度</p>
          <p className={`mt-1 font-mono text-2xl ${evidence?.sufficient_evidence ? "text-green-700" : "text-amber-700"}`}>
            {dimensionLabel}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">{evidenceText}</p>
        </div>
        <div className="rounded-lg border border-border bg-background p-3">
          <p className="text-xs text-muted-foreground">更新时间</p>
          <p className="mt-1 font-mono text-sm text-foreground">{quality?.last_updated || result.timestamp.slice(0, 19)}</p>
          <p className="mt-1 text-xs text-muted-foreground">本轮请求完成时间</p>
        </div>
      </div>
      {evidence?.dimension_labels?.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {evidence.dimension_labels.map((label) => (
            <span key={label} className="rounded-full border border-border bg-surface px-3 py-1 text-xs text-muted-foreground">
              {label}
            </span>
          ))}
        </div>
      ) : null}
    </Card>
  );
}

function ProviderCoverageMatrix({ rows }: { rows: MacroProviderResultView[] }) {
  if (!rows.length) {
    return (
      <Card>
        <CardTitle>Provider 覆盖矩阵</CardTitle>
        <p className="text-sm text-muted-foreground">本轮结果未返回 provider 明细。</p>
      </Card>
    );
  }

  return (
    <Card>
      <CardTitle>Provider 覆盖矩阵</CardTitle>
      <div className="space-y-2 md:hidden">
        {rows.map((row) => (
          <details key={row.provider_id} className="rounded-lg border border-border bg-background p-3">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
              <span className="font-mono text-sm font-semibold text-foreground">{row.provider_id}</span>
              <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">{statusLabel(row.status)}</span>
            </summary>
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
              <span>信号数</span>
              <span className="text-right font-mono text-foreground">{row.signal_count ?? row.signals?.length ?? 0}</span>
              <span>耗时</span>
              <span className="text-right font-mono text-foreground">{formatElapsedMs(Number(row.elapsed_ms || 0))}</span>
              <span>原因</span>
              <span className="text-right text-foreground">{providerReason(row)}</span>
            </div>
          </details>
        ))}
      </div>
      <div className="hidden md:block">
        <div className="table-scroll">
          <table className="min-w-[56rem] w-full text-sm">
            <thead>
              <tr className="border-b border-border text-muted-foreground">
                <th className="py-2 text-left">Provider</th>
                <th className="py-2 text-left">状态</th>
                <th className="py-2 text-right">耗时</th>
                <th className="py-2 text-right">信号数</th>
                <th className="py-2 text-left">数据质量</th>
                <th className="py-2 text-left">更新时间</th>
                <th className="py-2 text-left">失败/降级原因</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const firstSignal = row.signals?.[0];
                const metadata = row.metadata || {};
                return (
                  <tr key={row.provider_id} className="border-b border-border last:border-b-0">
                    <td className="py-2 font-mono font-semibold text-foreground">{row.provider_id}</td>
                    <td className="py-2 text-muted-foreground">{statusLabel(row.status)}</td>
                    <td className="py-2 text-right font-mono text-foreground">{formatElapsedMs(Number(row.elapsed_ms || 0))}</td>
                    <td className="py-2 text-right font-mono text-foreground">{row.signal_count ?? row.signals?.length ?? 0}</td>
                    <td className="py-2 text-muted-foreground">{firstSignal ? signalDataQuality(firstSignal) : String(metadata.data_quality || "-")}</td>
                    <td className="py-2 text-muted-foreground">{firstSignal ? signalFreshness(firstSignal) : String(metadata.source_time || "-")}</td>
                    <td className="py-2 text-muted-foreground">{providerReason(row)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </Card>
  );
}

function StepStrip({ result, loading }: { result: AgentAnalyzeResponse | null; loading: boolean }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [pulseTick, setPulseTick] = useState(0);

  useEffect(() => {
    if (!loading || result) {
      setActiveIndex(0);
      setPulseTick(0);
      return;
    }
    setActiveIndex(0);
    setPulseTick(0);
    const stepTimer = window.setInterval(() => {
      setActiveIndex((current) => Math.min(current + 1, LOADING_STEPS.length - 1));
    }, 900);
    const pulseTimer = window.setInterval(() => {
      setPulseTick((current) => current + 1);
    }, 220);
    return () => {
      window.clearInterval(stepTimer);
      window.clearInterval(pulseTimer);
    };
  }, [loading, result]);

  const steps = result?.steps?.length
    ? result.steps
    : LOADING_STEPS.map((name, index) => ({
      name,
      status: !loading ? "pending" : index < activeIndex ? "completed" : index === activeIndex ? "running" : "pending",
      summary: "",
      elapsed_ms: index < activeIndex ? (index + 1) * 900 : index === activeIndex ? ((pulseTick % 4) + 1) * 220 : 0,
    }));

  const completed = steps.filter((step) => isFinishedStepStatus(step.status)).length;
  const baseProgress = result
    ? completed / Math.max(steps.length, 1)
    : loading
      ? (activeIndex + 0.4 + (pulseTick % 4) * 0.08) / LOADING_STEPS.length
      : 0;
  const progressPercent = Math.max(0, Math.min(100, baseProgress * 100));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          进度 {Math.min(completed, steps.length)}/{steps.length}
        </p>
        {loading && !result && <p className="text-xs text-muted-foreground">正在实时推进…</p>}
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className={`h-full rounded-full transition-all duration-500 ${loading && !result ? "timeline-progress-live" : "bg-accent"}`}
          style={{ width: `${progressPercent}%` }}
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
          <div className="space-y-2 sm:hidden">
            {groupSignals.map((signal, index) => (
              <details key={`${group}-mobile-${signal.source}-${index}`} className="rounded-lg border border-border bg-surface p-3">
                <summary className="flex cursor-pointer list-none items-start justify-between gap-3">
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-semibold text-foreground">{signal.source}</span>
                    <span className="block text-xs text-muted-foreground">{signal.signal_type}</span>
                  </span>
                  <span className="shrink-0 font-mono text-sm font-semibold text-foreground">
                    {(Math.max(0, Math.min(1, Number(signal.confidence) || 0)) * 100).toFixed(0)}%
                  </span>
                </summary>
                <div className="mt-3 space-y-2 text-xs text-muted-foreground">
                  <p><span className="font-semibold text-foreground">当前值：</span>{formatUnknownValue(signal.value)}</p>
                  <p><span className="font-semibold text-foreground">解释：</span>{signal.interpretation}</p>
                  <div className="grid grid-cols-2 gap-2">
                    <p><span className="font-semibold text-foreground">期限：</span>{signal.time_horizon || "-"}</p>
                    <p><span className="font-semibold text-foreground">质量：</span>{signalDataQuality(signal)}</p>
                    <p className="col-span-2"><span className="font-semibold text-foreground">更新时间：</span>{signalFreshness(signal)}</p>
                  </div>
                  {signal.source_url ? (
                    <a href={signal.source_url} target="_blank" rel="noreferrer" className="inline-flex text-accent hover:underline">
                      查看来源
                    </a>
                  ) : null}
                </div>
              </details>
            ))}
          </div>
          <div className="hidden sm:block table-scroll">
            <table className="min-w-[42rem] w-full text-xs sm:min-w-[56rem] sm:text-sm">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  <th className="py-2 text-left">来源</th>
                  <th className="py-2 text-left">信号类型</th>
                  <th className="py-2 text-left">当前值</th>
                  <th className="py-2 text-left">解释</th>
                  <th className="py-2 text-left">期限</th>
                  <th className="py-2 text-right">置信度</th>
                  <th className="py-2 text-left">数据质量</th>
                  <th className="py-2 text-left">更新时间</th>
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
                    <td className="py-1.5 text-muted-foreground">{signalDataQuality(signal)}</td>
                    <td className="py-1.5 text-muted-foreground">{signalFreshness(signal)}</td>
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
    setResult(null);
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
  const providerRows = getMacroProviderRows(result);
  const evidence = result?.macro_dimension_coverage || report?.macro_evidence;

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
            {evidence && (
              <div className="mb-4 flex flex-wrap gap-2">
                <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${
                  evidence.sufficient_evidence
                    ? "border-green-200 bg-green-50 text-green-700"
                    : "border-amber-200 bg-amber-50 text-amber-700"
                }`}>
                  {evidence.sufficient_evidence ? "证据满足" : "证据不足"}
                </span>
                <span className="rounded-full border border-border bg-surface px-3 py-1 text-xs text-muted-foreground">
                  独立维度 {evidence.dimension_count}/{evidence.required_dimension_count}
                </span>
                {(evidence.dimension_labels || []).slice(0, 5).map((label) => (
                  <span key={label} className="rounded-full border border-border bg-background px-3 py-1 text-xs text-muted-foreground">
                    {label}
                  </span>
                ))}
              </div>
            )}
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

          <MacroDataQuality result={result} signals={macroSignals} />

          <ProviderCoverageMatrix rows={providerRows} />

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
