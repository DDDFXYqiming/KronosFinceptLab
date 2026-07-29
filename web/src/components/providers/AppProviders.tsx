"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Alert, Button, Card, ConfigProvider, Modal, Select, Spin, Tag, theme,
} from "antd";
import { StyleProvider, createCache } from "@ant-design/cssinjs";
import zhCN from "antd/locale/zh_CN";
import { ReactNode, useEffect, useMemo, useState } from "react";

const preWarmStyle: React.CSSProperties = {
  display: "none",
  position: "fixed",
  pointerEvents: "none",
  opacity: 0,
  zIndex: -1,
};

function CSSCachePreWarm() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);
  if (!mounted) return null;
  return (
    <div style={preWarmStyle} aria-hidden="true">
      <Button />
      <Button type="primary" />
      <Select />
      <Tag />
      <Alert title="" type="info" />
      <Card />
      <Spin />
      <Modal open={false} />
    </div>
  );
}

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
  const cache = useMemo(() => createCache(), []);

  return (
    <StyleProvider cache={cache}>
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
      <CSSCachePreWarm />
    </ConfigProvider>
    </StyleProvider>
  );
}
