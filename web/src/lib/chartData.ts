import type { AreaData, CandlestickData, LineData, Time } from "lightweight-charts";
import type { BacktestResponse, ForecastRow } from "@/types/api";

const DEFAULT_MAX_POINTS = 420;

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function normalizeDate(raw: string): string {
  const text = String(raw || "").trim();
  const compact = text.match(/^(\d{4})(\d{2})(\d{2})/);
  if (compact) {
    return `${compact[1]}-${compact[2]}-${compact[3]}`;
  }
  const isoLike = text.match(/^(\d{4})[-/](\d{2})[-/](\d{2})/);
  if (isoLike) {
    return `${isoLike[1]}-${isoLike[2]}-${isoLike[3]}`;
  }
  return text.slice(0, 10);
}

export function toChartTime(timestamp: string, baseDate?: string): Time {
  const match = String(timestamp).match(/^D(\d+)$/);
  if (!match) {
    return normalizeDate(timestamp) as Time;
  }

  const days = Number.parseInt(match[1], 10);
  const base = baseDate ? new Date(normalizeDate(baseDate)) : new Date();
  base.setDate(base.getDate() + days);
  return base.toISOString().slice(0, 10) as Time;
}

export function sampleChartRows<T>(rows: T[], maxPoints = DEFAULT_MAX_POINTS): T[] {
  if (rows.length <= maxPoints) return rows;
  const step = Math.ceil(rows.length / maxPoints);
  const sampled = rows.filter((_, index) => index % step === 0);
  const last = rows[rows.length - 1];
  return sampled[sampled.length - 1] === last ? sampled : [...sampled, last];
}

export function toCandlestickSeriesData(
  rows: ForecastRow[],
  maxPoints = DEFAULT_MAX_POINTS
): CandlestickData[] {
  return sampleChartRows(rows, maxPoints)
    .filter((row) =>
      isFiniteNumber(row.open) &&
      isFiniteNumber(row.high) &&
      isFiniteNumber(row.low) &&
      isFiniteNumber(row.close)
    )
    .map((row) => ({
      time: toChartTime(row.timestamp),
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
    }));
}

export function toForecastLineData(
  history: ForecastRow[],
  forecast: ForecastRow[],
  maxPoints = 160
): LineData[] {
  const latest = history[history.length - 1];
  const baseDate = latest?.timestamp;
  const points: LineData[] = [];

  if (latest && isFiniteNumber(latest.close)) {
    points.push({
      time: toChartTime(latest.timestamp),
      value: latest.close,
    });
  }

  sampleChartRows(forecast, maxPoints)
    .filter((row) => isFiniteNumber(row.close))
    .forEach((row) => {
      points.push({
        time: toChartTime(row.timestamp, baseDate),
        value: row.close,
      });
    });

  const byTime = new Map<string, LineData>();
  points.forEach((point) => byTime.set(String(point.time), point));
  return Array.from(byTime.values());
}

export function toEquityAreaData(
  equityCurve: BacktestResponse["equity_curve"],
  maxPoints = 720
): AreaData[] {
  return sampleChartRows(equityCurve, maxPoints)
    .filter((point) => isFiniteNumber(point.equity))
    .map((point) => ({
      time: toChartTime(point.date),
      value: point.equity,
    }));
}

export interface ReturnBarDatum {
  name: string;
  value: number;
  fill: string;
}

export function toReturnBarData(
  data: Array<{ name: string; return: number; fill: string }>,
  maxPoints = 24
): ReturnBarDatum[] {
  return sampleChartRows(data, maxPoints)
    .filter((item) => isFiniteNumber(item.return))
    .map((item) => ({
      name: item.name,
      value: item.return,
      fill: item.fill,
    }));
}
