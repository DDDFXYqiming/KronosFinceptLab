import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";

export const metadata: Metadata = {
  title: "KronosFinceptLab",
  description: "Financial quantitative analysis platform powered by Kronos",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="dark">
      <body className="bg-surface text-gray-100">
        <Sidebar />
        <div className="ml-60 transition-all duration-300">
          <Header />
          <main className="p-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
