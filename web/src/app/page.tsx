"use client";

import { useEffect, useState } from "react";
import { Card, CardTitle, CardStat } from "@/components/ui/Card";
import { api, HealthResponse } from "@/lib/api";

export default function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => {});
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-display">Dashboard</h1>

      {/* Status cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardStat
            label="API Status"
            value={health?.status === "ok" ? "Online" : "Offline"}
            color={health?.status === "ok" ? "text-accent-green" : "text-accent-red"}
          />
        </Card>
        <Card>
          <CardStat label="Model" value={health?.model_id?.split("/").pop() || "—"} />
        </Card>
        <Card>
          <CardStat label="Device" value={health?.device || "—"} />
        </Card>
        <Card>
          <CardStat label="Uptime" value={health ? `${Math.floor(health.uptime_seconds / 60)}m` : "—"} />
        </Card>
      </div>

      {/* Quick actions */}
      <Card>
        <CardTitle>Quick Start</CardTitle>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <a href="/forecast" className="p-4 rounded-lg bg-surface-overlay hover:bg-gray-700 transition-colors">
            <div className="text-2xl mb-2">🔮</div>
            <h3 className="font-semibold">Forecast</h3>
            <p className="text-sm text-gray-400">Predict stock price movements</p>
          </a>
          <a href="/backtest" className="p-4 rounded-lg bg-surface-overlay hover:bg-gray-700 transition-colors">
            <div className="text-2xl mb-2">📈</div>
            <h3 className="font-semibold">Backtest</h3>
            <p className="text-sm text-gray-400">Test ranking strategies</p>
          </a>
          <a href="/data" className="p-4 rounded-lg bg-surface-overlay hover:bg-gray-700 transition-colors">
            <div className="text-2xl mb-2">📋</div>
            <h3 className="font-semibold">Data Browser</h3>
            <p className="text-sm text-gray-400">Explore A-stock historical data</p>
          </a>
        </div>
      </Card>

      {/* Disclaimer */}
      <div className="text-center text-xs text-gray-500 py-4">
        ⚠️ Research forecast only; not trading advice. v2.0.0
      </div>
    </div>
  );
}
