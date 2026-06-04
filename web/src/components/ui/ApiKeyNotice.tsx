"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, getConfiguredApiKey } from "@/lib/api";
import { t } from "@/lib/i18n";
import { useAppStore } from "@/stores/app";

interface ApiKeyNoticeProps {
  compact?: boolean;
}

export function ApiKeyNotice({ compact = false }: ApiKeyNoticeProps) {
  const language = useAppStore((state) => state.preferences.language);
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
        // A failed health probe means API reachability is unknown/offline, not
        // that the site owner intentionally closed default API access. Keep
        // this banner hidden on transient proxy/backend failures so the
        // dashboard does not show a misleading "未开放默认 API 调用" warning.
        if (active) setHasAccess(true);
      });
    return () => { active = false; };
  }, []);

  if (hasAccess) return null;

  return (
    <div className={`rounded-xl border border-amber-200 bg-amber-50 text-amber-900 ${compact ? "p-3" : "p-4"}`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold">{t(language, "apiNotice.title")}</p>
          <p className="mt-1 text-xs text-amber-800">{t(language, "apiNotice.body")}</p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Link href="/settings" className="rounded-lg bg-amber-700 px-3 py-2 text-xs font-semibold text-white">
            {t(language, "apiNotice.settings")}
          </Link>
          <Link href="/forecast?demo=1" className="rounded-lg border border-amber-300 px-3 py-2 text-xs font-semibold">
            {t(language, "apiNotice.demo")}
          </Link>
        </div>
      </div>
    </div>
  );
}
