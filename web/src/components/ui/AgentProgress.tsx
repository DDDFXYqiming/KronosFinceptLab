"use client";

import { useEffect, useRef, useState } from "react";
import type { AgentStep } from "@/types/api";

type AgentProgressResult = {
  steps?: AgentStep[] | null;
} | null;

type AgentProgressProps = {
  loading: boolean;
  result: AgentProgressResult;
  loadingSteps: string[];
  expectedDurationMs?: number;
};

const LIVE_PROGRESS_CEILING = 92;
const LIVE_PROGRESS_FLOOR = 4;
const DEFAULT_EXPECTED_DURATION_MS = 45_000;

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
    estimated: "已推进",
  };
  return labels[status] || status;
}

function isFinishedStepStatus(status: string): boolean {
  return ["completed", "fallback", "skipped"].includes(status);
}

function isFailedStepStatus(status: string): boolean {
  return ["failed", "blocked"].includes(status);
}

function isEstimatedStepStatus(status: string): boolean {
  return status === "estimated";
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function liveTargetProgress(elapsedMs: number, expectedDurationMs: number): number {
  const duration = Math.max(expectedDurationMs, 5_000);
  const eased = 1 - Math.exp(-elapsedMs / duration);
  return clamp(LIVE_PROGRESS_FLOOR + (LIVE_PROGRESS_CEILING - LIVE_PROGRESS_FLOOR) * eased, LIVE_PROGRESS_FLOOR, LIVE_PROGRESS_CEILING);
}

function useLiveProgress(loading: boolean, hasResult: boolean, expectedDurationMs: number): number {
  const startedAtRef = useRef<number | null>(null);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (hasResult) {
      startedAtRef.current = null;
      setProgress(100);
      return;
    }
    if (!loading) {
      startedAtRef.current = null;
      setProgress(0);
      return;
    }

    startedAtRef.current = Date.now();
    setProgress(LIVE_PROGRESS_FLOOR);
    const timer = window.setInterval(() => {
      const startedAt = startedAtRef.current ?? Date.now();
      const elapsedMs = Date.now() - startedAt;
      const target = liveTargetProgress(elapsedMs, expectedDurationMs);
      setProgress((current) => Math.max(current, target));
    }, 250);

    return () => window.clearInterval(timer);
  }, [expectedDurationMs, hasResult, loading]);

  return progress;
}

function buildLiveSteps(names: string[], progressPercent: number): AgentStep[] {
  const stepCount = Math.max(names.length, 1);
  const liveRatio = clamp(progressPercent / LIVE_PROGRESS_CEILING, 0, 0.999);
  const activeIndex = clamp(Math.floor(liveRatio * stepCount), 0, stepCount - 1);

  return names.map((name, index) => ({
    name,
    status: index < activeIndex ? "estimated" : index === activeIndex ? "running" : "pending",
    summary: "",
    elapsed_ms: 0,
  }));
}

export function AgentProgress({ loading, result, loadingSteps, expectedDurationMs = DEFAULT_EXPECTED_DURATION_MS }: AgentProgressProps) {
  const hasResult = Boolean(result);
  const liveProgress = useLiveProgress(loading, hasResult, expectedDurationMs);
  const resultSteps = result?.steps?.length ? result.steps : null;
  const steps = resultSteps ?? buildLiveSteps(loadingSteps, liveProgress);
  const completedCount = resultSteps ? steps.filter((step) => isFinishedStepStatus(step.status) || isFailedStepStatus(step.status)).length : 0;
  const progressPercent = resultSteps ? 100 : liveProgress;
  const progressText = resultSteps
    ? `进度 ${Math.min(completedCount, steps.length)}/${steps.length}`
    : `进度 ${Math.round(progressPercent)}%`;
  const statusText = resultSteps ? "已完成" : loading ? "正在处理…" : "等待开始";

  return (
    <div className="space-y-3" data-agent-progress>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">{progressText}</p>
        <p className="text-xs text-muted-foreground">{statusText}</p>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          data-agent-progress-bar
          className="h-full rounded-full bg-accent transition-[width] duration-700 ease-out"
          style={{ width: `${clamp(progressPercent, 0, 100)}%` }}
        />
      </div>

      <div className="table-scroll">
        <div className="grid grid-flow-col auto-cols-[minmax(9.5rem,1fr)] gap-2 pb-1 sm:auto-cols-[minmax(12rem,1fr)]">
          {steps.map((step, index) => {
            const failed = isFailedStepStatus(step.status);
            const completed = isFinishedStepStatus(step.status);
            const estimated = isEstimatedStepStatus(step.status);
            const running = step.status === "running";
            return (
              <div
                key={`${step.name}-${index}`}
                className={`rounded-lg border px-3 py-2 ${
                  failed
                    ? "border-red-200 bg-red-50"
                    : completed
                      ? "border-green-200 bg-green-50"
                      : estimated
                        ? "border-blue-100 bg-blue-50/60"
                      : running
                        ? "border-blue-200 bg-blue-50"
                        : "border-border bg-muted"
                }`}
                title={step.summary || step.name}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
                      failed
                        ? "bg-red-100 text-red-700"
                        : completed
                          ? "bg-green-100 text-green-700"
                          : estimated
                            ? "bg-blue-100 text-blue-700"
                          : running
                            ? "bg-blue-100 text-blue-700"
                            : "bg-background text-muted-foreground"
                    }`}
                  >
                    {index + 1}
                  </span>
                  <span className="line-clamp-1 text-sm font-semibold text-foreground">{step.name}</span>
                </div>
                <p className="mt-1 font-mono text-xs text-muted-foreground">
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
