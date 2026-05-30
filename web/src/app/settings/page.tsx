"use client";

import { useEffect, useState } from "react";
import { Card, CardTitle } from "@/components/ui/Card";
import { SectionLabel } from "@/components/ui/SectionLabel";
import { Button } from "@/components/ui/Button";
import {
  KRONOS_API_KEY_STORAGE_KEY,
  api,
  formatApiError,
  getConfiguredApiKey,
  saveConfiguredApiKey,
} from "@/lib/api";
import { DEFAULT_MODEL_ID, SUPPORTED_MODEL_IDS } from "@/lib/defaults";
import { LANGUAGE_OPTIONS, type Language } from "@/lib/i18n";
import { MARKET_OPTIONS, type Market } from "@/lib/markets";
import { downloadTextFile } from "@/lib/exportUtils";
import { useAppStore } from "@/stores/app";
import type {
  HealthResponse,
  MacroProviderStatusResponse,
  ModelCacheClearResponse,
  ModelCacheResponse,
  ModelPrewarmResponse,
  SecuritySummaryResponse,
} from "@/types/api";

function isSensitiveStorageKey(key: string): boolean {
  return /api[-_]?key|token|secret|authorization|cookie/i.test(key);
}

function maskModelId(id: string | undefined | null): string {
  if (!id) return "-";
  const parts = id.split("/");
  if (parts.length > 1) {
    const provider = parts[0];
    const model = parts.slice(1).join("/");
    if (model.length <= 4) return `${provider}/${model[0]}***`;
    return `${provider}/${model.slice(0, 2)}${"*".repeat(Math.min(6, model.length - 4))}${model.slice(-2)}`;
  }
  // Single-part model ID
  if (id.length <= 4) return `${id[0]}***`;
  return `${id.slice(0, 2)}${"*".repeat(Math.min(6, id.length - 4))}${id.slice(-2)}`;
}

