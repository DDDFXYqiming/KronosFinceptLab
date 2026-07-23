"use client";

import { FormEvent, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useIsFetching, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { Card, CardTitle, CardGrid } from "@/components/ui/Card";
import { SectionLabel } from "@/components/ui/SectionLabel";
import { Button } from "@/components/ui/Button";
import { ApiKeyNotice } from "@/components/ui/ApiKeyNotice";
import { AgentProgress } from "@/components/ui/AgentProgress";
import { MarkdownText } from "@/components/ui/MarkdownText";
import { api, formatApiError } from "@/lib/api";
import { demoAgentResult } from "@/lib/demoData";
import { normalizeMarket, type Market } from "@/lib/markets";
import { DEFAULT_SYMBOL, DEFAULT_SYMBOL_NAME, normalizeSymbol } from "@/lib/symbols";
import { queryKeys } from "@/lib/queryKeys";
import { useSessionState } from "@/lib/useSessionState";
import { useAppStore } from "@/stores/app";
import type { Language } from "@/lib/i18n";
import type {
  AgentAnalyzeResponse,
  AgentAssetResult,
  AgentReport,
  ForecastRow,
  MacroMonitoringSignal,
  MacroProbabilityScenario,
  MacroSignal,
} from "@/types/api";

const LOADING_STEPS = [
  "理解问题",
  "范围/安全检查",
  "解析标的",
  "获取行情",
  "调用 Kronos",
  "网页检索",
  "LLM 汇总",
  "生成报告",
];
const _HARDCODED_EXAMPLES = [
  `帮我看看${DEFAULT_SYMBOL_NAME}现在能不能买`,
  "比较招商银行和贵州茅台的中短期风险",
  "分析一下 AAPL 和 NVDA 最近走势",
];

const DEFAULT_QUESTION = `帮我看看${DEFAULT_SYMBOL_NAME}现在能不能买`;
const MAX_ANALYSIS_TURNS = 5;

function tx(language: Language, zh: string, en: string): string {
  return language === "en-US" ? en : zh;
}

function defaultAnalysisQuestion(language: Language, symbol?: string) {
  if (symbol) {
    return tx(language, `分析 ${symbol} 的短期走势和风险`, `Analyze the short-term trend and risk for ${symbol}`);
  }
  return tx(language, DEFAULT_QUESTION, `Can I still buy ${DEFAULT_SYMBOL_NAME} now?`);
}

function fallbackAnalysisExamples(language: Language): string[] {
  if (language === "en-US") {
    return [
      `Can I still buy ${DEFAULT_SYMBOL_NAME} now?`,
      "Compare short-term risk in China Merchants Bank and Kweichow Moutai",
      "Analyze recent momentum in AAPL and NVDA",
    ];
  }
  return _HARDCODED_EXAMPLES;
}

type ActiveAnalysisRun = {
  queryKey: QueryKey;
  question: string;
  symbol?: string;
  market?: Market;
  turnIndex: number;
  startedAt: number;
};

function formatElapsedMs(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "-";
  if (value < 1000) return `${Math.round(value)}ms`;
  return `${(value / 1000).toFixed(1)}s`;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function calcReturnPct(end: number, base?: number | null): number | null {
  if (!isFiniteNumber(base) || base <= 0 || !isFiniteNumber(end)) return null;
  return end / base - 1;
}

function formatSignedPercent(value: number | null | undefined): string {
  if (!isFiniteNumber(value)) return "-";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
}

function returnTextClass(value: number | null | undefined): string {
  if (!isFiniteNumber(value)) return "text-muted-foreground";
  if (value > 0) return "text-green-700";
  if (value < 0) return "text-red-700";
  return "text-muted-foreground";
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

const TECHNICAL_DETAIL_PATTERN = /(?:^|\s)(?:[A-Za-z_][A-Za-z0-9_]*\s*=\s*)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?=$|[\s,.;，。；])/gi;
const TECHNICAL_LABEL_PATTERN = /\b(?:request[_-]?id|trace[_-]?id|session[_-]?id|correlation[_-]?id)\s*[=:：]\s*[^\s,;，；。]+/gi;
const TECHNICAL_NAME_PATTERN = /\b[A-Za-z]+(?:_[A-Za-z0-9]+){1,}\b/g;

function cleanUserVisibleText(value?: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(TECHNICAL_LABEL_PATTERN, "")
    .replace(TECHNICAL_DETAIL_PATTERN, "")
    .replace(TECHNICAL_NAME_PATTERN, "")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\s+([，。；：:,.])/g, "$1")
    .replace(/^[\s:：,，;；。-]+|[\s:：,，;；。-]+$/g, "")
    .trim();
}

function parseReportLiteral(text: string): unknown {
  const trimmed = text.trim();
  if (!/^[{[]/.test(trimmed)) return null;
  try {
    return JSON.parse(trimmed);
  } catch {}
  try {
    return JSON.parse(
      trimmed
        .replace(/\bNone\b/g, "null")
        .replace(/\bTrue\b/g, "true")
        .replace(/\bFalse\b/g, "false")
        .replace(/'/g, "\"")
    );
  } catch {
    return null;
  }
}

function formatReportText(value?: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) {
    return value.map(formatReportText).filter(Boolean).join("；");
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => {
        const text = formatReportText(item);
        return text ? `${key}：${text}` : "";
      })
      .filter(Boolean)
      .join("；");
  }
  const text = cleanUserVisibleText(value);
  const parsed = parseReportLiteral(text);
  return parsed ? formatReportText(parsed) : text;
}

function buildEvidenceSummary(result: AgentAnalyzeResponse): string {
  const completed = result.tool_calls
    .filter((call) => ["completed", "fallback", "skipped"].includes(call.status))
    .map((call, index) => {
      const summary = cleanUserVisibleText(call.summary);
      if (!summary) return "";
      const symbol = cleanUserVisibleText(call.metadata?.symbol);
      const scope = symbol ? `（${symbol}）` : "";
      return `${index + 1}. ${scope}${summary}`;
    })
    .filter(Boolean);
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

function EvidenceGraphViewer({ result }: { result: AgentAnalyzeResponse }) {
  const pack = result.evidence_pack;
  if (!pack?.items?.length) return null;
  const confidenceEntries = Object.entries(result.confidence_breakdown || {});
  return (
    <Card>
      <CardTitle subtitle="Evidence Pack + cited claims + confidence breakdown">Evidence Graph</CardTitle>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {pack.items.slice(0, 9).map((item) => (
          <div key={item.id} className="rounded-lg border border-border bg-card p-3">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="font-mono text-xs text-accent">{item.id}</span>
              <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">{item.category}</span>
            </div>
            <p className="font-semibold text-foreground">{item.title}</p>
            <p className="mt-1 line-clamp-3 text-sm text-muted-foreground">{cleanUserVisibleText(item.summary)}</p>
          </div>
        ))}
      </div>
      {result.cited_claims?.length ? (
        <div className="mt-4 space-y-2">
          <p className="text-sm font-semibold text-foreground">引用式结论</p>
          {result.cited_claims.map((claim, index) => (
            <div key={`${claim.claim}-${index}`} className="rounded-lg bg-muted p-3 text-sm">
              <p className="text-foreground">{cleanUserVisibleText(claim.claim)}</p>
              <p className="mt-1 font-mono text-xs text-muted-foreground">evidence: {claim.evidence_ids.join(", ")}</p>
            </div>
          ))}
        </div>
      ) : null}
      {confidenceEntries.length > 0 && (
        <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-5">
          {confidenceEntries.map(([key, value]) => (
            <div key={key} className="rounded-lg border border-border p-2">
              <p className="text-xs text-muted-foreground">{key}</p>
              <p className="text-lg font-bold text-foreground">{`${(Number(value || 0) * 100).toFixed(1)}%`}</p>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function ToolCallList({ result }: { result: AgentAnalyzeResponse }) {
  return (
    <div className="space-y-3">
      {result.tool_calls.map((call, index) => {
        const symbol = cleanUserVisibleText(call.metadata?.symbol);
        const market = cleanUserVisibleText(call.metadata?.market);
        const summary = cleanUserVisibleText(call.summary) || "该步骤已完成，暂无补充说明。";
        return (
          <details
            key={`${index}-${call.status}-${call.elapsed_ms}-${summary.slice(0, 24)}`}
            className="rounded-lg border border-border bg-muted px-3 py-2"
          >
            <summary className="cursor-pointer list-none">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-foreground">工具步骤 {index + 1}</span>
                    <span className="rounded bg-background px-2 py-0.5 text-xs text-muted-foreground">{statusLabel(call.status)}</span>
                    {symbol && <span className="rounded bg-background px-2 py-0.5 text-xs text-muted-foreground">{symbol}</span>}
                    {market && <span className="rounded bg-background px-2 py-0.5 text-xs text-muted-foreground">{market}</span>}
                  </div>
                  <p className="mt-1 break-words text-sm text-muted-foreground">{summary}</p>
                </div>
                <div className="shrink-0 text-xs text-muted-foreground">
                  <span>{formatElapsedMs(call.elapsed_ms)}</span>
                </div>
              </div>
            </summary>
            <div className="mt-3 rounded-md border border-border bg-background p-3 text-xs text-muted-foreground">
              <p className="font-semibold text-foreground">展示说明</p>
              <p className="mt-1 break-words">这里只展示面向研究结论的摘要、标的和市场信息；内部函数、变量和追踪编号不会展示在页面中。</p>
            </div>
          </details>
        );
      })}
    </div>
  );
}

function ReportSection({ title, value }: { title: string; value?: unknown }) {
  const text = formatReportText(value);
  if (!text) return null;
  return (
    <div className="border-b border-border last:border-b-0 py-4 first:pt-0 last:pb-0">
      <h3 className="text-sm font-semibold text-foreground mb-2">{title}</h3>
      <MarkdownText text={text} className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap" />
    </div>
  );
}

function formatMacroValue(value: unknown): string {
  if (typeof value === "number") return Number.isFinite(value) ? value.toFixed(2) : String(value);
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "-";
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function MacroSignalTable({ signals }: { signals: MacroSignal[] }) {
  if (!signals.length) return null;
  return (
    <div className="table-scroll mt-3 rounded-lg border border-border bg-background">
      <table className="min-w-[31rem] w-full text-xs sm:min-w-[38rem] sm:text-sm">
        <thead className="bg-muted">
          <tr className="border-b border-border text-muted-foreground">
            <th className="px-2 py-2 text-left">来源</th>
            <th className="px-2 py-2 text-left">信号</th>
            <th className="px-2 py-2 text-right">数值</th>
            <th className="px-2 py-2 text-left">解读</th>
            <th className="px-2 py-2 text-right">置信度</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((signal, index) => (
            <tr key={`${signal.source}-${signal.signal_type}-${index}`} className="border-b border-border align-top last:border-b-0">
              <td className="px-2 py-2 text-foreground">{signal.source}</td>
              <td className="px-2 py-2 text-foreground">{signal.signal_type}</td>
              <td className="px-2 py-2 text-right font-mono text-foreground">{formatMacroValue(signal.value)}</td>
              <td className="px-2 py-2 text-muted-foreground">{signal.interpretation}</td>
              <td className="px-2 py-2 text-right font-semibold text-foreground">{(signal.confidence * 100).toFixed(0)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MacroScenarioTable({ scenarios }: { scenarios: MacroProbabilityScenario[] }) {
  if (!scenarios.length) return null;
  return (
    <div className="table-scroll mt-3 rounded-lg border border-border bg-background">
      <table className="table-fixed min-w-[26rem] w-full text-xs sm:min-w-[28rem] sm:text-sm">
        <thead className="bg-muted">
          <tr className="border-b border-border text-muted-foreground">
            <th className="px-2 py-2 text-left">场景</th>
            <th className="px-2 py-2 text-right w-14">概率</th>
            <th className="px-2 py-2 text-left">依据</th>
          </tr>
        </thead>
        <tbody>
          {scenarios.map((item, index) => (
            <tr key={`${item.scenario}-${index}`} className="border-b border-border align-top last:border-b-0">
              <td className="px-2 py-2 font-semibold text-foreground">{item.scenario}</td>
              <td className="px-2 py-2 text-right font-mono text-foreground">{(item.probability * 100).toFixed(0)}%</td>
              <td className="px-2 py-2 text-muted-foreground">{item.basis}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MacroMonitoringTable({ monitoring }: { monitoring: MacroMonitoringSignal[] }) {
  if (!monitoring.length) return null;
  return (
    <div className="table-scroll mt-3 rounded-lg border border-border bg-background">
      <table className="min-w-[29rem] w-full text-xs sm:min-w-[32rem] sm:text-sm">
        <thead className="bg-muted">
          <tr className="border-b border-border text-muted-foreground">
            <th className="px-2 py-2 text-left">监控信号</th>
            <th className="px-2 py-2 text-right">当前值</th>
            <th className="px-2 py-2 text-left">阈值</th>
            <th className="px-2 py-2 text-left">意义</th>
          </tr>
        </thead>
        <tbody>
          {monitoring.map((item, index) => (
            <tr key={`${item.signal}-${index}`} className="border-b border-border align-top last:border-b-0">
              <td className="px-2 py-2 text-foreground">{item.signal}</td>
              <td className="px-2 py-2 text-right font-mono text-foreground">{formatMacroValue(item.current_value)}</td>
              <td className="px-2 py-2 text-muted-foreground">{item.threshold}</td>
              <td className="px-2 py-2 text-muted-foreground">{item.meaning}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MacroBackgroundDetails({ report }: { report?: AgentReport }) {
  const macroAnalysis = report?.macro_analysis?.trim() || "";
  const crossValidation = report?.cross_validation?.trim() || "";
  const contradictions = report?.contradictions?.trim() || "";
  const signals = report?.macro_signals || [];
  const probabilityScenarios = report?.probability_scenarios || [];
  const monitoringSignals = report?.monitoring_signals || [];
  if (!macroAnalysis && !crossValidation && !contradictions && !signals.length && !probabilityScenarios.length && !monitoringSignals.length) {
    return null;
  }

  return (
    <details className="mb-5 rounded-lg border border-border bg-muted/60 px-3 py-3" open>
      <summary className="cursor-pointer text-sm font-semibold text-foreground">
        宏观背景（辅助参考）
      </summary>
      <p className="mt-2 text-xs text-muted-foreground">
        当问题涉及买入时机、估值或风险评估时，系统会按需融合宏观信号；以下内容仅作为个股结论的辅助参考。
      </p>
      <div className="mt-3 space-y-2">
        <ReportSection title="宏观结论" value={macroAnalysis} />
        <ReportSection title="信号一致性评估（交叉验证）" value={crossValidation} />
        <ReportSection title="矛盾信号" value={contradictions} />
      </div>
      <MacroSignalTable signals={signals} />
      <MacroScenarioTable scenarios={probabilityScenarios} />
      <MacroMonitoringTable monitoring={monitoringSignals} />
    </details>
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

  const firstOpen = forecast[0]?.open;
  const basePrice = isFiniteNumber(asset.current_price) && asset.current_price > 0 ? asset.current_price : firstOpen;

  return (
    <div className="table-scroll max-h-48 overflow-y-auto rounded-lg border border-border bg-background">
      <table className="min-w-[32rem] w-full text-xs sm:min-w-[34rem] sm:text-sm">
        <thead className="sticky top-0 bg-muted">
          <tr className="border-b border-border text-muted-foreground">
            <th className="px-2 py-2 text-left">日期</th>
            <th className="px-2 py-2 text-right">开盘</th>
            <th className="px-2 py-2 text-right">最高</th>
            <th className="px-2 py-2 text-right">最低</th>
            <th className="px-2 py-2 text-right">收盘</th>
            <th className="px-2 py-2 text-right">涨跌幅</th>
          </tr>
        </thead>
        <tbody>
          {forecast.map((row, index) => {
            const previousClose = index > 0 ? forecast[index - 1]?.close : basePrice;
            const rowReturn = calcReturnPct(row.close, previousClose);
            return (
              <tr key={`${asset.symbol}-${row.timestamp}-${row.close}`} className="border-b border-border text-foreground hover:bg-muted">
                <td className="px-2 py-1.5 font-mono text-xs">{String(row.timestamp).slice(0, 10)}</td>
                <td className="px-2 py-1.5 text-right">{row.open.toFixed(2)}</td>
                <td className="px-2 py-1.5 text-right">{row.high.toFixed(2)}</td>
                <td className="px-2 py-1.5 text-right">{row.low.toFixed(2)}</td>
                <td className="px-2 py-1.5 text-right font-semibold">{row.close.toFixed(2)}</td>
                <td className={`px-2 py-1.5 text-right font-semibold ${returnTextClass(rowReturn)}`}>
                  {formatSignedPercent(rowReturn)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function KronosMiniKline({ forecast }: { forecast: ForecastRow[] }) {
  if (!forecast.length) return null;
  const height = 120;
  const candleWidth = 10;
  const slot = 20;
  const width = Math.max(140, forecast.length * slot);
  const maxHigh = Math.max(...forecast.map((row) => row.high));
  const minLow = Math.min(...forecast.map((row) => row.low));
  const range = Math.max(maxHigh - minLow, 0.0001);
  const toY = (price: number) => 10 + ((maxHigh - price) / range) * (height - 20);

  return (
    <div className="rounded-lg border border-border bg-[#0A0E1A] p-2">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-28 w-full">
        {forecast.map((row, index) => {
          const x = index * slot + slot / 2;
          const highY = toY(row.high);
          const lowY = toY(row.low);
          const openY = toY(row.open);
          const closeY = toY(row.close);
          const rising = row.close >= row.open;
          const color = rising ? "#10B981" : "#EF4444";
          const bodyTop = Math.min(openY, closeY);
          const bodyHeight = Math.max(Math.abs(openY - closeY), 1.6);
          return (
            <g key={`${row.timestamp}-${index}`}>
              <line x1={x} y1={highY} x2={x} y2={lowY} stroke={color} strokeWidth={1.2} />
              <rect
                x={x - candleWidth / 2}
                y={bodyTop}
                width={candleWidth}
                height={bodyHeight}
                rx={1.5}
                fill={color}
              />
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function KronosForecastPanel({ asset }: { asset: AgentAssetResult }) {
  const forecast = asset.kronos_prediction?.forecast || [];
  if (!forecast.length) {
    return asset.kronos_prediction_error ? (
      <div className="mb-5 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700">
        {asset.kronos_prediction_error}
      </div>
    ) : null;
  }

  const firstOpen = forecast[0]?.open ?? 0;
  const lastClose = forecast[forecast.length - 1]?.close ?? 0;
  const basePrice = isFiniteNumber(asset.current_price) && asset.current_price > 0 ? asset.current_price : firstOpen;
  const projectedReturn = calcReturnPct(lastClose, basePrice);
  const model = asset.kronos_prediction?.model || "Kronos";

  return (
    <div className="mb-5 rounded-lg border border-border bg-muted/60 p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-foreground">
          Kronos 预测（未来 {forecast.length} 日 OHLC）
        </h3>
        <span className="rounded bg-background px-2 py-0.5 text-xs font-mono text-muted-foreground">
          {model}
        </span>
      </div>
      <div className="mb-3 grid grid-cols-2 gap-2 text-xs text-muted-foreground sm:grid-cols-4">
        <div className="rounded-md bg-background px-3 py-2">
          <p>基准价</p>
          <p className="mt-1 text-sm font-semibold text-foreground">{basePrice.toFixed(2)}</p>
        </div>
        <div className="rounded-md bg-background px-3 py-2">
          <p>预测终点</p>
          <p className="mt-1 text-sm font-semibold text-foreground">{lastClose.toFixed(2)}</p>
        </div>
        <div className="rounded-md bg-background px-3 py-2">
          <p>预测涨跌幅</p>
          <p className={`mt-1 text-sm font-semibold ${returnTextClass(projectedReturn)}`}>
            {formatSignedPercent(projectedReturn)}
          </p>
        </div>
        <div className="rounded-md bg-background px-3 py-2">
          <p>来源</p>
          <p className="mt-1 truncate text-sm font-semibold text-foreground">Kronos 模型输出</p>
        </div>
      </div>
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,1.1fr)]">
        <KronosMiniKline forecast={forecast} />
        <ForecastTable asset={asset} />
      </div>
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

      <KronosForecastPanel asset={asset} />

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
      <MacroBackgroundDetails report={report} />

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

    </Card>
  );
}

function AnalysisContent() {
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const language = useAppStore((state) => state.preferences.language);
  const symbolParam = searchParams.get("symbol");
  const marketParam = searchParams.get("market");
  const demoMode = searchParams.get("demo") === "1";
  const normalizedMarketParam: Market | undefined = marketParam ? normalizeMarket(marketParam) : undefined;
  const normalizedSymbolParam = symbolParam ? normalizeSymbol(symbolParam) : undefined;
  const initialQuestion = defaultAnalysisQuestion(language, symbolParam ? normalizedSymbolParam || symbolParam : undefined);
  const [question, setQuestion] = useSessionState(
    "kronos-analysis-question",
    initialQuestion,
    { preferInitial: Boolean(symbolParam) }
  );
  const [loading, setLoading] = useState(false);
  const inFlightRef = useRef(false);
  const [error, setError] = useSessionState("kronos-analysis-error", "");
  const [result, setResult] = useSessionState<AgentAnalyzeResponse | null>("kronos-analysis-result", null);
  const [history, setHistory] = useSessionState<AgentAnalyzeResponse[]>("kronos-analysis-history", []);
  const [activeRun, setActiveRun] = useSessionState<ActiveAnalysisRun | null>("kronos-analysis-active-run", null);
  const [examples, setExamples] = useState<string[]>(() => fallbackAnalysisExamples(language));
  const activeRunFetching = useIsFetching({
    queryKey: activeRun?.queryKey ?? ["kronos-analysis-no-active-run"],
    exact: true,
  });
  const displayLoading = loading || activeRunFetching > 0 || Boolean(activeRun && !error);

  // Fetch LLM-generated suggestions (cached 2h in sessionStorage)
  useEffect(() => {
    setExamples(fallbackAnalysisExamples(language));
    // Legacy cache key prefix retained for tests and migration: "kronos-analysis-suggestions"
    const cacheKey = `kronos-analysis-suggestions-${language}`;
    try {
      const cached = window.sessionStorage.getItem(cacheKey);
      if (cached) {
        const { questions, generated_at } = JSON.parse(cached);
        if (Date.now() / 1000 - generated_at < 2 * 3600) {
          setExamples(questions);
          return;
        }
      }
    } catch {}
    api.getSuggestions("analysis").then((res) => {
      if (res.questions?.length) {
        setExamples(res.questions);
        try { window.sessionStorage.setItem(cacheKey, JSON.stringify(res)); } catch {}
      }
    }).catch(() => {});
  }, [language]);

  const appendHistory = useCallback((entry: AgentAnalyzeResponse) => {
    setHistory((current) => {
      const deduped = current.filter(
        (item) => !(item.timestamp === entry.timestamp && item.question === entry.question)
      );
      return [...deduped, entry].slice(-MAX_ANALYSIS_TURNS);
    });
  }, [setHistory]);

  const buildRequest = useCallback((run: ActiveAnalysisRun) => ({
    question: run.question,
    symbol: run.symbol,
    market: run.market,
    context: {
      entry: "web-analysis",
      default_symbol: DEFAULT_SYMBOL,
      turn_index: run.turnIndex,
      max_turns: MAX_ANALYSIS_TURNS,
      language,
    },
    language,
  }), [language]);

  const applyCompletedRun = useCallback((entry: AgentAnalyzeResponse) => {
    setResult(entry);
    appendHistory(entry);
    setQuestion(entry.question);
    if (typeof window !== "undefined") {
      const key = entry.symbol && entry.market ? `kronos-research-summary-${entry.market}:${entry.symbol}` : "";
      if (key) {
        window.localStorage.setItem(key, JSON.stringify({
          conclusion: cleanUserVisibleText(entry.report?.conclusion || entry.final_report).slice(0, 180),
          recommendation: entry.recommendation,
          risk_level: entry.risk_level,
          timestamp: entry.timestamp,
        }));
      }
    }
    setError("");
    setActiveRun(null);
  }, [appendHistory, setActiveRun, setError, setQuestion, setResult]);

  const resumeActiveRun = useCallback(async (run: ActiveAnalysisRun) => {
    if (inFlightRef.current) return;
    const key = run.queryKey;
    const cached = queryClient.getQueryData<AgentAnalyzeResponse>(key);
    if (cached) {
      applyCompletedRun(cached);
      setLoading(false);
      return;
    }

    const state = queryClient.getQueryState<AgentAnalyzeResponse>(key);
    if (state?.status === "error") {
      setError(formatApiError(state.error, tx(language, "分析请求失败", "Analysis request failed")));
      setActiveRun(null);
      setLoading(false);
      return;
    }

    inFlightRef.current = true;
    setLoading(true);
    setError("");
    try {
      const res = await queryClient.fetchQuery({
        queryKey: key,
        queryFn: ({ signal }) => api.agentAnalyze(buildRequest(run), { signal }),
      });
      applyCompletedRun(res);
    } catch (e: any) {
      setError(formatApiError(e, tx(language, "分析请求失败", "Analysis request failed")));
      setActiveRun(null);
    } finally {
      inFlightRef.current = false;
      setLoading(false);
    }
  }, [applyCompletedRun, buildRequest, queryClient, setActiveRun, setError]);

  const handleAnalyze = async (overrideQuestion?: string, forceRefresh = false) => {
    if (inFlightRef.current) return;
    const prompt = (overrideQuestion || question).trim();
    if (!prompt) return;
    const key = queryKeys.agent({
      question: prompt,
      symbol: normalizedSymbolParam,
      market: normalizedMarketParam,
      language,
    });
    const cached = forceRefresh ? undefined : queryClient.getQueryData<AgentAnalyzeResponse>(key);
    if (cached) {
      applyCompletedRun(cached);
      return;
    }

    const run: ActiveAnalysisRun = {
      queryKey: [...key],
      question: prompt,
      symbol: normalizedSymbolParam,
      market: normalizedMarketParam,
      turnIndex: Math.min(history.length + 1, MAX_ANALYSIS_TURNS),
      startedAt: Date.now(),
    };

    inFlightRef.current = true;
    setActiveRun(run);
    setResult(null);
    setLoading(true);
    setError("");
    try {
      if (forceRefresh) {
        await queryClient.invalidateQueries({ queryKey: key });
      }
      const res = await queryClient.fetchQuery({
        queryKey: key,
        queryFn: ({ signal }) => api.agentAnalyze(buildRequest(run), { signal }),
      });
      applyCompletedRun(res);
    } catch (e: any) {
      setError(formatApiError(e, tx(language, "分析请求失败", "Analysis request failed")));
      setActiveRun(null);
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
    setQuestion(defaultAnalysisQuestion(language));
    setResult(null);
    setHistory([]);
    setActiveRun(null);
    setError("");
  };

  useEffect(() => {
    if (!activeRun) return;
    if (result) {
      setResult(null);
    }
    void resumeActiveRun(activeRun);
  }, [activeRun, result, resumeActiveRun, setResult]);

  useEffect(() => {
    if (symbolParam) {
      handleAnalyze(initialQuestion);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!demoMode) return;
    setQuestion(demoAgentResult.question);
    setResult(demoAgentResult);
    setHistory([demoAgentResult]);
    setError("");
    setActiveRun(null);
  }, [demoMode, setActiveRun, setError, setHistory, setQuestion, setResult]);

  const report = result?.report;
  const assetResults = result ? getAssetResults(result) : [];

  return (
    <div className="page-shell space-y-6">
      <SectionLabel>{tx(language, "AI 分析", "AI Analysis")}</SectionLabel>
      <h1 className="page-title">{tx(language, "智能深度分析", "AI Research Analysis")}</h1>
      <ApiKeyNotice />
      {demoMode && (
        <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">
          {tx(language, "当前展示固定演示报告，不调用 LLM、行情或 Kronos 模型。", "Showing a fixed demo report. LLM, market data, and Kronos models are not called.")}
        </div>
      )}

      <Card>
        <form onSubmit={handleSubmit} className="space-y-4">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={4}
            className="app-input min-h-36 resize-none px-4 py-3"
            placeholder={tx(language, `例如：帮我看看${DEFAULT_SYMBOL_NAME}现在能不能买`, `Example: can I still buy ${DEFAULT_SYMBOL_NAME} now?`)}
          />
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex min-w-0 flex-wrap gap-2">
              {examples.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setQuestion(item)}
                  className="min-h-11 rounded-full border border-border px-4 py-1.5 text-xs text-muted-foreground transition-all duration-200 hover:border-accent/40 hover:bg-accent/5 hover:text-accent"
                >
                  {item}
                </button>
              ))}
            </div>
            <Button type="submit" loading={displayLoading} className="w-full lg:w-auto">
              {tx(language, "开始分析", "Start Analysis")}
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={displayLoading}
              onClick={handleNewChat}
              className="w-full lg:w-auto"
            >
              {tx(language, "新建对话/清空本轮", "New Conversation / Clear")}
            </Button>
            {result && (
              <Button
                type="button"
                variant="secondary"
                loading={displayLoading}
                onClick={() => handleAnalyze(undefined, true)}
                className="w-full lg:w-auto"
              >
                {tx(language, "重新分析", "Rerun Analysis")}
              </Button>
            )}
          </div>
        </form>
      </Card>

      {(displayLoading || result) && (
        <Card>
          <CardTitle>{tx(language, "Agent 执行进度", "Agent Progress")}</CardTitle>
          <AgentProgress result={result} loading={displayLoading} loadingSteps={LOADING_STEPS} />
        </Card>
      )}

      {history.length > 1 && (
        <Card>
          <div className="mb-3 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
            <CardTitle>{tx(language, "本轮历史", "Current Session History")}</CardTitle>
            <p className="text-sm text-muted-foreground">
              {tx(language, `保留最近 ${MAX_ANALYSIS_TURNS} 轮临时结果，不写入长期记忆。`, `Keeps the latest ${MAX_ANALYSIS_TURNS} temporary results without long-term memory.`)}
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
                className="rounded-xl border border-border bg-card p-3 text-left transition-all duration-200 hover:border-accent/30 hover:shadow-accent-sm hover:-translate-y-0.5"
              >
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium text-foreground">
                    {item.symbols.length ? item.symbols.join(" / ") : tx(language, "待澄清", "Needs clarification")}
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {(item.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="line-clamp-2 text-xs text-muted-foreground">{item.question}</p>
              </button>
            ))}
          </div>
        </Card>
      )}

      {error && (
        <div className="rounded-xl border border-error/20 bg-error/5 p-4 text-sm text-error">
          <div className="flex items-start gap-3">
                        <svg className="mt-0.5 h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" /></svg>
            <span>{error}</span>
          </div>
        </div>
      )}

      {result && (
        <>
          <Card>
            <CardTitle>{tx(language, "汇总结论", "Summary Conclusion")}</CardTitle>
            <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-3 mb-2">
                  <CardTitle>{result.symbols.length ? result.symbols.join(" / ") : tx(language, "待澄清", "Needs clarification")}</CardTitle>
                  <span className="px-2 py-0.5 text-xs rounded bg-muted text-muted-foreground">
                    {tx(language, `${assetResults.length} 个标的`, `${assetResults.length} assets`)}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground">
                  {tx(language, "多标的请求按标的拆分展示，顶部仅保留整体比较结论。", "Multi-asset requests are split by asset below; the top keeps only the overall comparison.")}
                </p>
              </div>
              <RecommendationBadge rec={result.recommendation} />
            </div>

            <MarkdownText text={formatReportText(report?.conclusion)} />

            <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-3">
              <div>
                <p className="text-sm text-muted-foreground mb-1">{tx(language, "置信度", "Confidence")}</p>
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
                <p className="text-sm text-muted-foreground mb-1">{tx(language, "风险等级", "Risk Level")}</p>
                <RiskBadge level={result.risk_level} />
              </div>
              <div>
                <p className="text-sm text-muted-foreground mb-1">{tx(language, "时间", "Time")}</p>
                <p className="text-sm text-foreground font-mono">{result.timestamp.slice(0, 19)}</p>
              </div>
            </div>
          </Card>

          <Card>
            <CardTitle>{tx(language, "汇总研究报告", "Research Report")}</CardTitle>
            <ReportSection title={tx(language, "结论", "Conclusion")} value={report?.conclusion} />
            <ReportSection title={tx(language, "短期预测", "Short-Term Forecast")} value={report?.short_term_prediction} />
            <ReportSection title={tx(language, "技术面", "Technical View")} value={report?.technical} />
            <ReportSection title={tx(language, "基本面", "Fundamentals")} value={report?.fundamentals} />
            <ReportSection title={tx(language, "风险指标", "Risk Metrics")} value={report?.risk} />
            <ReportSection title={tx(language, "关键不确定性", "Key Uncertainties")} value={report?.uncertainties} />
            <MacroBackgroundDetails report={report} />
            <ReportSection title={tx(language, "非投资建议声明", "Not Investment Advice")} value={report?.disclaimer} />
          </Card>

          {assetResults.length > 0 && (
            <div className="space-y-4">
              <h2 className="text-xl font-semibold text-foreground">{tx(language, "各标的分析", "Asset-Level Analysis")}</h2>
              {assetResults.map((asset) => (
                <AssetAnalysisCard key={`${asset.market}-${asset.symbol}`} asset={asset} />
              ))}
            </div>
          )}

          <EvidenceGraphViewer result={result} />

          <Card>
            <CardTitle>{tx(language, "依据与工具调用", "Evidence and Tool Calls")}</CardTitle>
            {/* Legacy test anchor: ReportSection title="依据" */}
            <ReportSection title={tx(language, "依据", "Evidence")} value={buildEvidenceSummary(result)} />
            {result.tool_calls.length > 0 && (
              <div className="pt-4">
                <ToolCallList result={result} />
              </div>
            )}
          </Card>
        </>
      )}

      {!result && !error && !displayLoading && (
        <Card>
          <div className="flex flex-col items-center py-16 text-center">
            <p className="text-lg font-semibold text-foreground mb-2">{tx(language, "输入一个自然语言问题", "Enter a natural-language question")}</p>
            <p className="text-sm text-muted-foreground">{tx(language, "例如：帮我看看招商银行现在能不能买。", "Example: can I still buy China Merchants Bank now?")}</p>
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
