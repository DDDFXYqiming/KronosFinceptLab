import { ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { ScrollManager } from "./ScrollManager";

export function Shell({ children }: { children: ReactNode }) {
  return (
    <>
      <Sidebar />
      <div className="min-w-0 transition-all duration-300 md:ml-72">
        <Header />
        <div className="h-[calc(4rem+env(safe-area-inset-top))]" aria-hidden="true" />
        <main className="min-h-[calc(100dvh-4rem)] min-w-0 overflow-x-hidden px-4 py-5 md:p-6">
          <div className="mx-auto w-full max-w-none min-w-0">{children}</div>
        </main>
      </div>
      <ScrollManager />
    </>
  );
}
