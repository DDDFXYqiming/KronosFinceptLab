"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardTitle, CardStat } from "@/components/ui/Card";
import { api, HealthResponse } from "@/lib/api";
import { useAppStore } from "@/stores/app";

export default function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const { watchlist } = useAppStore();

  useEffect(() => {
    api.health().then(setHealth).catch(() => {});
  }, []);

  const quickLinks = [
    { href: "/forecast", label: "Forecast", desc: "Predict stock price movements" },
    { href: "/analysis", label: "Analysis", desc: "AI-powered stock analysis" },
    { href: "/batch", label: "Batch", desc: "Compare multiple assets" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-display">Dashboard</h1>
        <div className="flex items-center gap-2 text-sm">
          <div
            className={`w-2 h-2 rounded-full animate-pulse-dot ${
              health?.status === "ok" ? "bg-success" : "bg-error"
            }`}
          />
          <span className="text-muted-foreground">
            {health?.status === "ok" ? "API Online" : "API Offline"}
          </span>
        </div>
      </div>

      {/* System Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardStat
            label="API Status"
            value={health?.status === "ok" ? "Online" : "Offline"}
            color={health?.status === "ok" ? "text-success" : "text-error"}
          />
        </Card>
        <Card>
          <CardStat label="Model" value={health?.model_id?.split("/").pop() || "-"} />
        </Card>
        <Card>
          <CardStat label="Device" value={health?.device || "-"} />
        </Card>
        <Card>
          <CardStat
            label="Uptime"
            value={health ? `${Math.floor(health.uptime_seconds / 60)}m` : "-"}
          />
        </Card>
      </div>

      {/* Watchlist */}
      <Card>
        <CardTitle>Watchlist</CardTitle>
        {watchlist.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <p className="mb-2">No stocks in watchlist</p>
            <Link href="/watchlist" className="text-accent hover:underline text-sm">
              Add stocks to your watchlist
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  <th className="py-2 text-left">Symbol</th>
                  <th className="py-2 text-left">Market</th>
                  <th className="py-2 text-right">Actions</th>
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
                        Forecast
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
        <CardTitle>Quick Links</CardTitle>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {quickLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="p-4 rounded-xl bg-muted border border-border hover:bg-muted/80 hover:border-accent/20 transition-all duration-200"
            >
              <h3 className="font-semibold text-accent">{link.label}</h3>
              <p className="text-sm text-muted-foreground mt-1">{link.desc}</p>
            </Link>
          ))}
        </div>
      </Card>

      {/* Disclaimer */}
      <div className="text-center text-xs text-muted-foreground py-4">
        Research forecast only; not trading advice.
      </div>
    </div>
  );
}
