"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAppStore } from "@/stores/app";

const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/forecast", label: "Forecast" },
  { href: "/analysis", label: "Analysis" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/batch", label: "Batch" },
  { href: "/backtest", label: "Backtest" },
  { href: "/data", label: "Data" },
  { href: "/settings", label: "Settings" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { sidebarOpen } = useAppStore();

  return (
    <aside
      className={`fixed top-0 left-0 z-40 h-screen transition-all duration-300 ${
        sidebarOpen ? "w-60" : "w-16"
      } bg-surface-raised border-r border-gray-800`}
    >
      {/* Logo */}
      <div className="flex items-center h-16 px-4 border-b border-gray-800">
        <span className="text-xl font-bold text-primary-light">K</span>
        {sidebarOpen && (
          <span className="ml-3 font-display text-lg bg-gradient-primary bg-clip-text text-transparent">
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
              className={`flex items-center px-3 py-2.5 rounded-lg transition-colors ${
                isActive
                  ? "bg-primary/20 text-primary-light"
                  : "text-gray-400 hover:bg-surface-overlay hover:text-gray-200"
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
          <div className="text-xs text-gray-500 text-center">
            v8.0 -- Research Only
          </div>
        </div>
      )}
    </aside>
  );
}
