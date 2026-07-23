"use client";

import { useEffect, useState } from "react";
import { Card, CardTitle } from "@/components/ui/Card";
import { SectionLabel } from "@/components/ui/SectionLabel";
import { Button } from "@/components/ui/Button";
import { AppSelect, type AppSelectOption } from "@/components/ui/AppSelect";
import { AppNumberInput } from "@/components/ui/AppNumberInput";
import {
  KRONOS_API_KEY_STORAGE_KEY,
  api,
  formatApiError,
  getConfiguredApiKey,
  saveConfiguredApiKey,
} from "@/lib/api";
import { DEFAULT_MODEL_ID, MODEL_SIZE_MAP, SUPPORTED_MODEL_IDS } from "@/lib/defaults";
import { LANGUAGE_OPTIONS, t } from "@/lib/i18n";
import { getMarketOptions } from "@/lib/markets";
import {
  DEFAULT_RSS_FEEDS,
  getStoredRssFeeds,
  isDefaultRssFeed,
  normalizeRssFeed,
  withProtectedDefaultRssFeeds,
  resetStoredRssFeeds,
  saveStoredRssFeeds,
} from "@/lib/rssFeeds";
import { downloadTextFile } from "@/lib/exportUtils";
import { useAppStore } from "@/stores/app";
import type {
  HealthResponse,
  MacroProviderStatusResponse,
  ModelCacheClearResponse,
  ModelCacheResponse,
  ModelPrewarmResponse,
  RssFeed,
  SecuritySummaryResponse,
} from "@/types/api";

function isSensitiveStorageKey(key: string): boolean {
  return /api[-_]?key|token|secret|authorization|cookie/i.test(key);
}

