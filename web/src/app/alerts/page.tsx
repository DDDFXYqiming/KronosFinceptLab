"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardTitle } from "@/components/ui/Card";
import { SectionLabel } from "@/components/ui/SectionLabel";
import { AntButton as Button } from "@/components/antd/AntButton";
import { AntSelect as AppSelect } from "@/components/antd/AntSelect";
import type { AppSelectOption } from "@/components/ui/AppSelect";
import { AntNumberInput as AppNumberInput } from "@/components/antd/AntNumberInput";
import { clampNumber } from "@/components/ui/AppNumberInput";
import { api, formatApiError } from "@/lib/api";
import { AntInput } from "@/components/antd/AntInput";
import { AntAlert } from "@/components/antd/AntAlert";
import { AntTable } from "@/components/antd/AntTable";
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

function thresholdBounds(alertType: string) {
  if (alertType === "price_change") return { min: -50, max: 50, step: 0.5, integer: false };
  if (alertType === "rsi_overbought" || alertType === "rsi_oversold") return { min: 0, max: 100, step: 1, integer: true };
  return { min: 0.01, max: 1000000, step: 0.01, integer: false };
}

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
  const [threshold, setThreshold] = useState(50);
  const [channel, setChannel] = useState("feishu");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [emailTo, setEmailTo] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const enabledRules = useMemo(() => rules.filter((rule) => rule.enabled).length, [rules]);

  const alertTypeLabel = (value: string) => t(language, ALERT_TYPE_KEYS[value] || value);
  const alertTypeOptions: Array<AppSelectOption<string>> = ALERT_TYPES.map((value) => ({
    value,
    label: alertTypeLabel(value),
  }));
  const channelOptions: Array<AppSelectOption<string>> = [
    { value: "feishu", label: t(language, "alerts.channelFeishu") },
    { value: "email", label: t(language, "alerts.channelEmail") },
  ];

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
    const bounds = thresholdBounds(alertType);
    const value = clampNumber(threshold, bounds.min, bounds.max);
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
            <AntInput value={name} onChange={setName} />
          </div>
          <div>
            <label className="field-label">{t(language, "common.symbol")}</label>
            <AntInput value={symbol} onChange={setSymbol} />
          </div>
          <div>
            <label className="field-label">{t(language, "common.market")}</label>
            <AppSelect value={market} onChange={setMarket} options={marketOptions} ariaLabel={t(language, "common.market")} className="mt-1" />
          </div>
          <div>
            <label className="field-label">{t(language, "common.type")}</label>
            <AppSelect
              value={alertType}
              onChange={(nextType) => {
                setAlertType(nextType);
                const bounds = thresholdBounds(nextType);
                setThreshold((value) => clampNumber(value, bounds.min, bounds.max));
              }}
              options={alertTypeOptions}
              ariaLabel={t(language, "common.type")}
              className="mt-1"
            />
          </div>
          <div>
            <label className="field-label">{t(language, "common.threshold")}</label>
            {(() => {
              const bounds = thresholdBounds(alertType);
              return (
                <AppNumberInput
                  value={threshold}
                  onChange={setThreshold}
                  min={bounds.min}
                  max={bounds.max}
                  step={bounds.step}
                  integer={bounds.integer}
                  ariaLabel={t(language, "common.threshold")}
                  className="mt-1"
                />
              );
            })()}
          </div>
          <div>
            <label className="field-label">{t(language, "alerts.channel")}</label>
            <AppSelect value={channel} onChange={setChannel} options={channelOptions} ariaLabel={t(language, "alerts.channel")} className="mt-1" />
          </div>
          <div className="md:col-span-2">
            <label className="field-label">{t(language, "common.webhookUrl")}</label>
            <AntInput value={webhookUrl} onChange={setWebhookUrl} placeholder="https://open.feishu.cn/..." />
          </div>
          <div>
            <label className="field-label">{t(language, "common.email")}</label>
            <AntInput value={emailTo} onChange={setEmailTo} />
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-3 md:flex-row">
          <Button onClick={createRule} loading={loading}>{t(language, "alerts.createRule")}</Button>
          <Button variant="secondary" onClick={() => runCheck()} loading={loading}>{t(language, "alerts.checkAll")}</Button>
          <Button variant="ghost" onClick={() => setShowSensitiveFields((value) => !value)}>
            {showSensitiveFields ? t(language, "alerts.hideSensitive") : t(language, "alerts.showSensitive")}
          </Button>
        </div>
        {error && <AntAlert type="error" message={error} />}
      </Card>

      <Card>
        <CardTitle>{t(language, "alerts.ruleList")}</CardTitle>
        <AntTable
          columns={[
            { title: t(language, "common.name"), dataIndex: "name", key: "name", width: 160 },
            { title: t(language, "common.symbol"), dataIndex: "symbol", key: "symbol", render: (v: string) => <span className="font-mono">{v}</span>, width: 120 },
            { title: t(language, "common.type"), key: "type", render: (_: unknown, r: AlertRule) => alertTypeLabel(r.alert_type), width: 120 },
            { title: t(language, "common.contact"), key: "contact", render: (_: unknown, r: AlertRule) => <span className="font-mono text-xs">{showSensitiveFields ? (r.webhook_url || r.email_to || "-") : (maskContactValue(r.webhook_url) || maskContactValue(r.email_to) || "-")}</span> },
            { title: t(language, "common.actions"), key: "actions", render: (_: unknown, r: AlertRule) => <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => runCheck(r.id)} disabled={loading}>{t(language, "common.check")}</Button><Button variant="danger" onClick={() => deleteRule(r.id)} disabled={loading}>{t(language, "common.delete")}</Button></div>, align: "right", width: 180 },
          ]}
          dataSource={rules}
          rowKey="id"
          pagination={false}
        />
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
