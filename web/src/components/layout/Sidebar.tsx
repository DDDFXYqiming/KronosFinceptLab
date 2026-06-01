"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Bell,
  ChevronLeft,
  ChevronRight,
  Database,
  GitCompareArrows,
  Globe2,
  History,
  LayoutDashboard,
  LineChart,
  Settings,
  Star,
  type LucideIcon,
} from "lucide-react";
import { t } from "@/lib/i18n";
import { useAppStore } from "@/stores/app";

export const navItems = [
  { href: "/", labelKey: "nav.dashboard", icon: LayoutDashboard },
  { href: "/forecast", labelKey: "nav.forecast", icon: LineChart },
  { href: "/analysis", labelKey: "nav.analysis", icon: BarChart3 },
  { href: "/macro", labelKey: "nav.macro", icon: Globe2 },
  { href: "/watchlist", labelKey: "nav.watchlist", icon: Star },
  { href: "/batch", labelKey: "nav.batch", icon: GitCompareArrows },
  { href: "/backtest", labelKey: "nav.backtest", icon: History },
  { href: "/data", labelKey: "nav.data", icon: Database },
  { href: "/settings", labelKey: "nav.settings", icon: Settings },
  { href: "/alerts", labelKey: "nav.alerts", icon: Bell },
] satisfies ReadonlyArray<{ href: string; labelKey: string; icon: LucideIcon }>;

export function Sidebar() {
  const pathname = usePathname();
  const { sidebarOpen, toggleSidebar, preferences } = useAppStore();

  return (
    <aside
      className={`fixed left-0 top-0 z-40 hidden h-screen border-r border-border bg-card/95 shadow-sm backdrop-blur-md transition-[width] duration-300 ease-out md:block ${
        sidebarOpen ? "w-72" : "w-20"
      }`}
    >
      <div className={`flex h-16 items-center border-b border-border px-3 ${sidebarOpen ? "justify-between" : "justify-center"}`}>
        <Link href="/" className={`flex min-w-0 items-center ${sidebarOpen ? "gap-3" : "justify-center"}`} aria-label="KronosFinceptLab">
          <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-accent/10 bg-accent/5 font-display text-xl font-bold gradient-text">
            K
          </span>
          {sidebarOpen && (
            <span className="truncate font-display text-lg gradient-text">
              KronosFinceptLab
            </span>
          )}
        </Link>
        <button
          type="button"
          onClick={toggleSidebar}
          className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-border bg-background text-muted-foreground shadow-sm transition-colors hover:border-accent/30 hover:bg-accent/5 hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 ${
            sidebarOpen ? "" : "absolute left-1/2 top-[4.25rem] -translate-x-1/2"
          }`}
          aria-label={t(preferences.language, "common.toggleSidebar")}
          aria-expanded={sidebarOpen}
          title={t(preferences.language, "common.toggleSidebar")}
        >
          {sidebarOpen ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>
      </div>

      <nav className={`${sidebarOpen ? "mt-4 px-2" : "mt-14 px-3"} space-y-1.5`}>
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          const label = t(preferences.language, item.labelKey);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              title={sidebarOpen ? undefined : label}
              className={`group relative flex min-h-11 items-center rounded-xl border transition-all duration-200 ${
                sidebarOpen ? "gap-3 px-3 py-2.5" : "justify-center px-0 py-2.5"
              } ${
                isActive
                  ? "border-accent/20 bg-accent/10 text-accent shadow-sm"
                  : "border-transparent text-muted-foreground hover:border-border hover:bg-muted hover:text-foreground"
              }`}
            >
              <Icon className={`h-[1.125rem] w-[1.125rem] shrink-0 ${isActive ? "stroke-[2.2]" : "stroke-[1.8]"}`} />
              {sidebarOpen && <span className="truncate text-sm font-medium">{label}</span>}
              {!sidebarOpen && (
                <span className="pointer-events-none absolute left-[calc(100%+0.5rem)] top-1/2 z-50 -translate-y-1/2 whitespace-nowrap rounded-lg border border-border bg-card px-2.5 py-1.5 text-xs font-medium text-foreground opacity-0 shadow-lg transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
                  {label}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

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