export default function SettingsPage() {
  const { preferences, setPreferences, clearLocalState } = useAppStore();
  const language = preferences.language;
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
  const [rssFeeds, setRssFeeds] = useState<RssFeed[]>(() => getStoredRssFeeds());
  const [rssTitle, setRssTitle] = useState("");
  const [rssUrl, setRssUrl] = useState("");
  const [rssTestResult, setRssTestResult] = useState("");
  const [rssBusy, setRssBusy] = useState(false);

  const refreshHealth = async () => {
    setError("");
    try {
      setHealth(await api.health());
    } catch (exc) {
      setError(formatApiError(exc, t(language, "settings.errHealth")));
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
    setRssFeeds(DEFAULT_RSS_FEEDS);
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
      setSecurityError(formatApiError(exc, t(language, "settings.errSecurity")));
    }
  };

  const refreshModelCache = async () => {
    setModelError("");
    try {
      setModelCache(await api.modelCache());
    } catch (exc) {
      setModelError(formatApiError(exc, t(language, "settings.errModelCache")));
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
      setModelError(formatApiError(exc, t(language, "settings.errModelClear")));
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
      setModelError(formatApiError(exc, t(language, "settings.errModelPrewarm")));
    } finally {
      setModelBusy(false);
    }
  };

  const refreshMacroProviderStatus = async (mode = macroMode) => {
    setMacroStatusError("");
    try {
      setMacroStatus(await api.macroProviderStatus(mode));
    } catch (exc) {
      setMacroStatusError(formatApiError(exc, t(language, "settings.errMacroProviders")));
    }
  };
  const modelOptions = Array.from(new Set([
    ...((health?.supported_model_ids?.length ? health.supported_model_ids : [health?.model_id || DEFAULT_MODEL_ID])),
  ].filter(Boolean)));
  const marketOptions = getMarketOptions(language);
  const macroModeOptions: Array<AppSelectOption<"fast" | "complete">> = [
    { value: "fast", label: t(language, "settings.fastMode") },
    { value: "complete", label: t(language, "settings.completeMode") },
  ];
  const modelSelectOptions: Array<AppSelectOption<string>> = modelOptions.map((id) => ({
    value: id,
    label: id.replace("NeoQuasar/", ""),
  }));
  const themeOptions: Array<AppSelectOption<"system" | "dark" | "light">> = [
    { value: "system", label: t(language, "settings.themeSystem") },
    { value: "dark", label: t(language, "settings.themeDark") },
    { value: "light", label: t(language, "settings.themeLight") },
  ];
  const providerStatusLabel = (status: string) => {
    if (status === "ready") return t(language, "settings.statusReady");
    if (status === "suspended" || status === "cooldown") return t(language, "settings.statusSuspended");
    if (status === "failed") return t(language, "settings.statusFailed");
    return status;
  };

  const persistRssFeeds = (nextFeeds: RssFeed[]) => {
    const normalized = withProtectedDefaultRssFeeds(nextFeeds);
    setRssFeeds(normalized);
    saveStoredRssFeeds(normalized);
  };

  const addRssFeed = () => {
    const feed = normalizeRssFeed({ title: rssTitle, url: rssUrl }, rssFeeds.length);
    if (!feed.url) return;
    persistRssFeeds([...rssFeeds, feed]);
    setRssTitle("");
    setRssUrl("");
    setRssTestResult("");
  };

  const removeRssFeed = (feedId: string) => {
    const target = rssFeeds.find((feed, index) => {
      const normalized = normalizeRssFeed(feed, index);
      return (normalized.id || normalized.url) === feedId;
    });
    if (target && isDefaultRssFeed(normalizeRssFeed(target, 0))) {
      return;
    }
    persistRssFeeds(rssFeeds.filter((feed, index) => {
      const normalized = normalizeRssFeed(feed, index);
      return (normalized.id || normalized.url) !== feedId;
    }));
    setRssTestResult("");
  };

  const resetRssFeeds = () => {
    setRssFeeds(resetStoredRssFeeds());
    setRssTestResult("");
  };

  const testRssFeeds = async () => {
    setRssBusy(true);
    setRssTestResult("");
    try {
      const res = await api.fetchRss({ feeds: rssFeeds, limit_per_feed: 2 });
      const errorCount = Object.keys(res.errors || {}).length;
      setRssTestResult(t(language, "settings.rssTestResult")
        .replace("{items}", String(res.items.length))
        .replace("{errors}", String(errorCount)));
    } catch (exc) {
      setRssTestResult(formatApiError(exc, t(language, "settings.errRssTest")));
    } finally {
      setRssBusy(false);
    }
  };

  return (
    <div className="page-shell space-y-6">
      <SectionLabel>{t(language, "settings.title")}</SectionLabel>
      <h1 className="page-title">{t(language, "settings.title")}</h1>

      <Card>
        <CardTitle subtitle={t(language, "settings.diagnosticsSubtitle")}>{t(language, "settings.diagnostics")}</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <div><p className="text-sm text-muted-foreground">{t(language, "common.api")}</p><p className={health?.status === "ok" ? "text-xl font-bold text-success" : "text-xl font-bold text-error"}>{health?.status || t(language, "common.unknown")}</p></div>
          <div><p className="text-sm text-muted-foreground">{t(language, "common.version")}</p><p className="text-xl font-bold">{health?.app_version || health?.version || "-"}</p></div>
          <div><p className="text-sm text-muted-foreground">{t(language, "common.model")}</p><p className="truncate text-xl font-bold">{health?.model_id || health?.default_model_id || "-"}</p></div>
          <div><p className="text-sm text-muted-foreground">{t(language, "settings.device")}</p><p className="text-xl font-bold">{health?.device || "-"}</p></div>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <div><p className="text-xs text-muted-foreground">{t(language, "settings.buildCommit")}</p><p className="font-mono text-sm font-bold">{health?.build_commit ? health.build_commit.slice(0, 7) : "-"}</p></div>
          <div><p className="text-xs text-muted-foreground">{t(language, "settings.buildSource")}</p><p className="font-mono text-sm font-bold">{health?.build_source || "-"}</p></div>
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row">
          <Button onClick={refreshHealth}>{t(language, "settings.recheck")}</Button>
          <Button variant="secondary" onClick={exportLocalState}>{t(language, "settings.exportState")}</Button>
          <Button variant="danger" onClick={clearLocalCaches}>{t(language, "settings.clearLocalCache")}</Button>
        </div>
        {error && <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{error}</div>}
      </Card>

      <Card>
        <CardTitle subtitle={t(language, "settings.llmSubtitle")}>{t(language, "settings.llmTitle")}</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div>
            <p className="text-sm text-muted-foreground">{t(language, "common.provider")}</p>
            <p className="truncate text-xl font-bold">{health?.model_id ? health.model_id.split("/")[0] : health?.default_model_id?.split("/")[0] || "-"}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">{t(language, "common.model")}</p>
            <p className="truncate font-mono text-xl font-bold" title={health?.model_id || health?.default_model_id || "-"}>{health?.model_id || health?.default_model_id || "-"}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">{t(language, "settings.modelLoadStatus")}</p>
            <p className={`text-xl font-bold ${health?.model_loaded ? "text-success" : health?.model_error ? "text-error" : "text-muted-foreground"}`}>
              {health?.model_loaded ? t(language, "settings.modelLoaded") : health?.model_error ? t(language, "common.loadingFailed") : health?.model_id ? t(language, "common.unknown") : t(language, "common.notConfigured")}
            </p>
          </div>
        </div>
      </Card>

      <Card>
        <CardTitle subtitle={t(language, "settings.modelCacheSubtitle")}>{t(language, "settings.modelCacheTitle")}</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="rounded-lg border border-border bg-muted p-3">
            <p className="text-sm text-muted-foreground">{t(language, "settings.cacheEntries")}</p>
            <p className="mt-1 font-mono text-2xl font-bold">{modelCache?.cache.size ?? "-"}</p>
          </div>
          <div className="rounded-lg border border-border bg-muted p-3 md:col-span-2">
            <p className="text-sm text-muted-foreground">{t(language, "settings.cacheKeys")}</p>
            <p className="mt-1 break-all font-mono text-xs text-foreground">
              {modelCache?.cache.keys.length ? modelCache.cache.keys.join(" · ") : t(language, "settings.noCacheEntries")}
            </p>
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row">
          <Button onClick={refreshModelCache} disabled={modelBusy}>{t(language, "settings.refreshCache")}</Button>
          <Button variant="secondary" onClick={() => prewarmModelCache(false)} loading={modelBusy}>{t(language, "settings.prewarmModel")}</Button>
          <Button variant="danger" onClick={clearModelCache} disabled={modelBusy}>{t(language, "settings.clearModelCache")}</Button>
        </div>
        {modelError && <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{modelError}</div>}
        {modelCacheResult && (
          <pre className="mt-4 max-h-48 overflow-auto rounded-lg bg-muted p-3 text-xs text-muted-foreground">
            {JSON.stringify(modelCacheResult, null, 2)}
          </pre>
        )}
      </Card>

      <Card>
        <CardTitle subtitle={t(language, "settings.rssSubtitle")}>{t(language, "settings.rssTitle")}</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_2fr_auto] md:items-end">
          <div>
            <label className="field-label">{t(language, "settings.rssName")}</label>
            <input
              value={rssTitle}
              onChange={(event) => setRssTitle(event.target.value)}
              className="app-input mt-1"
              placeholder="Federal Reserve"
            />
          </div>
          <div>
            <label className="field-label">RSS URL</label>
            <input
              value={rssUrl}
              onChange={(event) => setRssUrl(event.target.value)}
              className="app-input mt-1 font-mono"
              placeholder="https://..."
            />
          </div>
          <Button onClick={addRssFeed}>{t(language, "settings.rssAdd")}</Button>
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row md:flex-wrap">
          <Button variant="secondary" onClick={testRssFeeds} loading={rssBusy}>{t(language, "settings.rssTest")}</Button>
          <Button variant="secondary" onClick={resetRssFeeds}>{t(language, "settings.rssRestore")}</Button>
        </div>
        {rssTestResult && <p className="mt-3 text-sm text-muted-foreground">{rssTestResult}</p>}
        <div className="mt-4 space-y-2">
          {rssFeeds.map((feed, index) => {
            const normalized = normalizeRssFeed(feed, index);
            const key = normalized.id || normalized.url;
            const protectedDefault = isDefaultRssFeed(normalized);
            return (
              <div key={key} className="flex flex-col gap-2 rounded-lg border border-border p-3 md:flex-row md:items-center md:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium text-foreground">{normalized.title || normalized.id}</p>
                    {isDefaultRssFeed(normalized) && (
                      <span className="rounded-full border border-accent/20 bg-accent/10 px-2 py-0.5 text-xs text-accent">
                        {t(language, "settings.rssDefault")}
                      </span>
                    )}
                  </div>
                  <p className="truncate font-mono text-xs text-muted-foreground">{normalized.url}</p>
                </div>
                <Button
                  variant="ghost"
                  disabled={protectedDefault}
                  title={protectedDefault ? t(language, "settings.rssDefaultProtected") : undefined}
                  onClick={() => removeRssFeed(key)}
                >
                  {t(language, "settings.rssRemove")}
                </Button>
              </div>
            );
          })}
          {!rssFeeds.length && <p className="text-sm text-muted-foreground">{t(language, "settings.rssEmpty")}</p>}
        </div>
      </Card>

      <Card>
        <CardTitle subtitle={t(language, "settings.macroProviderSubtitle")}>{t(language, "settings.macroProviderTitle")}</CardTitle>
        <div className="flex flex-col gap-3 md:flex-row md:items-end">
          <div>
            <label className="field-label">{t(language, "settings.collectionMode")}</label>
            <AppSelect
              value={macroMode}
              onChange={(mode) => {
                setMacroMode(mode);
                void refreshMacroProviderStatus(mode);
              }}
              options={macroModeOptions}
              ariaLabel={t(language, "settings.collectionMode")}
              className="mt-1 md:min-w-64"
            />
          </div>
          <Button onClick={() => refreshMacroProviderStatus(macroMode)}>{t(language, "settings.refreshProviderStatus")}</Button>
        </div>
        {macroStatusError && <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{macroStatusError}</div>}
        <div className="mt-4 table-scroll">
          <table className="min-w-[52rem] w-full text-sm">
            <thead>
              <tr className="border-b border-border text-muted-foreground">
                <th className="py-2 text-left">{t(language, "settings.providerColumn")}</th>
                <th className="py-2 text-left">{t(language, "common.status")}</th>
                <th className="py-2 text-right">{t(language, "settings.failureCount")}</th>
                <th className="py-2 text-right">{t(language, "settings.cooldownRemaining")}</th>
                <th className="py-2 text-right">{t(language, "settings.cache")}</th>
                <th className="py-2 text-right">{t(language, "settings.timeout")}</th>
                <th className="py-2 text-left">{t(language, "settings.dimension")}</th>
              </tr>
            </thead>
            <tbody>
              {(macroStatus?.providers || []).map((row) => (
                <tr key={row.provider_id} className="border-b border-border last:border-b-0">
                  <td className="py-2 font-mono font-semibold text-foreground">{row.provider_id}</td>
                  <td className={row.status === "ready" ? "py-2 text-success" : "py-2 text-error"}>{providerStatusLabel(row.status)}</td>
                  <td className="py-2 text-right font-mono text-foreground">{row.failure_count}</td>
                  <td className="py-2 text-right font-mono text-foreground">{row.suspended_remaining_seconds}s</td>
                  <td className="py-2 text-right font-mono text-foreground">{row.cached_entries}</td>
                  <td className="py-2 text-right font-mono text-foreground">{row.timeout_seconds}s</td>
                  <td className="py-2 text-muted-foreground">{row.dimensions?.join(" / ") || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!macroStatus?.providers?.length && <p className="mt-3 text-sm text-muted-foreground">{t(language, "settings.noProviderStatus")}</p>}
        </div>
      </Card>

      <Card>
        <CardTitle subtitle={t(language, "settings.apiKeySubtitle")}>{t(language, "settings.apiKeyTitle")}</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_auto_auto] md:items-end">
          <div>
            <label className="field-label" htmlFor={KRONOS_API_KEY_STORAGE_KEY}>{t(language, "settings.apiKeyLabel")}</label>
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
                ? t(language, "settings.siteKeyConfigured")
                : t(language, "settings.siteKeyMissing")}
            </p>
          </div>
          <Button onClick={saveApiKey}>{t(language, "settings.saveKey")}</Button>
          <Button variant="secondary" onClick={clearApiKey}>{t(language, "settings.clearKey")}</Button>
        </div>
        {apiKeySaved && <p className="mt-3 text-sm text-success">{t(language, "settings.keySaved")}</p>}
      </Card>

      <Card>
        <CardTitle subtitle={t(language, "settings.securitySubtitle")}>{t(language, "settings.securityTitle")}</CardTitle>
        <Button onClick={refreshSecuritySummary}>{t(language, "settings.readSecurity")}</Button>
        {securityError && <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{securityError}</div>}
        {securitySummary && (
          <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            {Object.entries(securitySummary.counters).length === 0 ? (
              <p className="text-sm text-muted-foreground">{t(language, "settings.noSecurityCounters")}</p>
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
        <CardTitle>{t(language, "settings.preferences")}</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
          <div>
            <label className="field-label">{t(language, "settings.defaultMarket")}</label>
            <AppSelect
              value={preferences.defaultMarket}
              onChange={(defaultMarket) => setPreferences({ defaultMarket })}
              options={marketOptions}
              ariaLabel={t(language, "settings.defaultMarket")}
              className="mt-1"
            />
          </div>
          <div>
            <label className="field-label">{t(language, "settings.defaultPredLen")}</label>
            <AppNumberInput
              value={preferences.defaultPredLen}
              onChange={(defaultPredLen) => setPreferences({ defaultPredLen })}
              min={1}
              max={30}
              ariaLabel={t(language, "settings.defaultPredLen")}
              className="mt-1"
            />
          </div>
          <div>
            <label className="field-label">{t(language, "settings.defaultModel")}</label>
            {modelSelectOptions.length > 1 ? (
              <AppSelect
                value={modelOptions.includes(preferences.defaultModelId) ? preferences.defaultModelId : modelOptions[0]}
                onChange={(defaultModelId) => setPreferences({ defaultModelId })}
                options={modelSelectOptions}
                ariaLabel={t(language, "settings.defaultModel")}
                className="mt-1"
              />
            ) : (
              <div className="mt-1 flex min-h-11 items-center rounded-[10px] border border-slate-700 bg-slate-800 px-3 text-sm text-white">
                {modelSelectOptions[0]?.label || DEFAULT_MODEL_ID.replace("NeoQuasar/", "")}
              </div>
            )}
          </div>
          {/* Model size hints */}
          {(() => {
            const info = MODEL_SIZE_MAP[preferences.defaultModelId] ?? MODEL_SIZE_MAP[DEFAULT_MODEL_ID];
            return (
              <div className="mt-1 grid grid-cols-3 gap-2 text-[11px]">
                <div className="rounded-md border border-border bg-muted/50 px-2 py-1.5">
                  <span className="text-muted-foreground">{t(language, "settings.modelSize")}: </span>
                  <span className="font-medium text-foreground">{info.label}</span>
                </div>
                <div className="rounded-md border border-border bg-muted/50 px-2 py-1.5">
                  <span className="text-muted-foreground">{t(language, "settings.modelMemory")}: </span>
                  <span className="font-medium text-foreground">{info.memory}</span>
                </div>
                <div className="rounded-md border border-border bg-muted/50 px-2 py-1.5">
                  <span className="text-muted-foreground">{t(language, "settings.modelSpeed")}: </span>
                  <span className="font-medium text-foreground">{info.speed}</span>
                </div>
              </div>
            );
          })()}
          <div>
            <label className="field-label">{t(language, "settings.language")}</label>
            <AppSelect
              value={preferences.language}
              onChange={(language) => setPreferences({ language })}
              options={LANGUAGE_OPTIONS}
              ariaLabel={t(language, "settings.language")}
              className="mt-1"
            />
          </div>
          <div>
            <label className="field-label">{t(language, "settings.theme")}</label>
            <AppSelect
              value={preferences.theme}
              onChange={(theme) => setPreferences({ theme })}
              options={themeOptions}
              ariaLabel={t(language, "settings.theme")}
              className="mt-1"
            />
          </div>
        </div>
      </Card>
    </div>
  );
}
