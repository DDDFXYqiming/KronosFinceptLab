"use client";

import { useEffect, useMemo, useRef } from "react";
import { ColorType, CrosshairMode, createChart } from "lightweight-charts";
import type { IChartApi, ISeriesApi } from "lightweight-charts";
import { sampleChartRows, toChartTime } from "@/lib/chartData";
import type { ForecastRow } from "@/types/api";

interface PriceLineChartProps {
  rows: ForecastRow[];
  title?: string;
}

export function PriceLineChart({ rows, title = "收盘价走势" }: PriceLineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const lineSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const chartData = useMemo(
    () =>
      sampleChartRows(rows, 420)
        .filter((row) => Number.isFinite(row.close))
        .map((row) => ({ time: toChartTime(row.timestamp), value: row.close })),
    [rows]
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container || chartData.length === 0) return;

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: "#0A0E1A" },
        textColor: "#9CA3AF",
      },
      grid: {
        vertLines: { color: "#1F2937" },
        horzLines: { color: "#1F2937" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { borderColor: "#374151", timeVisible: true },
      rightPriceScale: { borderColor: "#374151" },
      width: container.clientWidth,
      height: container.clientHeight,
    });

    chartRef.current = chart;
    const series = chart.addLineSeries({
      color: "#10B981",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    lineSeriesRef.current = series;
    series.setData(chartData);
    chart.timeScale().fitContent();

    const resizeObserver = new ResizeObserver(([entry]) => {
      chart.applyOptions({
        width: Math.floor(entry.contentRect.width),
        height: Math.floor(entry.contentRect.height),
      });
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      lineSeriesRef.current = null;
    };
  }, [chartData]);

  if (chartData.length === 0) {
    return (
      <div className="chart-frame flex h-72 items-center justify-center text-sm text-muted-foreground md:h-80">
        暂无{title}数据
      </div>
    );
  }

  return <div ref={containerRef} className="chart-frame h-72 md:h-80" aria-label={title} />;
}
