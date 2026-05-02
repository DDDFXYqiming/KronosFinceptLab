"use client";

import { ReactNode } from "react";
import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";
import { useAppStore } from "@/stores/app";

export function AppShell({ children }: { children: ReactNode }) {
  const { sidebarOpen } = useAppStore();

  return (
    <>
      <Sidebar />
      <div
        className={`min-w-0 transition-all duration-300 ${
          sidebarOpen ? "md:ml-60" : "md:ml-16"
        }`}
      >
        <Header />
        <main className="min-h-[calc(100dvh-4rem)] min-w-0 overflow-x-hidden px-4 py-5 md:p-6">
          <div className="mx-auto w-full max-w-none min-w-0">{children}</div>
        </main>
      </div>
    </>
  );
}
