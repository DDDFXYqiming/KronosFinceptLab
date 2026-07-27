"use client";

import { Card } from "antd";
import { ReactNode } from "react";

interface AntCardProps {
  children: ReactNode;
  title?: ReactNode;
  className?: string;
  extra?: ReactNode;
}

export function AntCard({ children, title, className = "", extra }: AntCardProps) {
  return (
    <Card
      title={title}
      extra={extra}
      className={className}
      style={{ borderRadius: 12, marginBottom: 16 }}
    >
      {children}
    </Card>
  );
}
