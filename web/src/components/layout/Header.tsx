"use client";

import { useAppStore } from "@/stores/app";
import { useEffect, useState } from "react";
import { api, HealthResponse } from "@/lib/api";

export function Header() {
  const { sidebarOpen, toggleSidebar } = useAppStore();
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => {});
    const interval = setInterval(() => {
      api.health().then(setHealth).catch(() => {});
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="sticky top-0 z-30 h-16 bg-surface-raised/80 backdrop-blur-md border-b border-gray-800 flex items-center px-6">
      <button
        onClick={toggleSidebar}
        className="mr-4 p-2 rounded-lg hover:bg-surface-overlay text-gray-400"
      >
        ☰
      </button>

      <div className="flex-1" />

      {/* Status indicators */}
      <div className="flex items-center gap-4 text-sm">
        {health && (
          <>
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${health.status === "ok" ? "bg-accent-green" : "bg-accent-red"}`} />
              <span className="text-gray-400">{health.model_id.split("/").pop()}</span>
            </div>
            <span className="text-gray-600">|</span>
            <span className="text-gray-400 font-mono">{health.device}</span>
          </>
        )}
      </div>
    </header>
  );
}
