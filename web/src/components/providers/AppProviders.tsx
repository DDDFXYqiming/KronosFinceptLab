"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import { ReactNode, useState } from "react";

export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5 * 60 * 1000,
            gcTime: 30 * 60 * 1000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
          mutations: {
            retry: 0,
          },
        },
      })
  );

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: "#0052FF",
          borderRadius: 12,
          fontFamily: "Inter, system-ui, sans-serif",
        },
        components: {
          Button: {
            controlHeight: 44,
            borderRadiusLG: 12,
          },
          Select: {
            controlHeight: 44,
            borderRadiusLG: 12,
          },
          Input: {
            controlHeight: 44,
            borderRadiusLG: 12,
          },
          InputNumber: {
            controlHeight: 44,
            borderRadiusLG: 12,
          },
          DatePicker: {
            controlHeight: 44,
            borderRadiusLG: 12,
          },
          Card: {
            borderRadiusLG: 12,
          },
          Table: {
            borderRadiusLG: 12,
          },
        },
      }}
    >
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ConfigProvider>
  );
}
