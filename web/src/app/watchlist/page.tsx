"use client";

import { useState } from "react";
import Link from "next/link";
import { Card, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { useAppStore } from "@/stores/app";

type Market = "cn" | "us" | "hk" | "commodity";

const MARKET_OPTIONS: { value: Market; label: string }[] = [
  { value: "cn", label: "A股" },
  { value: "us", label: "美股" },
  { value: "hk", label: "港股" },
  { value: "commodity", label: "大宗商品" },
];

export default function WatchlistPage() {
  const { watchlist, addToWatchlist, removeFromWatchlist } = useAppStore();
  const [symbol, setSymbol] = useState("");
  const [market, setMarket] = useState<Market>("cn");

  const handleAdd = () => {
    const trimmed = symbol.trim().toUpperCase();
    if (!trimmed) return;
    addToWatchlist({
      symbol: trimmed,
      market,
      addedAt: new Date().toISOString(),
    });
    setSymbol("");
  };

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-display">自选股</h1>

      {/* Add Stock Form */}
      <Card>
        <CardTitle>添加股票</CardTitle>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="text-sm text-gray-400">代码</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleAdd()}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white font-mono"
              placeholder="例如 600519"
            />
          </div>
          <div>
            <label className="text-sm text-gray-400">市场</label>
            <select
              value={market}
              onChange={(e) => setMarket(e.target.value as Market)}
              className="w-full mt-1 px-3 py-2 bg-surface-overlay border border-gray-700 rounded-lg text-white"
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
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
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
                        {item.market}
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
