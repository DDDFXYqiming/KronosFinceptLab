"use client";

import Link from "next/link";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { useAppStore } from "@/stores/app";
import { DEFAULT_MARKET, MARKET_OPTIONS, getMarketLabel, type Market } from "@/lib/markets";
import { DEFAULT_SYMBOL, normalizeSymbol } from "@/lib/symbols";
import { useSessionState } from "@/lib/useSessionState";

export default function WatchlistPage() {
  const { watchlist, addToWatchlist, removeFromWatchlist } = useAppStore();
  const [symbol, setSymbol] = useSessionState("kronos-watchlist-symbol", "");
  const [market, setMarket] = useSessionState<Market>("kronos-watchlist-market", DEFAULT_MARKET);

  const handleAdd = () => {
    const requestSymbol = normalizeSymbol(symbol);
    if (!requestSymbol) return;
    addToWatchlist({
      symbol: requestSymbol,
      market,
      addedAt: new Date().toISOString(),
    });
    setSymbol("");
  };

  return (
    <div className="page-shell space-y-6">
      <h1 className="page-title">自选股</h1>

      {/* Add Stock Form */}
      <Card>
        <CardTitle>添加股票</CardTitle>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <div>
            <label className="field-label">代码</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleAdd()}
              className="app-input mt-1 font-mono"
              placeholder={`例如 ${DEFAULT_SYMBOL}`}
            />
          </div>
          <div>
            <label className="field-label">市场</label>
            <select
              value={market}
              onChange={(e) => setMarket(e.target.value as Market)}
              className="app-input mt-1"
            >
              {MARKET_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <Button onClick={handleAdd} className="w-full">
              添加
            </Button>
          </div>
        </div>
      </Card>

      {/* Empty State */}
      {watchlist.length === 0 && (
        <Card>
          <div className="text-center py-12 text-gray-500">
            <p className="text-lg mb-2">自选股列表为空</p>
            <p className="text-sm">添加股票开始追踪</p>
          </div>
        </Card>
      )}

      {/* Watchlist Items */}
      {watchlist.length > 0 && (
        <Card>
          <CardTitle>已保存股票 ({watchlist.length})</CardTitle>
          <div className="space-y-3 md:hidden">
            {watchlist.map((item) => (
              <div key={item.symbol} className="rounded-lg border border-border bg-muted p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-mono text-lg font-bold text-foreground">{item.symbol}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{getMarketLabel(item.market)}</p>
                  </div>
                  <button
                    onClick={() => removeFromWatchlist(item.symbol)}
                    className="min-h-11 rounded-lg border border-red-200 bg-red-50 px-3 text-xs font-medium text-red-700"
                  >
                    移除
                  </button>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <Link
                    href={`/analysis?symbol=${item.symbol}&market=${item.market}`}
                    className="flex min-h-11 items-center justify-center rounded-lg border border-accent/20 bg-accent/10 text-sm font-medium text-accent"
                  >
                    分析
                  </Link>
                  <Link
                    href={`/forecast?symbol=${item.symbol}&market=${item.market}`}
                    className="flex min-h-11 items-center justify-center rounded-lg border border-border bg-card text-sm font-medium text-foreground"
                  >
                    预测
                  </Link>
                </div>
              </div>
            ))}
          </div>
          <div className="table-scroll hidden md:block">
            <table className="min-w-[42rem] w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 text-gray-400">
                  <th className="py-2 text-left">代码</th>
                  <th className="py-2 text-left">市场</th>
                  <th className="py-2 text-left">添加时间</th>
                  <th className="py-2 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {watchlist.map((item) => (
                  <tr
                    key={item.symbol}
                    className="border-b border-gray-800 hover:bg-surface-overlay/50"
                  >
                    <td className="py-3 font-mono font-bold text-white">
                      {item.symbol}
                    </td>
                    <td className="py-3">
                      <span className="px-2 py-0.5 text-xs rounded bg-gray-700 text-gray-300">
                        {getMarketLabel(item.market)}
                      </span>
                    </td>
                    <td className="py-3 text-gray-400 text-xs">
                      {item.addedAt
                        ? new Date(item.addedAt).toLocaleDateString("en-US", {
                            year: "numeric",
                            month: "short",
                            day: "numeric",
                          })
                        : "--"}
                    </td>
                    <td className="py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Link
                          href={`/analysis?symbol=${item.symbol}&market=${item.market}`}
                          className="px-2 py-1 text-xs rounded bg-primary/20 text-primary-light hover:bg-primary/30 transition-colors"
                        >
                          分析
                        </Link>
                        <Link
                          href={`/forecast?symbol=${item.symbol}&market=${item.market}`}
                          className="px-2 py-1 text-xs rounded bg-surface-overlay text-gray-300 hover:bg-gray-700 transition-colors"
                        >
                          预测
                        </Link>
                        <button
                          onClick={() => removeFromWatchlist(item.symbol)}
                          className="px-2 py-1 text-xs rounded bg-red-900/30 text-red-400 hover:bg-red-900/50 transition-colors"
                        >
                          移除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
