"use client";

import { Layout } from "antd";
import { ReactNode } from "react";

const { Header, Sider, Content } = Layout;

interface AntLayoutProps {
  children: ReactNode;
  className?: string;
}

function AntLayoutRoot({ children, className = "" }: AntLayoutProps) {
  return <Layout className={className}>{children}</Layout>;
}

function AntLayoutSider({ children, className = "", width = 240 }: AntLayoutProps & { width?: number }) {
  return <Sider width={width} className={className} theme="dark">{children}</Sider>;
}

function AntLayoutHeader({ children, className = "" }: AntLayoutProps) {
  return <Header className={className}>{children}</Header>;
}

function AntLayoutContent({ children, className = "" }: AntLayoutProps) {
  return <Content className={className}>{children}</Content>;
}

export const AntLayout = { Root: AntLayoutRoot, Sider: AntLayoutSider, Header: AntLayoutHeader, Content: AntLayoutContent };
