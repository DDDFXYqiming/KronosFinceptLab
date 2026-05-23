"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getConfiguredApiKey } from "@/lib/api";

interface ApiKeyNoticeProps {
  compact?: boolean;
}

export function ApiKeyNotice({ compact = false }: ApiKeyNoticeProps) {
  const [hasKey, setHasKey] = useState(true);

  useEffect(() => {
    setHasKey(Boolean(getConfiguredApiKey()));
  }, []);

  if (hasKey) return null;

  return (
    <div className={`rounded-xl border border-amber-200 bg-amber-50 text-amber-900 ${compact ? "p-3" : "p-4"}`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold">预测、AI 分析、回测和告警需要 API Key。</p>
          <p className="mt-1 text-xs text-amber-800">未配置时只展示公开页面和固定演示样例，不会调用模型或 LLM。</p>
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
