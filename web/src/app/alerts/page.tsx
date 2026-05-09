"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { api, formatApiError } from "@/lib/api";
import { MARKET_OPTIONS, type Market } from "@/lib/markets";
import { DEFAULT_SYMBOL, normalizeSymbol } from "@/lib/symbols";
import type { AlertCheckResponse, AlertRule } from "@/types/api";

const ALERT_TYPES = [
  { value: "price_above", label: "价格高于" },
  { value: "price_below", label: "价格低于" },
  { value: "price_change", label: "价格变化" },
  { value: "rsi_overbought", label: "RSI 超买" },
  { value: "rsi_oversold", label: "RSI 超卖" },
];

export function maskContactValue(value?: string | null): string | null {
  if (!value) return null;
  if (value.length <= 8) return "[REDACTED]";
  return `${value.slice(0, 4)}...[REDACTED]...${value.slice(-4)}`;
}

export default function AlertsPage() {
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [events, setEvents] = useState<AlertCheckResponse["events"]>([]);
  const [showSensitiveFields, setShowSensitiveFields] = useState(false);
  const [name, setName] = useState("价格监控");
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
  const loadRules = async () => {
    setError("");
    try { setRules((await api.alertList()).rules); } catch (exc) { setError(formatApiError(exc, "获取告警规则失败")); }
  };
  useEffect(() => { void loadRules(); }, []);

  const params = () => {
    const value = Number(threshold);
    if (alertType === "price_above" || alertType === "price_below") return { threshold: value };
    if (alertType === "price_change") return { change_pct: value };
    if (alertType === "rsi_overbought" || alertType === "rsi_oversold") return { threshold: value };
    return { threshold: value };
  };

  const createRule = async () => {
    setLoading(true); setError("");
    try {
      await api.alertCreate({ name, symbol: normalizeSymbol(symbol), market, alert_type: alertType, params: params(), enabled: true, channel, webhook_url: webhookUrl || null, email_to: emailTo || null });
      await loadRules();
    } catch (exc) { setError(formatApiError(exc, "创建告警失败")); } finally { setLoading(false); }
  };
  const deleteRule = async (id: string) => { setLoading(true); try { await api.alertDelete(id); await loadRules(); } catch (exc) { setError(formatApiError(exc, "删除告警失败")); } finally { setLoading(false); } };
  const runCheck = async (ruleId?: string) => { setLoading(true); setError(""); try { const res = await api.alertCheck(ruleId); setEvents(res.events); } catch (exc) { setError(formatApiError(exc, "检查告警失败")); } finally { setLoading(false); } };

  return <div className="page-shell space-y-6"><h1 className="page-title">告警 / 监控</h1><div className="grid grid-cols-1 gap-4 md:grid-cols-3"><Card><p className="text-sm text-muted-foreground">规则总数</p><p className="text-2xl font-bold">{rules.length}</p></Card><Card><p className="text-sm text-muted-foreground">启用中</p><p className="text-2xl font-bold text-success">{enabledRules}</p></Card><Card><p className="text-sm text-muted-foreground">本次触发</p><p className="text-2xl font-bold text-accent">{events.length}</p></Card></div><Card><CardTitle subtitle="联系方式默认脱敏展示，避免泄露 webhook 或邮箱。">新增规则</CardTitle><div className="grid grid-cols-1 gap-4 md:grid-cols-3"><div><label className="field-label">名称</label><input className="app-input mt-1" value={name} onChange={(e) => setName(e.target.value)} /></div><div><label className="field-label">代码</label><input className="app-input mt-1 font-mono" value={symbol} onChange={(e) => setSymbol(e.target.value)} /></div><div><label className="field-label">市场</label><select className="app-input mt-1" value={market} onChange={(e) => setMarket(e.target.value as Market)}>{MARKET_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></div><div><label className="field-label">类型</label><select className="app-input mt-1" value={alertType} onChange={(e) => setAlertType(e.target.value)}>{ALERT_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></div><div><label className="field-label">阈值</label><input className="app-input mt-1" value={threshold} onChange={(e) => setThreshold(e.target.value)} /></div><div><label className="field-label">渠道</label><select className="app-input mt-1" value={channel} onChange={(e) => setChannel(e.target.value)}><option value="feishu">飞书</option><option value="email">邮箱</option></select></div><div className="md:col-span-2"><label className="field-label">Webhook URL</label><input className="app-input mt-1" value={webhookUrl} onChange={(e) => setWebhookUrl(e.target.value)} placeholder="敏感字段，保存后默认脱敏" /></div><div><label className="field-label">Email</label><input className="app-input mt-1" value={emailTo} onChange={(e) => setEmailTo(e.target.value)} /></div></div><div className="mt-4 flex flex-col gap-3 md:flex-row"><Button onClick={createRule} loading={loading}>创建规则</Button><Button variant="secondary" onClick={() => runCheck()} loading={loading}>立即检查全部</Button><Button variant="ghost" onClick={() => setShowSensitiveFields((value) => !value)}>{showSensitiveFields ? "隐藏敏感字段" : "显示敏感字段"}</Button></div>{error && <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{error}</div>}</Card><Card><CardTitle>规则列表</CardTitle><div className="table-scroll"><table className="min-w-[64rem] w-full text-sm"><thead><tr className="border-b border-gray-700 text-gray-400"><th className="py-2 text-left">名称</th><th className="py-2 text-left">代码</th><th className="py-2 text-left">类型</th><th className="py-2 text-left">联系</th><th className="py-2 text-right">操作</th></tr></thead><tbody>{rules.map((rule) => <tr key={rule.id} className="border-b border-gray-800"><td className="py-2">{rule.name}</td><td className="py-2 font-mono">{rule.symbol}</td><td className="py-2">{rule.alert_type}</td><td className="py-2 font-mono text-xs">{showSensitiveFields ? (rule.webhook_url || rule.email_to || "-") : (maskContactValue(rule.webhook_url) || maskContactValue(rule.email_to) || "-")}</td><td className="py-2 text-right"><div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => runCheck(rule.id)} disabled={loading}>检查</Button><Button variant="danger" onClick={() => deleteRule(rule.id)} disabled={loading}>删除</Button></div></td></tr>)}</tbody></table></div></Card>{events.length > 0 && <Card><CardTitle>触发事件</CardTitle><div className="space-y-2">{events.map((event) => <div key={`${event.rule_id}-${event.timestamp}`} className="rounded-lg border border-border p-3 text-sm"><span className="font-bold">{event.rule_name}</span> · {event.symbol} · {event.message}</div>)}</div></Card>}</div>;
}
