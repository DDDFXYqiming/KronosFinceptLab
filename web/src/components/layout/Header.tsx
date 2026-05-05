"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAppStore } from "@/stores/app";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/queryKeys";
import { navItems } from "@/components/layout/Sidebar";

const VERSION = "v10.8.4";

function compactModelName(modelId?: string): string {
  return modelId?.split("/").pop() || "Kronos";
}

export function Header() {
  const pathname = usePathname();
  const { toggleSidebar } = useAppStore();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { data: health } = useQuery({
    queryKey: queryKeys.health(),
    queryFn: ({ signal }) => api.health({ signal }),
    refetchInterval: 30000,
  });

  useEffect(() => {
    setMobileMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!mobileMenuOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [mobileMenuOpen]);

  const modelName = compactModelName(health?.model_id);
  const isHealthy = health?.status === "ok";

  return (
    <>
      <header className="mobile-safe-top sticky top-0 z-30 border-b border-border bg-card/90 backdrop-blur-md">
        <div className="flex h-16 min-w-0 items-center gap-3 px-4 md:px-6">
          <button
            onClick={() => setMobileMenuOpen(true)}
            className="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted md:hidden"
            aria-label="打开导航菜单"
            aria-expanded={mobileMenuOpen}
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
            </svg>
          </button>

          <Link href="/" className="flex min-w-0 items-center gap-2 md:hidden">
            <span className="text-xl font-bold gradient-text">K</span>
            <span className="truncate font-display text-lg gradient-text">KronosFinceptLab</span>
          </Link>

          <button
            onClick={toggleSidebar}
            className="hidden min-h-11 min-w-11 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted md:flex"
            aria-label="切换侧边栏"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
            </svg>
          </button>

          <div className="min-w-0 flex-1" />

          <div className="flex min-w-0 items-center gap-2 text-sm">
            <div className="hidden items-center gap-2 sm:flex">
              <div className={`h-2 w-2 rounded-full animate-pulse-dot ${isHealthy ? "bg-success" : "bg-error"}`} />
              <span className="max-w-[9rem] truncate text-muted-foreground">{modelName}</span>
            </div>
            <span className="hidden text-border sm:inline">|</span>
            <span className="hidden max-w-[4rem] truncate font-mono text-muted-foreground sm:inline">
              {health?.device || "cpu"}
            </span>
            <span className={`inline-flex min-h-8 max-w-[8.5rem] items-center gap-1 rounded-full border px-2.5 text-xs md:hidden ${
              isHealthy
                ? "border-green-200 bg-green-50 text-green-700"
                : "border-red-200 bg-red-50 text-red-700"
            }`}>
              <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${isHealthy ? "bg-success" : "bg-error"}`} />
              <span className="truncate">{modelName}</span>
            </span>
          </div>
        </div>
      </header>

      {mobileMenuOpen && (
        <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true">
          <button
            className="absolute inset-0 bg-foreground/30"
            onClick={() => setMobileMenuOpen(false)}
            aria-label="关闭导航遮罩"
          />
          <aside className="mobile-safe-bottom absolute left-0 top-0 flex h-full w-[min(82vw,18rem)] flex-col border-r border-border bg-card shadow-2xl">
            <div className="mobile-safe-top border-b border-border px-4">
              <div className="flex h-16 items-center gap-3">
                <button
                  onClick={() => setMobileMenuOpen(false)}
                  className="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted"
                  aria-label="关闭导航菜单"
                >
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                  </svg>
                </button>
                <div className="min-w-0">
                  <div className="font-display text-lg gradient-text">KronosFinceptLab</div>
                  <div className="mt-0.5 text-xs font-mono text-muted-foreground">{VERSION} — 仅供研究</div>
                </div>
              </div>
            </div>

            <nav className="flex-1 space-y-1 overflow-y-auto p-3">
              {navItems.map((item) => {
                const isActive = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex min-h-11 items-center rounded-lg border px-3 text-sm font-medium transition-colors ${
                      isActive
                        ? "border-accent/20 bg-accent/10 text-accent"
                        : "border-transparent text-muted-foreground hover:bg-muted hover:text-foreground"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </aside>
        </div>
      )}
    </>
  );
}
