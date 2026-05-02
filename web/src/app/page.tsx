"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardTitle, CardStat } from "@/components/ui/Card";
import { api } from "@/lib/api";
import { useAppStore } from "@/stores/app";
import { formatDuration } from "@/lib/utils";
import type { HealthResponse } from "@/types/api";

export default function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const { watchlist } = useAppStore();

  useEffect(() => {
    api.health().then(setHealth).catch(() => {});
  }, []);

  const quickLinks = [
    { href: "/forecast", label: "预测", desc: "预测股票价格走势" },
    { href: "/analysis", label: "分析", desc: "AI 智能分析" },
    { href: "/batch", label: "批量对比", desc: "多标的对比" },
  ];

  return (
    <div className="page-shell space-y-6">
      <div className="flex min-w-0 items-center justify-between gap-3">
        <h1 className="page-title">仪表盘</h1>
        <div className="flex shrink-0 items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-sm">
          <div
            className={`w-2 h-2 rounded-full animate-pulse-dot ${
              health?.status === "ok" ? "bg-success" : "bg-error"
            }`}
          />
          <span className="text-muted-foreground">
            {health?.status === "ok" ? "API 在线" : "API 离线"}
          </span>
        </div>
      </div>

      {/* System Stats */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
        <Card>
            <CardStat
              label="API 状态"
              value={health?.status === "ok" ? "在线" : "离线"}
            color={health?.status === "ok" ? "text-success" : "text-error"}
          />
        </Card>
        <Card>
          <CardStat label="模型" value={health?.model_id?.split("/").pop() || "-"} />
        </Card>
        <Card>
          <CardStat label="设备" value={health?.device || "-"} />
        </Card>
        <Card>
          <CardStat
            label="运行时间"
            value={health ? formatDuration(health.uptime_seconds) : "-"}
          />
        </Card>
      </div>

      {/* Watchlist */}
      <Card>
        <CardTitle>自选股</CardTitle>
        {watchlist.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <p className="mb-2">暂无自选股</p>
            <Link href="/watchlist" className="text-accent hover:underline text-sm">
              点击添加自选股
            </Link>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="min-w-[28rem] w-full text-sm">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  <th className="py-2 text-left">代码</th>
                  <th className="py-2 text-left">市场</th>
                  <th className="py-2 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {watchlist.map((item) => (
                  <tr key={item.symbol} className="border-b border-border hover:bg-muted">
                    <td className="py-2 font-mono">{item.symbol}</td>
                    <td className="py-2">
                      <span className="px-2 py-0.5 text-xs rounded-full bg-muted text-muted-foreground border border-border">
                        {item.market}
                      </span>
                    </td>
                    <td className="py-2 text-right">
                      <Link
                        href={`/forecast?symbol=${item.symbol}`}
                        className="text-accent hover:underline text-xs"
                      >
                        预测
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Quick Links */}
      <Card>
        <CardTitle>快捷入口</CardTitle>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {quickLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="min-h-24 p-4 rounded-xl bg-muted border border-border hover:bg-muted/80 hover:border-accent/20 transition-all duration-200"
            >
              <h3 className="font-semibold text-accent">{link.label}</h3>
              <p className="text-sm text-muted-foreground mt-1">{link.desc}</p>
            </Link>
          ))}
        </div>
      </Card>

      {/* Disclaimer */}
      <div className="text-center text-xs text-muted-foreground py-4">
        仅供研究参考，不构成投资建议。
      </div>
    </div>
  );
}
