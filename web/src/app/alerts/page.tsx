"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardTitle } from "@/components/ui/Card";
import { SectionLabel } from "@/components/ui/SectionLabel";
import { Button } from "@/components/ui/Button";
import { api, formatApiError } from "@/lib/api";
import { t } from "@/lib/i18n";
import { getMarketOptions, type Market } from "@/lib/markets";
import { DEFAULT_SYMBOL, normalizeSymbol } from "@/lib/symbols";
import { useAppStore } from "@/stores/app";
import type { AlertCheckResponse, AlertRule } from "@/types/api";

const ALERT_TYPE_KEYS: Record<string, string> = {
  price_above: "alerts.priceAbove",
  price_below: "alerts.priceBelow",
  price_change: "alerts.priceChange",
  rsi_overbought: "alerts.rsiOverbought",
  rsi_oversold: "alerts.rsiOversold",
};

const ALERT_TYPES = Object.keys(ALERT_TYPE_KEYS);

function maskContactValue(value?: string | null): string | null {
  if (!value) return null;
  if (value.length <= 8) return "[REDACTED]";
  return `${value.slice(0, 4)}...[REDACTED]...${value.slice(-4)}`;
}

export default function AlertsPage() {
  const { preferences } = useAppStore();
  const language = preferences.language;
  const marketOptions = getMarketOptions(language);
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [events, setEvents] = useState<AlertCheckResponse["events"]>([]);
  const [showSensitiveFields, setShowSensitiveFields] = useState(false);
  const [name, setName] = useState(() => t(language, "alerts.defaultRuleName"));
  const [symbol, setSymbol] = useState(DEFAULT_SYMBOL);
  const [market, setMarket] = useState<Market>("cn");
  const [alertType, setAlertType] = useState("price_above");
  const [threshold, setThreshold] = useState("50");
  const [channel, setChannel] = useState("feishu");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [emailTo, setEmailTo] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const enabledRules = useMemo(() => rules.filter((rule) => rule.enabled).length, [rules]);

  const alertTypeLabel = (value: string) => t(language, ALERT_TYPE_KEYS[value] || value);

  const loadRules = async () => {
    setError("");
    try {
      setRules((await api.alertList()).rules);
    } catch (exc) {
      setError(formatApiError(exc, t(language, "alerts.errList")));
    }
  };

  useEffect(() => {
    void loadRules();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const params = () => {
    const value = Number(threshold);
    if (alertType === "price_change") return { change_pct: value };
    return { threshold: value };
  };

  const createRule = async () => {
    setLoading(true);
    setError("");
    try {
      await api.alertCreate({
        name,
        symbol: normalizeSymbol(symbol),
        market,
        alert_type: alertType,
        params: params(),
        enabled: true,
        channel,
        webhook_url: webhookUrl || null,
        email_to: emailTo || null,
      });
      await loadRules();
    } catch (exc) {
      setError(formatApiError(exc, t(language, "alerts.errCreate")));
    } finally {
      setLoading(false);
    }
  };

  const deleteRule = async (id: string) => {
    setLoading(true);
    try {
      await api.alertDelete(id);
      await loadRules();
    } catch (exc) {
      setError(formatApiError(exc, t(language, "alerts.errDelete")));
    } finally {
      setLoading(false);
    }
  };

  const runCheck = async (ruleId?: string) => {
    setLoading(true);
    setError("");
    try {
      const res = await api.alertCheck(ruleId);
      setEvents(res.events);
    } catch (exc) {
      setError(formatApiError(exc, t(language, "alerts.errCheck")));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-shell space-y-6">
      <SectionLabel>{t(language, "alerts.section")}</SectionLabel>
      <h1 className="page-title">{t(language, "alerts.title")}</h1>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card>
          <p className="text-sm text-muted-foreground">{t(language, "alerts.totalRules")}</p>
          <p className="text-2xl font-bold">{rules.length}</p>
        </Card>
        <Card>
          <p className="text-sm text-muted-foreground">{t(language, "common.enabled")}</p>
          <p className="text-2xl font-bold text-success">{enabledRules}</p>
        </Card>
        <Card>
          <p className="text-sm text-muted-foreground">{t(language, "alerts.triggeredThisRun")}</p>
          <p className="text-2xl font-bold text-accent">{events.length}</p>
        </Card>
      </div>

      <Card>
        <CardTitle subtitle={t(language, "alerts.addRuleSubtitle")}>{t(language, "alerts.addRule")}</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div>
            <label className="field-label">{t(language, "common.name")}</label>
            <input className="app-input mt-1" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label className="field-label">{t(language, "common.symbol")}</label>
            <input className="app-input mt-1 font-mono" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
          </div>
          <div>
            <label className="field-label">{t(language, "common.market")}</label>
            <select className="app-input mt-1" value={market} onChange={(e) => setMarket(e.target.value as Market)}>
              {marketOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </div>
          <div>
            <label className="field-label">{t(language, "common.type")}</label>
            <select className="app-input mt-1" value={alertType} onChange={(e) => setAlertType(e.target.value)}>
              {ALERT_TYPES.map((value) => <option key={value} value={value}>{alertTypeLabel(value)}</option>)}
            </select>
          </div>
          <div>
            <label className="field-label">{t(language, "common.threshold")}</label>
            <input className="app-input mt-1" value={threshold} onChange={(e) => setThreshold(e.target.value)} />
          </div>
          <div>
            <label className="field-label">{t(language, "alerts.channel")}</label>
            <select className="app-input mt-1" value={channel} onChange={(e) => setChannel(e.target.value)}>
              <option value="feishu">{t(language, "alerts.channelFeishu")}</option>
              <option value="email">{t(language, "alerts.channelEmail")}</option>
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="field-label">{t(language, "common.webhookUrl")}</label>
            <input
              className="app-input mt-1"
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
              placeholder={t(language, "alerts.sensitivePlaceholder")}
            />
          </div>
          <div>
            <label className="field-label">{t(language, "common.email")}</label>
            <input className="app-input mt-1" value={emailTo} onChange={(e) => setEmailTo(e.target.value)} />
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row">
          <Button onClick={createRule} loading={loading}>{t(language, "alerts.createRule")}</Button>
          <Button variant="secondary" onClick={() => runCheck()} loading={loading}>{t(language, "alerts.checkAll")}</Button>
          <Button variant="ghost" onClick={() => setShowSensitiveFields((value) => !value)}>
            {showSensitiveFields ? t(language, "alerts.hideSensitive") : t(language, "alerts.showSensitive")}
          </Button>
        </div>
        {error && <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{error}</div>}
      </Card>

      <Card>
        <CardTitle>{t(language, "alerts.ruleList")}</CardTitle>
        <div className="table-scroll">
          <table className="min-w-[64rem] w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700 text-gray-400">
                <th className="py-2 text-left">{t(language, "common.name")}</th>
                <th className="py-2 text-left">{t(language, "common.symbol")}</th>
                <th className="py-2 text-left">{t(language, "common.type")}</th>
                <th className="py-2 text-left">{t(language, "common.contact")}</th>
                <th className="py-2 text-right">{t(language, "common.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <tr key={rule.id} className="border-b border-gray-800">
                  <td className="py-2">{rule.name}</td>
                  <td className="py-2 font-mono">{rule.symbol}</td>
                  <td className="py-2">{alertTypeLabel(rule.alert_type)}</td>
                  <td className="py-2 font-mono text-xs">
                    {showSensitiveFields
                      ? (rule.webhook_url || rule.email_to || "-")
                      : (maskContactValue(rule.webhook_url) || maskContactValue(rule.email_to) || "-")}
                  </td>
                  <td className="py-2 text-right">
                    <div className="flex justify-end gap-2">
                      <Button variant="ghost" onClick={() => runCheck(rule.id)} disabled={loading}>{t(language, "common.check")}</Button>
                      <Button variant="danger" onClick={() => deleteRule(rule.id)} disabled={loading}>{t(language, "common.delete")}</Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {events.length > 0 && (
        <Card>
          <CardTitle>{t(language, "alerts.triggeredEvents")}</CardTitle>
          <div className="space-y-2">
            {events.map((event) => (
              <div key={`${event.rule_id}-${event.timestamp}`} className="rounded-lg border border-border p-3 text-sm">
                <span className="font-bold">{event.rule_name}</span> · {event.symbol} · {event.message}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
