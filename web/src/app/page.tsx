"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Card, CardTitle, CardStat, CardGrid } from "@/components/ui/Card";
import { SectionLabel } from "@/components/ui/SectionLabel";
import { api } from "@/lib/api";
import { useAppStore } from "@/stores/app";
import { formatDuration } from "@/lib/utils";
import { fadeInUp, stagger, viewportOnce } from "@/lib/animations";
import type { HealthResponse } from "@/types/api";

const quickLinks = [
  { href: "/forecast", label: "预测", desc: "单标的 Kronos 预测", icon: "📈" },
  { href: "/analysis", label: "分析", desc: "AI 深度分析", icon: "🤖" },
  { href: "/macro", label: "宏观洞察", desc: "宏观信号与证据", icon: "🌐" },
  { href: "/watchlist", label: "自选股", desc: "研究工作台", icon: "⭐" },
  { href: "/batch", label: "批量对比", desc: "多标的排序", icon: "📊" },
  { href: "/backtest", label: "回测", desc: "组合策略验证", icon: "🔄" },
  { href: "/data", label: "数据", desc: "行情与指标", icon: "📡" },
  { href: "/settings", label: "设置", desc: "诊断与偏好", icon: "⚙️" },
  { href: "/alerts", label: "告警", desc: "监控规则", icon: "🔔" },
];

export default function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [recentResults, setRecentResults] = useState<string[]>([]);
  const { watchlist } = useAppStore();
  const watchlistQuotes = useMemo(() => watchlist.slice(0, 6), [watchlist]);

  useEffect(() => { api.health().then(setHealth).catch(() => {}); }, []);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const keys = Object.keys(window.sessionStorage)
      .filter((key) => key.startsWith("kronos-"))
      .slice(0, 8);
    setRecentResults(keys);
  }, []);

  const shortCommit =
    health?.build_commit && health.build_commit !== "unknown"
      ? health.build_commit.slice(0, 7)
      : "unknown";
  const deployedVersion = health?.app_version || health?.version || "-";
  const isOnline = health?.status === "ok";

  return (
    <div className="page-shell space-y-8">
      {/* ── Hero Section ── */}
      <motion.div
        variants={stagger}
        initial="hidden"
        animate="visible"
        className="hero-gradient -mx-4 -mt-5 px-4 pb-6 pt-10 md:-mx-6 md:-mt-6 md:px-6 md:pb-10 md:pt-14"
      >
        <motion.div variants={fadeInUp}>
          <SectionLabel>KronosFinceptLab</SectionLabel>
        </motion.div>

        <motion.div variants={fadeInUp} className="mt-4 max-w-2xl">
          <h1 className="page-title font-display text-3xl leading-tight tracking-tight sm:text-4xl md:text-5xl">
            <span className="gradient-text">Kronos</span>
            <span className="text-foreground"> 量化研究平台</span>
          </h1>
          <p className="mt-3 text-base text-muted-foreground sm:text-lg">
            AI 驱动的金融量化分析 — 从单标的预测到宏观洞察，一站式研究工具链。
          </p>
        </motion.div>

        {/* Status chip */}
        <motion.div variants={fadeInUp} className="mt-5">
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2 text-sm shadow-sm">
            <span
              className={`h-2.5 w-2.5 rounded-full animate-pulse-dot ${
                isOnline ? "bg-success" : "bg-error"
              }`}
            />
            <span className="text-muted-foreground">
              {isOnline ? "API 在线" : "API 离线"}
            </span>
            <span className="text-border">·</span>
            <span className="font-mono text-xs text-muted-foreground">
              {deployedVersion}
            </span>
            <span className="text-border">·</span>
            <span className="font-mono text-xs text-muted-foreground">
              {health?.device || "cpu"}
            </span>
          </div>
        </motion.div>
      </motion.div>

      {/* ── Stats Grid ── */}
      <CardGrid className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6 lg:gap-4">
        <Card index={0}>
          <CardStat
            label="API 状态"
            value={isOnline ? "在线" : "离线"}
            color={isOnline ? "text-success" : "text-error"}
          />
        </Card>
        <Card index={1}>
          <CardStat label="部署版本" value={deployedVersion} />
          <p className="mt-1 break-all font-mono text-xs text-muted-foreground">
            {health?.build_ref || "-"} · {health?.build_source || "-"}
          </p>
        </Card>
        <Card index={2}>
          <CardStat label="提交" value={shortCommit} />
        </Card>
        <Card index={3}>
          <CardStat
            label="模型"
            value={health?.model_id?.split("/").pop() || "-"}
          />
        </Card>
        <Card index={4}>
          <CardStat label="设备" value={health?.device || "-"} />
        </Card>
        <Card index={5}>
          <CardStat
            label="运行时间"
            value={health ? formatDuration(health.uptime_seconds) : "-"}
          />
        </Card>
      </CardGrid>

      {/* ── Quick Links ── */}
      <Card featured>
        <CardTitle subtitle="选择工具开始分析">快捷入口</CardTitle>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
          {quickLinks.map((link, i) => (
            <Link
              key={link.href}
              href={link.href}
              className="group flex min-h-[5rem] items-start gap-3 rounded-xl border border-border bg-muted p-4 transition-all duration-300 hover:border-accent/30 hover:bg-muted/80 hover:shadow-accent-sm"
            >
              <span className="mt-0.5 text-xl">{link.icon}</span>
              <div className="min-w-0">
                <h3 className="font-semibold text-foreground group-hover:text-accent transition-colors">
                  {link.label}
                </h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {link.desc}
                </p>
              </div>
            </Link>
          ))}
        </div>
      </Card>

      {/* ── Bottom Grid ── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardTitle subtitle={watchlistQuotes.length ? `${watchlistQuotes.length} 个标的` : undefined}>
            自选股快照
          </CardTitle>
          {watchlistQuotes.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              暂无自选股，去
              <Link href="/watchlist" className="text-accent hover:underline mx-1">
                自选股页面
              </Link>
              添加。
            </p>
          ) : (
            <div className="space-y-1">
              {watchlistQuotes.map((item) => (
                <div
                  key={`${item.market}:${item.symbol}`}
                  className="flex items-center justify-between rounded-lg px-3 py-2.5 transition-colors hover:bg-muted"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="font-mono text-sm font-bold text-foreground shrink-0">
                      {item.symbol}
                    </span>
                    <span className="text-xs text-muted-foreground uppercase">
                      {item.market}
                    </span>
                  </div>
                  <Link
                    href={`/analysis?symbol=${item.symbol}&market=${item.market}`}
                    className="text-xs font-medium text-accent hover:underline shrink-0"
                  >
                    分析 →
                  </Link>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <CardTitle subtitle={recentResults.length ? `${recentResults.length} 个缓存` : undefined}>
            最近结果
          </CardTitle>
          {recentResults.length === 0 ? (
            <p className="text-sm text-muted-foreground">暂无本地缓存结果。</p>
          ) : (
            <ul className="space-y-1">
              {recentResults.map((key) => (
                <li
                  key={key}
                  className="rounded-lg px-3 py-2 font-mono text-xs text-muted-foreground transition-colors hover:bg-muted"
                >
                  {key}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* ── Footer ── */}
      <motion.div
        variants={fadeInUp}
        initial="hidden"
        whileInView="visible"
        viewport={viewportOnce}
        className="py-6 text-center"
      >
        <div className="divider-accent" />
        <p className="text-xs text-muted-foreground">
          仅供研究参考，不构成投资建议 · KronosFinceptLab v10.8.8
        </p>
      </motion.div>
    </div>
  );
}
