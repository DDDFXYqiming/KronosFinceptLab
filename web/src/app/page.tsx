"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Card, CardTitle, CardStat } from "@/components/ui/Card";
import { api } from "@/lib/api";
import { useAppStore } from "@/stores/app";
import { formatDuration } from "@/lib/utils";
import type { HealthResponse } from "@/types/api";

const quickLinks = [
  { href: "/forecast", label: "预测", desc: "单标的 Kronos 预测" },
  { href: "/analysis", label: "分析", desc: "AI 深度分析" },
  { href: "/macro", label: "宏观洞察", desc: "宏观信号与证据" },
  { href: "/watchlist", label: "自选股", desc: "研究工作台" },
  { href: "/batch", label: "批量对比", desc: "多标的排序" },
  { href: "/backtest", label: "回测", desc: "组合策略验证" },
  { href: "/data", label: "数据", desc: "行情与指标" },
  { href: "/settings", label: "设置", desc: "诊断与偏好" },
  { href: "/alerts", label: "告警", desc: "监控规则" },
];

export default function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [recentResults, setRecentResults] = useState<string[]>([]);
  const { watchlist } = useAppStore();
  const watchlistQuotes = useMemo(() => watchlist.slice(0, 6), [watchlist]);

  useEffect(() => { api.health().then(setHealth).catch(() => {}); }, []);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const keys = Object.keys(window.sessionStorage).filter((key) => key.startsWith("kronos-")).slice(0, 8);
    setRecentResults(keys);
  }, []);

  const shortCommit = health?.build_commit && health.build_commit !== "unknown" ? health.build_commit.slice(0, 7) : "unknown";
  const deployedVersion = health?.app_version || health?.version || "-";

  return (
    <div className="page-shell space-y-6">
      <div className="flex min-w-0 items-center justify-between gap-3"><h1 className="page-title">仪表盘</h1><div className="flex shrink-0 items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-sm"><div className={`h-2 w-2 rounded-full ${health?.status === "ok" ? "bg-success" : "bg-error"}`} /><span className="text-muted-foreground">{health?.status === "ok" ? "API 在线" : "API 离线"}</span></div></div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6 lg:gap-4"><Card><CardStat label="API 状态" value={health?.status === "ok" ? "在线" : "离线"} color={health?.status === "ok" ? "text-success" : "text-error"} /></Card><Card><CardStat label="部署版本" value={deployedVersion} /><p className="mt-1 break-all text-xs text-muted-foreground">{health?.build_ref || "-"} · {health?.build_source || "-"}</p></Card><Card><CardStat label="提交" value={shortCommit} /></Card><Card><CardStat label="模型" value={health?.model_id?.split("/").pop() || "-"} /></Card><Card><CardStat label="设备" value={health?.device || "-"} /></Card><Card><CardStat label="运行时间" value={health ? formatDuration(health.uptime_seconds) : "-"} /></Card></div>
      <Card><CardTitle>快捷入口</CardTitle><div className="grid grid-cols-1 gap-4 md:grid-cols-3">{quickLinks.map((link) => <Link key={link.href} href={link.href} className="min-h-24 rounded-xl border border-border bg-muted p-4 transition hover:border-accent/20 hover:bg-muted/80"><h3 className="font-semibold text-accent">{link.label}</h3><p className="mt-1 text-sm text-muted-foreground">{link.desc}</p></Link>)}</div></Card>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2"><Card><CardTitle>自选股快照</CardTitle>{watchlistQuotes.length === 0 ? <p className="text-sm text-muted-foreground">暂无自选股，去自选股页面添加。</p> : <div className="space-y-2">{watchlistQuotes.map((item) => <div key={`${item.market}:${item.symbol}`} className="flex items-center justify-between rounded-lg bg-muted p-3"><span className="font-mono font-bold">{item.symbol}</span><span className="text-xs text-muted-foreground">{item.market}</span><Link href={`/analysis?symbol=${item.symbol}&market=${item.market}`} className="text-xs text-accent hover:underline">分析</Link></div>)}</div>}</Card><Card><CardTitle>最近结果</CardTitle>{recentResults.length === 0 ? <p className="text-sm text-muted-foreground">暂无本地缓存结果。</p> : <ul className="space-y-2 text-sm">{recentResults.map((key) => <li key={key} className="rounded bg-muted p-2 font-mono text-xs">{key}</li>)}</ul>}</Card></div>
      <div className="py-4 text-center text-xs text-muted-foreground">仅供研究参考，不构成投资建议。</div>
    </div>
  );
}
