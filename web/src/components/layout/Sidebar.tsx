"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { t } from "@/lib/i18n";
import { useAppStore } from "@/stores/app";

export const navItems = [
  { href: "/", labelKey: "nav.dashboard" },
  { href: "/forecast", labelKey: "nav.forecast" },
  { href: "/analysis", labelKey: "nav.analysis" },
  { href: "/macro", labelKey: "nav.macro" },
  { href: "/news", labelKey: "nav.news" },
  { href: "/watchlist", labelKey: "nav.watchlist" },
  { href: "/batch", labelKey: "nav.batch" },
  { href: "/backtest", labelKey: "nav.backtest" },
  { href: "/data", labelKey: "nav.data" },
  { href: "/settings", labelKey: "nav.settings" },
  { href: "/alerts", labelKey: "nav.alerts" },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const { sidebarOpen, preferences } = useAppStore();

  return (
    <aside
      className={`fixed left-0 top-0 z-40 hidden h-screen transition-all duration-300 md:block ${
        sidebarOpen ? "w-60" : "w-16"
      } bg-card border-r border-border`}
    >
      {/* Logo */}
      <div className="flex items-center h-16 px-4 border-b border-border">
        <span className="text-xl font-bold gradient-text">K</span>
        {sidebarOpen && (
          <span className="ml-3 font-display text-lg gradient-text">
            KronosFinceptLab
          </span>
        )}
      </div>

      {/* Nav */}
      <nav className="mt-4 px-2 space-y-1">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          const label = t(preferences.language, item.labelKey);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex min-h-11 items-center px-3 py-2.5 rounded-xl transition-all duration-200 ${
                isActive
                  ? "bg-accent/10 text-accent border border-accent/20"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground border border-transparent"
              }`}
            >
              <span className="text-sm font-medium">
                {sidebarOpen ? label : label.charAt(0)}
              </span>
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      {sidebarOpen && (
        <div className="absolute bottom-4 left-0 right-0 px-4">
          <div className="text-xs text-muted-foreground text-center font-mono">
            v10.8.8 - {t(preferences.language, "common.researchOnly")}
          </div>
        </div>
      )}
    </aside>
  );
}
