"use client";

import { useMemo } from "react";
import { toReturnBarData } from "@/lib/chartData";

interface ReturnComparisonChartProps {
  data: Array<{ name: string; return: number; fill: string }>;
}

export function ReturnComparisonChart({ data }: ReturnComparisonChartProps) {
  const bars = useMemo(() => toReturnBarData(data), [data]);

  if (bars.length === 0) {
    return (
      <div className="chart-frame flex h-72 items-center justify-center text-sm text-muted-foreground">
        暂无预测收益率数据
      </div>
    );
  }

  const width = 960;
  const height = 288;
  const padding = { top: 20, right: 24, bottom: 46, left: 52 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const values = bars.map((bar) => bar.value);
  const minValue = Math.min(0, ...values);
  const maxValue = Math.max(0, ...values);
  const range = maxValue - minValue || 1;
  const zeroY = padding.top + ((maxValue - 0) / range) * plotHeight;
  const step = plotWidth / bars.length;
  const barWidth = Math.max(12, Math.min(42, step * 0.56));

  return (
    <div className="chart-frame h-72 overflow-x-auto">
      <svg
        role="img"
        aria-label="预测收益率对比图"
        viewBox={`0 0 ${width} ${height}`}
        className="h-full min-w-[42rem] w-full"
      >
        <line
          x1={padding.left}
          y1={zeroY}
          x2={width - padding.right}
          y2={zeroY}
          stroke="#374151"
          strokeWidth="1"
        />
        <text x={padding.left - 10} y={padding.top + 4} textAnchor="end" fill="#9CA3AF" fontSize="12">
          {maxValue.toFixed(1)}%
        </text>
        <text x={padding.left - 10} y={zeroY + 4} textAnchor="end" fill="#9CA3AF" fontSize="12">
          0%
        </text>
        <text x={padding.left - 10} y={padding.top + plotHeight} textAnchor="end" fill="#9CA3AF" fontSize="12">
          {minValue.toFixed(1)}%
        </text>
        {bars.map((bar, index) => {
          const x = padding.left + index * step + (step - barWidth) / 2;
          const valueY = padding.top + ((maxValue - bar.value) / range) * plotHeight;
          const y = Math.min(valueY, zeroY);
          const h = Math.max(2, Math.abs(zeroY - valueY));
          return (
            <g key={bar.name}>
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={h}
                rx="4"
                fill={bar.fill}
                opacity="0.88"
              >
                <title>{`${bar.name}: ${bar.value.toFixed(2)}%`}</title>
              </rect>
              <text
                x={x + barWidth / 2}
                y={bar.value >= 0 ? y - 6 : y + h + 14}
                textAnchor="middle"
                fill={bar.value >= 0 ? "#10B981" : "#EF4444"}
                fontSize="12"
                fontWeight="600"
              >
                {bar.value >= 0 ? "+" : ""}
                {bar.value.toFixed(1)}%
              </text>
              <text
                x={x + barWidth / 2}
                y={height - 18}
                textAnchor="middle"
                fill="#9CA3AF"
                fontSize="12"
                fontFamily="monospace"
              >
                {bar.name}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