export default function SettingsPage() {
  const { preferences, setPreferences, clearLocalState } = useAppStore();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiKeySaved, setApiKeySaved] = useState(false);
  const [securitySummary, setSecuritySummary] = useState<SecuritySummaryResponse | null>(null);
  const [securityError, setSecurityError] = useState("");
  const [modelCache, setModelCache] = useState<ModelCacheResponse | null>(null);
  const [modelCacheResult, setModelCacheResult] = useState<ModelCacheClearResponse | ModelPrewarmResponse | null>(null);
  const [modelError, setModelError] = useState("");
  const [modelBusy, setModelBusy] = useState(false);
  const [macroStatus, setMacroStatus] = useState<MacroProviderStatusResponse | null>(null);
  const [macroMode, setMacroMode] = useState<"fast" | "complete">("fast");
  const [macroStatusError, setMacroStatusError] = useState("");

  const refreshHealth = async () => {
    setError("");
    try {
      setHealth(await api.health());
    } catch (exc) {
      setError(formatApiError(exc, "健康检查失败"));
    }
  };

  useEffect(() => {
    setApiKey(getConfiguredApiKey() || "");
    void refreshHealth();
    void refreshModelCache();
    void refreshMacroProviderStatus("fast");
  }, []);

  const exportLocalState = () => {
    if (typeof window === "undefined") return;
    const local: Record<string, string | null> = {};
    const session: Record<string, string | null> = {};
    Object.keys(window.localStorage)
      .filter((key) => key.startsWith("kronos-") && !isSensitiveStorageKey(key))
      .forEach((key) => { local[key] = window.localStorage.getItem(key); });
    Object.keys(window.sessionStorage)
      .filter((key) => key.startsWith("kronos-") && !isSensitiveStorageKey(key))
      .forEach((key) => { session[key] = window.sessionStorage.getItem(key); });
    downloadTextFile("kronos_local_state.json", JSON.stringify({ local, session }, null, 2), "application/json;charset=utf-8");
  };

  const clearLocalCaches = () => {
    if (typeof window !== "undefined") {
      Object.keys(window.localStorage).filter((key) => key.startsWith("kronos-")).forEach((key) => window.localStorage.removeItem(key));
      Object.keys(window.sessionStorage).filter((key) => key.startsWith("kronos-")).forEach((key) => window.sessionStorage.removeItem(key));
    }
    setApiKey("");
    setApiKeySaved(false);
    clearLocalState();
  };

  const saveApiKey = () => {
    saveConfiguredApiKey(apiKey);
    setApiKey(apiKey.trim());
    setApiKeySaved(Boolean(apiKey.trim()));
  };

  const clearApiKey = () => {
    saveConfiguredApiKey("");
    setApiKey("");
    setApiKeySaved(false);
  };

  const refreshSecuritySummary = async () => {
    setSecurityError("");
    try {
      setSecuritySummary(await api.securitySummary());
    } catch (exc) {
      setSecurityError(formatApiError(exc, "安全摘要获取失败"));
    }
  };

  const refreshModelCache = async () => {
    setModelError("");
    try {
      setModelCache(await api.modelCache());
    } catch (exc) {
      setModelError(formatApiError(exc, "模型缓存状态获取失败"));
    }
  };

  const clearModelCache = async () => {
    setModelBusy(true);
    setModelError("");
    try {
      const res = await api.modelClearCache();
      setModelCacheResult(res);
      await refreshModelCache();
    } catch (exc) {
      setModelError(formatApiError(exc, "模型缓存清理失败"));
    } finally {
      setModelBusy(false);
    }
  };

  const prewarmModelCache = async (force = false) => {
    setModelBusy(true);
    setModelError("");
    try {
      const res = await api.modelPrewarm(force);
      setModelCacheResult(res);
      await refreshModelCache();
    } catch (exc) {
      setModelError(formatApiError(exc, "模型预热失败"));
    } finally {
      setModelBusy(false);
    }
  };

  const refreshMacroProviderStatus = async (mode = macroMode) => {
    setMacroStatusError("");
    try {
      setMacroStatus(await api.macroProviderStatus(mode));
    } catch (exc) {
      setMacroStatusError(formatApiError(exc, "宏观 provider 状态获取失败"));
    }
  };
  const modelOptions = Array.from(new Set([
    ...(health?.supported_model_ids || SUPPORTED_MODEL_IDS),
    preferences.defaultModelId || DEFAULT_MODEL_ID,
  ].filter(Boolean)));

  return (
    <div className="page-shell space-y-6">
      <SectionLabel>设置 / 诊断</SectionLabel>
      <h1 className="page-title">设置 / 诊断</h1>

      <Card>
        <CardTitle subtitle="检查 API、导出本地状态、清理缓存。">运行诊断</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <div><p className="text-sm text-muted-foreground">API</p><p className={health?.status === "ok" ? "text-xl font-bold text-success" : "text-xl font-bold text-error"}>{health?.status || "unknown"}</p></div>
          <div><p className="text-sm text-muted-foreground">版本</p><p className="text-xl font-bold">{health?.app_version || health?.version || "-"}</p></div>
          <div><p className="text-sm text-muted-foreground">模型</p><p className="truncate text-xl font-bold">{health?.model_id || health?.default_model_id || "-"}</p></div>
          <div><p className="text-sm text-muted-foreground">设备</p><p className="text-xl font-bold">{health?.device || "-"}</p></div>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <div><p className="text-xs text-muted-foreground">构建提交</p><p className="font-mono text-sm font-bold">{health?.build_commit ? health.build_commit.slice(0, 7) : "-"}</p></div>
          <div><p className="text-xs text-muted-foreground">构建源</p><p className="font-mono text-sm font-bold">{health?.build_source || "-"}</p></div>
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row">
          <Button onClick={refreshHealth}>重新检查</Button>
          <Button variant="secondary" onClick={exportLocalState}>导出本地状态</Button>
          <Button variant="danger" onClick={clearLocalCaches}>清理本地缓存</Button>
        </div>
        {error && <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{error}</div>}
      </Card>

      <Card>
        <CardTitle subtitle="当前 LLM 配置状态">LLM 提供商 / 模型</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div>
            <p className="text-sm text-muted-foreground">提供商</p>
            <p className="truncate text-xl font-bold">{health?.model_id ? health.model_id.split("/")[0] : health?.default_model_id?.split("/")[0] || "-"}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">模型</p>
            <p className="truncate font-mono text-xl font-bold" title={health?.model_id || health?.default_model_id || "-"}>{maskModelId(health?.model_id || health?.default_model_id)}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">模型加载状态</p>
            <p className={`text-xl font-bold ${health?.model_loaded ? "text-success" : health?.model_error ? "text-error" : "text-muted-foreground"}`}>
              {health?.model_loaded ? "已加载" : health?.model_error ? "加载失败" : health?.model_id ? "未知" : "未配置"}
            </p>
          </div>
        </div>
      </Card>

      <Card>
        <CardTitle subtitle="读取/清理/预热后端进程内 Kronos predictor cache。">模型 Cache Admin</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="rounded-lg border border-border bg-muted p-3">
            <p className="text-sm text-muted-foreground">缓存条目</p>
            <p className="mt-1 font-mono text-2xl font-bold">{modelCache?.cache.size ?? "-"}</p>
          </div>
          <div className="rounded-lg border border-border bg-muted p-3 md:col-span-2">
            <p className="text-sm text-muted-foreground">缓存 Key</p>
            <p className="mt-1 break-all font-mono text-xs text-foreground">
              {modelCache?.cache.keys.length ? modelCache.cache.keys.join(" · ") : "当前无缓存条目"}
            </p>
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row">
          <Button onClick={refreshModelCache} disabled={modelBusy}>刷新缓存状态</Button>
          <Button variant="secondary" onClick={() => prewarmModelCache(false)} loading={modelBusy}>预热模型</Button>
          <Button variant="danger" onClick={clearModelCache} disabled={modelBusy}>清理模型缓存</Button>
        </div>
        {modelError && <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{modelError}</div>}
        {modelCacheResult && (
          <pre className="mt-4 max-h-48 overflow-auto rounded-lg bg-muted p-3 text-xs text-muted-foreground">
            {JSON.stringify(modelCacheResult, null, 2)}
          </pre>
        )}
      </Card>

      <Card>
        <CardTitle subtitle="不触发 LLM 汇总，只展示宏观 provider 的 ready/cooldown/cache/timeout。">宏观 Provider 状态</CardTitle>
        <div className="flex flex-col gap-3 md:flex-row md:items-end">
          <div>
            <label className="field-label">采集模式</label>
            <select
              value={macroMode}
              onChange={(event) => {
                const mode = event.target.value as "fast" | "complete";
                setMacroMode(mode);
                void refreshMacroProviderStatus(mode);
              }}
              className="app-input mt-1"
            >
              <option value="fast">fast：Web 快速超时</option>
              <option value="complete">complete：完整采集超时</option>
            </select>
          </div>
          <Button onClick={() => refreshMacroProviderStatus(macroMode)}>刷新 Provider 状态</Button>
        </div>
        {macroStatusError && <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{macroStatusError}</div>}
        <div className="mt-4 table-scroll">
          <table className="min-w-[52rem] w-full text-sm">
            <thead>
              <tr className="border-b border-border text-muted-foreground">
                <th className="py-2 text-left">Provider</th>
                <th className="py-2 text-left">状态</th>
                <th className="py-2 text-right">失败数</th>
                <th className="py-2 text-right">冷却剩余</th>
                <th className="py-2 text-right">缓存</th>
                <th className="py-2 text-right">超时</th>
                <th className="py-2 text-left">维度</th>
              </tr>
            </thead>
            <tbody>
              {(macroStatus?.providers || []).map((row) => (
                <tr key={row.provider_id} className="border-b border-border last:border-b-0">
                  <td className="py-2 font-mono font-semibold text-foreground">{row.provider_id}</td>
                  <td className={row.status === "ready" ? "py-2 text-success" : "py-2 text-error"}>{row.status}</td>
                  <td className="py-2 text-right font-mono text-foreground">{row.failure_count}</td>
                  <td className="py-2 text-right font-mono text-foreground">{row.suspended_remaining_seconds}s</td>
                  <td className="py-2 text-right font-mono text-foreground">{row.cached_entries}</td>
                  <td className="py-2 text-right font-mono text-foreground">{row.timeout_seconds}s</td>
                  <td className="py-2 text-muted-foreground">{row.dimensions?.join(" / ") || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!macroStatus?.providers?.length && <p className="mt-3 text-sm text-muted-foreground">暂无 provider 状态。</p>}
        </div>
      </Card>

      <Card>
        <CardTitle subtitle="站点已配置服务端 key 时无需填写；仅在你想使用自己的调用 key 覆盖站点默认配置时保存。">API 访问密钥（可选）</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_auto_auto] md:items-end">
          <div>
            <label className="field-label" htmlFor={KRONOS_API_KEY_STORAGE_KEY}>Kronos API Key</label>
            <input
              id={KRONOS_API_KEY_STORAGE_KEY}
              type="password"
              value={apiKey}
              onChange={(event) => { setApiKey(event.target.value); setApiKeySaved(false); }}
              className="app-input mt-1"
              autoComplete="off"
              placeholder="X-Kronos-Api-Key"
            />
            <p className="mt-2 text-xs text-muted-foreground">
              {health?.site_api_configured
                ? "当前站点已配置服务端 key，普通预测/分析无需浏览器保存密钥；这里的密钥只保存在本机浏览器。"
                : "当前站点未配置服务端 key；保存浏览器本地 key 后才能调用受保护 API。"}
            </p>
          </div>
          <Button onClick={saveApiKey}>保存密钥</Button>
          <Button variant="secondary" onClick={clearApiKey}>清除密钥</Button>
        </div>
        {apiKeySaved && <p className="mt-3 text-sm text-success">密钥已保存。</p>}
      </Card>

      <Card>
        <CardTitle subtitle="需要 Admin API Key；只显示聚合计数，不包含请求体或密钥。">安全运维摘要</CardTitle>
        <Button onClick={refreshSecuritySummary}>读取安全摘要</Button>
        {securityError && <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{securityError}</div>}
        {securitySummary && (
          <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            {Object.entries(securitySummary.counters).length === 0 ? (
              <p className="text-sm text-muted-foreground">当前启动周期暂无安全计数。</p>
            ) : (
              Object.entries(securitySummary.counters).map(([key, value]) => (
                <div key={key} className="rounded-lg border border-border bg-muted p-3">
                  <p className="break-all font-mono text-xs text-muted-foreground">{key}</p>
                  <p className="mt-1 text-2xl font-bold">{value}</p>
                </div>
              ))
            )}
          </div>
        )}
      </Card>

      <Card>
        <CardTitle>偏好</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
          <div><label className="field-label">默认市场</label><select value={preferences.defaultMarket} onChange={(e) => setPreferences({ defaultMarket: e.target.value as Market })} className="app-input mt-1">{MARKET_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>
          <div><label className="field-label">默认预测天数</label><input type="number" min={1} max={60} value={preferences.defaultPredLen} onChange={(e) => setPreferences({ defaultPredLen: Math.max(1, Number(e.target.value)) })} className="app-input mt-1" /></div>
          <div><label className="field-label">默认模型</label><select value={preferences.defaultModelId || DEFAULT_MODEL_ID} onChange={(e) => setPreferences({ defaultModelId: e.target.value })} className="app-input mt-1">{modelOptions.map((id) => <option key={id} value={id}>{id.replace("NeoQuasar/", "")}</option>)}</select></div>
          <div><label className="field-label">语言</label><select value={preferences.language} onChange={(e) => setPreferences({ language: e.target.value as Language })} className="app-input mt-1">{LANGUAGE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>
          <div><label className="field-label">主题</label><select value={preferences.theme} onChange={(e) => setPreferences({ theme: e.target.value as "system" | "dark" | "light" })} className="app-input mt-1"><option value="system">跟随系统</option><option value="dark">深色</option><option value="light">浅色</option></select></div>
        </div>
      </Card>
    </div>
  );
}
