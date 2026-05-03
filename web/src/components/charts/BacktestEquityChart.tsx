"use client";

import { useEffect, useMemo, useRef } from "react";
import { ColorType, CrosshairMode, createChart } from "lightweight-charts";
import type { IChartApi, ISeriesApi } from "lightweight-charts";
import { toEquityAreaData } from "@/lib/chartData";
import { formatNumber } from "@/lib/utils";
import type { BacktestResponse } from "@/types/api";

interface BacktestEquityChartProps {
  equityCurve: BacktestResponse["equity_curve"];
}

export function BacktestEquityChart({ equityCurve }: BacktestEquityChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const areaSeriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const chartData = useMemo(() => toEquityAreaData(equityCurve), [equityCurve]);
  const firstPoint = chartData[0];
  const lastPoint = chartData[chartData.length - 1];

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
      timeScale: {
        borderColor: "#374151",
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: "#374151",
      },
      width: container.clientWidth,
      height: container.clientHeight,
    });

    chartRef.current = chart;
    const areaSeries = chart.addAreaSeries({
      lineColor: "#0052FF",
      topColor: "rgba(0, 82, 255, 0.32)",
      bottomColor: "rgba(0, 82, 255, 0.02)",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    areaSeriesRef.current = areaSeries;
    areaSeries.setData(chartData);
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
      areaSeriesRef.current = null;
    };
  }, [chartData]);

  if (chartData.length === 0) {
    return (
      <div className="chart-frame flex h-72 items-center justify-center text-sm text-muted-foreground md:h-80">
        暂无权益曲线数据
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div ref={containerRef} className="chart-frame h-72 md:h-80" />
      <div className="grid grid-cols-2 gap-3 text-xs text-muted-foreground md:grid-cols-4">
        <span>起点 {String(firstPoint?.time || "-")}</span>
        <span>终点 {String(lastPoint?.time || "-")}</span>
        <span>初始权益 {formatNumber(firstPoint?.value || 0, 0)}</span>
        <span>最新权益 {formatNumber(lastPoint?.value || 0, 0)}</span>
      </div>
    </div>
  );
}
