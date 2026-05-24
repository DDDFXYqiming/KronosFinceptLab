"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, getConfiguredApiKey } from "@/lib/api";

interface ApiKeyNoticeProps {
  compact?: boolean;
}

export function ApiKeyNotice({ compact = false }: ApiKeyNoticeProps) {
  const [hasAccess, setHasAccess] = useState(true);

  useEffect(() => {
    let active = true;
    if (getConfiguredApiKey()) {
      setHasAccess(true);
      return () => { active = false; };
    }
    api.health()
      .then((health) => {
        if (active) setHasAccess(Boolean(health.site_api_configured));
      })
      .catch(() => {
        if (active) setHasAccess(false);
      });
    return () => { active = false; };
  }, []);

  if (hasAccess) return null;

  return (
    <div className={`rounded-xl border border-amber-200 bg-amber-50 text-amber-900 ${compact ? "p-3" : "p-4"}`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold">当前站点未开放默认 API 调用。</p>
          <p className="mt-1 text-xs text-amber-800">如需使用预测、AI 分析、回测或告警，请在设置页保存自己的 Kronos API Key；演示模式不会调用模型或 LLM。</p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Link href="/settings" className="rounded-lg bg-amber-700 px-3 py-2 text-xs font-semibold text-white">
            前往设置
          </Link>
          <Link href="/forecast?demo=1" className="rounded-lg border border-amber-300 px-3 py-2 text-xs font-semibold">
            查看演示
          </Link>
        </div>
      </div>
    </div>
  );
}
