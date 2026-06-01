"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Card, CardTitle, CardStat, CardGrid } from "@/components/ui/Card";
import { SectionLabel } from "@/components/ui/SectionLabel";
import { ApiKeyNotice } from "@/components/ui/ApiKeyNotice";
import { api } from "@/lib/api";
import { useAppStore } from "@/stores/app";
import type { Language } from "@/lib/i18n";
import { formatDuration } from "@/lib/utils";
import { fadeInUp, stagger, viewportOnce } from "@/lib/animations";
import type { HealthResponse } from "@/types/api";

function tx(language: Language, zh: string, en: string): string {
  return language === "en-US" ? en : zh;
}

function quickLinks(language: Language) {
  return [
    { href: "/forecast", label: tx(language, "预测", "Forecast"), desc: tx(language, "单标的 Kronos 预测", "Single-asset Kronos forecast") },
    { href: "/analysis", label: tx(language, "分析", "Analysis"), desc: tx(language, "AI 深度分析", "AI research report") },
    { href: "/macro", label: tx(language, "宏观洞察", "Macro"), desc: tx(language, "宏观信号与证据", "Macro signals and evidence") },
    { href: "/news", label: tx(language, "新闻", "News"), desc: tx(language, "RSS 聚合", "RSS aggregation") },
    { href: "/watchlist", label: tx(language, "自选股", "Watchlist"), desc: tx(language, "研究工作台", "Research workspace") },
    { href: "/batch", label: tx(language, "批量对比", "Batch"), desc: tx(language, "多标的排序", "Multi-asset ranking") },
    { href: "/backtest", label: tx(language, "回测", "Backtest"), desc: tx(language, "组合策略验证", "Portfolio strategy test") },
    { href: "/data", label: tx(language, "数据", "Data"), desc: tx(language, "行情与指标", "Quotes and indicators") },
    { href: "/settings", label: tx(language, "设置", "Settings"), desc: tx(language, "诊断与偏好", "Diagnostics and preferences") },
    { href: "/alerts", label: tx(language, "告警", "Alerts"), desc: tx(language, "监控规则", "Monitoring rules") },
  ];
}

