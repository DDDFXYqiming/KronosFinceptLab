"use client";

import { Tag } from "antd";
import { ReactNode } from "react";

interface AntTagProps {
  children: ReactNode;
  color?: string;
  className?: string;
}

export function AntTag({ children, color, className = "" }: AntTagProps) {
  return (
    <Tag color={color} className={className}>
      {children}
    </Tag>
  );
}
