"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAppStore } from "@/stores/app";

const navItems = [
  { href: "/", label: "仪表盘" },
  { href: "/forecast", label: "预测" },
  { href: "/analysis", label: "分析" },
  { href: "/watchlist", label: "自选股" },
  { href: "/batch", label: "批量对比" },
  { href: "/backtest", label: "回测" },
  { href: "/data", label: "数据" },
  { href: "/settings", label: "设置" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { sidebarOpen } = useAppStore();

  return (
    <aside
      className={`fixed top-0 left-0 z-40 h-screen transition-all duration-300 ${
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
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center px-3 py-2.5 rounded-xl transition-all duration-200 ${
                isActive
                  ? "bg-accent/10 text-accent border border-accent/20"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground border border-transparent"
              }`}
            >
              <span className="text-sm font-medium">
                {sidebarOpen ? item.label : item.label.charAt(0)}
              </span>
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      {sidebarOpen && (
        <div className="absolute bottom-4 left-0 right-0 px-4">
          <div className="text-xs text-muted-foreground text-center font-mono">
            v8.0 — 仅供研究
          </div>
        </div>
      )}
    </aside>
  );
}