export default function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [recentResults, setRecentResults] = useState<string[]>([]);
  const { watchlist, preferences } = useAppStore();
  const language = preferences.language;
  const links = useMemo(() => quickLinks(language), [language]);
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
  const isLlmConfigured = health?.model_loaded === true || Boolean(health?.model_id);

  return (
    <div className="page-shell space-y-8">
      {/* ── Hero ── */}
      <motion.div
        variants={stagger}
        initial="hidden"
        animate="visible"
        className="-mx-4 -mt-5 px-4 pb-8 pt-12 md:-mx-6 md:-mt-6 md:px-6 md:pb-12 md:pt-16"
      >
        <motion.div variants={fadeInUp}>
          <SectionLabel>KronosFinceptLab</SectionLabel>
        </motion.div>

        <motion.div variants={fadeInUp} className="mt-5 max-w-2xl">
          <h1 className="page-title font-display text-3xl leading-tight tracking-tight sm:text-4xl md:text-[3.25rem]">
            <span className="gradient-text">Kronos</span>
            <span className="text-foreground"> {tx(language, "量化研究平台", "Quant Research Platform")}</span>
          </h1>
          <p className="mt-4 max-w-lg text-base leading-relaxed text-muted-foreground sm:text-lg">
            {tx(language, "AI 驱动的金融量化分析，从单标的预测到宏观洞察，一站式研究工具链。", "AI-powered quantitative finance research, from single-asset forecasts to macro insight in one workspace.")}
          </p>
        </motion.div>

        <motion.div variants={fadeInUp} className="mt-6">
          <div className="inline-flex items-center gap-2.5 rounded-full border border-border bg-card px-4 py-2 text-sm shadow-sm">
            <span className={`h-2.5 w-2.5 rounded-full animate-pulse-dot ${isOnline ? "bg-success" : "bg-error"}`} />
            <span className="text-muted-foreground">{isOnline ? tx(language, "API 在线", "API online") : tx(language, "API 离线", "API offline")}</span>
            <span className="text-border select-none">|</span>
            <span className="font-mono text-xs text-muted-foreground">{deployedVersion}</span>
            <span className="text-border select-none">|</span>
            <span className="font-mono text-xs text-muted-foreground">{health?.device || "cpu"}</span>
            <span className="text-border select-none">|</span>
            <span className={`h-2.5 w-2.5 rounded-full animate-pulse-dot ${isLlmConfigured ? "bg-success" : "bg-error"}`} />
            <span className="text-muted-foreground">{isLlmConfigured ? tx(language, "LLM 已配置", "LLM configured") : tx(language, "LLM 未配置", "LLM not configured")}</span>
          </div>
        </motion.div>
      </motion.div>

      <ApiKeyNotice />

      {/* ── Stats ── */}
      <CardGrid className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6 lg:gap-4">
        <Card index={0}><CardStat label={tx(language, "API 状态", "API status")} value={isOnline ? tx(language, "在线", "Online") : tx(language, "离线", "Offline")} color={isOnline ? "text-success" : "text-error"} /></Card>
        <Card index={1}><CardStat label={tx(language, "部署版本", "Version")} value={deployedVersion} /><p className="mt-1 font-mono text-xs text-muted-foreground">{health?.build_ref || "-"} &middot; {health?.build_source || "-"}</p></Card>
        <Card index={2}><CardStat label={tx(language, "提交", "Commit")} value={shortCommit} /></Card>
        <Card index={3}><CardStat label={tx(language, "模型", "Model")} value={(health?.model_id || health?.default_model_id)?.split("/").pop() || "-"} /></Card>
        <Card index={4}><CardStat label={tx(language, "设备", "Device")} value={health?.device || "-"} /></Card>
        <Card index={5}><CardStat label={tx(language, "运行时间", "Uptime")} value={health ? formatDuration(health.uptime_seconds) : "-"} /></Card>
      </CardGrid>

      {/* ── Data Source Availability ── */}
      <Card>
        <CardTitle subtitle={tx(language, "数据接入与模型状态", "Data access and model status")}>{tx(language, "数据源可用性", "Data Source Availability")}</CardTitle>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-4">
            <span className={`h-3 w-3 rounded-full ${isOnline ? "bg-success" : "bg-error"}`} />
            <span className="text-sm font-medium text-foreground">{tx(language, "API 服务", "API service")}</span>
            <span className="ml-auto text-xs text-muted-foreground">{isOnline ? tx(language, "在线", "Online") : tx(language, "离线", "Offline")}</span>
          </div>
          <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-4">
            <span className={`h-3 w-3 rounded-full ${isLlmConfigured ? "bg-success" : "bg-error"}`} />
            <span className="text-sm font-medium text-foreground">{tx(language, "LLM 模型", "LLM model")}</span>
            <span className="ml-auto text-xs text-muted-foreground">{isLlmConfigured ? tx(language, "已配置", "Configured") : tx(language, "未配置", "Not configured")}</span>
          </div>
          <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-4">
            <span className={`h-3 w-3 rounded-full ${health?.site_api_configured ? "bg-success" : "bg-error"}`} />
            <span className="text-sm font-medium text-foreground">{tx(language, "站点 API Key", "Site API Key")}</span>
            <span className="ml-auto text-xs text-muted-foreground">{health?.site_api_configured ? tx(language, "已配置", "Configured") : tx(language, "未配置", "Not configured")}</span>
          </div>
        </div>
      </Card>

      {/* ── Quick Links ── */}
      <Card>
        <CardTitle subtitle={tx(language, "选择工具开始分析", "Choose a tool to start")}>{tx(language, "快捷入口", "Quick Links")}</CardTitle>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="group flex min-h-[5.5rem] flex-col justify-center rounded-xl border border-border bg-card p-4 transition-all duration-300 hover:border-accent/20 hover:shadow-accent-sm hover:-translate-y-0.5"
            >
              <h3 className="text-sm font-semibold text-foreground group-hover:text-accent transition-colors">
                {link.label}
              </h3>
              <p className="mt-1 text-xs text-muted-foreground">{link.desc}</p>
            </Link>
          ))}
        </div>
      </Card>

      {/* ── Bottom ── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardTitle subtitle={watchlistQuotes.length ? tx(language, `${watchlistQuotes.length} 个标的`, `${watchlistQuotes.length} symbols`) : undefined}>{tx(language, "自选股快照", "Watchlist Snapshot")}</CardTitle>
          {watchlistQuotes.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {tx(language, "暂无自选股，前往", "No watchlist yet. Open")}
              <Link href="/watchlist" className="mx-1 text-accent hover:underline">{tx(language, "自选股页面", "Watchlist")}</Link>
              {tx(language, "添加。", "to add symbols.")}
            </p>
          ) : (
            <div className="space-y-1">
              {watchlistQuotes.map((item) => (
                <div key={`${item.market}:${item.symbol}`} className="flex items-center justify-between rounded-lg px-3 py-2.5 transition-colors hover:bg-muted">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="shrink-0 font-mono text-sm font-semibold text-foreground">{item.symbol}</span>
                    <span className="text-xs uppercase text-muted-foreground">{item.market}</span>
                  </div>
                  <Link href={`/analysis?symbol=${item.symbol}&market=${item.market}`} className="shrink-0 text-xs font-medium text-accent hover:underline">
                    {tx(language, "分析", "Analyze")} &rarr;
                  </Link>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <CardTitle subtitle={recentResults.length ? tx(language, `${recentResults.length} 个缓存`, `${recentResults.length} cached`) : undefined}>{tx(language, "最近结果", "Recent Results")}</CardTitle>
          {recentResults.length === 0 ? (
            <p className="text-sm text-muted-foreground">{tx(language, "暂无本地缓存结果。", "No local cached results yet.")}</p>
          ) : (
            <ul className="space-y-1">
              {recentResults.map((key) => (
                <li key={key} className="rounded-lg px-3 py-2 font-mono text-xs text-muted-foreground transition-colors hover:bg-muted">{key}</li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* ── Footer ── */}
      <motion.div variants={fadeInUp} initial="hidden" whileInView="visible" viewport={viewportOnce} className="py-6 text-center">
        <div className="divider-accent" />
        <p className="text-xs text-muted-foreground">
          {tx(language, "仅供研究参考，不构成投资建议", "For research only. Not investment advice")} &middot; KronosFinceptLab v10.8.8
        </p>
      </motion.div>
    </div>
  );
}
