"use client";

import { useEffect, useState } from "react";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { api, formatApiError } from "@/lib/api";
import { MARKET_OPTIONS, type Market } from "@/lib/markets";
import { downloadTextFile } from "@/lib/exportUtils";
import { useAppStore } from "@/stores/app";
import type { HealthResponse } from "@/types/api";

export default function SettingsPage() {
  const { preferences, setPreferences, clearLocalState } = useAppStore();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState("");

  const refreshHealth = async () => {
    setError("");
    try { setHealth(await api.health()); } catch (exc) { setError(formatApiError(exc, "健康检查失败")); }
  };
  useEffect(() => { void refreshHealth(); }, []);

  const exportLocalState = () => {
    if (typeof window === "undefined") return;
    const local: Record<string, string | null> = {};
    const session: Record<string, string | null> = {};
    Object.keys(window.localStorage).filter((key) => key.startsWith("kronos-")).forEach((key) => { local[key] = window.localStorage.getItem(key); });
    Object.keys(window.sessionStorage).filter((key) => key.startsWith("kronos-")).forEach((key) => { session[key] = window.sessionStorage.getItem(key); });
    downloadTextFile("kronos_local_state.json", JSON.stringify({ local, session }, null, 2), "application/json;charset=utf-8");
  };

  const clearLocalCaches = () => {
    if (typeof window !== "undefined") {
      Object.keys(window.localStorage).filter((key) => key.startsWith("kronos-")).forEach((key) => window.localStorage.removeItem(key));
      Object.keys(window.sessionStorage).filter((key) => key.startsWith("kronos-")).forEach((key) => window.sessionStorage.removeItem(key));
    }
    clearLocalState();
  };

  return (
    <div className="page-shell space-y-6">
      <h1 className="page-title">设置 / 诊断</h1>
      <Card><CardTitle subtitle="检查 API、导出本地状态、清理缓存。">运行诊断</CardTitle><div className="grid grid-cols-1 gap-4 md:grid-cols-4"><div><p className="text-sm text-muted-foreground">API</p><p className={health?.status === "ok" ? "text-xl font-bold text-success" : "text-xl font-bold text-error"}>{health?.status || "unknown"}</p></div><div><p className="text-sm text-muted-foreground">版本</p><p className="text-xl font-bold">{health?.app_version || health?.version || "-"}</p></div><div><p className="text-sm text-muted-foreground">模型</p><p className="truncate text-xl font-bold">{health?.model_id || "-"}</p></div><div><p className="text-sm text-muted-foreground">设备</p><p className="text-xl font-bold">{health?.device || "-"}</p></div></div><div className="mt-4 flex flex-col gap-3 md:flex-row"><Button onClick={refreshHealth}>重新检查</Button><Button variant="secondary" onClick={exportLocalState}>导出本地状态</Button><Button variant="danger" onClick={clearLocalCaches}>清理本地缓存</Button></div>{error && <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{error}</div>}</Card>
      <Card><CardTitle>偏好</CardTitle><div className="grid grid-cols-1 gap-4 md:grid-cols-3"><div><label className="field-label">默认市场</label><select value={preferences.defaultMarket} onChange={(e) => setPreferences({ defaultMarket: e.target.value as Market })} className="app-input mt-1">{MARKET_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div><div><label className="field-label">默认预测天数</label><input type="number" min={1} max={60} value={preferences.defaultPredLen} onChange={(e) => setPreferences({ defaultPredLen: Math.max(1, Number(e.target.value)) })} className="app-input mt-1" /></div><div><label className="field-label">主题</label><select value={preferences.theme} onChange={(e) => setPreferences({ theme: e.target.value as "system" | "dark" | "light" })} className="app-input mt-1"><option value="system">跟随系统</option><option value="dark">深色</option><option value="light">浅色</option></select></div></div></Card>
    </div>
  );
}
