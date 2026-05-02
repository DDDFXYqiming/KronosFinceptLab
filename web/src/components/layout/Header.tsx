"use client";

import { useAppStore } from "@/stores/app";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/queryKeys";


export function Header() {
  const { sidebarOpen, toggleSidebar } = useAppStore();
  const { data: health } = useQuery({
    queryKey: queryKeys.health(),
    queryFn: ({ signal }) => api.health({ signal }),
    refetchInterval: 30000,
  });

  return (
    <header className="sticky top-0 z-30 h-16 bg-card/80 backdrop-blur-md border-b border-border flex items-center px-6">
      <button
        onClick={toggleSidebar}
        className="mr-4 p-2 rounded-lg hover:bg-muted text-muted-foreground"
      >
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
        </svg>
      </button>

      <div className="flex-1" />

      {/* Status indicators */}
      <div className="flex items-center gap-4 text-sm">
        {health && (
          <>
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full animate-pulse-dot ${health.status === "ok" ? "bg-success" : "bg-error"}`} />
              <span className="text-muted-foreground">{health.model_id.split("/").pop()}</span>
            </div>
            <span className="text-border">|</span>
            <span className="text-muted-foreground font-mono">{health.device}</span>
          </>
        )}

      </div>
    </header>
  );
}
