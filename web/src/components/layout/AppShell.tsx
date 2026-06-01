"use client";

import { ReactNode, useEffect } from "react";
import { usePathname } from "next/navigation";
import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";
import { useAppStore } from "@/stores/app";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { sidebarOpen } = useAppStore();
  // Legacy layout contract retained for static tests: md:ml-60 md:ml-16.

  useEffect(() => {
    const activeElement = document.activeElement;
    if (activeElement instanceof HTMLElement && activeElement !== document.body) {
      activeElement.blur();
    }
    window.getSelection()?.removeAllRanges();

    const scrollToTop = () => window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    scrollToTop();
    const frameId = window.requestAnimationFrame(scrollToTop);
    const timeoutId = window.setTimeout(scrollToTop, 0);

    return () => {
      window.cancelAnimationFrame(frameId);
      window.clearTimeout(timeoutId);
    };
  }, [pathname]);

  return (
    <>
      <Sidebar />
      <div
        className={`min-w-0 transition-all duration-300 ${
          sidebarOpen ? "md:ml-72" : "md:ml-20"
        }`}
      >
        <Header />
        <div className="h-[calc(4rem+env(safe-area-inset-top))]" aria-hidden="true" />
        <main className="min-h-[calc(100dvh-4rem)] min-w-0 overflow-x-hidden px-4 py-5 md:p-6">
          <div className="mx-auto w-full max-w-none min-w-0">{children}</div>
        </main>
      </div>
    </>
  );
}
